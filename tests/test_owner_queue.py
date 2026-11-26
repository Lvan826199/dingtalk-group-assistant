"""长核查不能占住消息读取；本人指令仍须按收到顺序执行。"""
import json
import threading
import time
from pathlib import Path


def event(mid):
    return {"message_id": mid, "conversation_id": "cidN", "sender": "本人", "content": "请核查 " + mid}


def stop(a):
    a.UPDATE_EXIT.set()
    if a.OWNER_THREAD:
        a.OWNER_THREAD.join(2)
        assert not a.OWNER_THREAD.is_alive()


def test_slow_owner_check_does_not_block_receive_and_keeps_order(make_agent, monkeypatch):
    a, notes, _ = make_agent()
    a.SERVICE_RUNNING = True
    first_started, release, second_done = threading.Event(), threading.Event(), threading.Event()
    order = []

    def command(e):
        order.append(e["message_id"])
        if e["message_id"] == "first":
            first_started.set()
            assert release.wait(3)
        else:
            second_done.set()

    monkeypatch.setattr(a, "command", command)
    try:
        assert not a.relevant(event("first"))
        assert first_started.wait(2)
        received = threading.Event()
        reader = threading.Thread(target=lambda: (a.relevant(event("second")), received.set()))
        reader.start()
        assert received.wait(1), "第二条消息读取不应等待第一条AI结束"
        reader.join(1)
        assert not second_done.is_set(), "发送/改稿指令不能越过前面的核查"
        # 原文已保留，即使当前还未轮到执行也不应丢失。
        rows = [json.loads(x) for x in (Path(a.HOME) / "inbox.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [x["message_id"] for x in rows] == ["first", "second"]
        assert "排队 1" in a.status_snapshot()
        limit = time.monotonic() + 1
        while len(notes) < 2 and time.monotonic() < limit:
            time.sleep(0.01)
        assert len([x for x in notes if x[0] == "💬 已收到你的消息"]) == 2
        release.set()
        assert second_done.wait(2)
        assert order == ["first", "second"]
    finally:
        release.set()
        stop(a)


def test_owner_failure_alerts_and_next_command_runs(make_agent, monkeypatch):
    a, _, _ = make_agent()
    a.SERVICE_RUNNING = True
    done = threading.Event()
    errors = []

    def command(e):
        if e["message_id"] == "bad":
            raise RuntimeError("test failure")
        done.set()

    monkeypatch.setattr(a, "command", command)
    monkeypatch.setattr(a, "runtime_alert", lambda *args: errors.append(args))
    try:
        a.relevant(event("bad"))
        a.relevant(event("next"))
        assert done.wait(2)
        assert errors and errors[0][0] == "owner-command"
    finally:
        stop(a)


def test_owner_duplicate_is_only_enqueued_once(make_agent, monkeypatch):
    a, _, _ = make_agent()
    a.SERVICE_RUNNING = True
    count, done = [], threading.Event()
    monkeypatch.setattr(a, "command", lambda e: (count.append(e["message_id"]), done.set()))
    try:
        a.relevant(event("same"))
        a.relevant(event("same"))
        assert done.wait(2)
        assert count == ["same"]
        rows = (Path(a.HOME) / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(rows) == 1
    finally:
        stop(a)


def test_stale_failed_command_does_not_flag(make_agent):
    import time
    a, notes, calls = make_agent()
    now = time.time()
    a.OWNER_COMMANDS["old"] = {"message_id": "old", "question": "旧的", "received": now - 13 * 3600, "stage": "failed"}
    a.OWNER_COMMANDS["new"] = {"message_id": "new", "question": "新的", "received": now - 60, "stage": "failed"}
    snap = a.owner_snapshot(now)
    assert snap["needs_attention"] == 1
    assert [x["message_id"] for x in snap["recent"] if not x.get("stale")][0] == "new"
