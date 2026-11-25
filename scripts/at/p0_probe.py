"""P0 接口核实（本地探测，不进平台）：按合同对每个接口做 正向 + 去掉必填 + 去掉可选，并把真实返回和合同响应结构逐字段比对。

结果用来：1) 分出「合同错」（进文档修正清单）和「疑似代码错」（群里核实）；2) 生成平台单接口用例的期望值。
安全：危险接口（注销账号、真实支付/推送、内部扣币、投币、渠道屏蔽、废弃写接口）不正向调用；这些接口一律不调用，留到 P1 用一次性账号 / 沙盒。

用法：python3 -I p0_probe.py   （环境变量 AT_SID/AT_PF/AT_APPVERSION/AT_APPBUILD 同 run_batch1.py；合同从 backend-server origin/dev 读）
输出：qa-notes/runs/p0/<日期>-<pf>-<commit>.json
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import BASE, CTX, Client  # noqa: E402
from schema_diff import collapse, diff  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.environ.get("APP_SERVER_REPO") or os.path.expanduser("~/qa-workflow/mirrors/backend-server")   # 只读镜像，launchd 读不了桌面（11-25）
sys.path.insert(0, HERE)
from fixtures import F  # noqa: E402
SERIES = F("p0_series")
COMMON = {"sid", "pf", "appVersion", "appBuild", "lang", "uid", "token", "tz", "ab"}

# P0 不调用（原因）。
NO_CALL = {
    "/api/user/remove": "注销账号", "/api/v1/member/frozen": "注销账号", "/api/v1/member/logout": "登出使 token 失效",
    "/api/v1/member/sign": "第三方登录，需要真实 openToken", "/api/v1/member/unbind": "解绑第三方",
    "/api/apple/notify": "苹果回调，需真实签名", "/api/pay/verify": "支付验单，需真实票据", "/api/af/push": "AppsFlyer 回调",
    "/api/open/push/send": "真实发推送", "/api/open/wallet/trade": "内部扣退币（X-Internal-Key）",
    "/api/v2/thirdPay/stripe/purchase": "创建 Stripe 支付", "/api/v2/thirdPay/stripe/portal": "创建 Stripe Customer",
    "/api/v2/thirdPay/stripe/subscription/cancel": "取消订阅", "/api/v2/thirdPay/stripe/subscription/resume": "恢复订阅",
    "/api/episode/insert/coin": "投币扣金币", "/api/channel/init": "写渠道屏蔽缓存，可能把测试剧屏蔽掉",
    "/api/user/token/save": "废弃写接口", "/api/v2/series/duration": "废弃写接口",
}


def deployed():
    import urllib.request
    with urllib.request.urlopen(BASE + "/actuator/info", timeout=10, context=CTX) as r:
        return json.loads(r.read().decode())["git"]["commit"]["id"]


def contract():
    raw = subprocess.check_output(["git", "-C", SERVER, "show", "origin/dev:api/openapi/app-v1.yaml"])
    out = subprocess.check_output(["uv", "run", "-q", "--no-project", "--with", "pyyaml", "python", "-c",
                                   "import sys,yaml,json;print(json.dumps(yaml.safe_load(sys.stdin.read())))"], input=raw)
    return json.loads(out)


def ops(spec):
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method != "post":
                continue
            rb = ((op.get("requestBody") or {}).get("content") or {})
            sch = (list(rb.values())[0].get("schema") if rb else None) or {}
            props = sch.get("properties") or {}
            req = [k for k in (sch.get("required") or []) if k not in COMMON]
            opt = [k for k in props if k not in COMMON and k not in req]
            resp = (((op.get("responses") or {}).get("200") or {}).get("content") or {}).get("application/json", {}).get("schema")
            yield path, op, props, req, opt, resp


class Ctx:
    """跑探测前先取一些真实值：tab、剧集、活动、推荐位。"""

    def __init__(self, c):
        self.c = c
        self.v = {"seriesId": SERIES, "pn": 1, "ps": 10, "cur": 0, "ts": int(time.time() * 1000), "duration": 60,
                  "vote": 0, "cancel": 1, "flush": 0, "fav": 0, "countryCode": "US", "currencyCode": "USD",
                  "paymentOrderIds": ["at-probe-none"], "key": "love", "uaInfo": "at-probe", "params": "",
                  "position": 1, "tagIds": "", "sortBy": 1, "incConf": 0}
        idx = (c.call("/api/drama/index").get("data") or {}).get("tabs") or []
        if idx:
            self.v["htId"] = idx[0].get("htId")
            # foid（栏位 id）按 合同维护人 11-11 的说法从 index/tab 返回里取，别写死；第一个 tab 不一定有，逐个 tab 找
            for t in idx:   # foid 在 data.hfds[].foid（栏位列表），不在 datas 里
                tab = c.call("/api/drama/index/tab", {"htId": t.get("htId"), "pn": 1, "ps": 20}).get("data") or {}
                fo = [d for d in (tab.get("hfds") or []) + (tab.get("ohfds") or []) if isinstance(d, dict) and d.get("foid")]
                if fo:
                    self.v["htId"], self.v["foid"] = t.get("htId"), fo[0]["foid"]
                    break
        sd = (c.call("/api/series/detail", {"seriesId": SERIES}).get("data") or {}).get("seriesData") or {}
        eds = [e for s in (sd.get("seds") or []) for e in (s.get("eds") or [])]
        free = [e for e in eds if (e.get("coin") or 0) == 0]
        # 服务端 ps 封顶 50，要翻页读全（11-16：1000058 的解锁记录被挤到第 2 页，探测拿不到已解锁集，unlock 正向被写成 10101）
        hist = []
        for pn in range(1, 41):
            hd = c.call("/api/user/episode/unlock/history", {"ps": 50, "pn": pn}).get("data") or {}
            hist += hd.get("data") or []
            if not hd.get("hasMore"):
                break
        done = [h.get("episodeId") for h in hist if h.get("seriesId") == SERIES]
        if free:
            self.v.update({"episodeId": free[0]["episodeId"], "sno": free[0]["sno"]})
        # 解锁类正向只用「已解锁过的集」，重复解锁跳过、不扣费
        unl = [e for e in eds if e.get("episodeId") in done]
        if unl:
            e = unl[0]
            self.v["episodes"] = json.dumps([{"episodeId": e["episodeId"], "sno": e["sno"], "coin": e.get("coin")}])
            self.v["cate"] = 2
        acts = ((c.call("/api/act/all/detail", {"ts": self.v["ts"]}).get("data") or {}).get("datas")) or []
        if acts:
            a = acts[0].get("data") or {}
            self.v.update({"actId": a.get("activityId"), "actCate": acts[0].get("cate", a.get("cate")), "curDay": a.get("curDay")})
        user = c.call("/api/user/info").get("user") or {}
        self.v["autoUnlock"] = user.get("autoUnlock", 0)

    def value(self, name, schema):
        if name in self.v and self.v[name] is not None:
            return self.v[name]
        t = (schema or {}).get("type")
        t = t[0] if isinstance(t, list) else t
        return {"integer": 1, "number": 1, "boolean": False, "array": [], "object": {}}.get(t, "")


def call(c, path, body, auth=True, drop=()):
    st, r = c.call(path, body, auth=auth, drop=drop, raw=True)
    return {"http": st, "code": r.get("code"), "message": r.get("message")}, r


def main():
    sid = os.environ.get("AT_SID", "at-sid-01")
    pf = os.environ.get("AT_PF", "a")
    c = Client(sid, pf=pf, app_version=os.environ.get("AT_APPVERSION", "1.1.0"),
               app_build=int(os.environ.get("AT_APPBUILD", "1010001")))
    v0 = deployed()
    print("测试服版本（开始）", v0, flush=True)
    spec = contract()
    login = c.login()
    assert login.get("code") == 0, login
    ctx = Ctx(c)
    routes = json.load(open(os.path.join(HERE, "../../runs/p0/java_routes.json"))) if os.path.exists(
        os.path.join(HERE, "../../runs/p0/java_routes.json")) else {}
    results = []
    for path, op, props, req, opt, resp in ops(spec):
        rec = {"path": path, "summary": op.get("summary"), "tag": (op.get("tags") or ["-"])[0],
               "draft": op.get("x-status") == "draft", "required": req, "optional": opt,
               "login": (routes.get(path) or {}).get("login")}
        if path in NO_CALL:
            rec["skipped"] = NO_CALL[path]  # 危险接口连「不带 token」也不调：万一登录标记判断错，请求会进到业务里
            results.append(rec)
            print("SKIP", path, NO_CALL[path], rec.get("no_token", ""), flush=True)
            continue
        body = {k: ctx.value(k, props.get(k)) for k in req + opt}
        rec["body"] = body
        rec["positive"], r = call(c, path, body)
        if resp:
            rec["schema_diff"] = collapse(diff(resp, r))
        rec["drop_required"] = {k: call(c, path, body, drop=(k,))[0] for k in req}
        rec["drop_optional"] = {k: call(c, path, body, drop=(k,))[0] for k in opt}
        if rec["login"]:
            rec["no_token"], _ = call(c, path, body, drop=("token",))
        results.append(rec)
        print(f"{'D' if rec['draft'] else 'F'} {path} → {rec['positive']['code']} {rec['positive']['message']} | "
              f"字段差异 {len(rec.get('schema_diff') or [])}", flush=True)
    v1 = deployed()
    print("测试服版本（结束）", v1, "（变化，本轮作废）" if v1 != v0 else "")
    os.makedirs(os.path.join(HERE, "../../runs/p0"), exist_ok=True)
    tag = os.environ.get("AT_TAG", "")  # 例如合同版本，避免同一测试服版本的多次探测互相覆盖
    out = os.path.join(HERE, f"../../runs/p0/{time.strftime('%Y-%m-%d')}-{pf}-{v0}{tag}.json")
    contract_rev = subprocess.check_output(["git", "-C", SERVER, "rev-parse", "--short", "origin/dev"]).decode().strip()
    json.dump({"version_start": v0, "version_end": v1, "contract": contract_rev, "sid": sid, "pf": pf, "results": results, "calls": c.log},
              open(out, "w"), ensure_ascii=False, indent=1)
    print("结果", os.path.normpath(out))


if __name__ == "__main__":
    main()
