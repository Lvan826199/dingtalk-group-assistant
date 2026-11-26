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
import uuid
import urllib.request
import urllib.parse
import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

A = {}                     # agent.py 的全局变量（start 时传进来）
TOKEN = ""
CLOSED_N = 20              # 「已处理」列只显示最近 20 条（11-19 梦无矶：3 天内为主，但始终保证 20 条）
POP = {"t": 0}             # 上次把操作台弹到前面的时间
GROUP_CANDIDATES = {}      # 只接受本次进程真实搜索出的群；不信任浏览器提交的群名
GROUP_SEARCH_LOCK = threading.Lock()
ACTION_LOCKS = {}
ACTION_LOCKS_GUARD = threading.Lock()
HELP_URL = "https://lvan826199.github.io/dingtalk-group-assistant//help.html"   # 顶栏「帮助」打开的使用帮助；打包 / 预览脚本会把 https://lvan826199.github.io/dingtalk-group-assistant/ 换成实际站点地址


def mirror_notification(value, config_dir=None):
    """供独立机器人发送脚本调用：只同步网页，离线落盘，不再次发送钉钉。"""
    from pathlib import Path
    from tempfile import NamedTemporaryFile
    root = Path(config_dir) if config_dir else Path.home() / ".qa-agent"
    payload = {**value, "notification_id": value.get("notification_id") or uuid.uuid4().hex}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        token = (root / "console_token").read_text(encoding="utf-8").strip()
        port = int(cfg.get("console_port") or 8765)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/notifications", data=data,
                                     headers={"Content-Type": "application/json", "X-Key": token})
        with urllib.request.urlopen(req, timeout=3) as response:
            if json.loads(response.read()).get("ok"):
                return True
    except (OSError, ValueError):
        pass
    outbox = root / "notification-outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=outbox, prefix=".", delete=False) as f:
        f.write(data)
        temp = f.name
    os.replace(temp, outbox / (uuid.uuid4().hex + ".json"))
    return False


META_LABELS = ("群", "任务", "时间", "消息时间", "处理时间")
QUOTE_LABELS = "原消息|草稿|新草稿|建议回复|要发的内容|你的问题|答复|已回复"
INLINE_LABELS = "结论|当前状态|状态|进度|已核实|已完成|待处理|下一步|需要你决定|需要你做|要你做|原因|错误|背景|依据|操作|验收完成"


def notification_body(text):
    """机器人卡片排版（3.4.5 改版：一眼看懂）。只整理格式，不删事实；代码、路径和 Markdown 链接保持原样。
    - 群 / 任务 / 时间 收成卡片底部一行灰字，任务和正文重复时不再写一遍；
    - 原消息、草稿、你的问题等放进引用块，一眼分清谁说的、要发什么；
    - 结论、状态、原因等写成「**标签：** 内容」一行；「回：…」「回「…」」类操作提示前加 👉。
    再排一次结果不变（幂等）。"""
    parts = re.split(r"(```[\s\S]*?```|`[^`\n]+`|\[[^\]\n]+\]\([^\s)]+\))", str(text or ""))
    meta = []
    for index in range(0, len(parts), 2):
        value = parts[index].replace("\\r\\n", "\n").replace("\\n", "\n")
        value = re.sub(r"\r\n?", "\n", value)
        lines = []
        pending_quote = False
        for line in value.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(("> ", "<font", "👉", "📍", "🕒", "🏷")) or re.fullmatch(r"\*\*[^*\n]{1,20}\*\*", line):
                lines.append(line); pending_quote = line.startswith("**") and line.strip("*") in QUOTE_LABELS.split("|"); continue
            m = re.match(r"^(" + "|".join(META_LABELS) + r")[：:]\s*(.*)$", line)
            if m and index == 0 and len(m.group(2)) <= 120:
                meta.append((m.group(1), m.group(2))); continue
            if re.fullmatch(r"【[^\n]{1,100}】", line):
                lines.append("**" + line[1:-1] + "**"); continue
            m = re.match(r"^(" + QUOTE_LABELS + r")[：:]\s*(.*)$", line, re.S)
            if m:
                lines.append(f"**{m.group(1)}**")
                if m.group(2):
                    who = re.match(r"^([^：:\s>*]{1,20})[：:](.+)$", m.group(2), re.S) if m.group(1) == "原消息" else None
                    lines.append(_quote(f"**{who.group(1)}**：{who.group(2).strip()}" if who else m.group(2)))
                pending_quote = not m.group(2); continue
            m = re.match(r"^(" + INLINE_LABELS + r")[：:]\s*(.*)$", line, re.S)
            if m:
                lines.append(f"**{m.group(1)}：** {m.group(2)}".rstrip()); pending_quote = False; continue
            if re.match(r"^回[：:「]", line):
                lines.append("👉 " + line); continue
            if pending_quote:
                lines.append(_quote(line)); continue
            # 很长的自然段按完整中文句子分段，保留数字、URL和原有顺序。
            if len(line) > 180 and not re.match(r"^(?:[-*>#]|\d+[.)、）])", line):
                line = re.sub(r"([。；])(?=[^\n])", r"\1\n\n", line)
            lines.append(line)
        parts[index] = "\n\n".join(lines)
        # 保护片段前后的空白不能丢，否则代码/链接会粘到相邻文本。
        if value.startswith("\n"):
            parts[index] = "\n\n" + parts[index]
        if value.endswith("\n"):
            parts[index] += "\n\n"
        if value.startswith((" ", "\t")):
            parts[index] = " " + parts[index]
        if value.endswith((" ", "\t")):
            parts[index] += " "
    body = "".join(parts).strip()
    if meta:
        # 钉钉机器人不认 <font> 颜色标签，整行会被吞掉（11-25 本人：没带时间）：改成正文第一行、带图标的纯文本
        d = dict(meta)
        line = "  ".join(x for x in (
            ("📍 " + d["群"]) if d.get("群") else "",
            ("🕒 " + (d.get("时间") or d.get("消息时间") or d.get("处理时间"))) if (d.get("时间") or d.get("消息时间") or d.get("处理时间")) else "",
            ("🏷 " + d["任务"]) if d.get("任务") and d["任务"][:20] not in body else "") if x)
        if line:
            body = line + ("\n\n" + body if body else "")
    return body


def _quote(text):
    """引用块：每行都带 >；很长的按完整中文句子分段，不截断、不删字。"""
    out = []
    for x in text.strip().splitlines():
        x = x.strip()
        if not x:
            continue
        if len(x) > 180:
            out.extend(y for y in re.split(r"(?<=[。；])(?=[^\n])", x) if y)
        else:
            out.append(x)
    return "\n\n".join("> " + x for x in out)


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


