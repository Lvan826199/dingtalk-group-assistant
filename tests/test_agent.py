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


def drafts(a):
    d = os.path.join(a.HOME, "drafts")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def mixed_run(a, calls):
    """AI 替身命令真跑，dws 等其他命令只记下来（不真发消息）。"""
    real = subprocess.run

    def run(args, **k):
        if args and args[0] == sys.executable:
            return real(args, capture_output=True, text=True, encoding="utf-8", **k)
        calls.append(args); return R(0, '{"success": true}')
    a.run = run


def confirm(a, no, how="可以发送"):
    a.relevant(msg(f"{no} {how}", sender="本人", cid="cidN", mid="c-" + no + how))


# ---------------- 别人之间的对话不插话（v2.6）
@pytest.mark.parametrize("content,drafted", [("@另一位同事 看下这个", False), ("@本人 @另一位同事 看下", True), ("@所有人 通知", True), ("没有 at 的消息", True)])
def test_others_conversation_skipped(make_agent, content, drafted):
    a, _, calls = make_agent({"groups": {GROUP: "测试群"}})
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "好"}
    a.handle([msg(content)])
    assert bool(drafts(a)) is drafted and not sent(calls)


# ---------------- v2.8 决策权交给人：任何配置都不会自动发出
@pytest.mark.parametrize("cfg", [{}, {"mode": "auto"}, {"auto_reply_groups": [GROUP]}, {"mode": "auto", "auto_reply_groups": [GROUP], "emoji": True}])
def test_never_auto_send(make_agent, cfg):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}, **cfg})
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "好", "emoji": "赞", "sticker": ""}
    a.handle([msg("@本人 在吗")])
    a.decide = lambda b: {"action": "escalate", "mine": True, "reason": "派活"}
    a.handle([msg("@本人 你来负责一下", mid="m2")])
    a.decide = lambda b: {"action": "ignore", "mine": True, "emoji": "赞"}
    a.handle([msg("@本人 谢谢", mid="m3")])
    assert calls == []                                                    # 没有发消息、没有回执、没有点表情
    assert any("草稿待你确认" in t for t, _ in notes) and any("需要你处理" in t for t, _ in notes)


def test_status_events_are_logged_and_announced(make_agent):
    a, notes, _ = make_agent({"status_notifications": True})
    a.status_event("收到消息", "测试群 / 同事：请核实版本", announce=True)
    a.status_event("处理完成", "已写入草稿", announce=True)
    rows = [json.loads(x) for x in open(a.STATUS_LOG, encoding="utf-8").read().splitlines()]
    assert [x["stage"] for x in rows[-2:]] == ["收到消息", "处理完成"]
    assert any("收到消息" in t for t, _ in notes) and any("处理完成" in t for t, _ in notes)


def test_auto_reply_commands_rejected_and_readonly_toggle(make_agent):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}})
    say = lambda t: a.relevant(msg(t, sender="本人", cid="cidN", mid=t))
    say("测试群 自动回复"); say("确认开启 测试群")
    assert all("不提供自动回复" in t for t, _ in notes[-2:])
    say("测试群 只看")
    assert not a.can_reply(GROUP)
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "好"}
    a.handle([msg("@本人 在吗")])
    assert not drafts(a) and any("需要你处理" in t for t, _ in notes)   # 只看的群连草稿都不出
    say("测试群 可发草稿")
    assert a.can_reply(GROUP)


def test_v28_notice_once(make_agent):
    a, notes, _ = make_agent({"groups": {GROUP: "测试群"}, "auto_reply_groups": [GROUP]})
    a.upgrade_ask(); a.upgrade_ask()
    assert len([t for t, _ in notes if "不再自动回复" in t]) == 1


def test_confirm_sends_and_audits(make_agent):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}})
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "测试服是 97f79eb", "reason": "发布通知 16:17"}
    a.handle([msg("@本人 测试服哪个版本", mid="mABCDE")])
    assert not sent(calls)
    confirm(a, "#ABCDE")
    assert len(sent(calls)) == 1 and not drafts(a)
    rec = [json.loads(l) for l in open(a.AUDIT, encoding="utf-8")]
    assert rec[-1]["发出内容"] == "测试服是 97f79eb" and rec[-1]["确认人"] == "本人" and rec[-1]["AI 依据"] == "发布通知 16:17"
    a.cleanup_old(); a.purge_now()
    assert os.path.exists(a.AUDIT)                                        # 留痕不随清理删除


