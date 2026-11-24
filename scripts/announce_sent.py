"""值守自动回复后留痕（11-23 本人：自动回复了要在调试群告诉我，操作台也要看得到）。
用法：announce_sent.py <群 cid> <正文> [被回复的人] [被引用的原消息 ID]
有原消息 ID 时：在操作台把对应事项关掉（调试群会出「✅ #编号 已处理」），并在「已自动回复」卡片标题写上 #编号（11-23 本人：看不出哪条回过了）。"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_user

cid, text = sys.argv[1], sys.argv[2]
who = sys.argv[3] if len(sys.argv) > 3 else ""
quoted = sys.argv[4] if len(sys.argv) > 4 else ""
KNOWN = {os.environ.get("QA_TEST_GROUP", ""): "测试群", os.environ.get("QA_COORD_GROUP", ""): "协调群", os.environ.get("QA_DEPT_GROUP", ""): "测试部群"}
try:
    name = KNOWN.get(cid) or json.loads(subprocess.run(["dws", "chat", "group", "info", "--conversation-id", cid, "--format", "json"],
                                     capture_output=True, text=True, timeout=20).stdout).get("title") or cid
except Exception:
    name = ""
if not name or name == cid:   # 私聊没有群名：取对方名字（11-23 本人：私聊只带 cid 看不出是谁）
    try:
        msgs = json.loads(subprocess.run(["dws", "chat", "message", "list", "--group", cid, "--limit", "10", "--format", "json"],
                                         capture_output=True, text=True, timeout=20).stdout).get("messages") or []
        title = next((m.get("conversationTitle") for m in msgs if m.get("conversationTitle")), "")
        peer = next((m.get("sender") for m in msgs if m.get("sender") and m.get("sender") != "本人"), "")
        name = title or ("私聊：" + peer if peer else cid)
    except Exception:
        name = cid
at = time.strftime("%m-%d %H:%M")
who = who or (name[3:] if name.startswith("私聊：") else "")
rec = {"no": "#auto" + time.strftime("%H%M%S"), "why": "值守已自动回复（" + name + "）", "who": who or name,
       "what": text[:60], "kind": "auto", "at": at, "done": at, "ts": time.time(), "cid": cid,
       "event": {}, "reason": "接口自动化范围内的事，按个人授权直接回复", "qa": [], "task_key": "", "related_events": [],
       "reply": {"content": text}}
with open(os.path.expanduser("~/qa-agent/logs/closed.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
nos = []
if quoted:
    try:
        opened = json.load(open(os.path.expanduser("~/qa-agent/logs/open.json"), encoding="utf-8"))
        nos = [no for no, x in opened.items() if (x.get("event") or {}).get("message_id") == quoted]
        tok = open(os.path.expanduser("~/.qa-agent/console_token")).read().strip()
        import urllib.request
        for no in nos:
            body = json.dumps({"no": no, "action": "manual_done", "text": "值守已自动回复：" + text[:200]}).encode()
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:8765/api/act?k={tok}", data=body,
                                   headers={"Content-Type": "application/json"}), timeout=20).read()
    except Exception:
        pass
if cid == os.environ.get("QA_NOTIFY_GROUP", ""):   # 在调试群里直接回本人的话，群里已经看得到，不再补一张「已自动回复」（11-24 本人：回了两遍）
    sys.exit(0)
notify_user.send("💬 已自动回复" + (" " + " ".join(nos) if nos else ""), ("" if name.startswith("私聊：") else "群：") + name + "\n时间：" + at + "\n\n" + text, at_me=False)
