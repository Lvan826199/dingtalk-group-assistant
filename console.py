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


def notification_body(text):
    """只整理阅读格式，不删事实；代码、路径和 Markdown 链接保持原样。"""
    parts = re.split(r"(```[\s\S]*?```|`[^`\n]+`|\[[^\]\n]+\]\([^\s)]+\))", str(text or ""))
    labels = r"群|任务|时间|消息时间|处理时间|原消息|结论|当前状态|进度|已核实|已完成|待处理|下一步|需要你决定|需要你做|原因|错误|背景|依据|草稿|新草稿|建议回复|要发的内容|操作|你的问题|答复|已回复|验收完成"
    for index in range(0, len(parts), 2):
        value = parts[index].replace("\\r\\n", "\n").replace("\\n", "\n")
        value = re.sub(r"\r\n?", "\n", value)
        lines = []
        for line in value.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.fullmatch(r"【[^\n]{1,100}】", line):
                line = "**" + line[1:-1] + "**"
            else:
                if re.match(r"^(?:群|任务|时间|消息时间|处理时间)[：:]", line):
                    line = re.sub(r"^([^：:]+)[：:]\s*", r"**\1：** ", line)
                else:
                    line = re.sub(r"^(" + labels + r")[：:]\s*", r"**\1**\n\n", line)
            # 很长的自然段按完整中文句子分段，保留数字、URL和原有顺序。
            chunks = line.split("\n\n")
            for n, chunk in enumerate(chunks):
                if len(chunk) > 180 and not re.match(r"^(?:[-*>#]|\d+[.)、）])", chunk):
                    chunks[n] = re.sub(r"([。；])(?=[^\n])", r"\1\n\n", chunk)
            line = "\n\n".join(chunks)
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
    return "".join(parts).strip()


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
            "owner": A["owner_snapshot"](), "executions": A["execution_snapshot"](30),
            "notifications": [{**x, "display_text": notification_body(x.get("text", ""))}
                              for x in A["notification_snapshot"]()],
            "time": time.strftime("%H:%M:%S")}


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
    if not re.fullmatch(r"#[A-Za-z0-9]{3,8}", no or ""):
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
        if u.path == "/api/state":
            return self._send(200, json.dumps(state(), ensure_ascii=False))
        if u.path == "/api/execution":
            key = (urllib.parse.parse_qs(u.query).get("key") or [""])[0]
            rec = A["_commit_load"]().get(key) or {}
            if not rec.get("execution_kind"):
                return self._send(404, "{}")
            output = ""
            path = (rec.get("execution_run") or {}).get("log")
            if path:
                try:
                    with open(path, "rb") as f:
                        f.seek(max(0, os.path.getsize(path) - 30000))
                        output = f.read().decode("utf-8", errors="replace")
                except OSError:
                    output = "运行日志暂不可读，请检查本机权限。"
            return self._send(200, json.dumps({"task": rec, "output": output}, ensure_ascii=False))
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
        if path == "/api/execution":
            if not self._local():
                return self._send(403, '{"msg":"只允许本机桥接调用"}')
            try:
                rec = A["external_execution_progress"](body)
            except (ValueError, TypeError) as ex:
                return self._send(400, json.dumps({"msg": str(ex)}, ensure_ascii=False))
            return self._send(200, json.dumps({"ok": True, "status": rec["status"]}))
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
            no_hint = "#" + re.sub(r"[^A-Za-z0-9]", "", message_id)[-5:]
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
.dtabs{display:flex;gap:6px;margin:0 0 10px}.draft.sent{background:var(--green-soft)}.draft.sent::before{content:"已发出";color:var(--green)}.t-gray{background:var(--soft);color:var(--muted)}
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
dialog{max-width:520px;width:calc(100% - 32px);border:1px solid var(--border);border-radius:14px;background:var(--surface);color:var(--text);padding:22px;box-shadow:var(--shadow-h)}dialog::backdrop{background:rgba(15,23,42,.45)}dialog h3{margin:0 0 12px}dialog textarea{width:100%;min-height:95px;margin:12px 0}.progress{margin:10px 0;padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--soft);white-space:pre-wrap}.progress b{color:var(--text)}
#monitorDialog{max-width:760px;max-height:90vh;overflow:auto}#monitorDialog label{display:block;margin:10px 0 6px}#monitorDialog input[type=time],#monitorDialog select{padding:8px;border:1px solid var(--border);border-radius:8px;font:inherit;background:var(--surface);color:var(--text)}.monitor-row{padding:12px 0;border-bottom:1px solid var(--border)}.monitor-row .btns{margin-top:8px}.monitor-hint{font-size:13px;color:var(--muted);white-space:pre-wrap}.monitor-error{color:var(--red);margin:10px 0;white-space:pre-wrap}#monitorEditor{margin:16px 0;padding:14px;background:var(--soft);border-radius:10px}#monitorResults{max-height:190px;overflow:auto}#monitorResults button{display:block;width:100%;text-align:left;margin-top:6px}

