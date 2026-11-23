"""通过「AI测试平台调试通知群」的自定义机器人（加签）给用户发提醒。只发需要用户拍板 / 只有用户能做的事。

凭据：~/.config/dingtalk/aitest-webhook.json {"webhook": ..., "secret": "SEC..."}（本机，不进仓库、不发群）。
用法：python3 -I notify_user.py "<标题>" "<正文（markdown）>"   （默认 @ 用户本人：要他拍板的事必须 @，用户 11-17 要求）
"""
import base64
import hashlib
import hmac
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request


def format_text(text):
    """还原误传的字面换行，保留代码/路径，钉钉Markdown用空行分段。"""
    # 与安装包共用纯排版函数；导入不会启动操作台、读取助手配置或发送消息。
    from pathlib import Path
    import importlib.util
    source = Path(__file__).resolve().parent.parent / "qa-agent-windows/console.py"
    if source.exists():
        spec = importlib.util.spec_from_file_location("qa_notice_layout", source)
        layout = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(layout)
        if hasattr(layout, "notification_body"):
            return layout.notification_body(text)
    parts = re.split(r"(```[\s\S]*?```|`[^`\n]+`)", str(text or ""))
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"\r\n?", "\n", parts[i].replace("\\r\\n", "\n").replace("\\n", "\n"))
        parts[i] = re.sub(r"\n+", "\n\n", parts[i])
    return "".join(parts).strip()


def mirror(title, text, delivered):
    """机器人结果同步操作台；网页离线由公共桥接落盘补记。"""
    from pathlib import Path
    import importlib.util
    source = Path(__file__).resolve().parent.parent / "qa-agent-windows/console.py"
    spec = importlib.util.spec_from_file_location("qa_notice_bridge", source)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    return bridge.mirror_notification({"title": str(title), "text": str(text),
                                      "delivered": bool(delivered), "source": "duty", "group": "AI测试平台调试通知群",
                                      "time": time.strftime("%Y-%m-%dT%H:%M:%S")})


def send(title, text, at_me=True):
    cfg = json.load(open(os.path.expanduser("~/.config/dingtalk/aitest-webhook.json")))
    me = cfg.get("my_user_id") if at_me else None
    ts = str(int(time.time() * 1000))
    sign = base64.b64encode(hmac.new(cfg["secret"].encode(), f"{ts}\n{cfg['secret']}".encode(), hashlib.sha256).digest()).decode()
    url = f"{cfg['webhook']}&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"
    body = {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n{format_text(text)}" + (f"\n\n---\n\n@{me}" if me else "")},
            "at": {"isAtAll": False, "atUserIds": [me] if me else []}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem")  # python.org 版 Python 不带根证书
    delivered = False
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            res = json.loads(r.read().decode())
        delivered = res.get("errcode") == 0
        if not delivered:
            raise SystemExit(f"钉钉机器人返回错误: {res}")
    finally:
        try:
            synced = mirror(title, text, delivered)
            if not synced:
                print("操作台同步暂不可用，通知已排队补记。", file=sys.stderr)
        except (OSError, ValueError, ImportError):
            print("操作台通知补记失败，请检查桥接与本机写入权限。", file=sys.stderr)
    return res


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    print(send(sys.argv[1], sys.argv[2]))
