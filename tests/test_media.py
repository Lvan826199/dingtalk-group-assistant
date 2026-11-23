"""图片真实输入、下载失败保护及后台草稿审核边界。无真实账号或发送。"""
import json
import os
from pathlib import Path

from conftest import R


def image_event():
    return {"sender": "同事", "content": "@本人[图片消息](mediaId=@real-media)",
            "message_id": "msgIMAGE1", "conversation_id": "cidG"}


def downloader(a, calls, partial=False, bad_path=False):
    def run(args, **kwargs):
        calls.append(args)
        directory = Path(a.HOME) / args[args.index("--output-dir") + 1]
        path = directory / "screenshot.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"verified-image")
        row = {"localPath": "../outside.png" if bad_path else os.path.relpath(path, a.HOME)}
        return R(0, json.dumps({"complete": True, "messagesComplete": True, "failures": [],
                              "resourceDownloads": {"ok": True, "partial": partial,
                                                    "failedCount": int(partial), "downloads": [row]}}))
    a.run = run


def test_image_download_is_passed_to_ai_and_cached(make_agent):
    a, _, calls = make_agent()
    downloader(a, calls)
    inputs = []
    a.ai_exec = lambda prompt, **kw: inputs.append((prompt, kw)) or '{"action":"reply","mine":true,"text":"图中13条"}'
    a.decide([image_event()])
    a.decide([image_event()])
    assert len(calls) == 1 and "--download-resources" in calls[0]
    assert len(inputs) == 2 and Path(inputs[0][1]["images"][0]).is_file()
    assert inputs[0][1]["images"] == inputs[1][1]["images"]
    assert "读取实际图像" in inputs[0][0]


def test_partial_download_retains_pending_without_false_reply(make_agent):
    a, notes, calls = make_agent({"groups": {"cidG": "测试群"}})
    downloader(a, calls, partial=True)
    a.ai_exec = lambda *args, **kw: (_ for _ in ()).throw(AssertionError("不完整的图不能交给AI猜"))
    result = a.handle([image_event()])
    assert "等待本人处理" in result
    assert a._open_load() and not list(Path(a.HOME, "drafts").glob("*.json"))
    assert any("图片读取失败" in title for title, _ in notes)
    assert not any("+messages-reply" in c or "+messages-send" in c for c in calls)


def test_download_cannot_escape_attachment_directory(make_agent):
    a, _, calls = make_agent()
    downloader(a, calls, bad_path=True)
    images, errors = a.image_inputs([image_event()])
    assert not images and errors and "超出" in errors[0]


def test_codex_receives_image_flag_in_actual_command(make_agent):
    a, _, calls = make_agent()
    a.run = lambda args, **kw: calls.append(args) or R(0, '{"action":"ignore"}')
    result = a._ai_once("Codex", ["codex", "exec"], "arg", "只读图片", 20, ["/tmp/image with space.png"])
    assert result and "--image=/tmp/image with space.png" in calls[0]


def test_unknown_engine_never_silently_drops_images(make_agent):
    a, _, calls = make_agent()
    assert a._ai_once("自定义", ["unknown-ai"], "stdin", "图片", 20, ["/tmp/a.png"]) == ""
    assert not calls


def test_claude_is_instructed_to_read_actual_image_file(make_agent):
    a, _, _ = make_agent()
    captured = []
    a.run = lambda args, **kw: captured.append(kw.get("input")) or R(0, "已读取")
    a._ai_once("Claude Code", ["claude", "-p"], "stdin", "判断图片", 20, ["/tmp/a.png"])
    assert "Read 工具" in captured[0] and "/tmp/a.png" in captured[0]


