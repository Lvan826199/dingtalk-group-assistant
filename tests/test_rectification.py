"""值守误判的真实边界：引用点名、诊断输出和同群多事项。"""
import pytest


@pytest.mark.parametrize("extra", [
    {"quoted_message": {"content": "请示例用户核对接口"}},
    {"quotedMessage": {"text": "请示例用户核对接口"}},
    {"quoted_message": {"atUserIds": ["owner-id"]}},
    {"mentions": [{"userId": "owner-id"}]},
    {"content": "<@owner-id> 请核对"},
])
def test_owner_in_quote_or_metadata_is_not_dropped(make_agent, extra):
    a, _, calls = make_agent({"my_name": "示例用户", "my_user_id": "owner-id", "groups": {"cidG": "测试群"}})
    e = {"message_id": "msgOWNER", "conversation_id": "cidG", "sender": "示例同事", "content": "@另一人 请看引用", **extra}
    assert a.event_mentions_me(e) and a.relevant(e)
    a.decide = lambda batch: {"action": "escalate", "mine": False, "reason": "需要本人判断"}
    a.escalation_draft = lambda *args: ""
    a.handle([e])
    assert a._open_load() and not calls


def test_reply_to_one_task_keeps_other_task_in_same_group(make_agent):
    a, _, _ = make_agent()
    first = {"message_id": "msgFIRST", "conversation_id": "cidG", "sender": "同事", "content": "接口A"}
    second = {"message_id": "msgSECOND", "conversation_id": "cidG", "sender": "同事", "content": "接口B"}
    n1 = a.open_add(first, "escalate", "A待处理")
    n2 = a.open_add(second, "escalate", "B待处理")
    a.close_by_conversation("cidG", {"quoted_message": {"message_id": "msgFIRST"}, "sender": "本人", "content": "A已核"})
    assert n1 not in a._open_load() and n2 in a._open_load()


def test_diagnostic_lines_do_not_trigger_parse_alerts(make_agent, monkeypatch):
    a, notes, _ = make_agent()
    class Process:
        stdout = iter(['[event] ready event_key=x\n', '[event] bus connected\n', '[event] transport connected\n'])
        def wait(self):
            a.UPDATE_EXIT.set()
    a.popen = lambda *args, **kwargs: Process()
    a.in_window = lambda: True
    a.minutes_left = lambda: 20
    monkeypatch.setattr(a.time, "sleep", lambda *args: None)
    a.listen([], "测试群")
    assert not any("解析" in title for title, _ in notes)
    assert "ready" not in str(notes) and "transport" not in str(notes)


def test_merged_batch_has_completion_for_every_message(make_agent):
    import json
    from pathlib import Path
    a, _, _ = make_agent({"groups": {"cidG": "测试群"}, "status_notifications": False})
    a.handle = lambda batch: "已核查，草稿待审"
    a.READY.put([{"message_id": mid, "conversation_id": "cidG", "sender": "同事", "content": "核查"} for mid in ('msgA', 'msgB')])
    window = iter([True, False])
    a.in_window = lambda: next(window)
    a.worker()
    rows = [json.loads(x) for x in Path(a.STATUS_LOG).read_text().splitlines()]
    assert {r['message_id'] for r in rows if r['stage'] == '处理完成'} == {'msgA', 'msgB'}


def test_uncertain_identity_is_pending_instead_of_ignored(make_agent):
    a, _, calls = make_agent({"groups": {"cidG": "测试群"}})
    a.decide = lambda batch: {"action": "ignore", "mine": False, "reason": "无法确认这个提及是不是本人"}
    a.escalation_draft = lambda *args: ""
    e = {"message_id": "msgUNCLEAR", "conversation_id": "cidG", "sender": "同事", "content": "<@unknown-id> 请核接口"}
    a.handle([e])
    assert a._open_load() and not calls


@pytest.mark.parametrize("question, expected", [
    ("这种你要核实后再回复，你先去核实", True),
    ("请复测一下", True), ("先核查接口", True),
    ("核查了吗", False), ("为什么核查失败", False),
    ("先不要核实，只解释原因", False), ("改成：我会去核查", False),
])
def test_verification_requires_current_user_instruction(make_agent, question, expected):
    a, _, _ = make_agent()
    assert a.verification_requested(question) is expected


