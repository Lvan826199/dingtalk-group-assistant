"""v3.0 本机操作台：只认带密钥的请求；三列不重复；页面操作和提醒群指令走同一条路（发出、留痕、提醒群「已处理」同步）。"""
import json, os, socket, sys, urllib.request, urllib.error
from conftest import R


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _boot(make_agent):
    a, notes, calls = make_agent({"groups": {"cidG": "测试群"}, "console_port": _port()})
    sys.path.insert(0, a.HOME)
    import importlib; console = importlib.import_module("console"); importlib.reload(console)
    srv = console.start(vars(a))
    assert srv
    e1 = {"sender": "同事甲", "content": "@本人 Jira 24680 补测好了吗", "conversation_id": "cidG", "message_id": "msgAAAAA11111"}
    e2 = {"sender": "同事乙", "content": "@本人 这个归你吗", "conversation_id": "cidG", "message_id": "msgBBBBB22222"}
    n1 = a.open_add(e1, "draft", "草稿"); f = a.save_draft(e1, "好了，已补测通过")
    p = os.path.join(a.HOME, "drafts", f); d = json.load(open(p, encoding="utf-8")); d["todo"] = n1; json.dump(d, open(p, "w", encoding="utf-8"))
    n2 = a.open_add(e2, "escalate", "拿不准是不是归你")
    return a, console, notes, calls, n1, n2


def _get(console, path, key=True):
    u = console.url().split("?")[0].rstrip("/") + path + (("&" if "?" in path else "?") + "k=" + console.TOKEN if key else "")
    return urllib.request.urlopen(u, timeout=5)


def _post(console, body):
    u = console.url().split("?")[0].rstrip("/") + "/api/act?k=" + console.TOKEN
    r = urllib.request.Request(u, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=5).read())


def test_console_requires_key_and_splits_columns(make_agent):
    a, console, *_ , n1, n2 = _boot(make_agent)
    try:
        _get(console, "/api/state", key=False); assert False, "没密钥也能打开"
    except urllib.error.HTTPError as ex:
        assert ex.code == 403
    s = json.loads(_get(console, "/api/state").read())
    assert [c["no"] for c in s["send"]] == [n1] and [c["no"] for c in s["judge"]] == [n2]   # 有草稿的只在「草稿待发」，没有的只在「要你判断」
    assert "<title>" in _get(console, "/").read().decode()


def test_console_send_goes_through_command_and_syncs(make_agent):
    a, console, notes, calls, n1, n2 = _boot(make_agent)
    a.run = lambda args, **k: calls.append(args) or R(0, '{"success": true}')
    assert _post(console, {"no": n1, "action": "edit_send", "text": "好了，24680 已补测通过"})["msg"] == "已处理"
    sent = [c for c in calls if "+messages-reply" in c]
    assert sent and "24680 已补测通过" in " ".join(sent[-1])                       # 真的发到原会话
    assert any(n1 in t and "已处理" in t for t, _ in notes)                       # 提醒群收到「已处理」
    s = console.state()
    assert n1 not in [c["no"] for c in s["send"]] and s["done"][0]["no"] == n1    # 页面：移到「已处理」
    assert os.path.exists(a.AUDIT)                                               # 留痕
    d = console.state()["done"][0]; assert d["result"] == "已发送" and "24680 已补测通过" in d["sent"]   # 「已处理」里看得到发出的内容
    det = json.loads(_get(console, "/api/done?no=" + n1.replace("#", "%23")).read())
    assert det["sent"].endswith("24680 已补测通过") and "改过草稿" in det["confirm"] and det["text"].startswith("@本人 Jira 24680")   # 点开看详情


def test_console_not_mine_and_reply_new(make_agent):
    a, console, notes, calls, n1, n2 = _boot(make_agent)
    a.run = lambda args, **k: calls.append(args) or R(0, '{"success": true}')
    assert _post(console, {"no": n2, "action": "reply_new", "text": "归我，我来看"})["msg"] == "已处理"
    assert any("归我，我来看" in " ".join(c) for c in calls if "+messages-reply" in c)
    assert _post(console, {"no": n1, "action": "drop"})["msg"] == "已处理"
    assert not any("好了，已补测通过" in " ".join(c) for c in calls)               # 不发的草稿没发出去
    s = console.state(); assert not s["send"] and not s["judge"] and len(s["done"]) == 2
    assert sorted(d["result"] for d in s["done"]) == ["不发", "已发送"]






