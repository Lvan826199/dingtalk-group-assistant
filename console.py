"""本机操作台（v3.0）：助手在本机起一个网页，三列看「要你判断 / 草稿待发 / 已处理」，在页面上直接处理。
- 只监听 127.0.0.1，链接带密钥（~/.qa-agent/console_token，只本人可读），同局域网别人打不开。
- 页面上的每个操作都转成和提醒群一模一样的指令（「#编号 可以发送」等）交给 agent.command 执行：
  发出、留痕、提醒群里的「✅ 已处理」都走原来那套，所以页面 / 提醒群 / 桌面通知三处天然同步。
- 只用 Python 标准库。agent.py 启动时调用 console.start(globals())。
"""
import glob
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

A = {}                     # agent.py 的全局变量（start 时传进来）
TOKEN = ""
CLOSED_N = 20              # 「已处理」列只显示最近 20 条（11-19 梦无矶：3 天内为主，但始终保证 20 条）
POP = {"t": 0}             # 上次把操作台弹到前面的时间


def _p(*parts):
    return os.path.join(A["HOME"], *parts)


def _token():
    path = os.path.join(os.path.expanduser("~"), ".qa-agent", "console_token")
    try:
        t = open(path, encoding="utf-8").read().strip()
        if len(t) >= 16:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(18)
    with open(path, "w", encoding="utf-8") as f:
        f.write(t)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return t