def test_verified_call_has_network_without_changing_judgement_preset(make_agent):
    a, _, _ = make_agent()
    a.ai_engine = lambda **kw: ("Codex", ["codex", "exec", "--sandbox", "read-only"], "arg")
    calls = []
    a._ai_once = lambda *args: calls.append(args) or "verified"
    assert a.ai_exec("核查", verify=True) == "verified"
    assert "workspace-write" in calls[0][1]
    assert "sandbox_workspace_write.network_access=true" in calls[0][1]
    a.ai_exec("只判断")
    assert "read-only" in calls[1][1]
    assert "sandbox_workspace_write.network_access=true" not in calls[1][1]


def test_verification_failure_never_retries_another_engine(make_agent):
    a, _, _ = make_agent()
    calls = []
    a.ai_engine = lambda **kw: ("Codex", ["codex", "exec", "--sandbox", "read-only"], "arg")
    a._ai_once = lambda *args: calls.append(args) or ""
    assert a.ai_exec("核查", verify=True) == ""
    assert len(calls) == 1


def test_ask_executes_verification_but_keeps_original_group_unsent(make_agent):
    a, _, commands = make_agent()
    ev = {"message_id": "msgVERIFY", "conversation_id": "cidG", "sender": "同事", "content": "请核接口"}
    no = a.open_add(ev, "escalate", "待核查")
    calls = []
    a.ai_exec = lambda prompt, **kw: calls.append((prompt, kw)) or '{"answer":"本次响应已核，仍需区分前置参数","new_draft":""}'
    a.ask_ai(no, "你先去核实")
    assert calls[0][1]["verify"] is True
    assert "本次真实响应" in calls[0][0]
    assert no in a._open_load()
    assert not commands


def test_plain_debug_question_gets_real_answer(make_agent):
    a, notes, _ = make_agent()
    prompts = []
    a.ai_exec = lambda prompt, **kw: prompts.append(prompt) or '{"answer":"此前普通对话没进入回答流程，现在会结合记录回答。"}'
    a.command({"sender":"本人", "conversation_id":"cidN", "message_id":"msgQUESTION", "content":"你为什么不回我消息"})
    assert notes and "回复你的消息" in notes[-1][0]
    assert "此前普通对话" in notes[-1][1] and "当前记录" in prompts[0]
    a.command({"sender":"本人", "conversation_id":"cidN", "message_id":"msgNEXT", "content":"那以后呢"})
    assert "你为什么不回我消息" in prompts[-1]


def test_plain_followup_uses_only_unique_quoted_task(make_agent):
    a, _, _ = make_agent()
    a.open_add({"sender":"同事", "conversation_id":"cidG", "message_id":"msgABCDE", "content":"请核查"}, "escalate", "待核查")
    calls = []
    a.ask_ai = lambda no, text: calls.append((no, text))
    a.command({"sender":"本人", "conversation_id":"cidN", "message_id":"msgFOLLOW", "content":"为什么又解析失败", "quoted_message":{"text":"#ABCDE AI的回答"}})
    assert calls == [("#ABCDE", "为什么又解析失败")]


@pytest.mark.parametrize("text", ["Jira之前不是可以登录吗", "可以告诉我结果吗", "#ABCDE 为什么没有发送", "#ABCDE 发送失败是什么原因"])
def test_debug_questions_containing_command_words_never_send(make_agent, text):
    a, notes, calls = make_agent()
    a.ai_exec = lambda *args, **kw: '{"answer":"根据记录说明原因，未代发消息。"}'
    a.command({"sender":"本人", "conversation_id":"cidN", "message_id":"msgQUESTION", "content":text})
    assert "回复你的消息" in notes[-1][0]
    assert not calls and a._open_load() == {}


def test_debug_verification_uses_explicit_instruction_only(make_agent):
    a, notes, calls = make_agent()
    requests = []
    a.ai_exec = lambda prompt, **kw: requests.append(kw) or '{"answer":"本次只读核验结果：HTTP200。"}'
    a.command({"sender":"本人", "conversation_id":"cidN", "message_id":"msgVERIFY", "content":"请核查一下测试服版本"})
    assert requests[0]["verify"] is True and not calls
