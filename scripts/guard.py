"""「先问用户」的动作用脚本拦住（11-20 整改第 5 条，11-23 落地）：
正式更新内网（build_docs 不带 --preview）、推 GitHub、发测试部群、值守时间重启助手、改工作手册，
执行前必须给出本人在调试群批准这件事的那条消息 ID；脚本去钉钉取回原文核对：发送人是本人本人、2 小时内、
内容含批准类词（批准 / 同意 / 上线 / 可以 / 推 / 发吧 / 做 / 好的），才放行（退出码 0），否则退出码 3 并说明。
用法：python3 -I scripts/guard.py <动作说明> <批准消息ID> && <真正的命令>"""
import json
import os
import subprocess
import sys
import time

GROUP = os.environ.get("QA_NOTIFY_GROUP", "")          # AI 测试平台调试通知群
OWNER = "本人"
WORDS = ("批准", "同意", "上线", "可以", "推", "发吧", "做", "好的", "ok", "OK")


def main(action, msg_id):
    r = subprocess.run(["dws", "chat", "+messages-mget", "--msg-ids", msg_id, "--no-reactions", "--no-threads", "--format", "json"],
                       capture_output=True, text=True, timeout=60)
    try:
        rows = json.loads(r.stdout).get("messages") or []
    except ValueError:
        rows = []
    if not rows:
        raise SystemExit(f"拦下：取不到批准消息 {msg_id}，先在调试群问用户「{action}」")
    m = rows[0]
    who, text, cid = m.get("sender"), str(m.get("content") or m.get("text") or ""), m.get("openConversationId") or m.get("conversationId")
    try:
        age = time.time() - time.mktime(time.strptime(m.get("createTime", "")[:19], "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        age = 1e9
    problems = [p for ok, p in ((who == OWNER, f"发送人是 {who}，不是{OWNER}"), (cid in (None, GROUP), "不是调试通知群里的消息"),
                                (age <= 7200, "批准超过 2 小时"), (any(w in text for w in WORDS), f"没看到批准的意思：「{text[:40]}」")) if not ok]
    if problems:
        print("拦下：" + "；".join(problems) + f"。先在调试群问用户「{action}」", file=sys.stderr); sys.exit(3)
    print(f"放行：{action}（{OWNER} {m.get('createTime')}：{text[:40]}）")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
