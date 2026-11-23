"""接口自动化试跑用的最小客户端：只用标准库，调测试服 tac。"""
import json
import ssl
import time
import urllib.error
import urllib.request

# python.org 版 Python 不带系统根证书，用 macOS 自带的证书包
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")

BASE = "https://api-test.example.com"


class Client:
    def __init__(self, sid, pf="a", app_version="1.1.0", app_build=1010001, lang="en_US"):
        self.common = {"sid": sid, "pf": pf, "appVersion": app_version, "appBuild": app_build, "lang": lang}
        self.uid = ""
        self.token = ""
        self.log = []

    def call(self, path, body=None, auth=True, drop=(), raw=False):
        """POST JSON。公共参数放 body；drop 里的公共参数会被去掉（反向用例用）。"""
        payload = dict(self.common)
        if auth:
            payload.update({"uid": self.uid, "token": self.token})
        payload.update(body or {})
        for k in drop:
            payload.pop(k, None)
        data = json.dumps(payload).encode()
        req = urllib.request.Request(BASE + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=20, context=CTX) as resp:
                status, text = resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            status, text = e.code, e.read().decode(errors="replace")
        ms = int((time.time() - start) * 1000)
        try:
            res = json.loads(text)
        except ValueError:
            res = {"_raw": text[:300]}
        self.log.append({"path": path, "status": status, "ms": ms, "code": res.get("code"), "message": res.get("message")})
        return (status, res) if raw else res

    def login(self):
        res = self.call("/api/user/login", auth=False)
        if res.get("code") == 0:
            self.uid = res["data"]["uid"]
            self.token = res["data"]["token"]
        return res
