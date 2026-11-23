"""旧后台（backend-server /sys、/business）最小客户端。账号读 ~/.config/app-admin/account.json，不打印凭据。

登录：POST /sys/login（表单，password 为 md5），返回 token；后续请求头带 token。
新 admin（/admin-next/api）用同一 token（sys_user.salt 验签）。
"""
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from client import BASE, CTX  # noqa: E402

ACCOUNT = os.path.expanduser("~/.config/app-admin/account.json")


class Admin:
    def __init__(self):
        with open(ACCOUNT, encoding="utf-8") as f:
            acc = json.load(f)
        self.username, self.password = acc["username"], acc["password"]
        self.token = ""

    def _send(self, path, data, form=False):
        if form:
            body = urllib.parse.urlencode(data).encode()
            ctype = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            ctype = "application/json"
        headers = {"Content-Type": ctype}
        if self.token:
            headers["token"] = self.token
        req = urllib.request.Request(BASE + path, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=20, context=CTX) as resp:
            return json.loads(resp.read().decode())

    def login(self):
        res = self._send("/sys/login", {
            "username": self.username,
            "password": hashlib.md5(self.password.encode()).hexdigest(),
        }, form=True)
        if res.get("code") == 0:
            self.token = res.get("token", "")
        return {"code": res.get("code"), "msg": res.get("msg"), "logged_in": bool(self.token)}

    def add_coin(self, uids, coin):
        """单次每个 uid 最多 2000（后端截断）。"""
        # 11-12 783/086 后 addGem 必填 grantSource（internal 内部加币 / cs_compensate 客服补偿），reason 选填；operator 服务端取当前登录账号
        return self._send("/business/member/addGem", {"coin": int(coin), "uids": list(uids), "grantSource": "internal", "reason": "OPS-018 接口自动化补币"})