def test_ask_ai_then_confirm(make_agent):
    stub = [sys.executable, "-c", "import sys,json; sys.stdin.read(); print(json.dumps({'answer':'依据是 16:17 的发布通知','new_draft':'您好，测试服现在是 97f79eb'}))"]
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}, "ai_cmd": stub, "ai_prompt": "stdin"})
    mixed_run(a, calls)
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "97f79eb"}
    a.handle([msg("@本人 测试服哪个版本", mid="mQWERT")])
    a.relevant(msg("#QWERT 问：依据是什么？顺便改得客气点", sender="本人", cid="cidN", mid="q1"))
    assert "AI 的回答" in notes[-1][0] and "16:17" in notes[-1][1]
    assert not sent(calls)                                                # 问 AI 不会发任何东西
    confirm(a, "#QWERT")
    rec = json.loads(open(a.AUDIT, encoding="utf-8").read().splitlines()[-1])
    assert rec["发出内容"] == "您好，测试服现在是 97f79eb" and rec["确认前问过 AI"][0]["问"].startswith("依据是什么")


def test_ask_ai_on_escalated_item(make_agent):
    stub = [sys.executable, "-c", "import sys,json; sys.stdin.read(); print(json.dumps({'answer':'这是派活，建议你自己回','new_draft':''}))"]
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}, "ai_cmd": stub, "ai_prompt": "stdin"})
    mixed_run(a, calls)
    a.decide = lambda b: {"action": "escalate", "mine": True, "reason": "派活"}
    a.handle([msg("@本人 这个你来负责", mid="mZXCVB")])
    a.relevant(msg("#ZXCVB 问：我该怎么回？", sender="本人", cid="cidN", mid="q2"))
    assert "建议你自己回" in notes[-1][1] and not sent(calls)


# ---------------- 表情（v2.6；v2.8 起只随确认发出）
def test_sticker_only_sent_on_confirm(make_agent):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}, "emoji": True})
    os.makedirs(a.MEMDIR, exist_ok=True)
    json.dump({"鼓掌": "https://example.invalid/x.gif"}, open(a.STICKERS, "w", encoding="utf-8"), ensure_ascii=False)
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "辛苦啦", "sticker": "鼓掌"}
    a.handle([msg("@本人 今天上线了", mid="mSTICK")])
    assert calls == [] and "配表情包：鼓掌" in [x for t, x in notes if "草稿" in t][-1]
    confirm(a, "#STICK")
    assert len(sent(calls)) == 1 and any("--title" in c and "鼓掌" in c for c in calls)


def test_own_sticker_not_counted_as_my_reply(make_agent):
    a, _, _ = make_agent()
    closed = []; a.close_by_conversation = lambda cid: closed.append(cid)
    a.relevant(msg("[图片消息](mediaId=" + a.BQB_CDN + "x.gif)", sender="本人"))
    assert closed == []


# ---------------- 钉钉发不出去（v2.7）：确认发送时失败，草稿保留、只提醒一次
def test_send_failure_on_confirm_keeps_draft(make_agent):
    a, notes, calls = make_agent({"groups": {GROUP: "测试群"}})
    a.decide = lambda b: {"action": "reply", "mine": True, "risk": "low", "text": "改完了"}
    a.handle([msg("@本人 改完没", mid="mFAIL1")])
    a.run = lambda args, **k: R(1, '{"error": {"message": "请求参数不能为空"}}')
    confirm(a, "#FAIL1"); confirm(a, "#FAIL1", "发送")
    fails = [t for t, _ in notes if "没发出去" in t]
    assert len(fails) == 1 and len(drafts(a)) == 1 and not os.path.exists(a.AUDIT)


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


# ---------------- 超时再提醒（v2.8）
def test_remind_after_two_hours_and_configurable(make_agent):
    a, notes, _ = make_agent({"groups": {GROUP: "测试群"}})
    a.decide = lambda b: {"action": "escalate", "mine": True, "reason": "派活"}
    a.handle([msg("@本人 这个你来负责", mid="mREMIN")])
    t0 = time.time()
    assert a.remind_due(t0 + 119 * 60) == []
    assert [no for no, _ in a.remind_due(t0 + 121 * 60)] == ["#REMIN"] and "超过 2 小时" in notes[-1][0]
    assert a.remind_due(t0 + 150 * 60) == []                             # 刚提醒过，不连着刷
    a.relevant(msg("提醒间隔 30分钟", sender="本人", cid="cidN", mid="i1"))
    assert json.load(open(a.CFG_PATH, encoding="utf-8"))["remind_after_minutes"] == 30
    assert a.remind_due(t0 + 152 * 60)                                    # 距上次提醒超过 30 分钟
    a.relevant(msg("提醒间隔 关", sender="本人", cid="cidN", mid="i2"))
    assert a.remind_due(t0 + 999 * 60) == []