.btn:disabled{opacity:.55;cursor:wait;filter:none}.card[aria-busy=true]{opacity:.7;pointer-events:none}
.ownerbar{margin:14px 24px 0;border:1px solid var(--border);border-radius:12px;background:var(--surface);flex:none;overflow:hidden}
.ownerbar summary{cursor:pointer;padding:11px 14px;display:flex;gap:10px;align-items:center;font-size:13px}.ownerbar summary:before{content:'›';font-size:20px;color:var(--muted)}.ownerbar[open] summary:before{transform:rotate(90deg)}.ownerbar summary .sp{color:var(--muted);font-size:12px}.owner-list{max-height:300px;overflow:auto;border-top:1px solid var(--border);padding:4px 14px}
.owner-item{padding:12px 0;border-bottom:1px solid var(--line)}.owner-item:last-child{border:0}.owner-question{margin:7px 0;white-space:pre-wrap;overflow-wrap:anywhere}.owner-answer{border-left:3px solid var(--blue);padding:8px 12px;background:var(--soft);margin:8px 0;border-radius:0 8px 8px 0;color:var(--text)}.readable{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}.readable p{margin:0 0 10px}.readable p:last-child{margin-bottom:0}.readable code{font-size:.92em;background:var(--blue-soft);padding:1px 4px;border-radius:4px}.owner-item .when{font-size:12px}
.toolbar{display:flex;gap:10px;align-items:center;margin:14px 24px 0;flex:none}.toolbar input{max-width:460px;background:var(--surface)}.toolbar span{font-size:12px;color:var(--muted)}
.card .draft{display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden}.card .why{display:block}.card .why:before{content:none}.c3 .card{opacity:1}.card-hint{margin-top:6px;font-size:12px;color:var(--muted)}
.progress.reply{border-color:var(--border);background:var(--green-soft);color:var(--text)}.progress summary{cursor:pointer;font-weight:600}.t-wait{color:var(--amber);background:var(--amber-soft)}.progress.exec{border-left:3px solid var(--blue)}
.bub.anchor .b{background:var(--amber-soft);border:2px solid var(--amber);color:var(--text)}.bub.reply .b{background:var(--green-soft);border:2px solid var(--green);color:var(--text)}.bubble-label{display:inline-block;margin-bottom:5px;padding:2px 7px;border-radius:5px;font-size:12px;font-weight:700;background:var(--amber);color:#fff}.bub.reply .bubble-label{background:var(--green)}.bub.anchor .w,.bub.reply .w,.bub.anchor .w span,.bub.reply .w span{color:var(--text)}.skeleton{height:16px;border-radius:6px;background:var(--border);margin:12px 0;animation:fade 1.2s infinite alternate}.skeleton.short{width:60%}.loading-note{color:var(--muted);font-size:13px;margin:12px 0}@keyframes fade{to{opacity:.35}}
@media(prefers-color-scheme:dark){.bubble-label{color:#171d29}.btn.p{color:#101726}.where,.when,.no,.ch .sub{color:#a8b3c5}}
@media(max-width:980px){.ownerbar,.toolbar{margin:12px 14px 0}.ownerbar summary{flex-wrap:wrap}.toolbar{flex-wrap:wrap}.toolbar input{max-width:none}header{padding:12px 14px;gap:10px}.chips{gap:5px}.owner-list{max-height:250px}.ownerbar summary .sp{flex-basis:100%;margin-left:20px}}
</style></head><body>
<header><div class="brand"><span class="logo">群</span>操作台</div><div class="chips" id="stat"><span class="chip">连接中…</span></div><span class="sp"></span>
<button class="btn sm" onclick="openMonitor()">监听设置</button><button class="btn sm" id="notif" style="display:none">🔔 开启桌面通知</button><span class="ver" id="ver"></span></header>
<details class="ownerbar" id="ownerTray"><summary><b>你的消息</b><span id="ownerCount" class="tag t-gray">读取中</span><span class="sp">调试群提问的接收、处理和回复记录</span></summary><div id="ownerList" class="owner-list"></div></details>
<details class="ownerbar" id="notificationTray"><summary><b>机器人通知</b><span id="notificationCount" class="tag t-gray">读取中</span><span class="sp">调试群回执与通知；投递成功不代表任务完成</span></summary><div id="notificationList" class="owner-list"></div></details>
<details class="ownerbar" id="executionTray" open><summary><b>执行任务</b><span id="executionCount" class="tag t-gray">读取中</span><span class="sp">接口回归与复测；回复和实际执行分开记录</span></summary><div id="executionList" class="owner-list"></div></details>
<div class="toolbar"><input class="q" id="taskSearch" aria-label="搜索任务" placeholder="搜索群名、任务编号、消息或回复…" oninput="taskQuery=this.value;render()"><span>已回复与实际执行进度分别显示</span></div>
<main>
<section class="col c1"><div class="ch"><span class="ic">✋</span><div><h2>要你判断</h2><div class="sub">拿不准是不是归你、要不要接</div></div><span class="cnt" id="n1">0</span></div><div class="list" id="judge"></div></section>
<section class="col c2"><div class="ch"><span class="ic">✉️</span><div><h2>草稿待发</h2><div class="sub">AI 写好了，你点头才发</div></div><span class="cnt" id="n2">0</span></div><div class="list" id="send"></div></section>
<section class="col c3"><div class="ch"><span class="ic">✓</span><div><h2>已处理</h2><div class="sub">页面、提醒群、原会话里处理的都算</div></div><span class="cnt" id="n3">0</span></div><div class="list" id="done"></div></section>
</main>
<div class="mask" id="mask" onclick="closeP()"></div>
<aside id="panel"><div class="ph"><span class="av" id="pav"></span><div><div class="t" id="ptitle"></div><div class="s" id="psub"></div></div><span class="sp"></span><button class="btn sm" onclick="closeP()">关闭</button></div><div class="pb" id="pbody"></div><div class="pf" id="pfoot"></div></aside>
<div class="toast" id="toast"></div>
<dialog id="actionDialog"><h3 id="actionTitle"></h3><div id="actionHint"></div><textarea id="actionNote" placeholder="例如：我已在群里回复，后续等待研发提供样本"></textarea><div class="btns"><button class="btn" id="actionCancel">取消</button><button class="btn p" id="actionOK">确认</button></div></dialog>
<dialog id="monitorDialog" aria-labelledby="monitorTitle"><div class="btns"><h3 id="monitorTitle" style="flex:1">监听设置</h3><button class="btn sm" onclick="$('monitorDialog').close()">关闭</button></div>
<p class="monitor-hint">调整群消息助手的监听群和每日时段。所有群回复仍需你确认；Jira、定时回归及其他值守脚本按各自规则运行。</p>
<div id="monitorError" class="monitor-error" role="status"></div>
<label>每日监听时间 <span id="monitorTimezone" class="monitor-hint"></span></label><div class="btns"><input type="time" id="monitorStart" aria-label="监听开始时间"> 至 <input type="time" id="monitorEnd" aria-label="监听结束时间"><label style="margin:0"><input type="checkbox" id="monitorAllDay" onchange="monitorAllDayChanged()"> 全天监听</label><button class="btn p" id="monitorTimeSave" onclick="saveMonitorTime()">保存时段</button></div>
<p class="monitor-hint">结束早于开始表示跨午夜。时间外暂停监听，操作台保持可用；已开始的任务继续完成，恢复后补读。电脑需保持开机，助手需保持运行。</p>
<div class="btns" style="margin-top:22px"><b style="flex:1">监听的群</b><button class="btn p" onclick="newMonitorGroup()">新增监听群</button></div><div id="monitorGroups"></div>
<div id="monitorEditor" hidden><h4 id="monitorEditorTitle">新增监听群</h4><div id="monitorSearchBox"><label for="monitorQuery">搜索钉钉群</label><div class="askrow"><input class="q" id="monitorQuery" placeholder="输入群名关键词" maxlength="100" onkeydown="if(event.key==='Enter')searchMonitorGroups()"><button class="btn" id="monitorSearch" onclick="searchMonitorGroups()">搜索</button></div><div id="monitorSearchHint" class="monitor-hint"></div><div id="monitorResults"></div></div>
<p id="monitorChosen" class="monitor-hint"></p><label for="monitorRule">监听说明（选填）</label><textarea id="monitorRule" maxlength="2000" placeholder="例如：关注发版、接口变更，以及涉及我的验收安排。留空则沿用已有规则。"></textarea>
<label for="monitorMode">处理方式</label><select id="monitorMode"><option value="draft">生成草稿，确认后发送</option><option value="readonly">只监听提醒，不向此群发草稿</option></select>
<label><input type="checkbox" id="monitorPaused"> 暂停监听此群</label><div class="btns"><button class="btn p" id="monitorGroupSave" onclick="saveMonitorGroup()">保存监听群</button><button class="btn" onclick="$('monitorEditor').hidden=true">取消</button></div></div>
</dialog>
<script>
const K=new URLSearchParams(location.search).get('k')||'';let dfilter='all',S=null,sel=null,seen=new Set(),first=true;const notes={};let panelRequest=0,taskQuery='';const pendingActions=new Set(),edits={},questions={},doneCache=new Map();
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const COLORS=['#3360e6','#1c8a4a','#c27a00','#8a4fd8','#d23b3b','#0f8f9e','#c2477d','#5b6b86'];
function av(n){n=String(n||'?');let h=0;for(const ch of n)h=(h*31+ch.charCodeAt(0))>>>0;return `<span class="av" style="background:${COLORS[h%COLORS.length]}">${esc(n.replace(/[-_ ].*/,'').slice(-2))}</span>`}
function toast(t){const x=$('toast');x.textContent=t;x.classList.add('on');clearTimeout(x._t);x._t=setTimeout(()=>x.classList.remove('on'),2600)}
async function api(p,b){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),b?90000:15000);try{const r=await fetch(p+(p.includes('?')?'&':'?')+'k='+encodeURIComponent(K),b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b),signal:controller.signal}:{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error(r.status===403?'操作台授权已失效，请重新打开本人链接':'助手返回错误 '+r.status);return await r.json()}finally{clearTimeout(timer)}}
function readable(text){return esc(text).split(/\n\s*\n/).map(p=>'<p>'+p.replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`\n]+)`/g,'<code>$1</code>')+'</p>').join('')}
function execLabel(status){return {committed:'待执行',starting:'正在启动',interrupted:'执行中断待核实',running:'执行中',waiting_resources:'等待前置',waiting_dependency:'等待配合',completed:'已完成',done:'已完成',failed:'执行异常',declined:'已拒接'}[status]||status||''}
function renderOwners(){const o=S.owner||{queued:0,running:0,needs_attention:0,recent:[]},count=$('ownerCount');count.textContent=o.running+' 处理中 · '+o.queued+' 排队'+(o.needs_attention?' · '+o.needs_attention+' 需关注':'');count.className='tag '+(o.needs_attention?'t-red':o.running||o.queued?'t-wait':'t-gray');const labels={queued:'排队中',running:'处理中',replied:'已回复',handled:'指令已处理',failed:'处理失败',interrupted:'处理中断'};const html=o.recent.map(x=>`<div class="owner-item"><span class="tag ${['failed','interrupted'].includes(x.stage)?'t-red':x.stage==='replied'?'t-ok':x.stage==='queued'||x.stage==='running'?'t-wait':'t-gray'}">${esc(labels[x.stage]||x.stage)}</span> <span class="when">${esc(x.message_time||'')}${['queued','running'].includes(x.stage)?' · 已等待 '+Math.floor(x.age_seconds/60)+' 分钟':''}</span><div class="owner-question">${esc(x.question)}</div>${x.error?`<div class="tag t-red">${esc(x.error)}</div>`:''}${x.answer?`<details><summary class="card-hint">查看答复</summary><div class="owner-answer readable">${readable(x.answer)}</div></details>`:''}</div>`).join('')||'<div class="loading-note">暂时没有调试群提问记录；新问题会显示接收和回复状态。</div>';if($('ownerList').dataset.content!==html){const expanded=new Set([...$('ownerList').querySelectorAll('.owner-item')].flatMap((el,i)=>el.querySelector('details[open]')?[i]:[]));$('ownerList').innerHTML=html;$('ownerList').dataset.content=html;[...$('ownerList').querySelectorAll('.owner-item')].forEach((el,i)=>{if(expanded.has(i)&&el.querySelector('details'))el.querySelector('details').open=true})}}
function renderNotifications(){const rows=S.notifications||[];$('notificationCount').textContent='最近 '+rows.length+' 条';const html=rows.map(x=>`<div class="owner-item" data-id="${esc(x.notification_id)}"><span class="tag ${x.delivered?'t-ok':'t-red'}">${x.delivered?'机器人已送达':'机器人未送达'}</span> <span class="when">${esc((x.time||'').replace('T',' '))}</span><div class="owner-question">${esc(x.title)}</div>${x.group?`<div class="where">${esc(x.group)}</div>`:''}<details><summary class="card-hint">查看完整通知</summary><div class="owner-answer readable">${readable(x.display_text||x.text)}</div></details></div>`).join('')||'<div class="loading-note">暂无机器人通知记录。</div>';const el=$('notificationList');if(el.dataset.content!==html){const expanded=new Set([...el.querySelectorAll('.owner-item')].filter(x=>x.querySelector('details[open]')).map(x=>x.dataset.id));el.innerHTML=html;el.dataset.content=html;[...el.querySelectorAll('.owner-item')].forEach(x=>{if(expanded.has(x.dataset.id))x.querySelector('details').open=true})}}
function renderExecutions(){const rows=S.executions||[];$('executionCount').textContent=rows.filter(x=>!['completed','declined'].includes(x.status)).length+' 未完成';const el=$('executionList'),html=rows.map(x=>{const run=x.execution_run||{},last=(x.history||[]).slice(-1)[0]||{};return `<div class="owner-item"><span class="tag ${x.status==='completed'?'t-ok':['failed','interrupted'].includes(x.status)?'t-red':'t-wait'}">${esc(x.execution_backend==='external'&&x.status==='committed'?'待值守执行回执':execLabel(x.status))}</span><div class="owner-question">${esc(x.commitment_text)}</div><div class="where">${esc(last.at||x.confirmed_at)} · ${esc(last.detail||x.next_action||'')}</div>${run.id?`<div class="where">运行编号：${esc(run.id)} · ${esc(run.environment)}${run.total!=null?' · '+esc(run.passed)+'/'+esc(run.total):''}</div><div class="where">日志：${esc(run.log)}</div>`:''}<button class="btn sm" onclick="openExecution('${esc(x.task_key)}')">查看进度与日志</button></div>`}).join('')||'<div class="loading-note">暂无已确认的回归或复测任务。</div>';if(el.dataset.content!==html){el.innerHTML=html;el.dataset.content=html}}
async function openExecution(key){sel=null;const request=++panelRequest;$('mask').classList.add('on');$('panel').classList.add('on');$('ptitle').textContent='执行任务';$('psub').textContent='实际运行日志与结果';$('pbody').innerHTML=loading('正在读取执行进度…');$('pfoot').innerHTML='';try{const r=await api('/api/execution?key='+encodeURIComponent(key));if(request!==panelRequest)return;const x=r.task;$('pbody').innerHTML=`<div class="note readable"><h4>${esc(execLabel(x.status))}</h4>${readable(x.commitment_text)}${(x.history||[]).map(h=>`<p><b>${esc(h.at)} · ${esc(h.stage)}</b><br>${esc(h.detail)}</p>`).join('')}</div><div class="note"><h4>实际运行输出（末30KB）</h4><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(r.output||'尚无运行输出；任务未执行时不生成虚假日志。')}</pre></div>`}catch(e){if(request===panelRequest)$('pbody').textContent='读取失败：'+e.message}}
function matches(c){return !taskQuery||[c.no,c.who,c.group,c.text,c.what,c.draft,c.sent,c.reason,c.why].some(x=>String(x||'').toLowerCase().includes(taskQuery.trim().toLowerCase()))}
function bubbles(rows,source=''){return rows.map(m=>{const anchor=m.anchor||(!m.reply&&m.text&&source&&source.startsWith(String(m.text||'').slice(0,30)));return `<div class="bub${m.reply?' reply':anchor?' anchor':''}" ${anchor?'data-anchor="true"':''}>${av(m.who)}<div class="b">${m.reply||anchor?`<div class="bubble-label">${m.reply?'已发送回复':'被提及的原消息'}</div>`:''}<div class="w">${esc(m.who)}<span>${esc((m.time||'').slice(5,16))}</span></div><div class="tx readable">${readable(m.text)}</div></div></div>`}).join('')}
function loading(text){return `<div role="status" aria-live="polite"><div class="loading-note">${esc(text)}</div><div class="skeleton"></div><div class="skeleton short"></div><div class="skeleton"></div></div>`}
function anchorScroll(){requestAnimationFrame(()=>{const target=$('pbody').querySelector('[data-anchor]');if(target)target.scrollIntoView({block:'center'});else $('pbody').scrollTop=0})}

