"""钉钉以本人身份发消息失败时（dws 故障 / 版本不兼容 / 服务端报错），用调试群机器人同步通知用户（用户 11-18 定：dws 出 bug 发不出去时必须通知）。
同一类失败 30 分钟内只提醒一次，之后的失败只记进 runs/send_failed.log。
用法：python3 -I send_failed.py <发往哪> <没发出去的正文> <错误信息>"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_user  # noqa: E402

where, text, err = (sys.argv[1:] + ["", "", ""])[:3]
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs", "send_failed.log")
STATE = LOG + ".last"
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps({"t": time.strftime("%F %T"), "where": where, "err": err[:300], "text": text[:500]}, ensure_ascii=False) + "\n")
last = float(open(STATE).read()) if os.path.exists(STATE) else 0
if time.time() - last > 1800:
    open(STATE, "w").write(str(time.time()))
    notify_user.send("⚠️ 钉钉消息没发出去", f"发往：{where}\n\n错误：{err[:200]}\n\n没发出去的内容：\n\n{text[:800]}\n\n30 分钟内再失败只记日志 runs/send_failed.log，不重复提醒。要紧的请先手动发。")
else:
    print("30 分钟内已提醒过，只记日志")