def _closed_log(no, why, x, reply_event=None):
    rec = {"no": no, "why": why, "who": x.get("who"), "what": x.get("what"), "kind": x.get("kind"), "at": x.get("at"),
           "done": time.strftime("%m-%d %H:%M"), "ts": time.time(), "cid": x.get("cid"),
           "event": x.get("event"), "reason": x.get("reason", ""), "qa": x.get("qa", []),
           "task_key": x.get("task_key", ""), "related_events": x.get("related_events", []),
           "reply": reply_event or {}}       # 点开「已处理」看详情用
    with A["LOCK"], open(_p("logs", "closed.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _wrap_open_close():
    """所有「处理完」都会经过 open_close（提醒群指令、页面、本人在原会话亲自回复），在这里顺手记一笔给「已处理」列。"""
    orig = A["open_close"]

    def open_close(no, why, reply_event=None):
        x = A["_open_load"]().get(no)
        orig(no, why, reply_event)
        if x:
            try:
                _closed_log(no, why, _message_context(no, x)["item"], reply_event)
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


def search_monitor_groups(query):
    query = str(query or "").strip()
    if not query or len(query) > 100:
        raise ValueError("请填写群名关键词，最多100字")
    r = A["run"]([A["DWS"], "chat", "+chat-search", "--query", query, "--page-all", "--page-limit", "5", "--format", "json"], timeout=60)
    try:
        data = json.loads(r.stdout)
    except (ValueError, AttributeError):
        raise ValueError("群搜索没有返回有效结果，请检查钉钉登录和网络")
    if r.returncode or not isinstance(data, dict) or data.get("failures") or not isinstance(data.get("chats"), list):
        raise ValueError("群搜索失败，请检查钉钉登录、权限和网络")
    matches = {}
    for g in data["chats"]:
        cid, name = g.get("openConversationId"), g.get("title") or g.get("name")
        if not cid or not name or cid == A["CFG"].get("notify_group"):
            continue
        matches[cid] = {"cid": cid, "name": name, "members": g.get("memberCount"), "existing": cid in _groups()}
    with GROUP_SEARCH_LOCK:
        now = time.time()
        for cid in list(GROUP_CANDIDATES):
            if now - GROUP_CANDIDATES[cid]["at"] > 600:
                GROUP_CANDIDATES.pop(cid)
        GROUP_CANDIDATES.update({cid: {**g, "at": now} for cid, g in matches.items()})
    complete = data.get("complete") is True and data.get("hasMore") is False
    return {"matches": list(matches.values()), "complete": complete,
            "msg": "" if complete else "仅列出部分结果；找不到时请使用更完整的群名搜索"}


def _records(path):
    try:
        with open(path, encoding="utf-8") as f:
            rows = []
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
            return rows
    except OSError:
        return []


def _task_history():
    try:
        with open(A.get("COMMITMENTS_PATH") or _p("logs", "commitments.json"), encoding="utf-8") as f:
            commits = json.load(f)
    except (OSError, ValueError):
        commits = {}
    return _records(A["AUDIT"]), _records(_p("logs", "closed.jsonl")), commits


def _message_context(no, item, history=None):
    """按原消息和会话关联历史；回复与执行进度分别返回，不能凭短编号串到别的消息。"""
    audits, closed, commits = history if history is not None else _task_history()
    x = dict(item)
    ev = dict(x.get("event") or {})
    mid, cid = ev.get("message_id"), x.get("cid") or ev.get("conversation_id")
    previous = [r for r in closed if r.get("no") == no and r.get("cid") == cid
                and mid and (r.get("event") or {}).get("message_id") == mid]
    audit = next((r for r in reversed(audits) if r.get("编号") == no and mid
                  and (r.get("原消息") or {}).get("消息ID") == mid
                  and (not r.get("群") or r.get("群") == _groups().get(cid))), {})
    source = (previous[0].get("event") or {}) if previous else {}
    if source:
        ev.update(source)
    original = audit.get("原消息") or {}
    if original.get("内容"):
        ev["content"] = original["内容"]
        ev["sender"] = original.get("谁") or ev.get("sender")
    x.update(event=ev, what=str(ev.get("content") or x.get("what") or "")[:60])
    commitment = commits.get(x.get("task_key")) or {}
    if mid and (not commitment or mid not in commitment.get("original_message_ids", [])):
        commitment = next((c for c in commits.values() if mid in c.get("original_message_ids", [])
                           and cid in c.get("conversation_ids", [])), {})
    if commitment:
        x["task_key"] = commitment.get("task_key", x.get("task_key", ""))
    reply = next((r.get("reply") for r in reversed(previous) if (r.get("reply") or {}).get("content")), {}) or {}
    sent = audit.get("发出内容") or reply.get("content", "")
    return {"item": x, "audit": audit, "sent": sent,
            "sent_at": audit.get("发出时间") or reply.get("create_time", ""),
            "reply_status": "已回复" if sent else "尚无回复记录", "commitment": commitment}


def state():
    items, drafts, groups, now = A["_open_load"](), _drafts(), _groups(), time.time()
    task_history = _task_history()
    remind = max(1, int(A["CFG"].get("remind_after_minutes") or 120)) * 60
    judge, send = [], []
    for no, x in sorted(items.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True):
        if x.get("kind") == "execution":
            continue  # 本人明确的执行指令只在执行区显示，不再当作等待本人决定的消息
        context = _message_context(no, x, task_history)
        x = context["item"]
        d = drafts.get(no) or {}
        ev = x.get("event") or {}
        card = {"no": no, "who": x.get("who"), "group": groups.get(x.get("cid"), "私聊" if x.get("cid") and x.get("cid") not in groups else ""),
                "text": str(ev.get("content") or x.get("what") or "")[:600], "at": str(ev.get("create_time") or "")[5:16] or x.get("at"), "reason": x.get("reason") or d.get("reason") or x.get("why", ""),
                "draft": d.get("draft", ""), "qa": x.get("qa", [])[-5:], "overdue": now - x.get("ts", now) > remind,
                "can_send": A["can_reply"](x.get("cid")), "sent": context["sent"],
                "sent_at": context["sent_at"], "reply_status": context["reply_status"],
                "commitment": context["commitment"], "task_key": x.get("task_key", "")}
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
    commitments = {}
    cpath = A.get("COMMITMENTS_PATH") or _p("logs", "commitments.json")
    if os.path.exists(cpath):
        try:
            commitments = json.load(open(cpath, encoding="utf-8"))
        except (OSError, ValueError):
            commitments = {}
    sent = {}                                   # 发出留痕：编号 → 实际发出的内容（「已处理」里区分「已发送」）
    if os.path.exists(A["AUDIT"]):
        for line in open(A["AUDIT"], encoding="utf-8").readlines()[-500:]:
            try:
                r = json.loads(line); sent[r.get("编号")] = r.get("发出内容", "")
            except ValueError:
                pass
    for d in done:
        context = _message_context(d.get("no"), d, task_history)
        d["sent"] = context["sent"]
        d["result"] = "已发送" if d["sent"] else ("不发" if "不发" in d.get("why", "") else ("不归我" if re.search(r"不归[你我]", d.get("why", "")) else ("你已回复" if "回复" in d.get("why", "") else "已处理")))
        c = context["commitment"]
        d["commitment_status"] = c.get("status", "")
        d["commitment_text"] = c.get("commitment_text", "")
    alive = sum(1 for v in A["LISTENERS"].values() if v.get("alive") and v.get("ready"))
    beat = A.get("LAST_EVENT", {}).get("t") or 0
    fails = {k: v for k, v in A.get("FAILS", {}).items() if v and v != 0}
    duty = ("ok", "值守中") if alive and alive == len(A["LISTENERS"]) and not fails else (("warn", "部分监听断开") if alive else ("bad", "没在监听"))
    if not A["in_window"]():
        duty = ("off", "值守时间外")
    return {"version": A["VERSION"], "me": A["CFG"].get("my_name"), "listeners": f"{alive}/{len(A['LISTENERS'])}",
            "duty": duty[0], "duty_text": duty[1], "last_event_t": time.strftime("%H:%M", time.localtime(beat)) if beat else "",
            "last_event": A["LAST_EVENT"].get("summary", ""), "judge": judge, "send": send, "done": done[:CLOSED_N],
            "today_done": sum(1 for x in done if x.get("done", "").startswith(time.strftime("%m-%d"))),
            "queue": A["Q"].qsize() + A["READY"].qsize(), "processing": A["BUSY"]["n"],
            "owner": A["owner_snapshot"](),
            "notifications": [{**x, "display_text": notification_body(x.get("text", ""))}
                              for x in A["notification_snapshot"]()],
            "time": time.strftime("%H:%M:%S")}


def chat(limit=80):
    """调试群对话（11-23 用户要求）：你在钉钉调试群说的话 + 机器人的回复 / 通知，按时间排成一条对话，和钉钉里看到的一致。"""
    rows = []
    for r in (A["owner_snapshot"]().get("recent") or []):
        rows.append({"me": True, "t": r.get("received", 0), "text": r.get("question", ""), "stage": r.get("stage", ""),
                     "error": r.get("error", "")})
        if r.get("answer"):                     # 机器人对这条的答复（存在本人消息记录里），作为机器人一条接在后面
            rows.append({"me": False, "t": r.get("finished") or r.get("updated") or r.get("received", 0) + 1, "title": "答复", "text": r["answer"], "delivered": None, "_ans": r.get("message_id")})
    for n in A["notification_snapshot"](limit):
        try:
            t = time.mktime(time.strptime(str(n.get("time", ""))[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            t = n.get("recorded", 0)
        rows.append({"me": False, "t": t, "title": n.get("title", ""), "text": n.get("text", ""), "delivered": n.get("delivered")})
    answered = {r["text"].strip() for r in rows if r.get("_ans")}
    rows = [r for r in rows if r.get("_ans") or r["me"] or r["text"].strip() not in answered]   # 同一条答复在通知里也有一份时只留一条
    rows.sort(key=lambda x: x["t"])
    for r in rows:
        r["time"] = time.strftime("%m-%d %H:%M", time.localtime(r["t"])) if r["t"] else ""
    return rows[-limit:]


def say(text):
    """在操作台输入框发消息：以本人身份发到钉钉调试群，再由监听收到、按调试群里一样的流程处理——钉钉和网页看到的是同一段对话。"""
    text = (text or "").strip()
    if not text or not A["CFG"].get("notify_group"):
        return "内容为空或没配提醒群"
    r = A["run"]([A["DWS"], "chat", "+messages-send", "--group", A["CFG"]["notify_group"], "--text", text, "--yes", "--format", "json"], timeout=60)
    return "已发到调试群" if re.search(r'"(success|ok)":\s*true', getattr(r, "stdout", "") or "") else "发送失败：" + (getattr(r, "stderr", "") or getattr(r, "stdout", ""))[:120]


def thread(no, x=None):
    """会话面板：这件事所在会话最近 20 条消息（群用 dws 拉；私聊只显示原消息）。"""
    x = x or A["_open_load"]().get(no) or {}
    x = _message_context(no, x)["item"]
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
    rows = sorted(rows, key=lambda m: m["time"])
    source = x.get("event") or {}
    source_id = source.get("message_id") or source.get("messageId")
    if source_id and not any(m.get("mid") == source_id for m in rows):
        rows.insert(0, {"who": source.get("sender"), "time": source.get("create_time", ""),
                        "text": str(source.get("content") or ""), "mid": source_id, "anchor": True})
    elif source_id:
        for m in rows:
            if m.get("mid") == source_id:
                m["anchor"] = True
    return rows


NAMES = {}                # cid → 钉钉里的群名（按需查一次，缓存）
HISTORY_N = 30            # 历史消息：每个群看最近 30 条（只为页面上翻看方便，全量去钉钉看）


def ding_name(cid, fallback):
    """群名按钉钉里的真实名字显示（11-19），查不到就用配置里的叫法。"""
    if cid not in NAMES:
        r = A["run"]([A["DWS"], "chat", "+conversation-info", "--group", cid, "--format", "json"], timeout=30)
        m = re.search(r'"title"\s*:\s*"([^"]+)"', getattr(r, "stdout", "") or "")
        NAMES[cid] = m.group(1) if m else ""
    return NAMES[cid] or fallback


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


def done_detail(no):
    """点开「已处理」：只读详情——原会话、AI 依据、问过 AI 的、最后结果（发出的原文、确认时间和方式）。"""
    rec = None
    path = _p("logs", "closed.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("no") == no:
                rec = r
    if not rec:
        return {}
    context = _message_context(no, rec)
    rec = context["item"]
    audit = {}
    if os.path.exists(A["AUDIT"]):
        for line in open(A["AUDIT"], encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("编号") == no:
                audit = r
    reply = rec.get("reply") or {}
    th = thread(no, {"cid": rec.get("cid"), "event": rec.get("event") or {"sender": rec.get("who"), "content": rec.get("what")}})
    if reply.get("content"):
        th.append({"who": reply.get("sender") or A["CFG"].get("my_name"), "time": reply.get("create_time", ""),
                   "text": str(reply.get("content") or ""), "mid": reply.get("message_id"), "reply": True})
    commitment = context["commitment"]
    cpath = A.get("COMMITMENTS_PATH") or _p("logs", "commitments.json")
    if os.path.exists(cpath):
        try:
            commitment = json.load(open(cpath, encoding="utf-8")).get(rec.get("task_key"), {}) or commitment
        except (OSError, ValueError):
            commitment = {}
    return {"no": no, "who": rec.get("who"), "group": _groups().get(rec.get("cid"), "私聊" if rec.get("cid") else ""), "at": rec.get("at"),
            "done": rec.get("done"), "why": rec.get("why"), "reason": rec.get("reason") or audit.get("AI 依据", ""),
            "qa": rec.get("qa") or audit.get("确认前问过 AI", []), "text": str((rec.get("event") or {}).get("content") or rec.get("what") or ""),
            "sent": context["sent"], "sent_at": context["sent_at"], "confirm": ("改过草稿后确认发送" if "改成" in audit.get("确认方式", "") else "命令行确认发送" if "命令行" in audit.get("确认方式", "")
                        else "直接确认发送" if audit else "") + (f"（{audit.get('确认人')}）" if audit.get("确认人") else ""),
            "task_key": rec.get("task_key", ""), "related_events": rec.get("related_events", []), "commitment": commitment,
            "thread": th}


def act(no, action, text=""):
    if not isinstance(no, str):
        return "编号不对"
    with ACTION_LOCKS_GUARD:
        lock = ACTION_LOCKS.setdefault(no, threading.Lock())
    if not lock.acquire(blocking=False):
        return "这条消息正在处理，请勿重复操作"
    try:
        return _act(no, action, text)
    finally:
        lock.release()


def _act(no, action, text=""):
    """页面按钮 → 提醒群同款指令，交给 agent.command（发出、留痕、提醒群「已处理」都走原逻辑）。"""
    if not re.fullmatch(r"#(?:\d{4}-\d{1,3}|[A-Za-z0-9]{3,8})", no or ""):
        return "编号不对"
    if no not in A["_open_load"]() and not A["draft_by_no"](no)[0]:
        return "这条消息已处理，请查看已处理记录"
    text = (text or "").strip()
    if action in ("manual_done", "not_mine") and not text:
        return "请填写处理说明" if action == "manual_done" else "请填写不归我的原因"
    if action == "reply_new":                       # 要你判断的事，自己写一段回复：先挂成草稿再按确认发出
        if not text:
            return "回复内容是空的"
        A["stash"](no, text)
        action = "send"
    cmd = {"send": f"{no} 可以发送", "drop": f"{no} 不发", "edit_send": f"{no} 改成：{text}", "stash": f"{no} 暂存：{text}",
           "ask": f"{no} 问：{text}", "not_mine": f"{no} 不归我：{text}",
           "manual_done": f"{no} 手动已处理：{text}"}.get(action)
    if not cmd or (action in ("edit_send", "stash", "ask") and not text):
        return "操作不对或内容为空"
    A["log"]("操作台", cmd[:80])
    A["command"]({"content": cmd, "sender": A["CFG"].get("my_name"), "conversation_id": A["CFG"].get("notify_group"), "message_id": f"console-{time.time_ns()}"})
    if action in ("send", "edit_send"):
        if A["draft_by_no"](no)[0] or no in A["_open_load"]():
            return "尚未确认发送成功，草稿已保留；请查看失败通知后再处理"
    return "ok"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return secrets.compare_digest((q.get("k") or [""])[0], TOKEN) or secrets.compare_digest(self.headers.get("X-Key", ""), TOKEN)

    def _local(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

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
        if u.path == "/api/reports":
            rows = [n for n in A["notification_snapshot"](5000) if re.search(r"每日汇报|日报|每日总结|今日总结", str(n.get("title") or ""))]
            return self._send(200, json.dumps([{"time": str(n.get("time", ""))[:16].replace("T", " "), "title": n.get("title"), "text": n.get("text")} for n in rows[:60]], ensure_ascii=False))
        if u.path == "/api/chat":
            return self._send(200, json.dumps(chat(), ensure_ascii=False))
        if u.path == "/api/state":
            return self._send(200, json.dumps(state(), ensure_ascii=False))
        if u.path == "/api/groups":
            return self._send(200, json.dumps([{"cid": c, "name": ding_name(c, n)} for c, n in _groups().items()], ensure_ascii=False))
        if u.path == "/api/monitor":
            return self._send(200, json.dumps(A["monitor_settings"](), ensure_ascii=False))
        if u.path == "/api/monitor/search":
            try:
                result = search_monitor_groups((urllib.parse.parse_qs(u.query).get("q") or [""])[0])
            except ValueError as ex:
                return self._send(400, json.dumps({"msg": str(ex)}, ensure_ascii=False))
            return self._send(200, json.dumps(result, ensure_ascii=False))
        if u.path == "/api/history":
            return self._send(200, json.dumps(history((urllib.parse.parse_qs(u.query).get("cid") or [""])[0]), ensure_ascii=False))
        if u.path == "/api/done":
            return self._send(200, json.dumps(done_detail((urllib.parse.parse_qs(u.query).get("no") or [""])[0]), ensure_ascii=False))
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
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/notifications":
            if not self._local():
                return self._send(403, '{"msg":"只允许本机桥接调用"}')
            try:
                added = A["record_notification"](body)
            except (ValueError, TypeError) as ex:
                return self._send(400, json.dumps({"msg": str(ex)}, ensure_ascii=False))
            except OSError:
                return self._send(503, '{"msg":"通知尚未落盘，请保留离线记录"}')
            return self._send(200, json.dumps({"ok": True, "added": added}))
        if path == "/api/monitor":
            if not self.headers.get("Content-Type", "").startswith("application/json") or not isinstance(body, dict):
                return self._send(400, '{"msg":"监听设置格式不对"}')
            group = body.get("group")
            cid = group.get("cid") if isinstance(group, dict) else None
            with GROUP_SEARCH_LOCK:
                candidate = dict(GROUP_CANDIDATES.get(cid) or {})
            if time.time() - candidate.get("at", 0) > 600:
                candidate = None
            try:
                settings = A["save_monitor_settings"](body, candidate)
            except (ValueError, TypeError) as ex:
                return self._send(400, json.dumps({"msg": str(ex)}, ensure_ascii=False))
            except OSError:
                return self._send(500, '{"msg":"保存失败，请检查配置目录权限；原设置保留"}')
            return self._send(200, json.dumps({"ok": True, "msg": "已保存，监听将在数秒内按新设置调整；已有任务和草稿保留", "settings": settings}, ensure_ascii=False))
        if path == "/api/draft":
            if not self._local():
                return self._send(403, '{"msg":"只允许本机桥接调用"}')
            try:
                no = A["stage_draft"](body.get("event") or {}, str(body.get("draft") or ""),
                                      str(body.get("reason") or "后台已核查，请本人审核发送"))
            except ValueError as ex:
                return self._send(400, json.dumps({"msg": str(ex)}, ensure_ascii=False))
            return self._send(200, json.dumps({"ok": True, "no": no, "sent": False}, ensure_ascii=False))
        if path == "/api/escalate":
            if not self._local():
                return self._send(403, '{"msg":"只允许本机桥接调用"}')
            event = body.get("event") or {}
            message_id = str(body.get("message_id") or event.get("message_id") or "")
            reason = str(body.get("reason") or "需要本人拍板")[:1000]
            if not message_id or not event.get("conversation_id"):
                return self._send(400, '{"msg":"缺少 message_id 或 conversation_id"}')
            no_hint = A["no_for"](message_id)
            restored = _message_context(no_hint, {"cid": event["conversation_id"], "event": event})["item"]
            event = restored["event"]
            items = A["_open_load"]()
            existing = next((no for no, x in items.items() if (x.get("event") or {}).get("message_id") == message_id
                             and x.get("cid") == event["conversation_id"]), None)
            if existing:
                items[existing]["reason"] = reason
                items[existing]["kind"] = "escalate"
                items[existing]["event"] = event
                items[existing]["what"] = str(event.get("content") or "")[:60]
                if restored.get("task_key"):
                    items[existing]["task_key"] = restored["task_key"]
                A["_open_save"](items)
                no = existing
            else:
                no = A["open_add"](event, "escalate", reason)
            brief = f"{event.get('sender', '未知发送人')}：{str(event.get('content') or '')[:240]}"
            A["notify"](f"🔔 {no} 需要你处理", f"{brief}\n原因：{reason}\n原消息 ID：{message_id}\n请在操作台或原会话完成决定。", True)
            return self._send(200, json.dumps({"ok": True, "no": no}, ensure_ascii=False))
        if path == "/api/say":                       # 3.4：以前排在 404 判断后面，聊天框发出去一直没反应
            return self._send(200, json.dumps({"msg": say(body.get("text", ""))}, ensure_ascii=False))
        if path != "/api/act":
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
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%233b5bdb'/%3E%3Ctext x='16' y='22' font-size='17' text-anchor='middle' fill='white' font-family='sans-serif'%3E群%3C/text%3E%3C/svg%3E">
<script>try{const t=localStorage.getItem('qa-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}</script>
<style>
:root{--bg:#f4f5f8;--surface:#fff;--soft:#f7f8fa;--sunken:#eceff4;--border:#e1e5ec;--line:#eceff3;--text:#172033;--muted:#5b6577;--faint:#8a93a3;
--accent:#3b5bdb;--accent-soft:#eaf0ff;--accent-ink:#fff;--amber:#b45f06;--amber-soft:#fff3e0;--red:#c92a2a;--overdue:#e53935;--b-pri:#3b5bdb;--b-pri-h:#364fc7;--b-pri-a:#2f44ad;--b-pri-fg:#fff;--b-st-bg:#fff3e8;--b-st-fg:#9a4a10;--b-st-bd:#fbd5b5;--b-st-h:#ffe8d4;--b-mn-bg:#efeaff;--b-mn-fg:#5b3cc4;--b-mn-bd:#d0bfff;--b-mn-h:#e4dbff;--b-ai-bg:#e2f5fa;--b-ai-fg:#0a6a80;--b-ai-bd:#a5e0ee;--b-ai-h:#cdeef6;--b-dg-fg:#c92a2a;--b-dg-bd:#ffc9c9;--b-dg-h:#fff0f0;--dr-bg:#eef2ff;--dr-bg-f:#f5f7ff;--dr-bd:#c7d2fe;--dr-fg:#4338ca;--overdue-soft:#ffe5e5;--sb:#c7cdd6;--sb-h:#a0a9b7;--red-soft:#ffeded;--green:#2b8a3e;--green-soft:#e9f9ec;
--shadow:0 1px 2px rgba(16,24,40,.06);--shadow-h:0 4px 14px rgba(16,24,40,.10);--shadow-x:0 20px 60px rgba(16,24,40,.22);--mask:rgba(15,23,42,.32);--r:12px;--r-sm:8px;--toast:#172033;--toast-ink:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0b0f15;--surface:#131922;--soft:#171e28;--sunken:#1c2430;--border:#283140;--line:#1f2732;--text:#e6eaf1;--muted:#a3adbd;--faint:#7b8698;
--accent:#91a7ff;--accent-soft:#1d2747;--accent-ink:#0b0f15;--amber:#ffc078;--amber-soft:#35270f;--red:#ff8787;--overdue:#ff4d4f;--b-pri:#91a7ff;--b-pri-h:#a5b8ff;--b-pri-a:#7d96f5;--b-pri-fg:#0b0f15;--b-st-bg:#3a2818;--b-st-fg:#ffc896;--b-st-bd:#5c3d22;--b-st-h:#44301d;--b-mn-bg:#2a2350;--b-mn-fg:#c9b8ff;--b-mn-bd:#3d3370;--b-mn-h:#342b63;--b-ai-bg:#0f3340;--b-ai-fg:#8fe3f5;--b-ai-bd:#1a4a5a;--b-ai-h:#144050;--b-dg-fg:#ff8787;--b-dg-bd:#6b2a2e;--b-dg-h:#3a1c20;--dr-bg:#1b2142;--dr-bg-f:#20284f;--dr-bd:#34407a;--dr-fg:#a5b4fc;--overdue-soft:#4a1517;--sb:#3b4555;--sb-h:#5b677b;--red-soft:#3a1c20;--green:#8ce99a;--green-soft:#142c1b;
--shadow:0 1px 2px rgba(0,0,0,.4);--shadow-h:0 6px 22px rgba(0,0,0,.5);--shadow-x:0 20px 60px rgba(0,0,0,.6);--mask:rgba(0,0,0,.5);--toast:#e6eaf1;--toast-ink:#0b0f15}}
:root[data-theme="dark"]{--bg:#0b0f15;--surface:#131922;--soft:#171e28;--sunken:#1c2430;--border:#283140;--line:#1f2732;--text:#e6eaf1;--muted:#a3adbd;--faint:#7b8698;
--accent:#91a7ff;--accent-soft:#1d2747;--accent-ink:#0b0f15;--amber:#ffc078;--amber-soft:#35270f;--red:#ff8787;--overdue:#ff4d4f;--b-pri:#91a7ff;--b-pri-h:#a5b8ff;--b-pri-a:#7d96f5;--b-pri-fg:#0b0f15;--b-st-bg:#3a2818;--b-st-fg:#ffc896;--b-st-bd:#5c3d22;--b-st-h:#44301d;--b-mn-bg:#2a2350;--b-mn-fg:#c9b8ff;--b-mn-bd:#3d3370;--b-mn-h:#342b63;--b-ai-bg:#0f3340;--b-ai-fg:#8fe3f5;--b-ai-bd:#1a4a5a;--b-ai-h:#144050;--b-dg-fg:#ff8787;--b-dg-bd:#6b2a2e;--b-dg-h:#3a1c20;--dr-bg:#1b2142;--dr-bg-f:#20284f;--dr-bd:#34407a;--dr-fg:#a5b4fc;--overdue-soft:#4a1517;--sb:#3b4555;--sb-h:#5b677b;--red-soft:#3a1c20;--green:#8ce99a;--green-soft:#142c1b;
--shadow:0 1px 2px rgba(0,0,0,.4);--shadow-h:0 6px 22px rgba(0,0,0,.5);--shadow-x:0 20px 60px rgba(0,0,0,.6);--mask:rgba(0,0,0,.5);--toast:#e6eaf1;--toast-ink:#0b0f15}
*{box-sizing:border-box;scrollbar-width:thin;scrollbar-color:var(--sb) transparent}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-track,::-webkit-scrollbar-corner{background:transparent}::-webkit-scrollbar-thumb{background:var(--sb);border-radius:99px;border:2px solid transparent;background-clip:padding-box}::-webkit-scrollbar-thumb:hover{background-color:var(--sb-h)}
html,body{margin:0}
body{background:var(--bg);color:var(--text);font:14.5px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden;-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit}:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.sp{flex:1}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:var(--r-sm);padding:6px 14px;font-size:13.5px;line-height:1.4;cursor:pointer;transition:background .15s,border-color .15s,color .15s;white-space:nowrap}
.btn:hover{border-color:var(--accent);color:var(--accent)}.btn:active{transform:translateY(1px)}
.btn.p{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:600;padding:6px 20px}.btn.p:hover{filter:brightness(1.08);color:var(--accent-ink)}
.btn.d{color:var(--red)}.btn.d:hover{border-color:var(--red);background:var(--red-soft)}.btn.dp{background:var(--red);border-color:var(--red);color:#fff}
.btn.g{border-color:transparent;background:transparent;color:var(--muted)}.btn.g:hover{background:var(--sunken);color:var(--text)}
.btn.sm{padding:4px 10px;font-size:13px}.btn:disabled{opacity:.5;cursor:progress}
.link{border:0;background:none;padding:0;color:var(--accent);cursor:pointer;font-size:13px}.link:hover{text-decoration:underline}
.badge{min-width:17px;height:17px;padding:0 5px;border-radius:9px;background:var(--accent);color:var(--accent-ink);font-size:11px;font-weight:700;display:inline-grid;place-items:center;line-height:1}.badge[hidden]{display:none}.badge.red{background:var(--red);color:#fff}
/* 顶栏一行 */
header{flex:none;z-index:5;height:50px;display:flex;align-items:center;gap:5px;padding:0 12px;background:var(--surface);border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:8px;font-weight:700;font-size:15px;white-space:nowrap}
.logo{width:26px;height:26px;border-radius:7px;background:var(--accent);color:var(--accent-ink);display:grid;place-items:center;font-size:13px;font-weight:700}
.pill{display:inline-flex;align-items:center;gap:4px;height:26px;padding:0 7px;border-radius:99px;font-size:12px;border:1px solid var(--border);background:var(--surface);color:var(--muted);cursor:pointer;white-space:nowrap;font-variant-numeric:tabular-nums}
.pill:hover{border-color:var(--accent)}.pill b{color:var(--text);font-weight:600}
.dot{width:8px;height:8px;border-radius:50%;background:var(--faint);flex:none}
.d-ok{background:var(--green-soft);color:var(--green);border-color:transparent}.d-ok b{color:var(--green)}.d-ok .dot{background:var(--green)}
.d-warn{background:var(--amber-soft);color:var(--amber);border-color:transparent}.d-warn b{color:var(--amber)}.d-warn .dot{background:var(--amber)}
.d-bad{background:var(--red-soft);color:var(--red);border-color:transparent}.d-bad b{color:var(--red)}.d-bad .dot{background:var(--red)}
.pill.hot{background:var(--overdue);color:#fff;border-color:transparent;font-weight:700}.pill.hot:hover{filter:brightness(1.08);border-color:transparent}.pill.hot[aria-pressed=true]{box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--overdue)}
#pills{display:flex;gap:3px;flex:none;white-space:nowrap}.pill.hot b{color:#fff}.pill.toggle[aria-pressed=true]{background:var(--overdue);color:#fff;border-color:transparent;font-weight:700}.search{position:relative;flex:none;width:34px;height:32px}.search input{position:absolute;right:0;top:0;width:34px;padding:0 0 0 8px!important;cursor:pointer;transition:width .15s;z-index:1;height:32px;border:1px solid var(--border);border-radius:var(--r-sm);padding:0 12px;font:inherit;font-size:13.5px;background:var(--soft);color:var(--text);outline:none}
.search .sicon{position:absolute;right:0;top:0;width:34px;height:32px;display:grid;place-items:center;font-size:13px;pointer-events:none;z-index:2}.search:not(.open) input:placeholder-shown::placeholder{color:transparent}.search.open .sicon,.search:has(input:not(:placeholder-shown)) .sicon{display:none}.search.open input,.search input:focus,.search input:not(:placeholder-shown){width:300px;z-index:6;padding:0 12px!important;cursor:text}.search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);background:var(--surface)}
.hbtns{display:flex;gap:3px;align-items:center;flex:none}.hbtns .btn{padding:4px 7px!important;font-size:12.5px!important;gap:4px}.hbtns .btn.ic{padding:4px 7px!important}.hbtns a.btn{text-decoration:none}.hbtns .btn.help{margin-left:2px}.ver{font-size:11px!important;margin-left:2px!important}.hbtns .btn{border-radius:99px;padding:5px 13px;font-size:13px;background:var(--soft);border:1px solid var(--border);color:var(--text)}.hbtns .btn:hover{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}.hbtns .em{font-size:13px;line-height:1}.ver{color:var(--faint);font-size:12px;white-space:nowrap;margin-left:4px}
.conn{display:none;flex:none;padding:7px 16px;background:var(--red-soft);color:var(--red);font-size:13px}.conn.on{display:block}
/* 主区：三列并排，一眼看全；每列自己滚动 */
main{flex:1;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:14px 16px 8px}
.col{display:flex;flex-direction:column;min-height:0;background:var(--sunken);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.colh{flex:none;display:flex;align-items:center;gap:8px;padding:11px 14px 9px;width:100%;border:0;background:none;text-align:left;font:inherit;color:inherit}
.colh h2{margin:0;font-size:15px}.colh .sub{color:var(--faint);font-size:12.5px;margin-left:auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cnt{min-width:24px;text-align:center;padding:0 8px;border-radius:99px;font-size:12.5px;font-weight:700;background:var(--surface);color:var(--muted);font-variant-numeric:tabular-nums}
.cnt.hot{background:var(--amber-soft);color:var(--amber)}.cnt.send{background:var(--accent-soft);color:var(--accent)}.cnt.ok{background:var(--green-soft);color:var(--green)}
.colb{flex:1;min-height:0;overflow:auto;padding:2px 10px 10px}
.dtabs{display:flex;gap:2px;padding:2px;background:var(--surface);border-radius:8px;border:1px solid var(--line)}.dtabs button{border:0;background:none;padding:1px 9px;border-radius:6px;font-size:12px;color:var(--muted);cursor:pointer}.dtabs button[aria-pressed=true]{background:var(--green-soft);color:var(--green);font-weight:600}
.tabs{display:flex;align-items:center;gap:4px;border-bottom:1px solid var(--border);margin-bottom:16px}
.tab{border:0;background:none;padding:10px 14px;font-size:15px;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;display:flex;align-items:center;gap:6px}
.tab:hover{color:var(--text)}.tab[aria-selected=true]{color:var(--text);font-weight:600;border-bottom-color:var(--accent)}
.tab .n{font-size:12.5px;font-weight:600;padding:0 7px;border-radius:99px;background:var(--sunken);color:var(--muted);font-variant-numeric:tabular-nums}
.tab[aria-selected=true] .n{background:var(--accent-soft);color:var(--accent)}.tab .n.hot{background:var(--amber-soft);color:var(--amber)}
.tabs .opt{margin-left:auto;font-size:13px;color:var(--muted);display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}
.hint{color:var(--faint);font-size:12.5px;margin:-6px 0 14px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:11px 14px 12px;margin-bottom:10px;box-shadow:var(--shadow);transition:opacity .3s,transform .3s,max-height .35s,margin .35s,padding .35s;overflow:hidden}
.card{border-left:4px solid var(--bar,var(--border))}.k-judge{--bar:var(--amber)}.k-send{--bar:var(--accent)}.k-done{--bar:var(--green)}.card.over{--bar:var(--overdue);border-left-width:5px}.col{border-top:3px solid var(--colbar)}.col-judge{--colbar:var(--amber)}.col-send{--colbar:var(--accent)}.col-done{--colbar:var(--green)}
.card.busy{opacity:.75}
.card.leaving{opacity:0;transform:translateX(16px);max-height:0!important;margin-bottom:0;padding-top:0;padding-bottom:0;border-width:0}
.card.flash{box-shadow:0 0 0 3px var(--accent-soft),var(--shadow-h);border-color:var(--accent)}
.c-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px;color:var(--muted)}.av{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:600;font-size:12px;flex:none}
.c-head .who{color:var(--text);font-weight:700;font-size:15.5px;letter-spacing:.01em}.c-head .age.late{color:var(--overdue);font-weight:700}.t-over{background:var(--overdue);color:#fff}.over-n{color:var(--overdue);font-weight:700}.c-head .no{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--faint)}
.c-head .right{margin-left:auto;display:flex;gap:12px;align-items:baseline}
.tag{display:inline-flex;align-items:center;border-radius:99px;padding:0 8px;font-size:12px;font-weight:600;line-height:20px;white-space:nowrap}
.t-red{background:var(--red-soft);color:var(--red)}.t-ok{background:var(--green-soft);color:var(--green)}.t-gray{background:var(--sunken);color:var(--muted)}.t-wait{color:var(--amber);background:var(--amber-soft)}.t-blue{background:var(--accent-soft);color:var(--accent)}
.c-msg{margin-top:6px;font-size:14.5px}.clamp{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.c-meta>div{margin-top:6px;font-size:12.5px;color:var(--muted)}.c-meta b{color:var(--text);font-weight:600}
.c-meta .qa{border-left:3px solid var(--accent);padding-left:10px}
.c-ctx{margin-top:10px;background:var(--soft);border:1px solid var(--line);border-radius:var(--r-sm);padding:8px 12px;max-height:280px;overflow:auto;font-size:13px}
.c-ctx .m{padding:4px 0;border-bottom:1px dashed var(--line)}.c-ctx .m:last-child{border-bottom:0}.c-ctx .m b{font-weight:600}.c-ctx .m .t{color:var(--faint);margin:0 6px;font-size:12px}
.c-ctx .m.anchor{background:var(--amber-soft);border-radius:6px;padding:4px 8px;margin:0 -8px}.c-ctx .m.reply{background:var(--green-soft);border-radius:6px;padding:4px 8px;margin:0 -8px}
.c-edit label{display:block;font-size:12px;color:var(--muted);margin:8px 0 3px}
textarea,input.q{width:100%;border:1px solid var(--border);border-radius:var(--r-sm);padding:8px 11px;font:inherit;font-size:14.5px;background:var(--soft);color:var(--text);outline:none;transition:border-color .15s,box-shadow .15s,background .15s}
textarea{min-height:64px;resize:vertical;line-height:1.6;display:block}textarea:focus,input.q:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);background:var(--surface)}
.c-acts{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:10px}.c-ask .act{flex:none}.ailab{display:flex!important;align-items:center;gap:5px;font-size:12px!important;font-weight:600;color:var(--dr-fg)!important;margin:10px 0 4px!important}.ailab svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.ailab span{font-weight:400;color:var(--muted)}textarea.ai{background:var(--dr-bg)!important;border:1px solid var(--dr-bd)!important;color:var(--text);border-radius:8px}textarea.ai:hover{border-color:var(--dr-fg)!important}textarea.ai:focus{background:var(--dr-bg-f)!important;border-color:var(--accent)!important;box-shadow:0 0 0 3px var(--accent-soft)!important}.c-acts .ro{flex-basis:100%;font-size:12.5px;color:var(--muted)}.c-acts .sep{flex:1}
.act{display:inline-flex;align-items:center;justify-content:center;gap:5px;height:32px;padding:0 11px;border-radius:6px;border:1px solid transparent;font:inherit;font-size:13.5px;font-weight:500;line-height:1;cursor:pointer;white-space:nowrap;transition:background-color .15s,border-color .15s,color .15s,box-shadow .15s}
.act svg{width:14px;height:14px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.act:active:not(:disabled){transform:translateY(1px)}.act:disabled{opacity:.45;cursor:not-allowed}.act:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.act.send{background:var(--b-pri);border-color:var(--b-pri);color:var(--b-pri-fg);font-weight:600;padding:0 14px;box-shadow:0 1px 2px rgba(16,24,40,.14)}.act.send:hover:not(:disabled){background:var(--b-pri-h);border-color:var(--b-pri-h)}.act.send:active:not(:disabled){background:var(--b-pri-a)}
.act.stash{background:var(--b-st-bg);border-color:var(--b-st-bd);color:var(--b-st-fg)}.act.stash:hover:not(:disabled){background:var(--b-st-h);border-color:var(--b-st-fg)}
.act.done{background:var(--b-mn-bg);border-color:var(--b-mn-bd);color:var(--b-mn-fg)}.act.done:hover:not(:disabled){background:var(--b-mn-h);border-color:var(--b-mn-fg)}
.act.ai{background:var(--b-ai-bg);border-color:var(--b-ai-bd);color:var(--b-ai-fg)}.act.ai:hover:not(:disabled),.act.ai[aria-expanded=true]{background:var(--b-ai-h);border-color:var(--b-ai-fg)}
.act.no{background:transparent;border-color:var(--b-dg-bd);color:var(--b-dg-fg)}.act.no:hover:not(:disabled){background:var(--b-dg-h);border-color:var(--b-dg-fg)}
.c-ask{display:flex;gap:8px;margin-top:10px}.c-ask input{flex:1}.c-ask[hidden],.c-ctx[hidden]{display:none}
.c-status{font-size:13px;margin-top:8px}.c-status:empty{display:none}.c-status.ok{color:var(--green);font-weight:600}.c-status.err{color:var(--red)}.c-status.info{color:var(--muted)}
.spin{width:12px;height:12px;border-radius:50%;border:2px solid currentColor;border-right-color:transparent;animation:spin .7s linear infinite;display:inline-block;vertical-align:-1px;margin-right:6px}@keyframes spin{to{transform:rotate(360deg)}}
.sent{margin-top:10px;background:var(--green-soft);border-radius:10px;padding:8px 10px;white-space:pre-wrap;word-break:break-word;font-size:13.5px;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical;overflow:hidden}.sent .l{display:block;font-size:11px;color:var(--green);font-weight:600;margin-bottom:2px}
.note-card{padding:9px 13px}.note-card .c-msg{font-size:13.5px}.note-card .c-head .who{font-size:14px}
.empty{color:var(--faint);text-align:center;padding:40px 12px;font-size:14px}.empty b{display:block;color:var(--text);font-size:16px;margin-bottom:4px;font-weight:600}
.btn .hi{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;margin-right:5px;border:1.5px solid currentColor;border-radius:50%;font-size:10px;font-weight:700;line-height:1;opacity:.75}   /* 帮助用中性色圆圈感叹号，不用红色问号（11-25 本人：红色像出了问题，忍不住点） */
.empty .big{display:block;font-size:40px;line-height:1;margin:8px 0 12px;opacity:.85}   /* 空状态大图标（11-25 本人：旧版有图案更友好） */
.sk{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;margin-bottom:12px}.skeleton{height:11px;border-radius:6px;background:var(--line);margin:8px 0;animation:fade 1.1s ease-in-out infinite alternate}.skeleton.short{width:45%}@keyframes fade{to{opacity:.4}}
.readable{overflow-wrap:anywhere}.readable p{margin:0 0 4px}.readable p:last-child{margin-bottom:0}.mdh{font-weight:700;margin:2px 0 4px}.mdl{margin:2px 0 4px;padding-left:18px}
.mention{color:var(--accent);font-weight:600}.readable a{color:inherit;text-decoration:underline}.readable code{font-size:.92em;background:var(--accent-soft);padding:1px 4px;border-radius:4px}
.foot{flex:none;text-align:center;color:var(--faint);font-size:12px;padding:0 0 8px}
/* 侧边抽屉：每日汇报 / 各群最近消息 / 调试群对话（次要功能，不占主区） */
.mask{position:fixed;inset:0;background:var(--mask);opacity:0;pointer-events:none;transition:opacity .2s;z-index:9}.mask.on{opacity:1;pointer-events:auto}
aside{position:fixed;top:0;right:0;height:100%;width:min(540px,100%);background:var(--surface);transform:translateX(100%);transition:transform .24s ease;display:flex;flex-direction:column;z-index:10;visibility:hidden}aside.on{transform:none;box-shadow:var(--shadow-x);visibility:visible}
.ah{display:flex;align-items:center;gap:10px;padding:12px 18px;border-bottom:1px solid var(--border)}.ah .t{font-weight:700;font-size:15px}.ah .s{color:var(--muted);font-size:12.5px}
.ab{flex:1;overflow:auto;padding:14px 18px;background:var(--soft)}.af{border-top:1px solid var(--border);padding:12px 18px;display:flex;gap:8px}.af input{flex:1}
.ab .item{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm);padding:9px 12px;margin-bottom:8px;font-size:13.5px}.ab .item .w{font-size:12px;color:var(--muted);margin-bottom:2px}
.ab .item.me{background:var(--accent-soft);border-color:transparent;margin-left:48px}.gtabs{display:flex;gap:6px;flex-wrap:wrap;margin:-14px -18px 14px;padding:10px 18px;position:sticky;top:-14px;background:var(--soft);border-bottom:1px solid var(--line);z-index:1}.bub{display:flex;gap:10px;margin-bottom:14px}.bub .av{width:28px;height:28px;font-size:11.5px}.bub .b{background:var(--surface);border:1px solid var(--border);border-radius:4px 12px 12px 12px;padding:8px 12px;max-width:100%;min-width:0}.bub .w{font-size:12px;color:var(--muted);margin-bottom:2px}.bub .w b{color:var(--text);font-weight:600}.bub .w span{color:var(--faint);margin-left:6px}.bub .tx{word-break:break-word;font-size:14px}
/* 会话抽屉：点卡片打开，不加遮罩，主看板照常可点 */
.card{cursor:pointer}.card:hover{box-shadow:0 0 0 1px color-mix(in srgb,var(--accent) 35%,transparent),var(--shadow-h);transform:translateY(-1px)}.card.sel{box-shadow:0 0 0 2px var(--accent),var(--shadow-h)}
#conv{width:min(500px,36vw);z-index:8;border-left:1px solid var(--border)}
.cf{flex:none;border-top:1px solid var(--border);padding:10px 18px 14px;background:var(--surface)}.cf .cl{font-size:12px;color:var(--muted);margin:0 0 4px}.cf textarea{min-height:80px;max-height:30vh}
.cf .c-status{margin-top:6px}.cnote{margin-top:6px;font-size:12.5px;color:var(--muted);background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm);padding:8px 11px}.cnote b{color:var(--text)}
.bub .lab{display:inline-block;font-size:11.5px;font-weight:700;color:var(--amber);margin-bottom:2px}
.bub.anchor .b{background:var(--amber-soft);border-color:transparent;box-shadow:0 0 0 2px var(--amber-soft)}.bub.reply .b{background:var(--green-soft);border-color:transparent}.bub.reply .lab{color:var(--green)}
.bub.anchor.pulse .b{animation:pulse 1.6s ease-out 1}@keyframes pulse{0%{box-shadow:0 0 0 0 var(--amber)}100%{box-shadow:0 0 0 10px transparent}}
/* 提示与对话框 */
.toasts{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);display:flex;flex-direction:column;gap:8px;align-items:center;z-index:30;pointer-events:none;max-width:calc(100% - 32px)}
.toast{background:var(--toast);color:var(--toast-ink);padding:9px 16px;border-radius:9px;box-shadow:var(--shadow-h);font-size:13.5px;opacity:0;transform:translateY(10px);transition:opacity .2s,transform .2s}.toast.on{opacity:1;transform:none}.toast.err{background:var(--red);color:#fff}
dialog{max-width:520px;width:calc(100% - 32px);border:1px solid var(--border);border-radius:12px;background:var(--surface);color:var(--text);padding:18px 20px;box-shadow:var(--shadow-x)}dialog::backdrop{background:var(--mask)}
dialog h3{margin:0 0 8px;font-size:16px}dialog textarea{min-height:90px;margin:12px 0 4px}dialog .row{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
.dhint{color:var(--muted);font-size:13.5px}.preview{margin:12px 0 4px;max-height:220px;overflow:auto;background:var(--accent-soft);border-radius:var(--r-sm);padding:10px 12px;font-size:14px}
#monitorDialog{max-width:760px;max-height:90vh;overflow:auto}#monitorDialog label{display:block;margin:10px 0 6px;font-size:13px}#monitorDialog input[type=time],#monitorDialog select{padding:6px 9px;border:1px solid var(--border);border-radius:var(--r-sm);font:inherit;background:var(--soft);color:var(--text)}
#monitorDialog .btns{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.mhead{display:flex;align-items:center;gap:10px;margin-bottom:4px}.mhead h3{flex:1;margin:0}
.msec{margin-top:16px;padding-top:12px;border-top:1px solid var(--line)}.monitor-row{padding:10px 0;border-bottom:1px solid var(--line)}.monitor-row:last-child{border-bottom:0}.monitor-row .btns{margin-top:8px}.monitor-hint{font-size:12.5px;color:var(--muted);white-space:pre-wrap}.monitor-error{color:var(--red);margin:8px 0;white-space:pre-wrap;font-size:13px}.monitor-error:empty{display:none}
#monitorEditor{margin:14px 0;padding:14px;background:var(--soft);border:1px solid var(--line);border-radius:var(--r)}#monitorEditor h4{margin:0 0 6px}#monitorResults{max-height:190px;overflow:auto}#monitorResults button{display:block;width:100%;text-align:left;margin-top:6px}.askrow{display:flex;gap:8px}.askrow input{flex:1}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
</style></head><body>
<header>
<div class="brand"><span class="logo">群</span>操作台</div>
<span id="pills"><span class="pill"><span class="dot"></span>连接中…</span></span>
<span class="sp"></span>
<label class="search"><span class="sicon" aria-hidden="true">🔍</span><input id="taskSearch" onfocus="this.parentNode.classList.add('open')" onblur="this.parentNode.classList.remove('open')" type="search" aria-label="搜索" placeholder="搜索人、群、编号、内容" title="搜索（点一下展开）" oninput="taskQuery=this.value;render()"></label>
<div class="hbtns">
<button class="btn" onclick="openChat()"><span class="em" aria-hidden="true">💬</span>调试群对话 <span class="badge" id="chatBadge" hidden></span></button>
<button class="btn" onclick="openReports()"><span class="em" aria-hidden="true">📋</span>每日汇报</button>
<button class="btn" onclick="openMonitor()"><span class="em" aria-hidden="true">⚙️</span>监听设置</button>
<button class="btn ic" id="notif" style="display:none" title="开启桌面通知" aria-label="开启桌面通知"><span class="em" aria-hidden="true">🔔</span></button>
<button class="btn ic" id="themeBtn" onclick="cycleTheme()" aria-label="切换外观"></button>
<span class="ver" id="ver"></span>
<a class="btn help" href="__HELP_URL__" target="_blank" rel="noopener" title="使用帮助（新标签页打开）"><span class="hi" aria-hidden="true">!</span>帮助</a>
</div></header>
<div class="conn" id="conn" role="alert">连接中断，正在重试…</div>
<main>
<section class="col col-judge" aria-labelledby="h-judge"><div class="colh"><h2 id="h-judge">要你判断</h2><span class="cnt" id="c-judge">0</span><span class="sub">拿不准、要你决定的</span></div><div class="colb" id="L-judge"><div class="sk"><div class="skeleton short"></div><div class="skeleton"></div><div class="skeleton"></div></div><div class="sk"><div class="skeleton short"></div><div class="skeleton"></div></div></div></section>
<section class="col col-send" aria-labelledby="h-send"><div class="colh"><h2 id="h-send">草稿待发</h2><span class="cnt" id="c-send">0</span><span class="sub">AI 写好了，你点头才发</span></div><div class="colb" id="L-send"><div class="sk"><div class="skeleton short"></div><div class="skeleton"></div><div class="skeleton"></div></div></div></section>
<section class="col col-done" aria-labelledby="h-done"><div class="colh"><h2 id="h-done">已处理</h2><span class="cnt ok" id="c-done">0</span><span class="dtabs" id="dtabs"></span><span class="sub" id="doneSub"></span></div><div class="colb" id="L-done"></div></section>
</main>
<div class="foot" id="foot">群消息助手 · 作者：梦无矶</div>
<div class="mask" id="mask" onclick="closeAll()"></div>
<aside id="conv" aria-labelledby="ctitle"><div class="ah"><span id="cav"></span><div><div class="t" id="ctitle"></div><div class="s" id="csub"></div></div><span class="sp"></span><button class="btn g" onclick="closeConv()">关闭</button></div><div class="ab" id="cbody"></div><div class="cf" id="cfoot"></div></aside>
<aside id="panel" role="dialog" aria-modal="true" aria-labelledby="ptitle"><div class="ah"><div><div class="t" id="ptitle"></div><div class="s" id="psub"></div></div><span class="sp"></span><button class="btn g" onclick="closeAll()">关闭</button></div><div class="ab" id="pbody"></div></aside>
<aside id="chatPanel" role="dialog" aria-modal="true" aria-labelledby="chatTitle"><div class="ah"><div><div class="t" id="chatTitle">调试群对话</div><div class="s">和钉钉调试群里看到的同一段对话。在这里发 = 以你的身份发到调试群</div></div><span class="sp"></span><button class="btn g" onclick="closeAll()">关闭</button></div>
<div class="ab" id="chatBody"></div>
<div class="af"><input class="q" id="chatInput" placeholder="对助手说，例如「待回复」「#编号 已处理：在钉钉里回过了」" onkeydown="if(event.key==='Enter'&&!event.isComposing)sendChat()"><button class="btn p" id="chatSend" onclick="sendChat()">发送</button></div></aside>
<div class="toasts" id="toasts" role="status" aria-live="polite"></div>
<dialog id="actionDialog" aria-labelledby="actionTitle"><h3 id="actionTitle"></h3><div id="actionHint" class="dhint"></div><div id="actionPreview" class="preview readable" hidden></div><textarea id="actionNote" placeholder="例如：我已在群里回复，后续等待研发提供样本"></textarea><div class="row"><button class="btn" id="actionCancel">取消</button><button class="btn p" id="actionOK">确认</button></div></dialog>
<dialog id="monitorDialog" aria-labelledby="monitorTitle"><div class="mhead"><h3 id="monitorTitle">监听设置</h3><button class="btn g" onclick="$('monitorDialog').close()">关闭</button></div>
<p class="monitor-hint">调整群消息助手的监听群和每日时段。所有群回复仍需你确认；你另外配置的值守脚本按各自规则运行。</p>
<div id="monitorError" class="monitor-error" role="status"></div>
<div><label>每日监听时间 <span id="monitorTimezone" class="monitor-hint"></span></label><div class="btns"><input type="time" id="monitorStart" aria-label="监听开始时间"> 至 <input type="time" id="monitorEnd" aria-label="监听结束时间"><label style="margin:0;display:flex;gap:6px;align-items:center"><input type="checkbox" id="monitorAllDay" onchange="monitorAllDayChanged()"> 全天监听</label><button class="btn p" id="monitorTimeSave" onclick="saveMonitorTime()">保存时段</button></div>
<p class="monitor-hint">结束早于开始表示跨午夜。时间外暂停监听，操作台保持可用；已开始的任务继续完成，恢复后补读。电脑需保持开机，助手需保持运行。</p></div>
<div class="msec"><div class="btns"><b style="flex:1">监听的群</b><button class="btn p sm" onclick="newMonitorGroup()">新增监听群</button></div><div id="monitorGroups"></div></div>
<div id="monitorEditor" hidden><h4 id="monitorEditorTitle">新增监听群</h4><div id="monitorSearchBox"><label for="monitorQuery">搜索钉钉群</label><div class="askrow"><input class="q" id="monitorQuery" placeholder="输入群名关键词" maxlength="100" onkeydown="if(event.key==='Enter')searchMonitorGroups()"><button class="btn" id="monitorSearch" onclick="searchMonitorGroups()">搜索</button></div><div id="monitorSearchHint" class="monitor-hint"></div><div id="monitorResults"></div></div>
<p id="monitorChosen" class="monitor-hint"></p><label for="monitorRule">监听说明（选填）</label><textarea id="monitorRule" maxlength="2000" placeholder="例如：关注发版、接口变更，以及涉及我的验收安排。留空则沿用已有规则。"></textarea>
<label for="monitorMode">处理方式</label><select id="monitorMode"><option value="draft">生成草稿，确认后发送</option><option value="readonly">只监听提醒，不向此群发草稿</option></select>
<label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="monitorPaused"> 暂停监听此群</label><div class="btns"><button class="btn p" id="monitorGroupSave" onclick="saveMonitorGroup()">保存监听群</button><button class="btn" onclick="$('monitorEditor').hidden=true">取消</button></div></div>
</dialog>
<script>
const K=new URLSearchParams(location.search).get('k')||'';
let S=null,tab=null,onlyOver=false,taskQuery='',seen=new Set(),first=true,lastFocus=null,hsel=null;
const notes={},pendingActions=new Set(),gone=new Set(),edits={},ui={},doneCache=new Map(),expanded=new Set();
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const U=no=>ui[no]||(ui[no]={});
const COLORS=['#3360e6','#1c8a4a','#c27a00','#8a4fd8','#d23b3b','#0f8f9e','#c2477d','#5b6b86'];
function av(n){n=String(n||'?');let h=0;for(const ch of n)h=(h*31+ch.charCodeAt(0))>>>0;return `<span class="av" style="background:${COLORS[h%COLORS.length]}" aria-hidden="true">${esc(n.replace(/[-_ ].*/,'').slice(-2))}</span>`}
function toast(t,type){t=String(t||'');type=type||(/失败|错误|超时|未确认|没发出去|中断|不对|为空|请填写|已失效|没找到|勿重复/.test(t)?'err':'');
const box=$('toasts'),x=document.createElement('div');x.className='toast '+type;x.textContent=t;box.appendChild(x);while(box.children.length>3)box.firstChild.remove();
requestAnimationFrame(()=>x.classList.add('on'));setTimeout(()=>{x.classList.remove('on');setTimeout(()=>x.remove(),250)},type==='err'?5000:2800)}
async function api(p,b){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),b?90000:15000);try{const r=await fetch(p+(p.includes('?')?'&':'?')+'k='+encodeURIComponent(K),b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b),signal:controller.signal}:{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error(r.status===403?'操作台授权已失效，请重新打开本人链接':'助手返回错误 '+r.status);return await r.json()}finally{clearTimeout(timer)}}
function errText(e){return e&&e.name==='AbortError'?'助手响应超时':(e&&e.message)||'连接失败'}
// 钉钉消息里的 Markdown 按人看的样子显示（标题、加粗、链接、代码、列表、换行），不显示 ### / ** / [](…) 原样符号
function inline(t){return t.replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/\[([^\]\n]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>').replace(/&lt;@[A-Za-z0-9_-]+&gt;/g,'<span class="mention">@某人</span>').replace(/(^|[^"=])(https?:\/\/[^\s<]+)/g,'$1<a href="$2" target="_blank" rel="noopener">$2</a>')}
function readable(text){const L=esc(String(text||'').replace(/\r/g,'')).split('\n');let out='',list=false;
for(const raw of L){const l=raw.trim();if(!l){if(list){out+='</ul>';list=false}continue}
let m=l.match(/^#{1,6}\s+(.*)$/);if(m){if(list){out+='</ul>';list=false}out+='<div class="mdh">'+inline(m[1])+'</div>';continue}
m=l.match(/^(?:[-*•]|\d+[.、)])\s+(.*)$/);if(m){if(!list){out+='<ul class="mdl">';list=true}out+='<li>'+inline(m[1])+'</li>';continue}
if(list){out+='</ul>';list=false}out+='<p>'+inline(l)+'</p>'}
return out+(list?'</ul>':'')}
function execLabel(status){return {committed:'待执行',starting:'正在启动',interrupted:'执行中断待核实',running:'执行中',waiting_resources:'等待前置',waiting_dependency:'等待配合',completed:'已完成',done:'已完成',failed:'执行异常',declined:'已拒接'}[status]||status||''}
function matches(c){return !taskQuery||[c.no,c.who,c.group,c.text,c.what,c.draft,c.sent,c.reason,c.why,c.title,c.display_text].some(x=>String(x||'').toLowerCase().includes(taskQuery.trim().toLowerCase()))}
function setHTML(el,h){if(el&&el._h!==h){el.innerHTML=h;el._h=h;return true}return false}
function parseAt(s){s=String(s||'');const n=new Date();let m=s.match(/(\d{4})-(\d{1,2})-(\d{1,2})[T ](\d{1,2}):(\d{2})/);if(m)return new Date(+m[1],m[2]-1,+m[3],+m[4],+m[5]);m=s.match(/(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})/);if(m)return new Date(n.getFullYear(),m[1]-1,+m[2],+m[3],+m[4]);m=s.match(/^(\d{1,2}):(\d{2})$/);return m?new Date(n.getFullYear(),n.getMonth(),n.getDate(),+m[1],+m[2]):null}
function rel(s){const d=parseAt(s);if(!d)return esc(s);const m=Math.round((Date.now()-d)/60000),p=x=>String(x).padStart(2,'0'),n=new Date();if(m<1)return '刚刚';if(m<60)return m+' 分钟前';if(d.toDateString()===n.toDateString())return Math.floor(m/60)+' 小时前';n.setDate(n.getDate()-1);if(d.toDateString()===n.toDateString())return '昨天 '+p(d.getHours())+':'+p(d.getMinutes());return (d.getMonth()+1)+'-'+d.getDate()+' '+p(d.getHours())+':'+p(d.getMinutes())}
const isLong=t=>String(t||'').length>150||String(t||'').split('\n').length>4;

let monitorState=null,monitorChoice=null,monitorMatches=[],monitorSearchSeq=0;
function monitorError(text){$('monitorError').textContent=text||''}
function monitorAllDayChanged(){for(const id of ['monitorStart','monitorEnd'])$(id).disabled=$('monitorAllDay').checked}
async function openMonitor(){const d=$('monitorDialog');if(!d.open)d.showModal();monitorError('正在读取设置…');$('monitorEditor').hidden=true;
try{const s=await api('/api/monitor');if(!s.groups)throw Error(s.msg||'无法读取监听设置');monitorState=s;$('monitorStart').value=s.window[0];$('monitorEnd').value=s.window[1];$('monitorAllDay').checked=s.all_day;$('monitorTimezone').textContent='（助手所在电脑：'+s.timezone+'）';monitorAllDayChanged();renderMonitorGroups();monitorError('')}catch(e){monitorError(e.message||'连接失败，请稍后重试')}}
function stateTag(s){return /监听中/.test(s)?'t-ok':/暂停/.test(s)?'t-gray':/连接/.test(s)?'t-wait':'t-blue'}
function renderMonitorGroups(){$('monitorGroups').innerHTML=monitorState.groups.map((g,i)=>`<div class="monitor-row"><b>${esc(g.name)}</b> <span class="tag ${stateTag(g.state)}">${esc(g.state)}</span><div class="monitor-hint">${esc(g.readonly?'只监听提醒':'草稿确认后发送')} · ${esc(g.rule||'沿用已有规则')}</div><div class="btns"><button class="btn sm" onclick="editMonitorGroup(${i})">编辑</button><button class="btn sm" onclick="toggleMonitorGroup(${i},this)">${g.paused?'恢复监听':'暂停监听'}</button></div></div>`).join('')||'<p class="monitor-hint">还没有监听群，点击“新增监听群”添加。</p>'}
function newMonitorGroup(){monitorSearchSeq++;monitorChoice=null;monitorMatches=[];$('monitorEditor').hidden=false;$('monitorSearchBox').hidden=false;$('monitorEditorTitle').textContent='新增监听群';$('monitorQuery').value='';$('monitorResults').innerHTML='';$('monitorSearchHint').textContent='搜索后请选择一个真实群；同名群请核对群标识。';$('monitorChosen').textContent='尚未选择群';$('monitorRule').value='';$('monitorMode').value='draft';$('monitorPaused').checked=false;monitorError('');$('monitorQuery').focus()}
function editMonitorGroup(i){monitorSearchSeq++;const g=monitorState.groups[i];monitorChoice={...g};$('monitorEditor').hidden=false;$('monitorSearchBox').hidden=true;$('monitorEditorTitle').textContent='编辑监听群';$('monitorChosen').textContent=g.name+' · '+g.cid;$('monitorRule').value=g.rule;$('monitorMode').value=g.readonly?'readonly':'draft';$('monitorPaused').checked=g.paused;monitorError('');$('monitorEditor').scrollIntoView({block:'nearest'})}
async function searchMonitorGroups(){const seq=++monitorSearchSeq,q=$('monitorQuery').value.trim();if(!q)return monitorError('请填写群名关键词');const b=$('monitorSearch');b.disabled=true;b.textContent='搜索中…';monitorChoice=null;$('monitorChosen').textContent='尚未选择群';$('monitorResults').innerHTML='';monitorError('');
try{const r=await api('/api/monitor/search?q='+encodeURIComponent(q));if(seq!==monitorSearchSeq)return;if(!r.matches)throw Error(r.msg||'群搜索失败');monitorMatches=r.matches;$('monitorSearchHint').textContent=r.msg||(!r.matches.length?'未找到群，请换一个关键词。':'请选择需要监听的群');$('monitorResults').innerHTML=r.matches.map((g,i)=>`<button class="btn sm" onclick="chooseMonitorGroup(${i})">${esc(g.name)}${g.existing?' · 已添加':''}<div class="monitor-hint">${esc(g.cid)}${g.members!=null?' · '+esc(g.members)+'人':''}</div></button>`).join('')}catch(e){if(seq===monitorSearchSeq)monitorError(e.message||'群搜索失败')}finally{b.disabled=false;b.textContent='搜索'}}
function chooseMonitorGroup(i){const g=monitorMatches[i],existing=monitorState.groups.findIndex(x=>x.cid===g.cid);if(existing>=0)return editMonitorGroup(existing);monitorChoice=g;$('monitorChosen').textContent='已选择：'+g.name+' · '+g.cid;$('monitorResults').innerHTML=''}
async function monitorSave(body,button){button.disabled=true;monitorError('正在保存…');try{const r=await api('/api/monitor',body);if(!r.ok)throw Error(r.msg||'保存失败');monitorState=r.settings;renderMonitorGroups();monitorError('');toast(r.msg);return true}catch(e){monitorError(e.message||'保存失败，请稍后重试');return false}finally{button.disabled=false}}
async function saveMonitorTime(){const b=$('monitorTimeSave');await monitorSave({window:[$('monitorStart').value,$('monitorEnd').value],all_day:$('monitorAllDay').checked},b)}
async function saveMonitorGroup(){if(!monitorChoice)return monitorError('请先搜索并选择一个群');if(await monitorSave({group:{cid:monitorChoice.cid,rule:$('monitorRule').value,readonly:$('monitorMode').value==='readonly',paused:$('monitorPaused').checked}},$('monitorGroupSave')))$('monitorEditor').hidden=true}
async function toggleMonitorGroup(i,button){const g=monitorState.groups[i];await monitorSave({group:{cid:g.cid,paused:!g.paused}},button)}

// ---------- 数据 ----------
function pend(k){if(!S)return[];return S[k].filter(c=>!gone.has(c.no))}
function findItem(no){if(!S)return null;const j=S.judge.find(c=>c.no===no);if(j)return {...j,_k:'judge'};const d=S.send.find(c=>c.no===no);return d?{...d,_k:'send'}:null}
function toggleOver(){onlyOver=!onlyOver;render()}
let dfilter='all';

// ---------- 待处理卡片：每张卡自带原消息、草稿和按钮 ----------
function head(c){return `${av(c.who)}<span class="who">${esc(c.who)}</span><span>${esc(c.group||'私聊')}</span><span class="age${c.overdue?' late':''}" title="${esc(c.at)}">${rel(c.at)}</span>${c.overdue?'<span class="tag t-over">超时</span>':''}${c.sent?'<span class="tag t-ok">已回复过</span>':''}<span class="right"><span class="no">${esc(c.no)}</span></span>`}
function meta(c){const x=c.commitment||{};let h='';
if(c.sent)h+=`<div><b>已回复（${esc(c.sent_at||'')}）：</b>${esc(c.sent)}</div>`;
if(x.status)h+=`<div><b>执行进度：</b>${esc(execLabel(x.status))}${x.next_action?' · '+esc(x.next_action):''}</div>`;
if(c.reason)h+=`<div><b>AI 判断：</b>${esc(c.reason)}</div>`;
for(const q of (c.qa||[]))h+=`<div class="qa"><b>问 AI：</b>${esc(q['问'])}<div class="readable">${readable(q['答'])}</div></div>`;return h}
const SV=d=>`<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`,IC={send:SV('<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>'),reply:SV('<path d="M9 17l-5-5 5-5"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>'),stash:SV('<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>'),ai:SV('<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 3v4M17 5h4"/>')};
const B=(cls,on,label,dis,extra='')=>`<button class="act ${cls}" onclick="${on}" ${dis} ${extra}>${label}</button>`;
function acts(c){const u=U(c.no),busy=pendingActions.has(c.no),dis=busy?'disabled':'',no=c.no,RO='<span class="ro">这个群设为只看，请在钉钉里回复；这里可以标记处理结果</span>';
// 按钮顺序（本人 11-25 定）：主按钮（实心蓝）→ 暂存（石板蓝）→ 已手动处理（紫）→ 不发/不归我（红色描边）→ 问 AI（青）放最后，同一组不留空隙
const AI=B('ai',`toggleAsk('${no}')`,IC.ai+'问 AI',dis,`aria-expanded="${!!u.ask}"`),DONE=B('done',`go('${no}','manual_done')`,'已手动处理',dis);
if(c._k==='send'){const edited=(edits[no]??c.draft).trim()!==String(c.draft||'').trim();
return (c.can_send?B('send',`sendCard('${no}')`,IC.send+(edited?'改了再发':'发送'),dis,'data-primary')+B('stash',`stashCard('${no}')`,IC.stash+'暂存',dis):RO)+DONE+B('no',`go('${no}','drop')`,'不发',dis)+AI}
if(u.reply)return B('send',`sendCard('${no}')`,IC.send+'发送回复',dis)+B('stash',`stashCard('${no}')`,IC.stash+'暂存',dis)+B('stash',`U('${no}').reply=false;render()`,'取消',dis);
return (c.can_send?B('send',`openReply('${no}')`,IC.reply+'回复',dis):RO)+DONE+B('no',`go('${no}','not_mine')`,'不归我',dis)+AI}
function buildCard(no){const el=document.createElement('article');el.className='card';el.dataset.no=no;el.tabIndex=0;el.setAttribute('aria-label','卡片：点开查看原会话');el.onclick=e=>cardClick(e,no);el.onkeydown=e=>{if(e.key==='Enter'&&e.target===el)openConv(no)};el.id='card-'+no.replace(/[^A-Za-z0-9-]/g,'');
el.innerHTML=`<div class="c-head"></div><div class="c-msg readable"></div><div class="c-more"></div><div class="c-meta"></div><div class="c-edit"></div><div class="c-acts"></div><div class="c-ask" hidden><input class="q" aria-label="问 AI" placeholder="问 AI：依据是什么？帮我改得客气点…" onkeydown="if(event.key==='Enter'&&!event.isComposing)askCard('${no}')"><button class="act ai" onclick="askCard('${no}')">提问</button></div><div class="c-status" role="status"></div>`;return el}
function updCard(el,c){const u=U(c.no),q=s=>el.querySelector(s);el.classList.toggle('over',!!c.overdue);el.classList.toggle('sel',convNo===c.no);el.classList.toggle('k-judge',c._k==='judge');el.classList.toggle('k-send',c._k==='send');el.classList.toggle('busy',pendingActions.has(c.no));
setHTML(q('.c-head'),head(c));const m=q('.c-msg');setHTML(m,readable(c.text));m.classList.toggle('clamp',!expanded.has(c.no));
setHTML(q('.c-more'),isLong(c.text)?`<button class="link" onclick="toggleExp('${c.no}')">${expanded.has(c.no)?'收起':'展开全文'}</button>`:'');
setHTML(q('.c-meta'),meta(c));
const wantEdit=c._k==='send'||u.reply,box=q('.c-edit');
if(wantEdit&&!box.querySelector('textarea')){box.innerHTML=c._k==='send'?`<label class="ailab">${IC.ai}AI 草稿 <span>可以直接改</span></label><textarea class="ai" aria-label="AI 草稿，可以直接改" placeholder="写回复内容；Ctrl+Enter 也可以发送"></textarea>`:`<label>你的回复</label><textarea aria-label="回复内容" placeholder="写回复内容；Ctrl+Enter 也可以发送"></textarea>`;const ta=box.querySelector('textarea');ta.value=edits[c.no]??(c.draft||'');
const fit=()=>{ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight+2,260)+'px'};requestAnimationFrame(fit);ta.oninput=()=>{fit();edits[c.no]=ta.value;const p=el.querySelector('[data-primary]');if(p)p.innerHTML=IC.send+(ta.value.trim()!==String(c.draft||'').trim()?'改了再发':'发送')};ta.onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.isComposing){e.preventDefault();sendCard(c.no)}};if(u.reply&&u.focusReply){u.focusReply=false;setTimeout(()=>ta.focus(),30)}}
else if(!wantEdit&&box.innerHTML)box.innerHTML='';
else if(wantEdit){const ta=box.querySelector('textarea');if(document.activeElement!==ta){const want=edits[c.no]??(c.draft||'');if(ta.value!==want)ta.value=want}}
setHTML(q('.c-acts'),acts(c));q('.c-ask').hidden=!u.ask;
const st=q('.c-status');st.className='c-status'+(u.st?' '+u.st[0]:'');setHTML(st,u.st?u.st[1]:'')}
function syncList(box,list){const want=list.map(c=>c.no),have=new Map([...box.querySelectorAll(':scope>article.card')].map(e=>[e.dataset.no,e]));
[...box.children].forEach(e=>{if(!e.classList.contains('card')||!want.includes(e.dataset.no)&&!e.dataset.keep)e.remove()});
let prev=null;for(const c of list){let el=have.get(c.no);if(el&&el.dataset.keep){prev=el;continue}if(!el)el=buildCard(c.no);const at=prev?prev.nextSibling:box.firstChild;if(el!==at)box.insertBefore(el,at);updCard(el,c);prev=el}
if(!list.length&&!box.querySelector('.card[data-keep]'))box.innerHTML=emptyFor(box.id)}
function emptyFor(id){const f=taskQuery||onlyOver;return f?'<div class="empty"><span class="big">🔍</span><b>没有符合条件的消息</b><button class="btn sm" onclick="clearFilters()">清除筛选</button></div>':id==='L-judge'?'<div class="empty"><span class="big">☕</span><b>没有要你判断的消息</b>新的会自动出现在这里</div>':'<div class="empty"><span class="big">📝</span><b>没有待发的草稿</b>AI 写好的回复会放在这里等你确认</div>'}
function clearFilters(){onlyOver=false;taskQuery='';$('taskSearch').value='';render()}
function toggleExp(no){expanded.has(no)?expanded.delete(no):expanded.add(no);render()}
function openReply(no){const u=U(no);u.reply=true;u.focusReply=true;render()}
function toggleAsk(no){const u=U(no);u.ask=!u.ask;render();if(u.ask){const el=document.querySelector(`.card[data-no="${CSS.escape(no)}"] .c-ask input`);el&&el.focus()}}
async function toggleCtx(no){const u=U(no),el=document.querySelector(`.card[data-no="${CSS.escape(no)}"]`);if(!el)return;u.ctx=!u.ctx;const box=el.querySelector('.c-ctx');box.hidden=!u.ctx;render();if(!u.ctx)return;
box.innerHTML='<div class="skeleton short"></div><div class="skeleton"></div><div class="skeleton"></div>';
try{const t=await api('/api/thread?no='+encodeURIComponent(no)),c=findItem(no),src=c?c.text:'';
box.innerHTML=t.map(m=>{const a=m.anchor||(!m.reply&&m.text&&src&&src.startsWith(String(m.text).slice(0,30)));return `<div class="m${a?' anchor':''}"${a?' data-a':''}><b>${esc(m.who)}</b><span class="t">${esc((m.time||'').slice(5,16))}</span>${esc(m.text)}</div>`}).join('')||'没有读到上下文';
const a=box.querySelector('[data-a]');if(a)box.scrollTop=a.offsetTop-box.clientHeight/2}catch(e){box.textContent='读取失败：'+errText(e)}}
function curText(no){if(convNo===no&&$('convTa'))return $('convTa').value;const el=document.querySelector(`.card[data-no="${CSS.escape(no)}"] textarea`);return el?el.value:(edits[no]??'')}
function sendCard(no){const c=findItem(no);if(!c)return;const text=curText(no);if(!text.trim())return setStatus(no,'err','回复内容是空的');
if(c._k==='send'){const edited=text.trim()!==String(c.draft||'').trim();return go(no,edited?'edit_send':'send',edited?text:'')}return go(no,'reply_new',text)}
function stashCard(no){const text=curText(no);if(!text.trim())return setStatus(no,'err','草稿是空的，写点内容再暂存');go(no,'stash',text)}
function askCard(no){const el=document.querySelector(`.card[data-no="${CSS.escape(no)}"] .c-ask input`),t=el?el.value.trim():'';if(!t)return setStatus(no,'err','先写下要问 AI 的问题');go(no,'ask',t).then(()=>{if(el)el.value=''})}
function setStatus(no,kind,html){U(no).st=html?[kind,html]:null;render()}

// ---------- 通知、已处理 ----------
function noteCard(n,i){const id='n'+i+(n.notification_id||n.time||''),open=expanded.has(id),body=n.display_text||n.text||'';return `<article class="card note-card"><div class="c-head"><span class="who">${esc(String(n.title||'').replace(/^[^\w一-龥#]+/,''))}</span>${n.delivered===false?'<span class="tag t-red">钉钉没送达</span>':''}<span class="right"><span title="${esc(n.time)}">${rel(n.time)}</span></span></div><div class="c-msg readable${open?'':' clamp'}" style="font-size:14px">${readable(body)}</div>${isLong(body)?`<button class="link" onclick="toggleExp('${esc(id)}')">${open?'收起':'展开全文'}</button>`:''}</article>`}
function doneCardH(d){const open=expanded.has('d'+d.no),det=doneCache.get(d.no);return `<article class="card k-done${convNo===d.no?' sel':''}" tabindex="0" data-no="${esc(d.no)}" onclick="cardClick(event,'${d.no}')" onkeydown="if(event.key==='Enter'&&event.target===this)openConv('${d.no}')"><div class="c-head">${av(d.who)}<span class="who">${esc(d.who)}</span><span class="tag ${d.result==='已发送'?'t-ok':'t-gray'}">${esc(d.result)}</span>${d.commitment_status?`<span class="tag t-wait">${esc(execLabel(d.commitment_status))}</span>`:''}<span title="${esc(d.done)}">${rel(d.done)} 处理</span><span class="right"><span class="no">${esc(d.no)}</span></span></div>
<div class="c-msg clamp" style="-webkit-line-clamp:2">${esc(d.what)}</div>${d.sent?`<div class="sent"><div class="l">已发出</div>${esc(d.sent)}</div>`:`<div class="c-meta"><div><b>处理说明：</b>${esc(d.why)}</div></div>`}
${open?`<div class="c-meta">${det?`${det.group?`<div><b>群：</b>${esc(det.group)} · 收到 ${esc(det.at||'')}</div>`:''}<div><b>原消息：</b>${esc(det.text)}</div>${det.reason?`<div><b>AI 判断：</b>${esc(det.reason)}</div>`:''}${det.confirm?`<div><b>确认方式：</b>${esc(det.confirm)}${det.sent_at?' · '+esc(det.sent_at):''}</div>`:''}${(det.qa||[]).map(q=>`<div class="qa"><b>问 AI：</b>${esc(q['问'])}<div class="readable">${readable(q['答'])}</div></div>`).join('')}`:'<div>正在读取…</div>'}</div>`:''}</article>`}
async function toggleDone(no){const k='d'+no;if(expanded.has(k)){expanded.delete(k);return render()}expanded.add(k);render();if(!doneCache.has(no)){try{const d=await api('/api/done?no='+encodeURIComponent(no));if(d.no)doneCache.set(no,d)}catch(e){toast('读取失败：'+errText(e))}render()}}

// ---------- 总渲染 ----------
function render(){if(!S)return;const s=S,J=pend('judge'),D=pend('send'),over=[...J,...D].filter(c=>c.overdue).length,o=s.owner||{},oq=(o.queued||0)+(o.running||0),N=s.notifications||[];
const oj=J.filter(c=>c.overdue).length,od=D.filter(c=>c.overdue).length;
// 顶栏信息与线上 / v1 一致：值守 · 监听 · 最近、要你判断、草稿待发、队列 · 处理中、今天已处理、本人 · 时间；外加「只看超时」
setHTML($('pills'),`<button class="pill d-${s.duty}" onclick="openH()" title="${esc('点开按群看最近消息\n最近收到：'+(s.last_event_t||'无')+(s.last_event?'\n'+s.last_event:''))}"><span class="dot"></span><b>${esc(s.duty_text)}</b> · 监听 ${esc(s.listeners)}${s.last_event_t?' · 最近 '+esc(s.last_event_t):''}</button>`+
(oj?`<button class="pill hot" aria-pressed="${onlyOver}" onclick="toggleOver()" title="有 ${oj} 件超时，点一下只看超时的，再点取消">要你判断 <b>${J.length}</b> · ${oj} 超时</button>`:`<span class="pill">要你判断 <b>${J.length}</b></span>`)+
(od?`<button class="pill hot" aria-pressed="${onlyOver}" onclick="toggleOver()" title="有 ${od} 件超时，点一下只看超时的，再点取消">草稿待发 <b>${D.length}</b> · ${od} 超时</button>`:`<span class="pill">草稿待发 <b>${D.length}</b></span>`)+
`<span class="pill">队列 <b>${s.queue||0}</b> · 处理中 <b>${s.processing||0}</b></span>`+
`<span class="pill">今天已处理 <b>${s.today_done}</b></span>`+
`<span class="pill">${esc(s.me||'')} · ${esc(s.time)}</span>`+
(onlyOver&&!oj&&!od?`<button class="pill toggle" aria-pressed="true" onclick="toggleOver()" title="正在只看超时的，点一下看全部">只看超时 ✕</button>`:''));
const b=$('chatBadge');b.hidden=!(oq||o.needs_attention);b.textContent=o.needs_attention?'!':oq;b.classList.toggle('red',!!o.needs_attention);
setHTML($('c-judge'),J.length+(oj?` · <span class="over-n">${oj} 超时</span>`:''));$('c-judge').className='cnt hot';
setHTML($('c-send'),D.length+(od?` · <span class="over-n">${od} 超时</span>`:''));$('c-send').className='cnt send';
$('c-done').textContent=s.done.length;$('doneSub').textContent='今天 '+s.today_done+' 件';const sentN=s.done.filter(d=>d.result==='已发送').length;
setHTML($('dtabs'),`<button aria-pressed="${dfilter==='all'}" onclick="dfilter='all';render()">全部</button><button aria-pressed="${dfilter==='sent'}" onclick="dfilter='sent';render()">已发送 ${sentN}</button>`);
const f=c=>matches(c)&&(!onlyOver||c.overdue),sortO=L=>[...L.filter(c=>c.overdue),...L.filter(c=>!c.overdue)];
syncList($('L-judge'),sortO(J.filter(f)).map(c=>({...c,_k:'judge'})));syncList($('L-send'),sortO(D.filter(f)).map(c=>({...c,_k:'send'})));
setHTML($('L-done'),s.done.filter(matches).filter(d=>dfilter==='all'||d.result==='已发送').map(doneCardH).join('')||(taskQuery?'<div class="empty">没有符合条件的记录</div>':(dfilter==='sent'?'<div class="empty"><span class="big">📭</span><b>还没有发出去的消息</b></div>':'<div class="empty"><span class="big">🗂️</span><b>还没有处理记录</b></div>')));
$('ver').textContent=s.version;setHTML($('foot'),`${esc(s.me||'')} · 今天已处理 ${s.today_done} · ${esc(s.version)} · ${esc(s.time)} 更新 · 作者：梦无矶`);
if($('chatPanel').classList.contains('on'))loadChat().catch(()=>{});
const open=[...s.judge,...s.send],now=new Set(open.map(c=>c.no));document.title=(J.length+D.length?'('+(J.length+D.length)+') ':'')+'群消息助手 · 操作台';
open.forEach(c=>{if(!seen.has(c.no)&&!first&&window.Notification&&Notification.permission==='granted'){const x=new Notification(`${c.draft?'草稿待发':'要你判断'} · ${c.who}`,{body:c.text.slice(0,90),tag:c.no});x.onclick=()=>{window.focus();focusCard(c.no)};notes[c.no]=x}});
Object.keys(notes).forEach(no=>{if(!now.has(no)){notes[no].close();delete notes[no]}});seen=now;first=false;for(const no of [...gone])if(!now.has(no))setTimeout(()=>gone.delete(no),400);
if(convNo&&convKind!=='done'){if(!findItem(convNo)){const was=convNo;closeConv(true);if(!gone.has(was))toast(was+' 已在别处处理')}else convFoot()}}
let ticking=false;async function tick(){if(ticking)return;ticking=true;try{const value=await api('/api/state');if(!value.judge)throw Error(value.msg||'无法读取状态');S=value;$('conn').classList.remove('on');render()}catch(e){$('conn').textContent='连接中断 · '+errText(e)+' · 正在重试（下面是最后一次读到的内容）';$('conn').classList.add('on')}finally{ticking=false}}
function focusCard(no){const c=findItem(no);if(!c)return;requestAnimationFrame(()=>{const el=document.querySelector(`.card[data-no="${CSS.escape(no)}"]`);if(!el)return;el.scrollIntoView({block:'nearest'});el.classList.add('flash');setTimeout(()=>el.classList.remove('flash'),2200)})}

// ---------- 操作：确认 → 卡片内显示进度和结果 → 处理完卡片收起 ----------
function confirmAction(action,c,text){return new Promise(resolve=>{const d=$('actionDialog'),note=$('actionNote'),manual=action==='manual_done',explain=manual||action==='not_mine',drop=action==='drop',ok=$('actionOK'),pv=$('actionPreview');
const where=c&&c.group?'「'+c.group+'」':'原会话',body=action==='send'?(c&&c.draft):text;
$('actionTitle').textContent=manual?'已手动处理':explain?'不归我':drop?'这条草稿不发':'发送到'+where;
$('actionHint').textContent=manual?'请说明你在哪里、如何处理了这条消息。已有验证任务会继续保留执行进度，不会据此标成验收通过。':explain?'请填写这件事不归你的原因。':drop?'草稿不会发出去，这件事会移到「已处理」。':'确认将下面这段回复以你的身份发到'+where+'？';
pv.hidden=explain||drop||!body;pv.innerHTML=body?readable(body):'';note.hidden=!explain;note.required=explain;note.value='';ok.className='btn '+(drop?'dp':'p');ok.textContent=manual||explain?'确认':drop?'确认不发':'确认发送';
let settled=false;const finish=value=>{if(settled)return;settled=true;d.close();resolve(value)};$('actionCancel').onclick=()=>finish(null);d.oncancel=e=>{e.preventDefault();finish(null)};ok.onclick=()=>{if(explain&&!note.value.trim()){note.setCustomValidity('请填写处理说明');note.reportValidity();return}finish(explain?note.value.trim():true)};
note.oninput=()=>note.setCustomValidity('');note.onkeydown=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();ok.click()}};note.setCustomValidity('');d.showModal();if(explain)note.focus();else ok.focus()})}
const DOING={send:'正在发送…',edit_send:'正在发送…',reply_new:'正在发送…',drop:'正在标记不发…',stash:'正在暂存…',ask:'正在提交问题…',not_mine:'正在标记不归我…',manual_done:'正在标记已处理…'};
const DONE={send:'已发送',edit_send:'已发送',reply_new:'已发送',drop:'已标记不发',not_mine:'已标记不归我',manual_done:'已标记已处理'};
async function go(no,action,text){if(pendingActions.has(no))return toast('这条消息正在处理，请稍候');const c=findItem(no);
if(['send','edit_send','reply_new','manual_done','not_mine','drop'].includes(action)){const answer=await confirmAction(action,c,text);if(answer===null)return;if(['manual_done','not_mine'].includes(action))text=answer}
pendingActions.add(no);U(no).st=['info','<span class="spin"></span>'+DOING[action]];render();
try{const r=await api('/api/act',{no,action,text:text||''}),msg=r.msg||'请查看处理结果',ok=msg==='已处理';
if(ok&&DONE[action]){U(no).st=['ok','✓ '+DONE[action]+'，这张卡片会移到「已处理」'];delete edits[no];doneCache.delete(no);pendingActions.delete(no);render();
const el=document.querySelector(`.card[data-no="${CSS.escape(no)}"]`);if(el)el.dataset.keep='1';toast(no+' '+DONE[action]);gone.add(no);setTimeout(()=>gone.delete(no),15000);
setTimeout(()=>{if(el){el.style.maxHeight=el.scrollHeight+'px';void el.offsetHeight;el.classList.add('leaving');setTimeout(()=>{el.remove();delete ui[no];render()},380)}},900);return}
if(ok&&action==='stash'){U(no).st=['ok','✓ 已暂存，没有发出'];delete edits[no]}
else if(action==='ask'){U(no).st=['info',esc(msg)];U(no).ask=false}
else U(no).st=['err',esc(msg)];if(!ok&&action!=='ask')toast(msg,'err')}
catch(e){U(no).st=['err',esc(e.name==='AbortError'?'等待结果超时，请先到「已处理」里确认，勿重复发送':'操作未确认：'+e.message)]}
finally{pendingActions.delete(no);render();tick()}}

// ---------- 会话抽屉：点卡片打开，像 v1 一样直接看原会话并定位到被提及的那条 ----------
let convNo=null,convKind='',convReq=0;
function cardClick(e,no){if(e.target.closest('button,a,input,textarea,select,label,summary,.c-ask'))return;openConv(no)}
function markSel(){document.querySelectorAll('main .card').forEach(e=>e.classList.toggle('sel',e.dataset.no===convNo))}
function bubbles(rows,source){return rows.map(m=>{const a=m.anchor||(!m.reply&&m.text&&source&&String(source).startsWith(String(m.text||'').slice(0,30)));return `<div class="bub${m.reply?' reply':a?' anchor':''}"${a?' data-anchor="1"':''}>${av(m.who)}<div class="b">${m.reply?'<div class="lab">已发送回复</div>':a?'<div class="lab">被提及的原消息</div>':''}<div class="w"><b>${esc(m.who)}</b><span>${esc((m.time||'').slice(5,16))}</span></div><div class="tx readable">${readable(m.text)}</div></div></div>`}).join('')}
function scrollAnchor(){requestAnimationFrame(()=>{const b=$('cbody'),a=b.querySelector('[data-anchor]');if(a){a.scrollIntoView({block:'center'});a.classList.add('pulse')}else b.scrollTop=1e9})}
function showConv(){for(const x of ['panel','chatPanel'])$(x).classList.remove('on');$('mask').classList.remove('on');$('conv').classList.add('on');markSel()}
function closeConv(silent){if(!$('conv').classList.contains('on')&&!convNo)return;$('conv').classList.remove('on');convNo=null;convKind='';convReq++;markSel()}
async function openConv(no){if(!S)return;const c=findItem(no);if(!c)return openDoneConv(no);convNo=no;convKind=c._k;const r=++convReq;showConv();
$('cav').innerHTML=av(c.who);$('ctitle').textContent=c.who;$('csub').textContent=`${c.group||'私聊'} · ${no} · ${c.at}`;
$('cbody').innerHTML='<div class="skeleton short"></div><div class="skeleton"></div><div class="skeleton"></div>';$('cfoot').innerHTML='';$('cfoot')._h=null;convFoot();
try{const t=await api('/api/thread?no='+encodeURIComponent(no));if(r!==convReq)return;$('cbody').innerHTML=bubbles(t,c.text)+(c.reason?`<div class="cnote"><b>AI 判断：</b>${esc(c.reason)}</div>`:'');scrollAnchor()}
catch(e){if(r===convReq)$('cbody').innerHTML='<div class="empty">读取会话失败：'+esc(errText(e))+'<br>卡片上的按钮照常可用</div>'}}
function convFoot(){const c=findItem(convNo);if(!c)return;const f=$('cfoot'),no=c.no;
if(c.can_send&&!f.querySelector('textarea')){f.innerHTML=`${c._k==='send'?`<label class="ailab">${IC.ai}AI 草稿 <span>可以直接改，和卡片上同步</span></label>`:'<div class="cl">回复内容</div>'}<textarea id="convTa"${c._k==='send'?' class="ai"':''} aria-label="${c._k==='send'?'AI 草稿，可以直接改':'回复内容'}" placeholder="写回复内容；Ctrl+Enter 也可以发送"></textarea><div class="c-acts" id="convActs"></div><div class="c-ask" id="convAsk" hidden><input class="q" id="convAskQ" aria-label="问 AI" placeholder="问 AI：依据是什么？帮我改得客气点…" onkeydown="if(event.key===\'Enter\'&&!event.isComposing)askConv()"><button class="act ai" onclick="askConv()">提问</button></div><div class="c-status" id="convSt"></div>`;
const ta=$('convTa');ta.value=edits[no]??(c.draft||'');ta.oninput=()=>{edits[no]=ta.value;render()};ta.onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.isComposing){e.preventDefault();sendCard(no)}}}
else if(!c.can_send&&!$('convActs')){f.innerHTML='<div class="cl">这个群设为只看，请在钉钉里回复</div><div class="c-acts" id="convActs"></div><div class="c-ask" id="convAsk" hidden><input class="q" id="convAskQ" aria-label="问 AI" placeholder="问 AI：依据是什么？帮我改得客气点…" onkeydown="if(event.key===\'Enter\'&&!event.isComposing)askConv()"><button class="act ai" onclick="askConv()">提问</button></div><div class="c-status" id="convSt"></div>'}
const ta=$('convTa');if(ta&&document.activeElement!==ta){const want=edits[no]??(c.draft||'');if(ta.value!==want)ta.value=want}
const busy=pendingActions.has(no),dis=busy?'disabled':'',edited=c._k==='send'&&curText(no).trim()!==String(c.draft||'').trim();
setHTML($('convActs'),(c.can_send?B('send',`sendCard('${no}')`,IC.send+(c._k==='send'?(edited?'改了再发':'发送'):'发送回复'),dis)+B('stash',`stashCard('${no}')`,IC.stash+'暂存',dis):'')+
B('done',`go('${no}','manual_done')`,'已手动处理',dis)+(c._k==='send'?B('no',`go('${no}','drop')`,'不发',dis):B('no',`go('${no}','not_mine')`,'不归我',dis))+B('ai','toggleConvAsk()',IC.ai+'问 AI',dis,`aria-expanded="${!$('convAsk').hidden}"`));
const u=U(no),st=$('convSt');st.className='c-status'+(u.st?' '+u.st[0]:'');setHTML(st,u.st?u.st[1]:'')}
function toggleConvAsk(){const a=$('convAsk');a.hidden=!a.hidden;convFoot();if(!a.hidden)$('convAskQ').focus()}
function askConv(){const no=convNo,q=$('convAskQ'),t=q?q.value.trim():'';if(!t)return setStatus(no,'err','先写下要问 AI 的问题');go(no,'ask',t).then(()=>{if(q)q.value='';if($('convAsk'))$('convAsk').hidden=true;convFoot()})}
async function openDoneConv(no){const d0=S.done.find(x=>x.no===no);if(!d0)return;convNo=no;convKind='done';const r=++convReq;showConv();
$('cav').innerHTML=av(d0.who);$('ctitle').textContent=d0.who;$('csub').textContent=`${no} · ${d0.done} 处理`;$('cbody').innerHTML='<div class="skeleton short"></div><div class="skeleton"></div>';$('cfoot').innerHTML='';$('cfoot')._h=null;
try{const d=doneCache.get(no)||await api('/api/done?no='+encodeURIComponent(no));if(r!==convReq)return;if(!d.no)throw Error('没找到这条记录');doneCache.set(no,d);
$('csub').textContent=`${d.group||''} · ${no} · 收到 ${d.at||''} · 处理 ${d.done||''}`;$('cbody').innerHTML=bubbles(d.thread||[],d.text)+(d.reason?`<div class="cnote"><b>AI 判断：</b>${esc(d.reason)}</div>`:'')+(d.qa||[]).map(q=>`<div class="cnote"><b>问 AI：</b>${esc(q['问'])}<div class="readable">${readable(q['答'])}</div></div>`).join('');
$('cfoot').innerHTML=d.sent?`<div class="sent"><div class="l">已发出${d.sent_at?' · '+esc(d.sent_at):''}</div>${esc(d.sent)}</div>${d.confirm?`<div class="cl" style="margin-top:6px">确认方式：${esc(d.confirm)}</div>`:''}`:`<div class="cl">处理说明</div><div class="readable">${readable(d.why)}</div>`;scrollAnchor()}
catch(e){if(r===convReq)$('cbody').innerHTML='<div class="empty">读取失败：'+esc(errText(e))+'</div>'}}

// ---------- 抽屉：每日汇报 / 各群最近消息 / 调试群对话 ----------
function openDrawer(id){lastFocus=document.activeElement;for(const x of ['panel','chatPanel'])$(x).classList.toggle('on',x===id);closeConv(true);$('mask').classList.add('on')}
function closeAll(){const was=$('panel').classList.contains('on')||$('chatPanel').classList.contains('on');$('panel').classList.remove('on');$('chatPanel').classList.remove('on');$('mask').classList.remove('on');if(was&&lastFocus&&document.contains(lastFocus))lastFocus.focus({preventScroll:true})}
let preq=0;
// 每日汇报：和调试群机器人发的「每日汇报」同一份内容，只读本机记录，不另外发钉钉
async function openReports(){const r=++preq;openDrawer('panel');$('ptitle').textContent='每日汇报';$('psub').textContent='和调试群里机器人发的汇报一致，只存在本机';$('pbody').innerHTML='<div class="skeleton"></div><div class="skeleton short"></div>';
try{const rows=await api('/api/reports');if(r!==preq)return;$('pbody').innerHTML=rows.map(x=>`<div class="item"><div class="w">${esc(x.time)} · ${esc(x.title)}</div><div class="readable">${readable(x.text)}</div></div>`).join('')||'<div class="empty">还没有汇报记录（每天上岗时会发一份）</div>'}catch(e){if(r===preq)$('pbody').textContent='读取失败：'+errText(e)}}
// 顶栏「值守中」点开：按群看最近消息
let hgroups=null;
function htabs(gs){return '<div class="gtabs" role="group" aria-label="选择群">'+gs.map(g=>`<button class="btn sm${g.cid===hsel?' p':''}" aria-pressed="${g.cid===hsel}" onclick="openH('${g.cid}')">${esc(g.name)}</button>`).join('')+'</div>'}
async function openH(cid){const r=++preq;if(!$('panel').classList.contains('on'))openDrawer('panel');$('ptitle').textContent='最近消息';$('psub').textContent='按群看，每个群最近 30 条 · 只读，要回复请在卡片或钉钉里处理';
if(!hgroups||!cid){$('pbody').innerHTML='<div class="skeleton"></div><div class="skeleton short"></div><div class="skeleton"></div>';try{hgroups=await api('/api/groups')}catch(e){if(r===preq)$('pbody').textContent='读取失败：'+errText(e);return}if(r!==preq)return}
const gs=hgroups;if(!gs.length){$('pbody').innerHTML='<div class="empty">没有监听的群</div>';return}hsel=cid||hsel||gs[0].cid;
$('pbody').innerHTML=htabs(gs)+'<div class="skeleton"></div><div class="skeleton short"></div><div class="skeleton"></div>';
let t;try{t=await api('/api/history?cid='+encodeURIComponent(hsel))}catch(e){if(r===preq)$('pbody').innerHTML=htabs(gs)+'<div class="empty">读取失败：'+esc(errText(e))+'</div>';return}if(r!==preq||!$('panel').classList.contains('on'))return;
$('pbody').innerHTML=htabs(gs)+(t.map(m=>`<div class="bub">${av(m.who)}<div class="b"><div class="w"><b>${esc(m.who)}</b><span>${esc((m.time||'').slice(5,16))}</span></div><div class="tx readable">${readable(m.text)}</div></div></div>`).join('')||'<div class="empty">没有消息</div>');$('pbody').scrollTop=1e9}
// 调试群对话：钉钉调试群里你和机器人的对话原样搬到这里；在这里发 = 以你的身份发到调试群，两边始终一致
const STAGE={queued:'已排队',running:'处理中',replied:'已回复',answered:'已回复',done:'已处理',failed:'处理失败',interrupted:'中断了'};
async function loadChat(){const rows=await api('/api/chat');const b=$('chatBody'),atEnd=b.scrollTop+b.clientHeight>=b.scrollHeight-40;
const h=rows.map(r=>r.me?`<div class="item me"><div class="w">你 · ${esc(r.time)}${r.stage?' · '+esc(STAGE[r.stage]||r.stage):''}</div><div class="readable">${readable(r.text)}</div>${r.error?`<div class="w" style="color:var(--red)">${esc(r.error)}</div>`:''}</div>`
:`<div class="item"><div class="w">机器人 · ${esc(r.time)}${r.delivered===false?' · <span class="tag t-red">钉钉没送达</span>':''}</div><div class="readable"><b>${esc(r.title||'')}</b></div><div class="readable">${readable(r.text)}</div></div>`).join('')||'<div class="empty">还没有对话</div>';if(setHTML(b,h)&&atEnd)b.scrollTop=1e9}
function openChat(){openDrawer('chatPanel');if(!$('chatBody').innerHTML)$('chatBody').innerHTML='<div class="skeleton"></div><div class="skeleton short"></div>';loadChat().then(()=>{$('chatBody').scrollTop=1e9;$('chatInput').focus()}).catch(e=>{$('chatBody').textContent='读取失败：'+errText(e)})}
async function sendChat(){const t=$('chatInput').value.trim();if(!t)return;const btn=$('chatSend');$('chatInput').value='';btn.disabled=true;let r=null;try{r=await api('/api/say',{text:t})}catch(e){}finally{btn.disabled=false}
if(!r||!r.msg){$('chatInput').value=t;return toast('没发出去，内容已放回输入框','err')}toast(r.msg);loadChat().catch(()=>{});setTimeout(()=>loadChat().catch(()=>{}),3000)}

// 外观：跟随系统 / 浅色 / 深色（只记在这个浏览器里）
let theme='auto';try{theme=localStorage.getItem('qa-theme')||'auto'}catch(e){}
const THEME={auto:'跟随系统',light:'浅色',dark:'深色'};
function applyTheme(){if(theme==='auto')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=theme;$('themeBtn').innerHTML='<span class="em" aria-hidden="true">🌓</span>';$('themeBtn').setAttribute('aria-label','外观：'+THEME[theme]);$('themeBtn').title='外观：'+THEME[theme]+'（点一下切换）'}
function cycleTheme(){theme={auto:'light',light:'dark',dark:'auto'}[theme]||'auto';try{localStorage.setItem('qa-theme',theme)}catch(e){}applyTheme()}
applyTheme();
// 键盘只保留通用习惯：Esc 关闭抽屉 / 清空搜索；回复框里 Ctrl(⌘)+Enter 发送；单行输入框回车提交
document.addEventListener('keydown',e=>{if(e.key!=='Escape'||document.querySelector('dialog[open]'))return;if($('panel').classList.contains('on')||$('chatPanel').classList.contains('on')){e.preventDefault();return closeAll()}if($('conv').classList.contains('on')&&!/^(INPUT|TEXTAREA)$/.test(e.target.tagName)){e.preventDefault();return closeConv()}
if(e.target.id==='taskSearch'&&e.target.value){e.target.value='';taskQuery='';render()}});
if(window.Notification&&Notification.permission==='default'){$('notif').style.display='';$('notif').onclick=()=>Notification.requestPermission().then(()=>$('notif').style.display='none')}
// 有新事件时助手会用浏览器打开带 focus 的链接（弹到最前面）；新页面打开后通知旧页面关掉，始终只留一个操作台
const FOCUS=new URLSearchParams(location.search).get('focus');let alive=true;
try{const bc=new BroadcastChannel('qa-console');const me=Date.now()+Math.random();bc.postMessage({t:'new',me});
bc.onmessage=m=>{if(m.data&&m.data.t==='new'&&m.data.me!==me){alive=false;window.close();setTimeout(()=>{document.body.innerHTML='<div class="empty" style="margin-top:20vh">操作台已在新标签页打开，这一页可以关掉了。</div>'},300)}}}catch(e){}
tick().then(()=>{if(FOCUS){focusCard(FOCUS);history.replaceState(null,'',location.pathname+location.search.replace(/[&?]focus=[^&]*/,''))}});setInterval(()=>{if(alive)tick()},3000);
</script></body></html>"""
PAGE = PAGE.replace("__HELP_URL__", HELP_URL)