let monitorState=null,monitorChoice=null,monitorMatches=[],monitorSearchSeq=0;
function monitorError(text){$('monitorError').textContent=text||''}
function monitorAllDayChanged(){for(const id of ['monitorStart','monitorEnd'])$(id).disabled=$('monitorAllDay').checked}
async function openMonitor(){const d=$('monitorDialog');if(!d.open)d.showModal();monitorError('正在读取设置…');$('monitorEditor').hidden=true;
try{const s=await api('/api/monitor');if(!s.groups)throw Error(s.msg||'无法读取监听设置');monitorState=s;$('monitorStart').value=s.window[0];$('monitorEnd').value=s.window[1];$('monitorAllDay').checked=s.all_day;$('monitorTimezone').textContent='（助手所在电脑：'+s.timezone+'）';monitorAllDayChanged();renderMonitorGroups();monitorError('')}catch(e){monitorError(e.message||'连接失败，请稍后重试')}}
function renderMonitorGroups(){$('monitorGroups').innerHTML=monitorState.groups.map((g,i)=>`<div class="monitor-row"><b>${esc(g.name)}</b> <span class="tag">${esc(g.state)}</span><div class="monitor-hint">${esc(g.readonly?'只监听提醒':'草稿确认后发送')} · ${esc(g.rule||'沿用已有规则')}</div><div class="btns"><button class="btn sm" onclick="editMonitorGroup(${i})">编辑</button><button class="btn sm" onclick="toggleMonitorGroup(${i},this)">${g.paused?'恢复监听':'暂停监听'}</button></div></div>`).join('')||'<p class="monitor-hint">还没有监听群，点击“新增监听群”添加。</p>'}
function newMonitorGroup(){monitorSearchSeq++;monitorChoice=null;monitorMatches=[];$('monitorEditor').hidden=false;$('monitorSearchBox').hidden=false;$('monitorEditorTitle').textContent='新增监听群';$('monitorQuery').value='';$('monitorResults').innerHTML='';$('monitorSearchHint').textContent='搜索后请选择一个真实群；同名群请核对群标识。';$('monitorChosen').textContent='尚未选择群';$('monitorRule').value='';$('monitorMode').value='draft';$('monitorPaused').checked=false;monitorError('');$('monitorQuery').focus()}
function editMonitorGroup(i){monitorSearchSeq++;const g=monitorState.groups[i];monitorChoice={...g};$('monitorEditor').hidden=false;$('monitorSearchBox').hidden=true;$('monitorEditorTitle').textContent='编辑监听群';$('monitorChosen').textContent=g.name+' · '+g.cid;$('monitorRule').value=g.rule;$('monitorMode').value=g.readonly?'readonly':'draft';$('monitorPaused').checked=g.paused;monitorError('')}
async function searchMonitorGroups(){const seq=++monitorSearchSeq,q=$('monitorQuery').value.trim();if(!q)return monitorError('请填写群名关键词');const b=$('monitorSearch');b.disabled=true;b.textContent='搜索中…';monitorChoice=null;$('monitorChosen').textContent='尚未选择群';$('monitorResults').innerHTML='';monitorError('');
try{const r=await api('/api/monitor/search?q='+encodeURIComponent(q));if(seq!==monitorSearchSeq)return;if(!r.matches)throw Error(r.msg||'群搜索失败');monitorMatches=r.matches;$('monitorSearchHint').textContent=r.msg||(!r.matches.length?'未找到群，请换一个关键词。':'请选择需要监听的群');$('monitorResults').innerHTML=r.matches.map((g,i)=>`<button class="btn sm" onclick="chooseMonitorGroup(${i})">${esc(g.name)}${g.existing?' · 已添加':''}<div class="monitor-hint">${esc(g.cid)}${g.members!=null?' · '+esc(g.members)+'人':''}</div></button>`).join('')}catch(e){if(seq===monitorSearchSeq)monitorError(e.message||'群搜索失败')}finally{b.disabled=false;b.textContent='搜索'}}
function chooseMonitorGroup(i){const g=monitorMatches[i],existing=monitorState.groups.findIndex(x=>x.cid===g.cid);if(existing>=0)return editMonitorGroup(existing);monitorChoice=g;$('monitorChosen').textContent='已选择：'+g.name+' · '+g.cid;$('monitorResults').innerHTML=''}
async function monitorSave(body,button){button.disabled=true;monitorError('正在保存…');try{const r=await api('/api/monitor',body);if(!r.ok)throw Error(r.msg||'保存失败');monitorState=r.settings;renderMonitorGroups();monitorError('');toast(r.msg);return true}catch(e){monitorError(e.message||'保存失败，请稍后重试');return false}finally{button.disabled=false}}
async function saveMonitorTime(){const b=$('monitorTimeSave');await monitorSave({window:[$('monitorStart').value,$('monitorEnd').value],all_day:$('monitorAllDay').checked},b)}
async function saveMonitorGroup(){if(!monitorChoice)return monitorError('请先搜索并选择一个群');if(await monitorSave({group:{cid:monitorChoice.cid,rule:$('monitorRule').value,readonly:$('monitorMode').value==='readonly',paused:$('monitorPaused').checked}},$('monitorGroupSave')))$('monitorEditor').hidden=true}
async function toggleMonitorGroup(i,button){const g=monitorState.groups[i];await monitorSave({group:{cid:g.cid,paused:!g.paused}},button)}
function head(c){return `<div class="top">${av(c.who)}<div><div class="who">${esc(c.who)}</div><div class="where">${esc(c.group||'')} <span class="no">${c.no}</span></div></div><span class="when">${c.overdue?'<span class="tag t-red">超时</span> ':''}${esc(c.at)}</span></div>`}
function progress(c){const x=c.commitment||{};return(c.sent?`<details class="progress reply"><summary>已回复 · ${esc(c.sent_at||'')} · 查看原文</summary><div class="readable">${readable(c.sent)}</div></details>`:'')+(x.status?`<div class="progress exec"><b>执行进度：${esc(execLabel(x.status))}</b>${x.next_action?`<div>${esc(x.next_action)}</div>`:''}</div>`:'')}

