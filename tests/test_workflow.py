"""对实际漏答、假成功、并发重发和中断场景做验证，不连接真实群。"""
import ast
import importlib.util
import json
from pathlib import Path
import threading

from conftest import R
from test_console import _boot, _post
from test_owner_queue import event, stop


def real_notify(a):
    tree = ast.parse(Path(a.__file__).read_text(encoding="utf-8"))
    fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "notify")
    exec(compile(ast.Module(body=[fn], type_ignores=[]), a.__file__, "exec"), vars(a))


def test_owner_no_answer_is_failed_and_not_silently_completed(make_agent):
    a, notes, _ = make_agent()
    a.ai_exec = lambda *args, **kwargs: ""
    a.SERVICE_RUNNING = True
    try:
        a.relevant(event("empty"))
        a.OWNER_Q.join()
        row = a.owner_snapshot()["recent"][0]
        assert row["stage"] == "failed" and row["error"]
        assert any("尚未回答" in title for title, _ in notes)
        assert not any(title == "💬 回复你的消息" for title, _ in notes)
    finally:
        stop(a)


def test_invalid_answer_alerts_instead_of_sending_raw_json(make_agent):
    a, notes, _ = make_agent()
    a.ai_exec = lambda *args, **kwargs: '{"answer":{"invalid":"shape"}}'
    assert a.process_owner_command(event("invalid")) == "failed"
    assert any("尚未回答" in title for title, _ in notes)
    assert not any(title == "💬 回复你的消息" for title, _ in notes)


def test_detailed_question_keeps_all_paragraphs_and_has_identity(make_agent):
    a, notes, _ = make_agent()
    answer = "结论：还没通过。\n\n" + "\n\n".join(f"{i}）原因和已核实的结果。" for i in range(1, 12))
    seen = []
    a.ai_exec = lambda prompt, **kwargs: seen.append(prompt) or json.dumps({"answer": answer})
    a.answer_user(event("detail"), "请逐项写全原因和之前找人的进展")
    body = next(body for title, body in notes if title == "💬 回复你的消息")
    assert answer in body and "你的问题：" in body and "时间：" in body
    assert "不限制行数" in seen[0] and "1～5行" not in seen[0]