def _closed_log(no, why, x):
    rec = {"no": no, "why": why, "who": x.get("who"), "what": x.get("what"), "kind": x.get("kind"), "at": x.get("at"),
           "done": time.strftime("%m-%d %H:%M"), "ts": time.time(), "cid": x.get("cid")}
    with A["LOCK"], open(_p("logs", "closed.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _wrap_open_close():
    """所有「处理完」都会经过 open_close（提醒群指令、页面、本人在原会话亲自回复），在这里顺手记一笔给「已处理」列。"""
    orig = A["open_close"]

    def open_close(no, why):
        x = A["_open_load"]().get(no)
        orig(no, why)
        if x:
            try:
                _closed_log(no, why, x)
            except OSError:
                pass
    A["open_close"] = open_close


def popup(no=""):
    """有新的要处理 → 用系统默认浏览器打开操作台并定位到这件事（浏览器会切到最前面）。
    同一时间只留一个操作台标签页：新打开的页面会通知旧页面自己关掉。提醒群「弹出 关」可以关掉，默认 60 秒内最多弹一次。"""
    cfg = A["CFG"]
    if not cfg.get("popup", True) or not A["in_window"]() or time.time() - POP["t"] < int(cfg.get("popup_seconds") or 60):
        return False
    POP["t"] = time.time()
    u = url() + ("&focus=" + urllib.parse.quote(no) if no else "")
    try:
        if os.name == "nt":
            os.startfile(u)                                   # noqa: S606
        elif os.uname().sysname == "Darwin":
            A["popen"](["open", u])
        else:
            A["popen"](["xdg-open", u])
        A["log"]("操作台已弹出", no)
        return True
    except Exception as ex:
        A["log"]("操作台弹出失败", repr(ex)[:120])
        return False


def _wrap_open_add():
    orig = A["open_add"]

    def open_add(e, kind, why):
        no = orig(e, kind, why)
        threading.Thread(target=popup, args=(no,), daemon=True).start()
        return no
    A["open_add"] = open_add


def _wrap_group_command():
    orig = A["group_command"]

    def group_command(text):
        m = re.fullmatch(r"弹出\s*(开|关|打开|关闭)", text or "")
        if m:
            on = m.group(1) in ("开", "打开")
            A["save_cfg"]("popup", on)
            A["notify"]("🖥 操作台弹出已" + ("打开" if on else "关闭"), "有新的要处理时" + ("会自动把操作台弹到最前面（60 秒内最多一次）" if on else "不再弹出，只发桌面通知和提醒群消息") + "；发「弹出 开 / 关」切换。")
            return True
        return orig(text)
    A["group_command"] = group_command


def _drafts():
    out = {}
    for f in glob.glob(_p("drafts", "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("todo"):
            out[d["todo"]] = d
    return out


def _groups():
    return {**A["CFG"].get("groups", {}), **A["CFG"].get("readonly_groups", {})}


def state():
    items, drafts, groups, now = A["_open_load"](), _drafts(), _groups(), time.time()
    remind = max(1, int(A["CFG"].get("remind_after_minutes") or 120)) * 60
    judge, send = [], []
    for no, x in sorted(items.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True):
        d = drafts.get(no) or {}
        ev = x.get("event") or {}
        card = {"no": no, "who": x.get("who"), "group": groups.get(x.get("cid"), "私聊" if x.get("cid") and x.get("cid") not in groups else ""),
                "text": str(ev.get("content") or x.get("what") or "")[:600], "at": x.get("at"), "reason": x.get("reason") or d.get("reason") or x.get("why", ""),
                "draft": d.get("draft", ""), "qa": x.get("qa", [])[-5:], "overdue": now - x.get("ts", now) > remind,
                "can_send": A["can_reply"](x.get("cid"))}
        (send if card["draft"] else judge).append(card)
    done = []
    path = _p("logs", "closed.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8").readlines()[-CLOSED_N:]:
            try:
                done.append(json.loads(line))
            except ValueError:
                pass
    done.reverse()
    alive = sum(1 for v in A["LISTENERS"].values() if v.get("alive"))
    beat = A.get("LAST_EVENT", {}).get("t") or 0
    fails = {k: v for k, v in A.get("FAILS", {}).items() if v and v != 0}
    duty = ("ok", "值守中") if alive and alive == len(A["LISTENERS"]) and not fails else (("warn", "部分监听断开") if alive else ("bad", "没在监听"))
    if not A["in_window"]():
        duty = ("off", "值守时间外")
    return {"version": A["VERSION"], "me": A["CFG"].get("my_name"), "listeners": f"{alive}/{len(A['LISTENERS'])}",
            "duty": duty[0], "duty_text": duty[1], "last_event_t": time.strftime("%H:%M", time.localtime(beat)) if beat else "",
            "last_event": A["LAST_EVENT"].get("summary", ""), "judge": judge, "send": send, "done": done[:CLOSED_N],
            "today_done": sum(1 for x in done if x.get("done", "").startswith(time.strftime("%m-%d"))), "time": time.strftime("%H:%M:%S")}


def thread(no):
    """会话面板：这件事所在会话最近 20 条消息（群用 dws 拉；私聊只显示原消息）。"""
    x = A["_open_load"]().get(no) or {}
    cid = x.get("cid")
    if not cid or cid not in _groups():
        ev = x.get("event") or {}
        return [{"who": ev.get("sender"), "time": "", "text": str(ev.get("content") or "")}]
    r = A["run"]([A["DWS"], "chat", "message", "list", "--group", cid, "--limit", "20", "--format", "json"], timeout=60)
    try:
        msgs = json.loads(r.stdout).get("messages") or []
    except (ValueError, AttributeError):
        return [{"who": "（读取失败）", "time": "", "text": str(getattr(r, "stderr", "") or getattr(r, "stdout", ""))[:200]}]
    rows = [{"who": m.get("sender"), "time": m.get("createTime", ""), "text": str(m.get("content") or m.get("text") or ""),
             "mid": m.get("openMessageId") or m.get("messageId")} for m in msgs]
    return sorted(rows, key=lambda m: m["time"])


HISTORY_N = 30            # 历史消息：每个群看最近 30 条（只为页面上翻看方便，全量去钉钉看）


def history(cid):
    """顶栏「值守中」点开：按群看最近 30 条消息（直接从钉钉拉，不存本地）。"""
    if cid not in _groups():
        return []
    r = A["run"]([A["DWS"], "chat", "message", "list", "--group", cid, "--limit", str(HISTORY_N), "--format", "json"], timeout=60)
    try:
        msgs = json.loads(r.stdout).get("messages") or []
    except (ValueError, AttributeError):
        return [{"who": "（读取失败）", "time": "", "text": str(getattr(r, "stderr", "") or "")[:200]}]
    return sorted(({"who": m.get("sender"), "time": m.get("createTime", ""), "text": str(m.get("content") or m.get("text") or "")} for m in msgs), key=lambda m: m["time"])


def act(no, action, text=""):
    """页面按钮 → 提醒群同款指令，交给 agent.command（发出、留痕、提醒群「已处理」都走原逻辑）。"""
    if not re.fullmatch(r"#[A-Za-z0-9]{3,8}", no or ""):
        return "编号不对"
    text = (text or "").strip()
    if action == "reply_new":                       # 要你判断的事，自己写一段回复：先挂成草稿再按确认发出
        if not text:
            return "回复内容是空的"
        A["stash"](no, text)
        action = "send"
    cmd = {"send": f"{no} 可以发送", "drop": f"{no} 不发", "edit_send": f"{no} 改成：{text}", "stash": f"{no} 暂存：{text}",
           "ask": f"{no} 问：{text}", "not_mine": f"{no} 不归我"}.get(action)
    if not cmd or (action in ("edit_send", "stash", "ask") and not text):
        return "操作不对或内容为空"
    A["log"]("操作台", cmd[:80])
    A["command"]({"content": cmd, "sender": A["CFG"].get("my_name"), "conversation_id": A["CFG"].get("notify_group"), "message_id": f"console-{time.time_ns()}"})
    return "ok"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return secrets.compare_digest((q.get("k") or [""])[0], TOKEN) or secrets.compare_digest(self.headers.get("X-Key", ""), TOKEN)

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._ok():
            return self._send(403, "需要带密钥的链接：在提醒群里找「打开操作台」那条。", "text/plain; charset=utf-8")
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/state":
            return self._send(200, json.dumps(state(), ensure_ascii=False))
        if u.path == "/api/groups":
            return self._send(200, json.dumps([{"cid": c, "name": n} for c, n in _groups().items()], ensure_ascii=False))
        if u.path == "/api/history":
            return self._send(200, json.dumps(history((urllib.parse.parse_qs(u.query).get("cid") or [""])[0]), ensure_ascii=False))
        if u.path == "/api/thread":
            no = (urllib.parse.parse_qs(u.query).get("no") or [""])[0]
            return self._send(200, json.dumps(thread(no), ensure_ascii=False))
        self._send(404, "{}")

    def do_POST(self):
        if not self._ok():
            return self._send(403, "{}")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, '{"msg": "格式不对"}')
        if urllib.parse.urlparse(self.path).path != "/api/act":
            return self._send(404, "{}")
        no, action, text = body.get("no"), body.get("action"), body.get("text", "")
        if action == "ask":                          # 问 AI 要几十秒，后台跑，答案回来后卡片自动更新
            threading.Thread(target=act, args=(no, action, text), daemon=True).start()
            return self._send(200, '{"msg": "已经去问 AI 了，答案出来会显示在卡片里，提醒群也会收到"}')
        try:
            msg = act(no, action, text)
        except Exception as ex:                      # 发送失败等：原逻辑已用机器人通知
            msg = "失败：" + repr(ex)[:200]
        self._send(200, json.dumps({"msg": "已处理" if msg == "ok" else msg}, ensure_ascii=False))


def _lan_ip():
    import socket
    try:
        x = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); x.connect(("223.5.5.5", 80)); ip = x.getsockname()[0]; x.close(); return ip
    except OSError:
        return "127.0.0.1"


def lan():
    """console_host 设成 0.0.0.0（或本机内网 IP）= 允许内网其他电脑打开（比如助手装在 Mac、人在 Windows 上看）。"""
    return (A["CFG"].get("console_host") or "127.0.0.1") not in ("127.0.0.1", "localhost")


def url():
    host = A["CFG"].get("console_url_host") or (_lan_ip() if lan() else "127.0.0.1")
    return f"http://{host}:{int(A['CFG'].get('console_port') or 8765)}/?k={TOKEN}"


def start(ns):
    """agent.py 启动时调用。端口被占用（比如开了两个助手）就不开，只记日志。"""
    global TOKEN, A
    if A or not ns.get("CFG", {}).get("console", True):
        return None
    A = ns                                       # 直接用 agent 的全局变量（不拷贝），之后的替换 / 更新都能看到
    TOKEN = _token()
    _wrap_open_close()
    _wrap_open_add()
    _wrap_group_command()
    try:
        srv = ThreadingHTTPServer((A["CFG"].get("console_host") or "127.0.0.1", int(A["CFG"].get("console_port") or 8765)), H)   # console_host 只给演示用，平时只本机
    except OSError as ex:
        A["log"]("操作台没开起来（端口被占用？）", repr(ex)[:120])
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    A["log"]("操作台已开", url().split("?")[0])
    return srv


PAGE = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>群消息助手 · 操作台</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%233360e6'/%3E%3Ctext x='16' y='22' font-size='17' text-anchor='middle' fill='white' font-family='sans-serif'%3E群%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#f4f6fb;--surface:#fff;--soft:#f6f8fc;--border:#e4e9f2;--line:#eef1f7;--text:#1b2638;--muted:#6b7688;--faint:#97a1b2;
--blue:#3360e6;--blue-2:#5b7ff0;--blue-soft:#ecf1ff;--amber:#c27a00;--amber-soft:#fff4dc;--red:#d23b3b;--red-soft:#fdeeee;--green:#1c8a4a;--green-soft:#e7f6ed;
--shadow:0 1px 2px rgba(20,35,70,.04),0 4px 14px rgba(20,35,70,.06);--shadow-h:0 2px 6px rgba(20,35,70,.08),0 10px 28px rgba(20,35,70,.10)}
@media (prefers-color-scheme:dark){:root{--bg:#0f131b;--surface:#171d29;--soft:#1c2331;--border:#2a3242;--line:#222a38;--text:#e7ebf2;--muted:#9aa5b6;--faint:#6f7a8c;
--blue:#7d9bff;--blue-2:#94acff;--blue-soft:#1d2848;--amber:#f0b44c;--amber-soft:#3a2d12;--red:#ff8a80;--red-soft:#3a1e22;--green:#6fd59a;--green-soft:#163222;--shadow:0 1px 2px rgba(0,0,0,.3);--shadow-h:0 6px 22px rgba(0,0,0,.4)}}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--text);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:16px;padding:12px 24px;background:var(--surface);border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:16px}.logo{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,var(--blue),var(--blue-2));color:#fff;display:grid;place-items:center;font-size:15px}
.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:99px;background:var(--soft);border:1px solid var(--border);font-size:12.5px;color:var(--muted)}
.chip b{color:var(--text);font-weight:600}.dot{width:7px;height:7px;border-radius:50%;background:var(--green)}.dot.bad{background:var(--red)}
.duty .dot{box-shadow:0 0 0 0 currentColor;animation:pulse 2s infinite}.d-ok{color:var(--green);background:var(--green-soft);border-color:transparent}.d-ok b{color:var(--green)}
.d-warn{color:var(--amber);background:var(--amber-soft);border-color:transparent}.d-warn .dot{background:var(--amber)}.d-warn b{color:var(--amber)}
.d-bad{color:var(--red);background:var(--red-soft);border-color:transparent}.d-bad .dot{background:var(--red)}.d-bad b{color:var(--red)}.d-off .dot{background:var(--faint);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(28,138,74,.45)}70%{box-shadow:0 0 0 7px rgba(28,138,74,0)}100%{box-shadow:0 0 0 0 rgba(28,138,74,0)}}
.sp{flex:1}.ver{color:var(--faint);font-size:12px}
.btn{border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:9px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer;transition:.15s}
.btn:hover{border-color:var(--blue);color:var(--blue)}.btn.p{background:var(--blue);border-color:var(--blue);color:#fff}.btn.p:hover{filter:brightness(1.08);color:#fff}
.btn.d{color:var(--red)}.btn.d:hover{border-color:var(--red)}.btn.sm{padding:4px 10px;font-size:12.5px}
main{flex:1;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;padding:18px 24px 22px}
.col{display:flex;flex-direction:column;min-height:0}
.ch{display:flex;align-items:center;gap:10px;padding:2px 4px 12px}.ch .ic{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;font-size:14px}
.ch h2{margin:0;font-size:15px}.ch .sub{color:var(--faint);font-size:12px}.ch .cnt{margin-left:auto;min-width:26px;text-align:center;padding:1px 8px;border-radius:99px;font-weight:700;font-size:12.5px}
.c1 .ic,.c1 .cnt{background:var(--amber-soft);color:var(--amber)}.c2 .ic,.c2 .cnt{background:var(--blue-soft);color:var(--blue)}.c3 .ic,.c3 .cnt{background:var(--green-soft);color:var(--green)}
.list{flex:1;overflow:auto;padding:2px 6px 8px 2px;scrollbar-width:thin}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 16px;margin-bottom:12px;cursor:pointer;box-shadow:var(--shadow);transition:.15s;position:relative}
.card:hover{box-shadow:var(--shadow-h);transform:translateY(-1px)}.card.sel{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-soft)}
.c1 .card{border-left:4px solid var(--amber)}.c2 .card{border-left:4px solid var(--blue)}.c3 .card{border-left:4px solid var(--green);cursor:default;opacity:.92}.c3 .card:hover{transform:none}
.top{display:flex;align-items:center;gap:10px}.av{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:600;font-size:13px;flex:none}
.who{font-weight:600}.where{color:var(--muted);font-size:12px}.when{margin-left:auto;color:var(--faint);font-size:12px;white-space:nowrap}
.no{font-size:11.5px;color:var(--faint);font-family:ui-monospace,Menlo,monospace}
.txt{margin:10px 0 0;white-space:pre-wrap;word-break:break-word;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.draft{margin-top:10px;background:var(--blue-soft);border-radius:10px;padding:8px 10px;white-space:pre-wrap;word-break:break-word;font-size:13.5px}
.draft::before{content:"草稿";display:block;font-size:11px;color:var(--blue);font-weight:600;margin-bottom:2px}
.why{margin-top:8px;color:var(--muted);font-size:12.5px;display:flex;gap:6px}.why::before{content:"💡"}
.tag{display:inline-block;border-radius:99px;padding:0 8px;font-size:11.5px;font-weight:600}.t-red{background:var(--red-soft);color:var(--red)}.t-ok{background:var(--green-soft);color:var(--green)}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.empty{color:var(--faint);text-align:center;padding:48px 10px}.empty .big{font-size:30px;display:block;margin-bottom:6px}
.mask{position:fixed;inset:0;background:rgba(10,18,35,.25);opacity:0;pointer-events:none;transition:.2s;z-index:9}.mask.on{opacity:1;pointer-events:auto}
aside{position:fixed;top:0;right:0;height:100%;width:min(560px,100%);background:var(--surface);box-shadow:none;transform:translateX(100%);transition:transform .22s ease;display:flex;flex-direction:column;z-index:10}
aside.on{transform:none;box-shadow:-12px 0 40px rgba(10,20,45,.18)}.ph{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}.ph .t{font-weight:700}.ph .s{color:var(--muted);font-size:12.5px}
.pb{flex:1;overflow:auto;padding:16px 20px;background:var(--soft)}.pf{border-top:1px solid var(--border);padding:14px 20px;background:var(--surface)}
.bub{display:flex;gap:10px;margin-bottom:14px}.bub .av{width:28px;height:28px;font-size:12px}.bub .b{background:var(--surface);border:1px solid var(--border);border-radius:4px 12px 12px 12px;padding:8px 12px;max-width:100%}
.bub .w{font-size:12px;color:var(--muted);margin-bottom:2px}.bub .w span{color:var(--faint);margin-left:6px}.bub .tx{white-space:pre-wrap;word-break:break-word}
.bub.hl .b{border-color:var(--amber);box-shadow:0 0 0 3px var(--amber-soft)}
.note{background:var(--surface);border:1px dashed var(--border);border-radius:10px;padding:10px 12px;margin-top:6px;font-size:13px}.note h4{margin:0 0 4px;font-size:12px;color:var(--muted)}
.qa{border-left:3px solid var(--blue);padding:2px 0 2px 10px;margin:8px 0;font-size:13px}
textarea,input.q{width:100%;border:1px solid var(--border);border-radius:10px;padding:10px 12px;font:inherit;background:var(--soft);color:var(--text);outline:none;transition:.15s}
textarea{min-height:96px;resize:vertical}textarea:focus,input.q:focus{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-soft);background:var(--surface)}
.askrow{display:flex;gap:8px;margin-top:10px}.askrow input{flex:1}.lbl{font-size:12px;color:var(--muted);margin:0 0 6px}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(20px);opacity:0;background:#1b2638;color:#fff;padding:10px 16px;border-radius:10px;box-shadow:var(--shadow-h);transition:.2s;z-index:20;font-size:13px}.toast.on{opacity:1;transform:translateX(-50%)}
@media (max-width:980px){main{grid-template-columns:1fr;overflow:auto}.col{min-height:auto}.list{overflow:visible}header{flex-wrap:wrap}}
</style></head><body>
<header><div class="brand"><span class="logo">群</span>操作台</div><div class="chips" id="stat"><span class="chip">连接中…</span></div><span class="sp"></span>
<button class="btn sm" id="notif" style="display:none">🔔 开启桌面通知</button><span class="ver" id="ver"></span></header>
<main>
<section class="col c1"><div class="ch"><span class="ic">✋</span><div><h2>要你判断</h2><div class="sub">拿不准是不是归你、要不要接</div></div><span class="cnt" id="n1">0</span></div><div class="list" id="judge"></div></section>
<section class="col c2"><div class="ch"><span class="ic">✉️</span><div><h2>草稿待发</h2><div class="sub">AI 写好了，你点头才发</div></div><span class="cnt" id="n2">0</span></div><div class="list" id="send"></div></section>
<section class="col c3"><div class="ch"><span class="ic">✓</span><div><h2>已处理</h2><div class="sub">页面、提醒群、原会话里处理的都算</div></div><span class="cnt" id="n3">0</span></div><div class="list" id="done"></div></section>
</main>
<div class="mask" id="mask" onclick="closeP()"></div>
<aside id="panel"><div class="ph"><span class="av" id="pav"></span><div><div class="t" id="ptitle"></div><div class="s" id="psub"></div></div><span class="sp"></span><button class="btn sm" onclick="closeP()">关闭</button></div><div class="pb" id="pbody"></div><div class="pf" id="pfoot"></div></aside>
<div class="toast" id="toast"></div>
<script>
const K=new URLSearchParams(location.search).get('k')||'';let S=null,sel=null,seen=new Set(),first=true;const notes={};
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const COLORS=['#3360e6','#1c8a4a','#c27a00','#8a4fd8','#d23b3b','#0f8f9e','#c2477d','#5b6b86'];
function av(n){n=String(n||'?');let h=0;for(const ch of n)h=(h*31+ch.charCodeAt(0))>>>0;return `<span class="av" style="background:${COLORS[h%COLORS.length]}">${esc(n.replace(/[-_ ].*/,'').slice(-2))}</span>`}
function toast(t){const x=$('toast');x.textContent=t;x.classList.add('on');clearTimeout(x._t);x._t=setTimeout(()=>x.classList.remove('on'),2600)}
async function api(p,b){const r=await fetch(p+(p.includes('?')?'&':'?')+'k='+encodeURIComponent(K),b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}:{cache:'no-store'});return r.json()}
function head(c){return `<div class="top">${av(c.who)}<div><div class="who">${esc(c.who)}</div><div class="where">${esc(c.group||'')} <span class="no">${c.no}</span></div></div><span class="when">${c.overdue?'<span class="tag t-red">超时</span> ':''}${esc(c.at)}</span></div>`}
function card(c,kind){return `<div class="card${sel===c.no?' sel':''}" onclick="openP('${c.no}')">${head(c)}<div class="txt">${esc(c.text)}</div>
${kind==='send'?`<div class="draft">${esc(c.draft)}</div>`:(c.reason?`<div class="why">${esc(c.reason)}</div>`:'')}
<div class="btns" onclick="event.stopPropagation()">${kind==='send'?`<button class="btn p" onclick="go('${c.no}','send')">发送</button><button class="btn" onclick="openP('${c.no}')">修改</button><button class="btn d" onclick="go('${c.no}','drop')">不发</button>`:
`<button class="btn p" onclick="openP('${c.no}')">回复</button><button class="btn" onclick="go('${c.no}','not_mine')">不归我</button>`}<button class="btn" onclick="openP('${c.no}',1)">问 AI</button></div></div>`}
function empty(t){return `<div class="empty"><span class="big">☕</span>${t}</div>`}
function render(){const s=S,ok=/^(\d+)\/\1$/.test(s.listeners)&&s.listeners!=='0/0';
$('stat').innerHTML=`<span class="chip duty d-${s.duty}" style="cursor:pointer" onclick="openH()" title="点开按群看最近消息；最近收到消息 ${esc(s.last_event_t||'无')}；${esc(s.last_event||'')}"><span class="dot"></span><b>${esc(s.duty_text)}</b> · 监听 ${s.listeners}${s.last_event_t?' · 最近 '+s.last_event_t:''}</span><span class="chip">要你判断 <b>${s.judge.length}</b></span><span class="chip">草稿待发 <b>${s.send.length}</b></span><span class="chip">今天已处理 <b>${s.today_done}</b></span><span class="chip">${esc(s.me)} · ${s.time}</span>`;$('ver').textContent=s.version;
$('judge').innerHTML=s.judge.map(c=>card(c,'judge')).join('')||empty('没有要你判断的事');$('send').innerHTML=s.send.map(c=>card(c,'send')).join('')||empty('没有待发的草稿');
$('done').innerHTML=s.done.map(d=>`<div class="card">${head({who:d.who,group:'',no:d.no,at:d.done})}<div class="txt">${esc(d.what)}</div><div class="why" style="--x:0">${esc(d.why)}</div></div>`).join('')||empty('今天还没有处理记录');
$('n1').textContent=s.judge.length;$('n2').textContent=s.send.length;$('n3').textContent=s.done.length;
const open=[...s.judge,...s.send],n=open.length;document.title=(n?'('+n+') ':'')+'群消息助手 · 操作台';const now=new Set(open.map(c=>c.no));
open.forEach(c=>{if(!seen.has(c.no)&&!first&&window.Notification&&Notification.permission==='granted'){const x=new Notification(`${c.draft?'草稿待发':'要你判断'} · ${c.who}`,{body:c.text.slice(0,90),tag:c.no});x.onclick=()=>{window.focus();openP(c.no)};notes[c.no]=x}});
Object.keys(notes).forEach(no=>{if(!now.has(no)){notes[no].close();delete notes[no]}});seen=now;first=false;
if(sel&&!now.has(sel)){closeP();toast(sel+' 已处理')}else if(sel)fillFoot()}
async function tick(){try{S=await api('/api/state');render()}catch(e){$('stat').innerHTML='<span class="chip"><span class="dot bad"></span>连不上助手（助手停了？）</span>'}}
function cur(){return [...S.judge,...S.send].find(c=>c.no===sel)}
async function openP(no,ask){sel=no;const c=cur();if(!c)return;$('pav').outerHTML=av(c.who).replace('class="av"','class="av" id="pav"');$('ptitle').textContent=c.who;$('psub').textContent=`${c.group||''} · ${no} · ${c.at}`;
$('panel').classList.add('on');$('mask').classList.add('on');render();$('pbody').innerHTML='<div class="empty">正在读会话…</div>';fillFoot(ask);
const t=await api('/api/thread?no='+encodeURIComponent(no));if(sel!==no)return;
$('pbody').innerHTML=t.map(m=>`<div class="bub${m.text&&c.text&&c.text.startsWith(m.text.slice(0,30))?' hl':''}">${av(m.who)}<div class="b"><div class="w">${esc(m.who)}<span>${esc((m.time||'').slice(5,16))}</span></div><div class="tx">${esc(m.text)}</div></div></div>`).join('')+
(c.reason?`<div class="note"><h4>AI 的判断依据</h4>${esc(c.reason)}</div>`:'')+((c.qa||[]).length?`<div class="note"><h4>问过 AI</h4>${c.qa.map(q=>`<div class="qa"><b>问</b> ${esc(q['问'])}<br><b>答</b> ${esc(q['答'])}</div>`).join('')}</div>`:'');$('pbody').scrollTop=1e9}
function fillFoot(ask){const c=cur();if(!c)return;const f=$('pfoot');if(f.contains(document.activeElement))return;
f.innerHTML=`<div class="lbl">${c.draft?'草稿（可以直接改）':'你的回复'}</div><textarea id="ta" placeholder="${c.draft?'':'写一段回复，点发送前还会再确认一次'}">${esc(c.draft)}</textarea>
<div class="btns">${c.can_send?`<button class="btn p" onclick="go('${c.no}','${c.draft?'edit_send':'reply_new'}',$('ta').value)">发送到原会话</button>`:'<span class="where">这个群设成了「只看」，请在钉钉里自己回</span>'}
<button class="btn" onclick="go('${c.no}','stash',$('ta').value)">暂存不发</button>${c.draft?`<button class="btn d" onclick="go('${c.no}','drop')">不发</button>`:`<button class="btn" onclick="go('${c.no}','not_mine')">不归我</button>`}</div>
<div class="askrow"><input class="q" id="q" placeholder="问 AI：依据是什么？帮我改得客气点…" onkeydown="if(event.key==='Enter')go('${c.no}','ask',this.value)"><button class="btn" onclick="go('${c.no}','ask',$('q').value)">问 AI</button></div>`;if(ask)setTimeout(()=>$('q').focus(),60)}
// 顶栏「值守中」点开：按群看最近消息（复用右侧面板）
let hsel=null;async function openH(cid){sel=null;const gs=await api('/api/groups');if(!gs.length)return toast('没有监听的群');hsel=cid||hsel||gs[0].cid;
$('pav').outerHTML='<span class="av" id="pav" style="background:var(--green)">群</span>';$('ptitle').textContent='最近消息';$('psub').textContent='按群看，每个群最近 30 条';
$('panel').classList.add('on');$('mask').classList.add('on');
const tabs='<div class="btns" style="margin:0 0 14px;position:sticky;top:-16px;background:var(--soft);padding:8px 0;z-index:1">'+gs.map(g=>`<button class="btn sm${g.cid===hsel?' p':''}" onclick="openH('${g.cid}')">${esc(g.name)}</button>`).join('')+'</div>';
$('pfoot').innerHTML='<div class="where">只读：这里只看消息，要回复请在卡片或钉钉里处理</div>';$('pbody').innerHTML=tabs+'<div class="empty">正在读…</div>';const t=await api('/api/history?cid='+encodeURIComponent(hsel));if(!$('panel').classList.contains('on'))return;
$('pbody').innerHTML=tabs+t.map(m=>`<div class="bub">${av(m.who)}<div class="b"><div class="w">${esc(m.who)}<span>${esc((m.time||'').slice(5,16))}</span></div><div class="tx">${esc(m.text)}</div></div></div>`).join('')||'<div class="empty">没有消息</div>';$('pbody').scrollTop=1e9}
function closeP(){sel=null;hsel=hsel;$('panel').classList.remove('on');$('mask').classList.remove('on');render()}
async function go(no,action,text){if(['send','edit_send','reply_new'].includes(action)&&!confirm('确认发到原会话？'))return;
const r=await api('/api/act',{no,action,text:text||''});toast(r.msg||'好了');if(action==='ask'&&$('q'))$('q').value='';document.activeElement&&document.activeElement.blur();tick()}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeP()});
if(window.Notification&&Notification.permission==='default'){$('notif').style.display='';$('notif').onclick=()=>Notification.requestPermission().then(()=>$('notif').style.display='none')}
// 有新事件时助手会用浏览器打开带 focus 的链接（弹到最前面）；新页面打开后通知旧页面关掉，始终只留一个操作台
const FOCUS=new URLSearchParams(location.search).get('focus');let alive=true;
try{const bc=new BroadcastChannel('qa-console');const me=Date.now()+Math.random();bc.postMessage({t:'new',me});
bc.onmessage=m=>{if(m.data&&m.data.t==='new'&&m.data.me!==me){alive=false;window.close();setTimeout(()=>{document.body.innerHTML='<div class="empty" style="margin-top:20vh"><span class="big">↗</span>操作台已在新标签页打开，这一页可以关掉了。</div>'},300)}}}catch(e){}
tick().then(()=>{if(FOCUS)openP(FOCUS);if(FOCUS)history.replaceState(null,'',location.pathname+'?k='+encodeURIComponent(K))});setInterval(()=>{if(alive)tick()},3000);
</script></body></html>"""
