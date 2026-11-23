"""OPS-019 补验（QA负责人 11-18 19:06 测试群）：/api/series/detail 的 429/10429 完整响应头、响应体和合同比对。
全部用一次性游客号（sid at-tmp-ops019-<场景>-<时间戳>），不碰固定回归账号。证据写 runs/ops019/<时间>.json。
用法：python3 -I ops019_evidence.py run       跑场景 A / B / 控制场景
      python3 -I ops019_evidence.py recheck   场景 B 封禁约 1 小时后，用同一个号再看一次详情是否恢复
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from client import BASE, CTX, Client  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "runs", "ops019")
LATEST = os.path.join(OUT, "latest.json")
SERIES = 1000034                     # 测试服现有剧（env 164 套件用的同一部）
PF, VER, BUILD = "a", "1.1.1", 1010100
NOW = lambda: time.strftime("%Y-%m-%d %H:%M:%S")


def full(c, path, body=None):
    """和 Client.call 一样发请求，但把响应头和原文都留下来做证据。"""
    payload = dict(c.common, uid=c.uid, token=c.token, **(body or {}))
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t = NOW()
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            status, headers, text = r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        status, headers, text = e.code, dict(e.headers), e.read().decode(errors="replace")
    try:
        js = json.loads(text)
    except ValueError:
        js = None
    return {"time": t, "path": path, "req": body or {}, "status": status, "headers": headers, "body": text, "json": js}


def short(r):
    j = r["json"] or {}
    return (r["status"], j.get("code"), j.get("message"))


def guest(tag):
    c = Client(f"at-tmp-ops019-{tag}-{int(time.time() * 1000)}", PF, VER, BUILD)
    assert c.login().get("code") == 0, f"{tag} 游客登录失败"
    return c


def first_episode(c):
    d = (c.call("/api/series/detail", {"seriesId": SERIES}).get("data") or {}).get("seriesData") or {}
    return [e for s in d.get("seds") or [] for e in s.get("eds") or []][0]


def scope(c, ep):
    """封禁期间别的接口应不受影响。"""
    return {
        "user/info": full(c, "/api/user/info"),
        "drama/foryou": full(c, "/api/drama/foryou", {"pn": 1, "ps": 10}),
        "series/search": full(c, "/api/series/search", {"key": "love"}),
        "episode/play": full(c, "/api/episode/play", {"seriesId": SERIES, "episodeId": ep["episodeId"], "sno": ep["sno"], "ts": 1000}),
    }


def contract_check(r):
    """合同 api/openapi/app-v1.yaml（ba0de461）/api/series/detail：429 写在 description 里——HTTP 429，body code=10429、message=TOO_MANY_REQUESTS；
    responses 只定义了 200（必有 code / message / data / user）。逐项对。"""
    j = r["json"] or {}
    return {
        "HTTP 状态 = 429": r["status"] == 429,
        "code = 10429": j.get("code") == 10429,
        "message = TOO_MANY_REQUESTS": j.get("message") == "TOO_MANY_REQUESTS",
        "body 是 JSON": r["json"] is not None,
        "字段（200 结构要求 code/message/data/user）": sorted(j.keys()),
        "data": j.get("data", "<缺>"),
        "user": j.get("user", "<缺>"),
        "Content-Type": r["headers"].get("Content-Type"),
    }


def run():
    os.makedirs(OUT, exist_ok=True)
    with urllib.request.urlopen(BASE + "/actuator/info", timeout=10, context=CTX) as r:
        info = json.loads(r.read().decode())
    ev = {"start": NOW(), "actuator": info, "client": {"pf": PF, "appVersion": VER, "appBuild": BUILD}}
    ep = first_episode(guest("probe"))

    # 场景 A：1 分钟内 51 部以上不同的剧（1..55，不存在的剧号也算一部，合同原文）
    a = guest("A")
    while time.time() % 60 > 35:
        time.sleep(1)
    with ThreadPoolExecutor(10) as ex:
        ra = list(ex.map(lambda i: full(a, "/api/series/detail", {"seriesId": i}), range(1, 51)))
    ra += [full(a, "/api/series/detail", {"seriesId": i}) for i in range(51, 54)]   # 第 51～53 次串行，序号确定
    first = next((i + 1 for i, r in enumerate(ra) if r["status"] == 429), None)
    ra.append(full(a, "/api/series/detail", {"seriesId": SERIES}))                  # 封后看真实存在的剧
    ev["A"] = {"uid": a.uid, "sid": a.common["sid"], "请求数": len(ra), "首个 429 序号": first,
               "前 50 次": sorted(set(map(short, ra[:50]))), "第 51 次起": [short(r) for r in ra[50:]],
               "第 51 次完整响应": ra[50], "封后看存在的剧": ra[-1], "合同比对": contract_check(ra[50]),
               "其他接口": {k: short(v) for k, v in scope(a, ep).items()}}

    # 场景 B：同一部剧看 200 次、一集没播，第 201 次起
    b = guest("B")
    with ThreadPoolExecutor(10) as ex:
        rb = list(ex.map(lambda i: full(b, "/api/series/detail", {"seriesId": SERIES}), range(200)))
    b201, b202 = full(b, "/api/series/detail", {"seriesId": SERIES}), full(b, "/api/series/detail", {"seriesId": 1000007})
    ev["B"] = {"uid": b.uid, "sid": b.common["sid"], "token": b.token, "前 200 次": sorted(set(map(short, rb))),
               "第 201 次完整响应": b201, "第 202 次（换一部剧）": short(b202), "限频开始": b201["time"],
               "合同比对": contract_check(b201),
               "与场景 A body 一致": (b201["json"] or {}) == (ra[50]["json"] or {}),
               "其他接口": {k: short(v) for k, v in scope(b, ep).items()}}

    # 控制场景
    n = guest("C-normal")
    c_same = guest("C-same")
    with ThreadPoolExecutor(10) as ex:
        same = list(ex.map(lambda i: full(c_same, "/api/series/detail", {"seriesId": SERIES}), range(60)))
    c_play = guest("C-play")
    p = full(c_play, "/api/episode/play", {"seriesId": SERIES, "episodeId": ep["episodeId"], "sno": ep["sno"], "ts": 1000})
    with ThreadPoolExecutor(10) as ex:
        rp = list(ex.map(lambda i: full(c_play, "/api/series/detail", {"seriesId": SERIES}), range(200)))
    p201 = full(c_play, "/api/series/detail", {"seriesId": SERIES})
    c_404 = guest("C-404")
    ev["控制"] = {
        "正常账号看 1 次详情": short(full(n, "/api/series/detail", {"seriesId": SERIES})),
        "同一部剧 1 分钟内看 60 次": sorted(set(map(short, same))),
        "先播放一集": short(p), "播放后详情 200 次": sorted(set(map(short, rp))), "播放后第 201 次": short(p201),
        "不存在的剧号 999999999（新号）": full(c_404, "/api/series/detail", {"seriesId": 999999999}),
    }
    with urllib.request.urlopen(BASE + "/actuator/info", timeout=10, context=CTX) as r:
        ev["actuator_end"] = json.loads(r.read().decode())
    ev["end"] = NOW()
    path = os.path.join(OUT, time.strftime("%Y%m%d-%H%M%S") + ".json")
    for f in (path, LATEST):
        json.dump(ev, open(f, "w"), ensure_ascii=False, indent=1)
    print(path)


def recheck():
    ev = json.load(open(LATEST))
    b = Client(ev["B"]["sid"], PF, VER, BUILD)
    b.uid, b.token = ev["B"]["uid"], ev["B"]["token"]
    r = full(b, "/api/series/detail", {"seriesId": SERIES})
    ev["B"]["到期后复查"] = {"time": r["time"], "结果": short(r)}
    json.dump(ev, open(LATEST, "w"), ensure_ascii=False, indent=1)
    print(r["time"], short(r))


if __name__ == "__main__":
    {"run": run, "recheck": recheck}[sys.argv[1]]()