function card(c,kind){return `<div aria-busy="${pendingActions.has(c.no)}" class="card${sel===c.no?' sel':''}" onclick="openP('${c.no}')">${head(c)}<div class="txt">${esc(c.text)}</div>${progress(c)}
${kind==='send'?`<div class="draft">${esc(c.draft)}</div><div class="card-hint">点开查看完整草稿和依据</div>`:(c.reason?`<div class="why">${esc(c.reason)}</div>`:'')}
<div class="btns" onclick="event.stopPropagation()">${kind==='send'?`<button class="btn p" onclick="go('${c.no}','send')">发送</button><button class="btn" onclick="openP('${c.no}')">修改</button><button class="btn d" onclick="go('${c.no}','drop')">不发</button>`:
`<button class="btn p" onclick="openP('${c.no}')">${c.sent?'补充回复':'回复'}</button><button class="btn" onclick="go('${c.no}','not_mine')">不归我</button>`}<button class="btn" onclick="go('${c.no}','manual_done')">已手动处理</button><button class="btn" onclick="openP('${c.no}',1)">问 AI</button></div></div>`}
function empty(t){return `<div class="empty"><span class="big">☕</span>${t}</div>`}
function render(){if(!S)return;const s=S;renderOwners();renderNotifications();renderExecutions();const ok=/^(\d+)\/\1$/.test(s.listeners)&&s.listeners!=='0/0';
$('stat').innerHTML=`<span class="chip duty d-${s.duty}" style="cursor:pointer" onclick="openH()" title="点开按群看最近消息；最近收到消息 ${esc(s.last_event_t||'无')}；${esc(s.last_event||'')}"><span class="dot"></span><b>${esc(s.duty_text)}</b> · 监听 ${s.listeners}${s.last_event_t?' · 最近 '+s.last_event_t:''}</span><span class="chip">要你判断 <b>${s.judge.length}</b></span><span class="chip">草稿待发 <b>${s.send.length}</b></span><span class="chip">队列 <b>${s.queue||0}</b> · 处理中 <b>${s.processing||0}</b></span><span class="chip">今天已处理 <b>${s.today_done}</b></span><span class="chip">${esc(s.me)} · ${s.time}</span>`;$('ver').textContent=s.version;
$('judge').innerHTML=s.judge.filter(matches).map(c=>card(c,'judge')).join('')||empty('没有要你判断的事');$('send').innerHTML=s.send.filter(matches).map(c=>card(c,'send')).join('')||empty('没有待发的草稿');
const dl=s.done.filter(matches).filter(d=>dfilter==='all'||d.result==='已发送');
$('done').innerHTML=`<div class="dtabs"><button class="btn sm${dfilter==='all'?' p':''}" onclick="dfilter='all';render()">全部 ${s.done.length}</button><button class="btn sm${dfilter==='sent'?' p':''}" onclick="dfilter='sent';render()">已发送 ${s.done.filter(d=>d.result==='已发送').length}</button></div>`+
(dl.map(d=>`<div class="card" style="cursor:pointer" onclick="openD('${d.no}')">${head({who:d.who,group:'',no:d.no,at:d.done})}<div class="txt">${esc(d.what)}</div>${d.sent?`<div class="draft sent">${esc(d.sent)}</div>`:''}<div class="why" style="--x:0"><span class="tag ${d.result==='已发送'?'t-ok':'t-gray'}">${d.result}</span>${d.commitment_status?` <span class="tag ${['completed','done'].includes(d.commitment_status)?'t-ok':d.commitment_status==='failed'?'t-red':'t-wait'}">${esc(execLabel(d.commitment_status))}</span>`:''} ${d.sent?'':esc(d.why)}</div></div>`).join('')||empty(dfilter==='sent'?'还没有发出去的消息':'今天还没有处理记录'));
$('n1').textContent=s.judge.length;$('n2').textContent=s.send.length;$('n3').textContent=s.done.length;
const open=[...s.judge,...s.send],n=open.length;document.title=(n?'('+n+') ':'')+'群消息助手 · 操作台';const now=new Set(open.map(c=>c.no));
open.forEach(c=>{if(!seen.has(c.no)&&!first&&window.Notification&&Notification.permission==='granted'){const x=new Notification(`${c.draft?'草稿待发':'要你判断'} · ${c.who}`,{body:c.text.slice(0,90),tag:c.no});x.onclick=()=>{window.focus();openP(c.no)};notes[c.no]=x}});
Object.keys(notes).forEach(no=>{if(!now.has(no)){notes[no].close();delete notes[no]}});seen=now;first=false;
if(sel&&!now.has(sel)){const previous=sel;closeP();toast(previous+' 已处理')}else if(sel)fillFoot()}
let ticking=false;async function tick(){if(ticking)return;ticking=true;try{const value=await api('/api/state');if(!value.judge)throw Error(value.msg||'无法读取状态');S=value;render()}catch(e){$('stat').innerHTML='<span class="chip d-bad">连接中断 · '+esc(e.name==='AbortError'?'助手响应超时':e.message)+' · 正在重试</span>'}finally{ticking=false}}