def test_background_result_updates_one_draft_without_sending(make_agent):
    a, notes, calls = make_agent({"groups": {"cidG": "测试群"}})
    e = image_event()
    no = a.stage_draft(e, "第一次核查", "初步证据")
    assert a.stage_draft(e, "13项canCreate=false", "真实接口结果") == no
    files = list(Path(a.HOME, "drafts").glob("*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text(encoding="utf-8"))["draft"] == "13项canCreate=false"
    assert len(a._open_load()) == 1 and not calls
    assert "草稿待你确认" in notes[-1][0]


def test_unquoted_unrelated_message_keeps_pending_but_quoted_reply_closes(make_agent):
    a, _, _ = make_agent()
    e = image_event()
    no = a.open_add(e, "draft", "待审核")
    a.close_by_conversation("cidG", {"content": "另一件事已处理"})
    assert no in a._open_load()
    # 11-23 用户：代本人值守的程序用本人身份引用回复，也算处理了（以前不关，导致已处理的还挂在草稿待发）
    a.close_by_conversation("cidG", {"quoted_message": {"openMessageId": e["message_id"]}, "messageAiSendFlag": "DWS"})
    assert no not in a._open_load()


def test_reply_mentioning_same_ticket_closes_only_that_item(make_agent):
    a, _, _ = make_agent()
    e1 = {**image_event(), "message_id": "msgAAAA1", "content": "【COMIC-1999-092｜请确认测试进度】"}
    e2 = {**image_event(), "message_id": "msgBBBB2", "content": "TICKET-832 请安排测"}
    n1 = a.open_add(e1, "draft", "x"); n2 = a.open_add(e2, "draft", "y")
    a.close_by_conversation("cidG", {"content": "收到，COMIC-1999-092 接口核对我来测", "quoted_message": {"message_id": "别的消息"}})
    assert n1 not in a._open_load() and n2 in a._open_load()


def test_robot_text_restores_newlines_and_preserves_code(make_agent):
    a, _, _ = make_agent()
    assert a.tidy(r"11:40 已完成\n12:43 已核实\n14:25 待处理") == "11:40 已完成\n\n12:43 已核实\n\n14:25 待处理"
    assert a.tidy(r"路径 `C:\new\notes`\n下一行") == "路径 `C:\\new\\notes`\n\n下一行"


def test_late_ai_answer_cannot_reopen_closed_task(make_agent):
    a, notes, calls = make_agent({"groups": {"cidG": "测试群"}})
    e = {**image_event(), "content": "@本人 接口核查"}
    no = a.stage_draft(e, "核查中")
    def answer(*args, **kwargs):
        a.open_close(no, "本人已处理")
        f, _ = a.draft_by_no(no)
        if f:
            os.remove(f)
        return '{"answer":"迟到的回答","new_draft":"迟到的新草稿"}'
    a.ai_exec = answer
    a.ask_ai(no, "核查了吗")
    assert not a._open_load() and not list(Path(a.HOME, "drafts").glob("*.json"))
    assert not any("AI 的回答" in title for title, _ in notes) and not calls


def test_timeout_closes_child_pipe_and_returns_without_hanging(make_agent):
    import sys
    import time
    a, _, _ = make_agent(fake_run=False)
    code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)"
    start = time.monotonic()
    result = a.run([sys.executable, "-c", code], timeout=0.5)
    assert result.returncode == 124 and time.monotonic() - start < 5
    assert not a.CHILDREN


def test_local_draft_endpoint_only_stages_and_never_sends(make_agent):
    import importlib
    import sys
    import urllib.request
    import urllib.error
    import socket
    a, _, calls = make_agent({"groups": {"cidG": "测试群"}, "popup": False})
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        a.CFG["console_port"] = sock.getsockname()[1]
    sys.path.insert(0, a.HOME)
    console = importlib.import_module("console")
    importlib.reload(console)
    server = console.start(vars(a))
    try:
        url = console.url().split("?")[0].rstrip("/") + "/api/draft"
        payload = json.dumps({"event": image_event(), "draft": "截图13条已核实", "reason": "核查证据"}).encode()
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "X-Key": console.TOKEN})
        result = json.load(urllib.request.urlopen(request, timeout=5))
        assert result["ok"] and result["sent"] is False
        assert len(a._open_load()) == 1 and not calls
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(request, timeout=5)
            assert False, "无认证的草稿写入应被拒绝"
        except urllib.error.HTTPError as ex:
            assert ex.code == 403
    finally:
        server.shutdown()
