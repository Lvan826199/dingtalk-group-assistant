#!/usr/bin/env python3
"""测试数据读取 + 有效性抽查（11-25 优化 5）。
用法：from fixtures import F; F("remix_series")      取值
      python3 -I fixtures.py check                      逐项实测，失效的打印「测试数据失效」并退出码 3
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = json.load(open(os.path.join(HERE, "fixtures.json"), encoding="utf-8"))


def F(key):
    return _DATA[key]["value"]


def _hcall(c, path, body):
    """Header 模式（/api/go/remix/*）：公共参数和登录态放请求头。"""
    import urllib.request, urllib.error
    from client import BASE, CTX
    h = {"Content-Type": "application/json", **{k: str(v) for k, v in c.common.items()}, "uid": c.uid, "token": c.token}
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, ValueError) as ex:
        return {"code": None, "message": repr(ex)[:80]}


def check():
    sys.path.insert(0, HERE)
    from client import Client  # noqa: E402
    c = Client(**F("go_accounts")["android"])
    if c.login().get("code") != 0:
        print("测试数据抽查：专用号登录失败，没法抽查"); return 3
    bad = []
    r = _hcall(c, "/api/go/remix/eligibility", {"seriesId": F("remix_series")})
    if (r.get("data") or {}).get("canCreate") is not True:
        bad.append(f"remix_series {F('remix_series')}：eligibility canCreate 不是 true（{r.get('code')} {r.get('message')}），找研发C要新的二创开放剧")
    for key, ids in (("p0_series", [F("p0_series")]), ("aa_other_series", F("aa_other_series"))):
        for sid in ids:
            r = c.call("/api/series/detail", {"seriesId": sid})
            if r.get("code") != 0:
                bad.append(f"{key} {sid}：series/detail 返回 {r.get('code')} {r.get('message')}")
    for line in bad:
        print("测试数据失效：" + line)
    print("测试数据抽查：" + ("全部有效" if not bad else f"{len(bad)} 项失效"))
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(check() if sys.argv[1:2] == ["check"] else 0)