function cur(){return [...S.judge,...S.send].find(c=>c.no===sel)}
async function openP(no,ask){sel=no;const request=++panelRequest,c=cur();if(!c)return;$('pav').outerHTML=av(c.who).replace('class="av"','class="av" id="pav"');$('ptitle').textContent=c.who;$('psub').textContent=`${c.group||''} · ${no} · ${c.at}`;
$('panel').classList.add('on');$('mask').classList.add('on');render();$('pbody').innerHTML=progress(c)+loading('正在读取对应消息与回复…');fillFoot(ask);
try{const t=await api('/api/thread?no='+encodeURIComponent(no));if(request!==panelRequest||sel!==no)return;$('pbody').innerHTML=progress(c)+bubbles(t,c.text)+(c.reason?`<div class="note readable"><h4>判断依据</h4>${readable(c.reason)}</div>`:'')+((c.qa||[]).length?`<div class="note"><h4>问过 AI</h4>${c.qa.map(q=>`<div class="qa readable"><b>问</b> ${esc(q['问'])}<br><b>答</b> ${readable(q['答'])}</div>`).join('')}</div>`:'');anchorScroll()}catch(e){if(request===panelRequest)$('pbody').innerHTML='<div class="note">读取失败：'+esc(e.name==='AbortError'?'助手响应超时':e.message)+'。请关闭后重试；草稿保留。</div>'}}

