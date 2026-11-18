"""群消息助手回归测试：每个用例对应一条真实踩过的坑或定下的规则（见 CHANGELOG）。钉钉、AI 都用替身，不碰真实账号。
运行：python -m pytest -q tests"""
import json, os, subprocess, sys, time

import pytest

from conftest import R

GROUP = "cidG"


def msg(content, sender="同事", cid=GROUP, mid="m1"):
    return {"conversation_id": cid, "message_id": mid, "sender": sender, "content": content}


def sent(calls):
    """真正发到群里的回复（+messages-reply）"""
    return [c for c in calls if "+messages-reply" in c]


# ---------------- 回复格式（v2.6）
def test_tidy_blank_line_between_lines(make_agent):
    a, _, _ = make_agent()
    assert a.tidy("第一行\n第二行\\n第三行\n\n  ") == "第一行\n\n第二行\n\n第三行"


# ---------------- 别人之间的对话不插话（v2.6）
@pytest.mark.parametrize("content,replied", [("@另一位同事 看下这个", False), ("@本人 @另一位同事 看下", True), ("@所有人 通知", True), ("没有 at 的消息", True)])
def test_others_conversation_skipped(make_agent, content, replied):
    a, _, calls = make_agent({"groups": {GROUP: "测试群"}, "auto_reply_groups": [GROUP]})
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "好"}
    a.handle([msg(content)])
    assert bool(sent(calls)) is replied


# ---------------- 群聊默认只提醒，开自动回复要二次确认（v2.6）
def test_new_deploy_groups_remind_only(make_agent):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}, "auto_reply_groups": []})
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "好"}
    a.handle([msg("@本人 在吗")])
    assert not sent(calls) and any("需要你处理" in t for t, _ in notes)


def test_group_auto_reply_needs_second_confirm(make_agent):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}, "auto_reply_groups": []})
    say = lambda t: a.relevant(msg(t, sender="本人", cid="cidN", mid=t))
    say("测试群 自动回复")
    assert not a.can_reply(GROUP) and "二次确认" in notes[-1][0]
    say("确认开启 测试群")
    assert a.can_reply(GROUP)
    say("测试群 只提醒")
    assert not a.can_reply(GROUP)
    cfg = json.load(open(a.CFG_PATH, encoding="utf-8"))
    assert cfg["auto_reply_groups"] == []


# ---------------- 升级不覆盖已有规则（v2.7）
def test_upgrade_keeps_legacy_auto_reply_and_asks(make_agent):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}})          # 旧配置：没有 auto_reply_groups
    assert a.can_reply(GROUP)
    a.upgrade_ask()
    assert "需要你定" in notes[-1][0]
    a.relevant(msg("全部只提醒", sender="本人", cid="cidN", mid="x"))
    assert not a.can_reply(GROUP)
    n = len(notes); a.upgrade_ask()
    assert len(notes) == n                                               # 选过以后不再问


# ---------------- 表情（v2.6）
def test_emoji_off_by_default_and_whitelist(make_agent):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}, "auto_reply_groups": [GROUP]})
    a.decide = lambda b: {"action": "ignore", "mine": True, "emoji": "赞"}
    a.handle([msg("谢谢")])
    assert not [c for c in calls if "add-emoji" in c]                    # 默认关
    a.relevant(msg("表情 开", sender="本人", cid="cidN", mid="e"))
    a.handle([msg("谢谢", mid="m2")])
    assert [c for c in calls if "add-emoji" in c]
    a.decide = lambda b: {"action": "ignore", "mine": True, "emoji": "随便写的"}
    n = len(calls); a.handle([msg("谢谢", mid="m3")])
    assert len(calls) == n                                               # 白名单外不点


def test_own_sticker_not_counted_as_my_reply(make_agent):
    a, _, _ = make_agent()
    closed = []; a.close_by_conversation = lambda cid: closed.append(cid)
    a.relevant(msg("[图片消息](mediaId=" + a.BQB_CDN + "x.gif)", sender="本人"))
    assert closed == []


# ---------------- 钉钉发不出去（v2.7）
def test_send_failure_notifies_once_and_keeps_draft_with_number(make_agent):
    a, notes, _ = make_agent({"groups": {GROUP: "测试群"}, "auto_reply_groups": [GROUP]})
    a.run = lambda args, **k: R(1, '{"error": {"message": "请求参数不能为空"}}')
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "改完了"}
    for i in range(2):
        with pytest.raises(a.SendFailed):
            a.handle([msg("@本人 改完没", mid=f"m{i}")])
    fails = [t for t, _ in notes if "没发出去" in t]
    assert len(fails) == 1 and "#m0" in fails[0]                         # 只提醒一次，标题带草稿编号
    assert len(os.listdir(os.path.join(a.HOME, "drafts"))) == 2


# ---------------- 找不到命令 / 卡住都不崩（v2.7）
def test_run_missing_command_and_timeout(make_agent):
    a, _, _ = make_agent(fake_run=False)
    assert a.run(["no-such-command-xyz"]).returncode == 127
    r = a.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1)
    assert r.returncode == 124


