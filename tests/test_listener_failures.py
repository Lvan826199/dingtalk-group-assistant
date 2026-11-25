"""复现到时停机的多行 JSON、订阅冷却以及失败重试风暴。"""
import json

import pytest


def test_pretty_error_is_one_complete_record(make_agent):
    a, _, _ = make_agent()
    failure = {"error": {"reason": "personal_subscription_cooldown", "retryable": True,
                         "retry_after_seconds": 120, "message": "稍后重试"}}
    records = list(a.listen_records(iter(json.dumps(failure, indent=2).splitlines(True))))
    assert records == [("record", failure)]


def test_diagnostics_do_not_corrupt_multiline_error(make_agent):
    a, _, _ = make_agent()
    rows = list(a.listen_records(iter(['{\n', '[event] bus connected\n', '"error": "cancelled"\n', '}\n'])))
    assert rows == [("diagnostic", "[event] bus connected"), ("record", {"error": "cancelled"})]


def test_bad_json_keeps_the_next_real_message(make_agent):
    a, _, _ = make_agent()
    event = {"message_id": "msgRECOVER", "sender": "同事", "content": "请核查"}
    rows = list(a.listen_records(iter(['{bad\n', json.dumps(event) + '\n'])))
    assert rows[0][0] == "invalid" and rows[1] == ("record", event)


@pytest.mark.parametrize("retryable,budget", [(False, 0), (True, 2), (None, 1)])
def test_retry_budget_and_server_deadline(make_agent, monkeypatch, retryable, budget):
    a, _, _ = make_agent()
    monkeypatch.setattr(a.time, "time", lambda: 1000)
    delay, actual = a.listen_retry_policy({"retryable": retryable, "retry_after_seconds": 200,
                                         "next_retry_at": "1970-01-01T00:30:00+00:00"})
    assert delay == 800 and actual == budget


def configure_process(a, monkeypatch, output, stop_on_wait=False):
    calls = []
    class Process:
        returncode = 1
        def __init__(self):
            self.stdout = iter(output)
        def wait(self):
            if stop_on_wait:
                a.UPDATE_EXIT.set()
    a.in_window = lambda: True
    a.minutes_left = lambda: 20
    a.popen = lambda args, **kw: calls.append(args) or Process()
    monkeypatch.setattr(a.time, "sleep", lambda *args: None)
    return calls


def test_structured_cooldown_is_not_parse_failure_and_has_bounded_retries(make_agent, monkeypatch):
    a, notes, _ = make_agent()
    error = {"error": {"reason": "personal_subscription_cooldown", "retryable": True,
                       "retry_after_seconds": 180}}
    calls = configure_process(a, monkeypatch, json.dumps(error, indent=2).splitlines(True))
    waits = []
    a.listener_wait = lambda seconds, *args: waits.append(seconds)
    a.listen([], "测试群")
    assert len(calls) == 3 and waits == [180, 180]
    assert all(command[-2:] == ["--format", "ndjson"] for command in calls)
    assert a.LISTENERS["测试群"]["retry_blocked"] is True
    assert not a.LISTENERS["测试群"]["alive"]
    assert not any("解析" in title for title, _ in notes)
    assert "personal_subscription_cooldown" in str(notes)


def test_nonretryable_failure_does_not_recreate_subscription(make_agent, monkeypatch):
    a, _, _ = make_agent()
    calls = configure_process(a, monkeypatch, [json.dumps({"error": {"retryable": False, "reason": "denied"}})])
    a.listener_wait = lambda *args: pytest.fail("不可重试不能等待后重建")
    a.listen([], "测试群")
    assert len(calls) == 1 and a.LISTENERS["测试群"]["retry_blocked"]


def test_expected_stop_does_not_report_partial_cleanup_json(make_agent, monkeypatch):
    a, notes, _ = make_agent()
    calls = configure_process(a, monkeypatch, [], stop_on_wait=True)
    class Output:
        def __iter__(self):
            a.UPDATE_EXIT.set()
            yield '{\n'
    a.popen = lambda *args, **kw: type("Process", (), {"stdout": Output(), "wait": lambda self: None})()
    a.listen([], "测试群")
    assert not any("失败" in title or "异常" in title for title, _ in notes)


def test_error_is_not_counted_as_ready_and_real_event_is_queued(make_agent, monkeypatch):
    a, notes, _ = make_agent({"groups": {"cidG": "测试群"}, "my_name": "本人"})
    event = {"message_id": "msgREAL", "conversation_id": "cidG", "sender": "同事", "content": "@本人 请核查"}
    configure_process(a, monkeypatch, ['[event] ready event_key=x\n', json.dumps(event) + '\n'], stop_on_wait=True)
    a.listen([], "测试群")
    assert a.Q.get_nowait()["message_id"] == "msgREAL"
    assert not any("失败" in title for title, _ in notes)


def test_supervisor_respects_exhausted_retry_budget(make_agent, monkeypatch):
    a, _, _ = make_agent()
    a.in_window = lambda: True
    a.LISTENERS["提醒群"] = {"alive": False, "retry_blocked": True}
    monkeypatch.setattr(a.threading, "Thread", lambda **kw: pytest.fail("不能绕过预算启动线程"))
    a.sync_listeners()


def test_exhausted_budget_retries_after_pause(make_agent, monkeypatch):
    a, _, _ = make_agent()
    a.LISTENERS["提醒群"] = {"alive": False, "retry_blocked": True, "blocked_until": a.time.time() + 600}
    assert a.listener_blocked(a.LISTENERS["提醒群"])
    a.LISTENERS["提醒群"]["blocked_until"] = a.time.time() - 1
    assert not a.listener_blocked(a.LISTENERS["提醒群"])