function fillFoot(ask){const c=cur();if(!c)return;const f=$('pfoot');if(f.contains(document.activeElement))return;
f.innerHTML=`<div class="lbl">${c.draft?'AI 建议草稿（可以直接改）':'AI 尚未生成草稿，请先问 AI 或自己补充'}</div><textarea id="ta" oninput="edits[sel]=this.value" placeholder="${c.draft?'':'点击“问 AI”生成建议，或在这里补充回复内容'}">${esc(edits[c.no]??c.draft)}</textarea>
<div class="btns">${c.can_send?`<button class="btn p" onclick="go('${c.no}','${c.draft?'edit_send':'reply_new'}',$('ta').value)">发送到原会话</button>`:'<span class="where">这个群设成了「只看」，请在钉钉里自己回</span>'}
<button class="btn" onclick="go('${c.no}','manual_done')">已手动处理</button><button class="btn" onclick="go('${c.no}','stash',$('ta').value)">暂存不发</button>${c.draft?`<button class="btn d" onclick="go('${c.no}','drop')">不发</button>`:`<button class="btn" onclick="go('${c.no}','not_mine')">不归我</button>`}</div>
<div class="askrow"><input class="q" id="q" oninput="questions[sel]=this.value" value="${esc(questions[c.no]||'')}" placeholder="问 AI：依据是什么？帮我改得客气点…" onkeydown="if(event.key==='Enter')go('${c.no}','ask',this.value)"><button class="btn" onclick="go('${c.no}','ask',$('q').value)">问 AI</button></div>`;if(ask)setTimeout(()=>$('q').focus(),60)}
// 点开「已处理」：只读详情
async function openD(no){sel=null;const request=++panelRequest,cached=doneCache.get(no),summary=S.done.find(x=>x.no===no)||{};$('panel').classList.add('on');$('mask').classList.add('on');$('ptitle').textContent=summary.who||'处理记录';$('psub').textContent=`${no} · ${summary.done||''}`;$('pav').outerHTML=av(summary.who).replace('class="av"','class="av" id="pav"');$('pfoot').innerHTML='';$('pbody').innerHTML=cached?'':loading('正在读取这条消息的处理记录…');
const show=d=>{if(request!==panelRequest)return;$('ptitle').textContent=d.who||'';$('psub').textContent=`${d.group||''} · ${no} · 收到 ${d.at||''} · 处理 ${d.done||''}`;$('pbody').innerHTML=progress({...d,sent:''})+bubbles(d.thread||[],d.text)+(d.reason?`<div class="note readable"><h4>判断依据</h4>${readable(d.reason)}</div>`:'')+((d.qa||[]).length?`<div class="note"><h4>问过 AI</h4>${d.qa.map(q=>`<div class="qa readable"><b>问</b> ${esc(q['问'])}<br><b>答</b> ${readable(q['答'])}</div>`).join('')}</div>`:'');$('pfoot').innerHTML=d.sent?`<div class="lbl">已发出 · ${esc(d.sent_at)}</div><div class="draft sent readable">${readable(d.sent)}</div><div class="where" style="margin-top:8px">确认方式：${esc(d.confirm)}</div>`:`<div class="lbl">处理说明</div><div class="readable">${readable(d.why)}</div>`;anchorScroll()};if(cached)show(cached);
try{const d=await api('/api/done?no='+encodeURIComponent(no));if(request!==panelRequest)return;if(!d.no)throw Error('没找到这条记录');doneCache.set(no,d);show(d)}catch(e){if(request===panelRequest&&!cached)$('pbody').innerHTML='<div class="note">读取失败：'+esc(e.name==='AbortError'?'助手响应超时':e.message)+'。请关闭后重试。</div>'}}