# ---------------- 判断用的 AI（v2.7）
def test_custom_ai_command(make_agent):
    stub = [sys.executable, "-c", "import sys,json; d=sys.stdin.read(); print(json.dumps({'action':'ignore','reason':'收到 %d 字' % len(d)}))"]
    a, _, _ = make_agent({"ai": "Trae", "ai_cmd": stub, "ai_prompt": "stdin"}, fake_run=False)
    assert a.ai_engine()[0] == "Trae"
    assert a.decide([msg("hi")])["action"] == "ignore"


def test_dsh_preset_reads_task_from_stdin(make_agent):
    a, _, _ = make_agent()
    assert a.AI_PRESETS["dsh"]["args"] == ["--profile", "headless", "-"] and a.AI_PRESETS["dsh"]["prompt"] == "stdin"


@pytest.mark.skipif(os.name == "nt", reason="替身命令用 sh 脚本")
def test_ai_fallback_to_other_installed(make_agent, tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"; bin_.mkdir()
    s = bin_ / "claude"
    s.write_text('#!/bin/sh\ncat >/dev/null\necho \'{"action":"ignore","reason":"备用 AI"}\'\n'); s.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}/usr/bin{os.pathsep}/bin")
    a, notes, _ = make_agent({"ai": "qoder"}, fake_run=False)            # 指定的 qoder 没装
    d = a.decide([msg("hi")])
    assert d["reason"] == "备用 AI" and any("备用" in t for t, _ in notes)


def test_ai_fallback_can_be_disabled(make_agent, monkeypatch):
    monkeypatch.setenv("PATH", "")
    a, _, _ = make_agent({"ai": "qoder", "ai_fallback": False}, fake_run=False)
    assert a.ai_exec("hi") == ""


# ---------------- 版本检查（v2.7）
def test_dws_version_check(make_agent):
    a, notes, _ = make_agent()
    a.run = lambda args, **k: R(0, "  新版本可用:  v1.0.58 → v1.0.68\n")
    a.dws_version_check(); a.dws_version_check()
    assert len([t for t, _ in notes if "钉钉 CLI" in t]) == 1
    a2, notes2, _ = make_agent()
    a2.run = lambda args, **k: R(0, "  ✔ 已是最新版本 v1.0.68")
    a2.dws_version_check()
    assert not notes2


def test_self_update_check(make_agent, monkeypatch):
    a, notes, _ = make_agent()

    class Resp:
        def __init__(self, body): self.body = body.encode()
        def read(self, n=-1): return self.body
        def __enter__(self): return self
        def __exit__(self, *x): return False

    monkeypatch.setattr(a.urllib.request, "urlopen", lambda *x, **k: Resp('{"version": "v99.1 2099-01-01"}'))
    a.self_update_check(); a.self_update_check()
    assert len([t for t, _ in notes if "新版本 v99.1" in t]) == 1
    monkeypatch.setattr(a.urllib.request, "urlopen", lambda *x, **k: Resp(f'VERSION = "{a.VERSION}"'))
    n = len(notes); a.self_update_check()
    assert len(notes) == n
    assert a._ver("v2.10") > a._ver("v2.9") and a._ver("v2.7 2026-11-18") == (2, 7)


# ---------------- 保留期（v2.7）
def test_cleanup_old_keeps_memory(make_agent):
    a, notes, _ = make_agent({"keep_days": 30})
    inbox = os.path.join(a.HOME, "inbox.jsonl")
    with open(inbox, "w", encoding="utf-8") as f:
        f.write(json.dumps({"content": "旧", "_t": int(time.time()) - 40 * 86400}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"content": "新", "_t": int(time.time())}, ensure_ascii=False) + "\n")
        f.write("坏行\n")
    mem = os.path.join(a.MEMDIR, "负责人.md"); open(mem, "w", encoding="utf-8").write("# 负责人\n")
    os.makedirs(os.path.join(a.HOME, "history"), exist_ok=True)
    old = os.path.join(a.HOME, "history", "群.json"); open(old, "w").write("{}")
    os.utime(old, (time.time() - 40 * 86400,) * 2)
    a.cleanup_old()
    lines = open(inbox, encoding="utf-8").read()
    assert "新" in lines and "旧" not in lines and not os.path.exists(old) and os.path.exists(mem)


def test_purge_command(make_agent):
    a, notes, _ = make_agent()
    open(os.path.join(a.HOME, "inbox.jsonl"), "w", encoding="utf-8").write('{"x":1}\n{"x":2}\n')
    a.relevant(msg("清理记录", sender="本人", cid="cidN", mid="p"))
    assert "已清理" in notes[-1][0] and os.path.getsize(os.path.join(a.HOME, "inbox.jsonl")) == 0


# ---------------- 停掉助手时连同子进程一起结束（v2.7；CI 在 Windows / macOS / Linux 都跑）
def test_stop_children_kills_grandchild(make_agent):
    a, _, _ = make_agent(fake_run=False)
    code = ("import subprocess,sys,time;"
            "g=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
            "print(g.pid,flush=True);time.sleep(60)")
    p = a.popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
    gpid = int(p.stdout.readline())
    a._stop_children()
    time.sleep(2)

    def alive(pid):
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
            return str(pid) in out
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        try:                                                              # 僵尸进程也算已结束
            return "Z" not in subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout
        except Exception:
            return True
    assert not alive(gpid)
