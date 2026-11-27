"""跑套件前的前置条件 2：每个环境的 series 还够不够做"金币解锁 + 跳集"用例。

batch1 的 B4 要在剧里找"付费未解锁、且本集+2 也未解锁"的一对，每轮用掉一对；账号把剧解锁完就得换剧（数据问题，不是缺陷）。
本脚本：读平台环境 163/164 的 series 变量 → 用对应账号算剩余可用对数 → 少于 MIN_PAIRS 就从首页 tab 里挑一部没碰过、
前几集免费、第 lock 集起付费、可用对 ≥ 6 的剧，改掉环境变量（平台变量不支持改，删了重建），并打印。

用法：python3 -I series_check.py [--dry-run]
"""
import json
import time
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import Client  # noqa: E402

T = open(os.path.expanduser("~/.config/aitest/token")).read().strip()
B = "http://aitest.example.internal:8000/api/v1/projects/903"
ENVS = {  # 平台环境 id → 账号
    "170": ("at-sid-07", "i", "1.1.0", 1010002),   # iOS 1.1.0（11-26 全量上线，11-27 加）
    "169": ("at-sid-06", "a", "1.1.1", 1010103),
    "168": ("at-sid-05", "a", "1.1.1", 1010102),
    "163": ("at-sid-01", "a", "1.1.0", 1010001),
    "164": ("at-sid-02", "i", "1.0.9", 1000901),
    "165": ("at-sid-03", "a", "1.1.1", 1010100),
    "166": ("at-sid-04", "i", "1.1.1", 1010101),   # iOS 1.1.1（048 新分支，11-13 加）
}
MIN_PAIRS = 1   # 本轮至少要有一对
MAX_SCAN = 20   # 换剧时每个号最多查的候选剧数（防刷限频）
PICK_PAIRS = 6  # 换剧时候选至少要有这么多对
DRY = "--dry-run" in sys.argv


def req(m, p, body=None):
    r = urllib.request.Request(B + p, data=json.dumps(body).encode() if body else None, method=m,
                               headers={"Authorization": "Bearer " + T, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))


def env_vars(env):
    d = req("GET", f"/environments/{env}/variables?page=1&page_size=100")["data"]
    return d.get("items") if isinstance(d, dict) else d


def set_series(env, sid, why):
    for v in env_vars(env):
        if v["name"] == "series":
            req("DELETE", f"/environments/{env}/variables/{v['id']}")
    req("POST", f"/environments/{env}/variables", {"name": "series", "value": str(sid), "type": "json", "description": why})


def episodes(c, sid):
    d = (c.call("/api/series/detail", {"seriesId": int(sid)}).get("data") or {}).get("seriesData") or {}
    eds = [e for s in (d.get("seds") or []) for e in (s.get("eds") or [])]
    return d, eds


def pairs(c, sid, done):
    d, eds = episodes(c, sid)
    lock = d.get("lockEpisode") or 0
    ids = {e["episodeId"] for e in eds}
    free = [e for e in eds if not e.get("coin")]
    if not lock or not free:
        return d.get("title"), 0
    # 只把确实需要金币的未解锁集算入候选；服务端偶尔会把 lockEpisode 指到
    # 免费/价格为 0 的集，不能因此误判“还有可用付费集”。
    ps = [e["episodeId"] for e in eds if e["episodeId"] >= lock and (e.get("coin") or 0) > 0
          and e["episodeId"] not in done
          and e["episodeId"] + 2 in ids and e["episodeId"] + 2 not in done]
    return d.get("title"), len(ps)


def history(c):
    # 服务端 ps 封顶 50，要按 pn 翻页读全（11-16：只读第一页漏了第 2 页的 1000058，163 换过去后十条用例连锁失败）
    items = []
    for pn in range(1, 41):
        d = c.call("/api/user/episode/unlock/history", {"ps": 50, "pn": pn}).get("data") or {}
        items += d.get("data") or []
        if not d.get("hasMore"):
            break
    h = {}
    for i in items:
        h.setdefault(i.get("seriesId"), set()).add(i.get("episodeId"))
    return h


def candidates(c):
    idx = c.call("/api/drama/index", {}).get("data") or {}
    out = []
    for t in (idx.get("tabs") or [])[:4]:
        d = c.call("/api/drama/index/tab", {"htId": t.get("htId") or t.get("id"), "pn": 1, "ps": 30}).get("data") or {}
        for it in d.get("datas") or []:
            sid = (it.get("seriesData") or it).get("seriesId")
            if sid and sid not in out:
                out.append(sid)
    return out


def main():
    rc = 0
    for env, (sid, pf, ver, build) in ENVS.items():
        c = Client(sid, pf, ver, build)
        if c.login().get("code") != 0:
            print(f"env {env} {sid} 登录失败", flush=True)
            rc = 1
            continue
        cur = next((v["value"] for v in env_vars(env) if v["name"] == "series"), None)
        hist = history(c)
        title, n = pairs(c, cur, hist.get(int(cur), set()))
        if n >= MIN_PAIRS:
            print(f"env {env} series {cur}《{title}》剩 {n} 对可用", flush=True)
            continue
        print(f"env {env} series {cur}《{title}》只剩 {n} 对，换剧…", flush=True)
        pick = None
        # 11-16：防刷 OPS-019 一分钟内看超过 50 部不同的剧会封 24 小时（当晚这里连查候选把三个固定号封了）。
        # 每个号最多查 MAX_SCAN 部候选，每次间隔 2 秒，一分钟不超过 30 部
        scanned = 0
        for s in candidates(c):
            if str(s) == str(cur) or s in hist:
                continue
            if scanned >= MAX_SCAN:
                break
            scanned += 1
            time.sleep(2)
            t2, n2 = pairs(c, s, set())
            if n2 >= PICK_PAIRS:
                pick = (s, t2, n2)
                break
        if not pick:
            print(f"env {env} 没找到合适的剧，需要人工换账号或换剧", flush=True)
            rc = 1
            continue
        if not DRY:
            set_series(env, pick[0], f"{sid} 把 {cur} 的付费集解锁完，series_check 自动换成 {pick[0]}")
        print(f"env {env} series {cur} → {pick[0]}《{pick[1]}》{pick[2]} 对" + ("（dry-run 未改）" if DRY else "（已改平台变量，记得同步 platform_batch1.py 的 ENVS）"), flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