def test_duplicate_open_preserves_source_and_questions(make_agent):
    a, _, _, _, n1, _ = _boot(make_agent)
    items = a._open_load(); original = items[n1]["event"].copy()
    items[n1]["qa"] = [{"问": "之前回过吗", "答": "回过"}]; a._open_save(items)
    assert a.open_add({**original, "content": "后台说明"}, "escalate", "等待前置") == n1
    x = a._open_load()[n1]
    assert x["event"] == original and x["qa"][0]["答"] == "回过"
    assert x["reason"] == "等待前置"


def test_history_does_not_join_different_message_or_group(make_agent):
    a, console, _, _, n1, _ = _boot(make_agent)
    x = a._open_load()[n1]
    a.audit(n1, {**x["event"], "message_id": "unrelated-message"}, "别的事项回复", "确认")
    assert console._message_context(n1, x)["sent"] == ""
    a.audit(n1, x["event"], "别的群回复", "确认")
    changed = {**x, "cid": "cidOther", "event": {**x["event"], "conversation_id": "cidOther"}}
    assert console._message_context(n1, changed)["sent"] == ""


def test_escalation_reopen_restores_original_instead_of_backend_summary(make_agent):
    a, console, notes, calls, n1, _ = _boot(make_agent)
    original = a._open_load()[n1]["event"].copy()
    a.audit(n1, original, "已承诺核验", "本人确认")
    a.open_close(n1, "已发送")
    a.notify = lambda *args: True
    u = console.url().split("?")[0].rstrip("/") + "/api/escalate"
    body = {"event": {**original, "content": "后台核查缺少前置"}, "reason": "等授权入口"}
    req = urllib.request.Request(u, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Key": console.TOKEN}, method="POST")
    assert json.loads(urllib.request.urlopen(req, timeout=5).read())["no"] == n1
    x = a._open_load()[n1]
    assert x["event"]["content"] == original["content"]
    assert "后台核查缺少前置" not in x["what"]
    assert not any("+messages-reply" in c for c in calls)


def test_escalation_gets_reviewable_ai_draft(make_agent, monkeypatch):
    a, console, notes, calls, *_ = _boot(make_agent)
    a.clear_all()
    e = {"sender": "项目助手", "content": "@本人 请确认回归结论", "conversation_id": "cidG", "message_id": "msgESCALATE777"}
    monkeypatch.setattr(a, "decide", lambda batch: {"action": "escalate", "mine": True, "risk": "high",
                                                       "text": "已核实，回归结论我确认后回复。",
                                                       "reason": "需要本人确认最终结论"})
    a.handle([e])
    s = console.state()
    assert len(s["send"]) == 1 and s["judge"] == []
    assert s["send"][0]["draft"] == "已核实，回归结论我确认后回复。"


def test_escalation_asks_ai_when_decision_has_no_text(make_agent, monkeypatch):
    a, console, notes, calls, *_ = _boot(make_agent)
    a.clear_all()
    e = {"sender": "项目助手", "content": "@本人 请确认回归结论", "conversation_id": "cidG", "message_id": "msgESCALATE888"}
    monkeypatch.setattr(a, "decide", lambda batch: {"action": "escalate", "mine": True, "risk": "high",
                                                       "text": "", "reason": "需要本人确认最终结论"})
    monkeypatch.setattr(a, "ai_exec", lambda prompt, timeout=300: '{"draft":"我先核对证据，确认后回复。"}')
    a.handle([e])
    s = console.state()
    assert len(s["send"]) == 1 and s["send"][0]["draft"] == "我先核对证据，确认后回复。"


def test_todo_question_in_notify_group_gets_console_link(make_agent):
    a, console, notes, calls, n1, n2 = _boot(make_agent)
    for q in ("有什么待办", "还有什么没处理的？", "待回复"):
        notes.clear()
        a.relevant({"sender": "本人", "content": q, "conversation_id": "cidN", "message_id": "q" + str(len(q))})
        assert notes and console.url() in notes[-1][1], q


def test_new_todo_pops_console_with_focus_and_can_be_turned_off(make_agent, monkeypatch):
    a, console, notes, calls, n1, n2 = _boot(make_agent)
    a.CFG["popup"] = True
    opened = []
    monkeypatch.setattr(console.os, "startfile", lambda u: opened.append(u), raising=False)
    a.popen = lambda args, **k: opened.append(args[-1])
    a.in_window = lambda: True
    console.POP["t"] = 0
    no = a.open_add({"sender": "同事丙", "content": "@本人 新事", "conversation_id": "cidG", "message_id": "msgCCCCC33333"}, "escalate", "x")
    import time as _t; _t.sleep(0.3)
    assert opened and "focus=" in opened[-1] and no.lstrip("#") in opened[-1]
    a.relevant({"sender": "本人", "content": "弹出 关", "conversation_id": "cidN", "message_id": "p1"})
    assert a.CFG["popup"] is False
    console.POP["t"] = 0; opened.clear()
    a.open_add({"sender": "同事丁", "content": "@本人 又一件", "conversation_id": "cidG", "message_id": "msgDDDDD44444"}, "escalate", "x"); _t.sleep(0.3)
    assert not opened


def test_setup_notify_creates_group_and_picks_up_robot(make_agent, monkeypatch):
    import json as _j
    a, notes, calls = make_agent({"notify_group": ""})
    a.CFG["notify_group"] = ""
    hook = "https://oapi.dingtalk.com/robot/send?access_token=" + "a1" * 32
    sec = "SEC" + "b2" * 32

    def fake(args, **k):
        calls.append(args)
        if "+chat-create" in args:
            return R(0, '{"result": {"openConversationId": "cidNEW"}}')
        if "list" in args:
            return R(0, _j.dumps({"messages": [{"sender": "本人", "content": hook}, {"sender": "本人", "content": sec}]}))
        return R(0, '{"success": true}')
    a.run = fake
    monkeypatch.setattr(a.time, "sleep", lambda s: None)
    assert a.setup_notify(wait_minutes=1)
    assert a.CFG["notify_group"] == "cidNEW" and a.CFG["webhook"] == hook and a.CFG["secret"] == sec
    assert any("+messages-send" in c for c in calls)                         # 群里发了加机器人的步骤
    assert notes and "自检" in notes[-1][0]


def test_status_not_spammed_to_notify_group_but_problems_are(make_agent):
    a, notes, _ = make_agent()
    a.status_event("收到消息", "x", announce=True); a.status_event("心跳", "x", announce=True)
    assert not notes                                                          # v3.0：例行状态不发提醒群
    a.status_event("监听异常", "测试群 断开", announce=True)
    assert notes and "监听异常" in notes[-1][0]


def test_setup_notify_binds_existing_group_and_robot_without_creating(make_agent):
    a, notes, calls = make_agent({"notify_group": ""})
    a.CFG["notify_group"] = ""
    a.run = lambda args, **k: calls.append(args) or R(0, '{"items": [{"openConversationId": "cidOLD"}]}')
    hook = "https://oapi.dingtalk.com/robot/send?access_token=" + "c3" * 32
    assert a.setup_notify(group="我的提醒群", webhook=hook, secret="SEC" + "d4" * 32)
    assert a.CFG["notify_group"] == "cidOLD" and a.CFG["webhook"] == hook
    assert not any("+chat-create" in c for c in calls)                       # 没建新群
    assert notes and "自检" in notes[-1][0]


def test_console_lan_mode_link_uses_lan_address(make_agent):
    a, console, *_ = _boot(make_agent)
    assert console.url().startswith("http://127.0.0.1:")
    a.CFG["console_host"] = "0.0.0.0"; a.CFG["console_url_host"] = "10.0.0.9"
    assert console.lan() and console.url().startswith("http://10.0.0.9:")


def test_console_opens_browser_on_start(make_agent, monkeypatch):
    a, notes, _ = make_agent({"console_port": _port()})
    a.CFG["popup"] = True
    opened = []
    a.popen = lambda args, **k: opened.append(args[-1])
    monkeypatch.setattr(a.os, "startfile", lambda u: opened.append(u), raising=False)
    a.in_window = lambda: True
    sys.path.insert(0, a.HOME)
    import importlib; console = importlib.import_module("console"); importlib.reload(console)
    console.start(vars(a)); console.popup()
    assert opened and opened[0].startswith("http://127.0.0.1:")


def test_history_by_group(make_agent):
    import json as _j
    a, console, *_ = _boot(make_agent)
    a.run = lambda args, **k: R(0, _j.dumps({"messages": [{"sender": "乙", "createTime": "2026-11-19 10:02:00", "content": "二"}, {"sender": "甲", "createTime": "2026-11-19 10:01:00", "content": "一"}]}))
    gs = json.loads(_get(console, "/api/groups").read())
    assert gs == [{"cid": "cidG", "name": "测试群"}]
    h = json.loads(_get(console, "/api/history?cid=cidG").read())
    assert [m["text"] for m in h] == ["一", "二"]                                  # 按时间正序
    assert json.loads(_get(console, "/api/history?cid=cidX").read()) == []      # 没监听的群不给看


def test_dingtalk_done_and_console_chat_stay_in_sync(make_agent):
    """11-23：在钉钉调试群说「#编号 已处理：说明」和在操作台点「已手动处理」一样；操作台对话里能看到调试群的往来。"""
    a, console, notes, calls, n1, n2 = _boot(make_agent)
    a.command({"content": f"{n2} 已处理：钉钉里回过了", "sender": "本人", "conversation_id": "cidN", "message_id": "m-done"})
    s = console.state()
    assert n2 not in [c["no"] for c in s["judge"]] and any(d["no"] == n2 and "钉钉里回过了" in d["why"] for d in s["done"])
    rows = console.chat()
    assert isinstance(rows, list)
    assert console.say("") == "内容为空或没配提醒群"


def test_quoted_reminder_plain_words_close_as_not_mine(make_agent):
    """11-23：引用提醒回「和我无关，无需回复」要直接当「不归我」关掉，不要当成追问。"""
    a, console, notes, calls, n1, n2 = _boot(make_agent)
    q = {"message_id": "robot1", "text": f"### ⏰ 1 件超过 2 小时还没处理\n\n**任务：** {n2} / TICKET-832\n\n一位同事：请安排测"}
    a.command({"content": "@提醒助手 和我无关，无需回复", "sender": "本人", "conversation_id": "cidN", "message_id": "m-x", "quoted_message": q})
    assert n2 not in a._open_load()
    assert any(d["no"] == n2 and "不归我" in d["why"] for d in console.state()["done"])


def test_late_ai_draft_skipped_when_owner_already_replied(make_agent):
    """11-23 #USbGg：本人 14:35 已引用回复，AI 14:36 才出草稿——草稿不该再出现。"""
    a, console, notes, calls, n1, n2 = _boot(make_agent)
    e = {"sender": "同事戊", "content": "@本人 合同 diff 给一下", "conversation_id": "cidG", "message_id": "msgLATE00001"}
    a.close_by_conversation("cidG", {"content": "已发", "quoted_message": {"message_id": "msgLATE00001"}})
    a.decide = lambda batch: {"action": "reply", "mine": True, "text": "我来整理", "reason": "x"}
    assert "不再生成草稿" in a.handle([e])
    assert not any(x.get("event", {}).get("message_id") == "msgLATE00001" for x in a._open_load().values())


def test_handled_elsewhere_skips_ai_answer(make_agent, monkeypatch):
    a, console, notes, calls, *_ = _boot(make_agent)
    a.CFG["handled_elsewhere"] = r"^(批准|同意)"
    asked = []
    monkeypatch.setattr(a, "ai_exec", lambda *x, **k: asked.append(x) or '{"answer":"未执行"}')
    a.answer_user({"sender": "本人", "content": "批准发布3.2", "conversation_id": "cidN", "message_id": "msgAPPROVE1"}, "批准发布3.2")
    assert asked == [] and not any("AI 的回答" in t or "未执行" in x for t, x in notes)


def test_reply_before_item_exists_still_blocks_late_draft(make_agent, monkeypatch):
    a, console, notes, calls, *_ = _boot(make_agent)
    a.REPLIED.clear()
    a.close_by_conversation("cidZ", {"quotedMessage": {"message_id": "msgEARLY1"}, "message_id": "r1"})
    a.REPLIED.clear()                      # 模拟重启：内存清空，应从磁盘恢复
    assert a.already_replied({"message_id": "msgEARLY1"})


def test_receipt_says_duty_offline_without_flag(make_agent, monkeypatch):
    import os, time
    a, console, notes, calls, *_ = _boot(make_agent)
    a.CFG["handled_elsewhere"] = r"^(批准|同意)"
    monkeypatch.setattr(a, "ai_exec", lambda *x, **k: '{"answer":"未执行"}')
    flag = os.path.join(a.HOME, "logs", "duty_on")
    os.makedirs(os.path.dirname(flag), exist_ok=True)
    if os.path.exists(flag):
        os.remove(flag)
    a.enqueue_owner_command({"sender": "本人", "content": "批准发布", "conversation_id": "cidN", "message_id": "msgOFF1"})
    for _ in range(50):                      # 回执在后台线程里发，等第一条发完再上岗
        if any("已收到你的消息" in t for t, _ in notes):
            break
        time.sleep(0.05)
    open(flag, "w").close()
    a.enqueue_owner_command({"sender": "本人", "content": "批准上线", "conversation_id": "cidN", "message_id": "msgON1"})
    for _ in range(50):
        if sum("已收到你的消息" in t for t, _ in notes) >= 2:
            break
        time.sleep(0.05)
    states = [x for t, x in notes if "已收到你的消息" in t]
    assert any("批准发布" in x and "不在岗" in x for x in states)
    assert any("批准上线" in x and "交给值守处理" in x for x in states)