// 顶栏「值守中」点开：按群看最近消息（复用右侧面板）
let hsel=null;async function openH(cid){sel=null;const request=++panelRequest;const gs=await api('/api/groups');if(request!==panelRequest)return;if(!gs.length)return toast('没有监听的群');hsel=cid||hsel||gs[0].cid;
$('pav').outerHTML='<span class="av" id="pav" style="background:var(--green)">群</span>';$('ptitle').textContent='最近消息';$('psub').textContent='按群看，每个群最近 30 条';
$('panel').classList.add('on');$('mask').classList.add('on');
const tabs='<div class="btns" style="margin:0 0 14px;position:sticky;top:-16px;background:var(--soft);padding:8px 0;z-index:1">'+gs.map(g=>`<button class="btn sm${g.cid===hsel?' p':''}" onclick="openH('${g.cid}')">${esc(g.name)}</button>`).join('')+'</div>';
$('pfoot').innerHTML='<div class="where">只读：这里只看消息，要回复请在卡片或钉钉里处理</div>';$('pbody').innerHTML=tabs+'<div class="empty">正在读…</div>';const t=await api('/api/history?cid='+encodeURIComponent(hsel));if(request!==panelRequest||!$('panel').classList.contains('on'))return;
$('pbody').innerHTML=tabs+t.map(m=>`<div class="bub">${av(m.who)}<div class="b"><div class="w">${esc(m.who)}<span>${esc((m.time||'').slice(5,16))}</span></div><div class="tx">${esc(m.text)}</div></div></div>`).join('')||'<div class="empty">没有消息</div>';$('pbody').scrollTop=1e9}
function closeP(){panelRequest++;sel=null;hsel=hsel;$('panel').classList.remove('on');$('mask').classList.remove('on');render()}
function confirmAction(action){return new Promise(resolve=>{const d=$('actionDialog'),note=$('actionNote'),manual=action==='manual_done',explain=manual||action==='not_mine';
$('actionTitle').textContent=manual?'已手动处理':explain?'不归我':'发送到原会话';$('actionHint').textContent=manual?'请说明你在哪里、如何处理了这条消息。已有验证任务会继续保留执行进度，不会据此标成验收通过。':explain?'请填写这件事不归你的原因。':'确认将这段回复发送到原会话？';note.hidden=!explain;note.required=explain;note.value='';
let settled=false;const finish=value=>{if(settled)return;settled=true;d.close();resolve(value)};$('actionCancel').onclick=()=>finish(null);d.oncancel=e=>{e.preventDefault();finish(null)};$('actionOK').onclick=()=>{if(explain&&!note.value.trim()){note.setCustomValidity('请填写处理说明');note.reportValidity();return}finish(explain?note.value.trim():true)};note.oninput=()=>note.setCustomValidity('');note.setCustomValidity('');d.showModal();if(explain)note.focus()})}
async function go(no,action,text){if(pendingActions.has(no))return toast('这条消息正在处理，请稍候');if(['send','edit_send','reply_new','manual_done','not_mine'].includes(action)){const answer=await confirmAction(action);if(answer===null)return;if(['manual_done','not_mine'].includes(action))text=answer}
pendingActions.add(no);render();const foot=$('pfoot');foot.querySelectorAll('button').forEach(x=>x.disabled=true);toast(action==='ask'?'正在提交问题…':'正在处理，请稍候…');
try{const r=await api('/api/act',{no,action,text:text||''});toast(r.msg||'请查看处理结果');if(r.msg==='已处理'){delete edits[no];doneCache.delete(no)}if(action==='ask'){delete questions[no];if($('q'))$('q').value=''}}catch(e){toast(e.name==='AbortError'?'等待结果超时，请先查看已处理记录，勿重复发送':'操作未确认：'+e.message)}finally{pendingActions.delete(no);foot.querySelectorAll('button').forEach(x=>x.disabled=false);document.activeElement&&document.activeElement.blur();await tick()}}

document.addEventListener('keydown',e=>{if(e.key==='Escape')closeP()});
if(window.Notification&&Notification.permission==='default'){$('notif').style.display='';$('notif').onclick=()=>Notification.requestPermission().then(()=>$('notif').style.display='none')}
// 有新事件时助手会用浏览器打开带 focus 的链接（弹到最前面）；新页面打开后通知旧页面关掉，始终只留一个操作台
const FOCUS=new URLSearchParams(location.search).get('focus');let alive=true;
try{const bc=new BroadcastChannel('qa-console');const me=Date.now()+Math.random();bc.postMessage({t:'new',me});
bc.onmessage=m=>{if(m.data&&m.data.t==='new'&&m.data.me!==me){alive=false;window.close();setTimeout(()=>{document.body.innerHTML='<div class="empty" style="margin-top:20vh"><span class="big">↗</span>操作台已在新标签页打开，这一页可以关掉了。</div>'},300)}}}catch(e){}
tick().then(()=>{if(FOCUS)openP(FOCUS);if(FOCUS)history.replaceState(null,'',location.pathname+'?k='+encodeURIComponent(K))});setInterval(()=>{if(alive)tick()},3000);
</script></body></html>"""
