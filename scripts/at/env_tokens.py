"""每轮回归开跑前：用各平台环境自己的设备号（sid / pf / appVersion / appBuild）登录测试服，把 uid、token 写进该环境的变量。
这样任何用例都能单独跑（不再依赖套件第一条「登录」用例在本轮提取的变量）。用户 2026-11-13 提议。
套件里的登录用例照常跑（它本身也是测试），提取到的值在本轮内覆盖环境变量。
平台环境变量只能 DELETE + POST，不能 PUT。token 是测试服专用号的，内网平台，和 sid 同等对待。
用法：python3 -I env_tokens.py [env_id ...]   （默认 163 164 165 166）
"""
import os
import sys

sys.argv = sys.argv[:1] + [a for a in sys.argv[1:]]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from client import Client  # noqa: E402
import series_check as sc  # noqa: E402  复用它的平台 req / env_vars


def main():
    envs = [a for a in sys.argv[1:] if a.isdigit()] or ["163", "164", "165", "166", "168", "169", "170"]
    for env in envs:
        v = {x["name"]: x for x in sc.env_vars(env)}
        try:
            c = Client(v["sid"]["value"], v["pf"]["value"], v["appVersion"]["value"], int(v["appBuild"]["value"]))
        except KeyError as e:
            raise SystemExit(f"env {env} 缺变量 {e}，本轮前置阻塞")
        if c.login().get("code") != 0:
            raise SystemExit(f"env {env} {v['sid']['value']} 登录失败，本轮前置阻塞")
        # 评论屏蔽/解除屏蔽用专用QA对照号；新增环境同样要补齐，不能漏变量。
        reference = "164" if env == "163" else "163"
        peers = {x["name"]: x for x in sc.env_vars(reference)}
        other_uid = (peers.get("uid") or {}).get("value")
        if not other_uid or other_uid == c.uid:
            raise SystemExit(f"env {env} 缺少有效的QA对照账号，先补齐环境{reference}的uid")
        for name, value in (("uid", c.uid), ("token", c.token), ("other_uid", other_uid)):
            if name in v:
                if v[name]["value"] == value:
                    continue
                sc.req("DELETE", f"/environments/{env}/variables/{v[name]['id']}")
            sc.req("POST", f"/environments/{env}/variables", {"name": name, "value": value, "type": "text",
                                                               "description": "env_tokens.py 每轮开跑前登录写入"})
        print(f"env {env} {v['sid']['value']} uid {c.uid} token 已写入", flush=True)


if __name__ == "__main__":
    main()