def test_bot_delivery_failure_is_visible_as_failed(make_agent):
    a, _, _ = make_agent()
    a.ai_exec = lambda *args, **kwargs: '{"answer":"核查完成，仍缺数据。"}'
    a.notify = lambda *args: False
    assert a.process_owner_command(event("delivery")) == "failed"
    row = json.loads((Path(a.HOME) / "logs/user-dialogue.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["delivered"] is False


def test_restart_exposes_unfinished_owner_commands_without_resending(make_agent):
    a, notes, calls = make_agent()
    a.owner_update(event("queued"), "queued")
    a.owner_update(event("running"), "running")
    a.owner_update(event("finished"), "replied", answer="结果已回复")
    a.OWNER_COMMANDS.clear()
    a.recover_owner_commands()
    rows = {r["message_id"]: r for r in a.owner_snapshot()["recent"]}
    assert rows["queued"]["stage"] == rows["running"]["stage"] == "interrupted"
    assert rows["finished"]["stage"] == "replied"
    assert a.OWNER_Q.empty() and not calls
    assert any("未完成" in title for title, _ in notes)
    a.relevant(event("running"))
    assert a.OWNER_Q.empty()


def test_slow_owner_notice_is_once_then_timeout_and_never_rolls_back_reply(make_agent):
    a, notes, _ = make_agent()
    a.owner_update(event("slow"), "running", received=100)
    a.check_owner_commands(now=221)
    a.check_owner_commands(now=222)
    assert len(notes) == 1 and "仍在处理" in notes[0][0]
    a.check_owner_commands(now=701)
    assert len(notes) == 2 and "超时" in notes[1][0]
    a.check_owner_commands(now=702)
    assert len(notes) == 2
    # 发送慢提醒期间结果返回，提醒收尾不能把已回复改回处理中。
    a.owner_update(event("race"), "running", received=100)
    def notify(*args):
        a.owner_update(event("race"), "replied", answer="已经答复")
        return True
    a.notify = notify
    a.check_owner_commands(now=221)
    assert next(x for x in a.owner_snapshot()["recent"] if x["message_id"] == "race")["stage"] == "replied"


def test_console_send_failure_never_reports_handled_or_removes_draft(make_agent):
    a, c, _, calls, no, _ = _boot(make_agent)
    a.run = lambda *args, **kwargs: R(1, "", "fixture send failed")
    result = _post(c, {"no": no, "action": "send"})
    assert "尚未确认发送成功" in result["msg"]
    assert a.draft_by_no(no)[0] and no in a._open_load()
    assert not any(x["no"] == no and x.get("sent") for x in c.state()["done"])


def test_console_double_click_only_sends_once(make_agent):
    a, c, _, calls, no, _ = _boot(make_agent)
    entered, release = threading.Event(), threading.Event()
    def run(args, **kwargs):
        if "+messages-reply" in args:
            calls.append(args); entered.set(); assert release.wait(3)
        return R(0, '{"success":true}')
    a.run = run
    result = []
    t = threading.Thread(target=lambda: result.append(c.act(no, "send")))
    try:
        t.start(); assert entered.wait(2)
        assert "请勿重复" in c.act(no, "send")
        release.set(); t.join(3)
        assert not t.is_alive() and result == ["ok"]
        assert "已处理" in c.act(no, "send")
        assert len(calls) == 1
    finally:
        release.set(); t.join(3)


def test_console_does_not_mark_connecting_listener_ready_and_shows_queue(make_agent):
    a, c, _, _, _, _ = _boot(make_agent)
    a.LISTENERS.update({"one": {"alive": True, "ready": True}, "two": {"alive": True, "starting": True}})
    a.owner_update(event("waiting"), "queued")
    s = c.state()
    assert s["listeners"] == "1/2" and s["duty"] != "ok"
    assert s["owner"]["queued"] == 1 and "processing" in s and "queue" in s




def test_confirmation_ignores_old_number_mentioned_in_report_body(make_agent):
    a, c, notes, calls, no, _ = _boot(make_agent)
    message = event("approval")
    message.update(content="可以发送", quoted_message={"text": "### 本轮回归详细说明\n\n27项明细如下。\n\n之前的" + no + "旧草稿已取消，不再发送。"})
    assert a.command_text(message) is None
    a.command(message)
    assert not calls and a.draft_by_no(no)[0]
    assert any("没能确定" in title for title, _ in notes)
    message["quoted_message"]["text"] = "### 📝 " + no + " 草稿待你确认\n\n历史提到 #OLD01，不是本次操作对象。"
    assert a.command_text(message) == no + " 可以发送"




def test_notification_layout_preserves_code_links_and_all_facts():
    path = Path(__file__).resolve().parents[1] / "console.py"
    spec = importlib.util.spec_from_file_location("notice_layout", path)
    c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    source = '群：测试群\\n任务：任务甲\\n结论：未通过。\n\n详情见 [记录](https://example.invalid/issue/1)。\n\n代码：`C:\\new\\notes`\n\n```python\nvalue = "\\n"\nprint(value)\n```'
    body = c.notification_body(source)
    assert body.startswith("📍 测试群  🏷 任务甲")   # 3.4.5：群 / 时间 / 任务收成正文第一行（钉钉不认 <font>）
    assert "**结论：** 未通过。" in body
    assert '[记录](https://example.invalid/issue/1)' in body
    assert '`C:\\new\\notes`' in body
    assert '```python\nvalue = "\\n"\nprint(value)\n```' in body
    assert "未通过" in body
    assert c.notification_body(body) == body


def test_long_notification_is_split_without_losing_information():
    path = Path(__file__).resolve().parents[1] / "console.py"
    spec = importlib.util.spec_from_file_location("notice_long", path)
    c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    sentences = [str(i) + "核查结果仍缺少数据，继续保留原始证据。" * 5 + "。" for i in range(8)]
    result = c.notification_body("答复：" + "".join(sentences))
    assert result.count("\n\n") >= 8
    assert result.replace("**答复**", "").replace("> ", "").replace("\n", "") == "".join(sentences)
