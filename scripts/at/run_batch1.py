"""第一批 22 个核心接口 + 场景 + 反向用例试跑。测试服 tac，固定账号 at-sid-01。"""
import json
import sys
import time

sys.path.insert(0, ".")
from client import Client  # noqa: E402

SERIES = 1000058  # 首页 Popular 里的剧：前 5 集免费，第 6 集起付费
results = []


def deployed():
    """测试服当前部署的 commit（S1）。"""
    import urllib.request
    from client import BASE, CTX
    try:
        with urllib.request.urlopen(BASE + "/actuator/info", timeout=10, context=CTX) as r:
            info = json.loads(r.read().decode())
        return info.get("git", {}).get("commit", {}).get("id", "?")
    except Exception as e:  # noqa: BLE001
        return f"unknown({type(e).__name__})"


VERSION_START = deployed()
print("测试服版本（开始）:", VERSION_START, flush=True)


def check(case, endpoint, ok, detail=""):
    results.append({"case": case, "endpoint": endpoint, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + case + (" | " + detail if detail else ""), flush=True)


def code(r):
    return r.get("code")


import os
SID = os.environ.get("AT_SID", "at-sid-01")
PF = os.environ.get("AT_PF", "a")
AV = os.environ.get("AT_APPVERSION", "1.1.0")
AB = int(os.environ.get("AT_APPBUILD", "1010001"))
c = Client(SID, pf=PF, app_version=AV, app_build=AB)

# ---- S-A 登录与基础 ----
r = c.login()
check("A1 登录拿 token/uid", "/api/user/login", code(r) == 0 and c.uid and c.token)
r = c.call("/api/init")
check("A2 init 返回配置", "/api/init", code(r) == 0 and "globalConf" in (r.get("data") or {}))
r = c.call("/api/conf")
check("A3 conf 成功", "/api/conf", code(r) == 0 and isinstance(r.get("data"), dict))
r = c.call("/api/user/info")
check("A4 user/info 结果在 user 字段", "/api/user/info", code(r) == 0 and r.get("user") and r.get("data") is None)
r = c.call("/api/user/rich")
rich0 = r.get("data") or {}
check("A5 rich 有 coin/bonus", "/api/user/rich", code(r) == 0 and "coin" in rich0 and "bonus" in rich0, f"coin={rich0.get('coin')} bonus={rich0.get('bonus')}")

# ---- S-B 浏览到播放 ----
r = c.call("/api/drama/index")
tabs = (r.get("data") or {}).get("tabs") or []
check("B1 首页 tabs 非空", "/api/drama/index", code(r) == 0 and tabs, f"{len(tabs)} 个 tab")
r = c.call("/api/drama/index/tab", {"htId": tabs[0]["htId"] if tabs else 1})
check("B2 tab 详情有剧", "/api/drama/index/tab", code(r) == 0 and (r.get("data") or {}).get("datas"))
r = c.call("/api/series/data")
check("B3 series/data", "/api/series/data", code(r) == 0 and "we" in (r.get("data") or {}))
r = c.call("/api/series/detail", {"seriesId": SERIES})
sd = (r.get("data") or {}).get("seriesData") or {}
eds = [e for s in (sd.get("seds") or []) for e in (s.get("eds") or [])]
check("B4 剧详情含分集", "/api/series/detail", code(r) == 0 and eds, f"lockEpisode={sd.get('lockEpisode')} 集数={len(eds)}")
r2 = c.call(f"/api/series/detail?seriesId={SERIES}", {"seriesId": 0})
check("B4- seriesId 放 query 无效（只读 body）", "/api/series/detail", code(r2) == 10101, f"code={code(r2)}")
free_ep = next((e for e in eds if e.get("coin", 0) == 0), None)
lock_sno = sd.get("lockEpisode")
# lockEpisode 是剧的首个付费集（episodeId，按剧配置，不随用户变化）；sno 是季号。
# 同一账号会反复跑：取该账号还没解锁的第一个付费集，否则重复解锁会被跳过、不扣费。
_hist = (c.call("/api/user/episode/unlock/history", {"ps": 50}).get("data") or {}).get("data") or []
_done = {i.get("episodeId") for i in _hist if i.get("seriesId") == SERIES}
paid_ep = next((e for e in eds if e.get("episodeId", 0) >= lock_sno and e.get("episodeId") not in _done), None)
lock_sno = paid_ep["episodeId"] if paid_ep else lock_sno
r = c.call("/api/episode/detail", {"seriesId": SERIES, "episodeId": free_ep["episodeId"]})
check("B5 集详情", "/api/episode/detail", code(r) == 0 and (r.get("data") or {}).get("ed"))
r = c.call("/api/episode/detail", {"seriesId": SERIES, "episodeId": 999999})
check("B5- 不存在的集 → 10404", "/api/episode/detail", code(r) == 10404, f"code={code(r)}")
r = c.call("/api/episode/play", {"seriesId": SERIES, "episodeId": free_ep["episodeId"], "sno": free_ep["sno"], "ts": 1000})
check("B6 播放上报（ts>0，不加阅读数）", "/api/episode/play", code(r) == 0)
r = c.call("/api/series/search", {"key": "love"})
check("B7 搜索", "/api/series/search", code(r) == 0 and isinstance((r.get("data") or {}).get("datas"), list), f"{len((r.get('data') or {}).get('datas') or [])} 条")

# ---- S-C 金币解锁 ----
price = paid_ep.get("coin") if paid_ep else None
r = c.call("/api/episode/detail", {"seriesId": SERIES, "episodeId": paid_ep["episodeId"]})
ed = (r.get("data") or {}).get("ed") or {}
check("C0 付费集价格", "/api/episode/detail", code(r) == 0 and ed.get("coin", 0) > 0, f"第{paid_ep['sno']}集 price={ed.get('coin')}")
price = ed.get("coin")
balance0 = (rich0.get("coin") or 0) + (rich0.get("bonus") or 0)
skip = next((e for e in eds if e.get("episodeId") == lock_sno + 2), None)
if skip:
    r = c.call("/api/episode/unlock", {"seriesId": SERIES, "cate": 2, "episodes": json.dumps([{"episodeId": skip["episodeId"], "sno": skip["sno"], "coin": skip.get("coin")}])})
    check("C1- 跳集解锁 → 14005", "/api/episode/unlock", code(r) == 14005, f"code={code(r)}")
r = c.call("/api/episode/unlock", {"seriesId": SERIES, "cate": 2, "episodes": json.dumps([{"episodeId": paid_ep["episodeId"], "sno": paid_ep["sno"], "coin": price + 1}])})
check("C1- 价格不符 → 14004", "/api/episode/unlock", code(r) == 14004, f"code={code(r)}")
r = c.call("/api/episode/unlock", {"seriesId": SERIES, "cate": 3, "episodes": json.dumps([{"episodeId": paid_ep["episodeId"], "sno": paid_ep["sno"], "coin": price}])})
check("C1- cate 非法 → 10101", "/api/episode/unlock", code(r) == 10101, f"code={code(r)}")
r = c.call("/api/episode/unlock", {"seriesId": SERIES, "cate": 1, "episodes": json.dumps([{"episodeId": 999999, "sno": 1}])})
check("C1- cate=1 不属于该剧的集 → 10101 episodeId INVALID（37921f4d 修复）", "/api/episode/unlock", code(r) == 10101, f"code={code(r)} message={r.get('message')}")
r = c.call("/api/episode/unlock", {"seriesId": SERIES, "cate": 2, "episodes": "[]"})
check("C1- episodes 为空 → 10101", "/api/episode/unlock", code(r) == 10101, f"code={code(r)}")
if balance0 >= price:
    r = c.call("/api/episode/unlock", {"seriesId": SERIES, "cate": 2, "episodes": json.dumps([{"episodeId": paid_ep["episodeId"], "sno": paid_ep["sno"], "coin": price}])})
    d = r.get("data") or {}
    check("C1 金币解锁成功", "/api/episode/unlock", code(r) == 0, f"返回 coin={d.get('coin')} bonus={d.get('bonus')}")
    time.sleep(2)
    rich1 = c.call("/api/user/rich").get("data") or {}
    balance1 = (rich1.get("coin") or 0) + (rich1.get("bonus") or 0)
    check("C1 余额减少 = 价格", "/api/user/rich", abs((balance0 - balance1) - price) < 1e-6, f"{balance0} → {balance1}，价格 {price}")
    r = c.call("/api/episode/unlock", {"seriesId": SERIES, "cate": 2, "episodes": json.dumps([{"episodeId": paid_ep["episodeId"], "sno": paid_ep["sno"], "coin": price}])})
    time.sleep(1)
    rich2 = c.call("/api/user/rich").get("data") or {}
    balance2 = (rich2.get("coin") or 0) + (rich2.get("bonus") or 0)
    check("C1 重复解锁不再扣费", "/api/episode/unlock", code(r) == 0 and abs(balance2 - balance1) < 1e-6, f"余额 {balance1} → {balance2}")
    time.sleep(2)
    r = c.call("/api/user/episode/unlock/history")
    items = (r.get("data") or {}).get("data") or []
    check("C2 解锁历史有该集", "/api/user/episode/unlock/history",
          code(r) == 0 and any(i.get("seriesId") == SERIES and i.get("episodeId") == paid_ep["episodeId"] for i in items), f"{len(items)} 条")
else:
    r = c.call("/api/episode/unlock", {"seriesId": SERIES, "cate": 2, "episodes": json.dumps([{"episodeId": paid_ep["episodeId"], "sno": paid_ep["sno"], "coin": price}])})
    check("C1- 余额不足 → 14002", "/api/episode/unlock", code(r) == 14002, f"code={code(r)}，余额 {balance0} < 价格 {price}")
    results.append({"case": "C1 金币解锁成功 / 扣费 / 重复不扣费 / 解锁历史", "endpoint": "/api/episode/unlock", "pass": None, "detail": f"阻塞：余额 {balance0} < 价格 {price}，需要补币"})
    print("BLOCKED C1 正向解锁：余额不足，需要补币")
    r = c.call("/api/user/episode/unlock/history")
    check("C2 解锁历史接口可用", "/api/user/episode/unlock/history", code(r) == 0, f"{len((r.get('data') or {}).get('data') or [])} 条")

# ---- S-D 收藏 ----
r = c.call("/api/series/fav", {"seriesId": SERIES, "fav": 1})
check("D1 收藏", "/api/series/fav", code(r) == 0)
found = False
for _ in range(5):
    time.sleep(1)
    r = c.call("/api/series/fav/list")
    found = any(((x.get("seriesData") or {}).get("seriesId") or (x.get("seData") or {}).get("seriesId")) == SERIES for x in (r.get("data") or []))
    if found:
        break
check("D2 收藏列表含该剧（异步，最多等 5 秒）", "/api/series/fav/list", code(r) == 0 and found)
r = c.call("/api/series/fav", {"seriesId": SERIES, "fav": 0})
gone = False
for _ in range(5):
    time.sleep(1)
    r = c.call("/api/series/fav/list")
    gone = not any(((x.get("seriesData") or {}).get("seriesId") or (x.get("seData") or {}).get("seriesId")) == SERIES for x in (r.get("data") or []))
    if gone:
        break
check("D1 取消收藏后列表不含（复原）", "/api/series/fav/list", code(r) == 0 and gone, f"data={'null' if r.get('data') is None else 'list'}")
r = c.call("/api/series/play/list")
check("D3 播放列表含该剧", "/api/series/play/list",
      code(r) == 0 and any(((x.get("seriesData") or {}).get("seriesId") or (x.get("seData") or {}).get("seriesId")) == SERIES for x in (r.get("data") or [])))

# ---- S-E 任务签到 ----
r = c.call("/api/task/list")
check("E1 任务墙", "/api/task/list", code(r) == 0, f"分组数={len((r.get('data') or {}).get('taskListData') or [])}")
r = c.call("/api/task/chin/list")
ck0 = (r.get("data") or {}).get("checkedDays")
check("E2 签到列表", "/api/task/chin/list", code(r) == 0, f"checkedDays={ck0} today={(r.get('data') or {}).get('today')}")
r = c.call("/api/task/ckin/reward")
first = code(r)
check("E3 签到领取（成功或本档已领）", "/api/task/ckin/reward", first in (0, 14001), f"code={first} rewardBonus={(r.get('data') or {}).get('rewardBonus')}")
r = c.call("/api/task/ckin/reward")
check("E3- 同一档再领 → 14001", "/api/task/ckin/reward", code(r) == 14001, f"code={code(r)}")

# ---- S-G 商店只读 ----
r = c.call("/api/goods/list")
check("F1 商品列表", "/api/goods/list", code(r) == 0, f"keys={list((r.get('data') or {}).keys())}")
r = c.call("/api/vip/rules")
check("F2 VIP 规则", "/api/vip/rules", code(r) == 0)

# ---- S-F 鉴权反向用例 ----
for k, exp in (("token", 10402), ("uid", 10403), ("sid", 10101), ("pf", 10101)):
    r = c.call("/api/user/rich", drop=(k,))
    check(f"F- 缺 {k} → {exp}", "/api/user/rich", code(r) == exp, f"code={code(r)} message={r.get('message')}")
r = c.call("/api/user/rich", {"token": c.token[:-4] + "abcd"})
check("F- token 篡改 → 10401", "/api/user/rich", code(r) == 10401, f"code={code(r)}")
r = Client(SID, pf=PF, app_version=AV, app_build=AB).call("/api/user/login", auth=False, drop=("appVersion",))
check("F- 登录缺 appVersion → 10101", "/api/user/login", code(r) == 10101, f"code={code(r)}")
r = c.call("/api/init", {"appBuild": 0})
check("F- init appBuild=0 → 10101", "/api/init", code(r) == 10101, f"code={code(r)}")

VERSION_END = deployed()
print("测试服版本（结束）:", VERSION_END)
if VERSION_END != VERSION_START:
    print("⚠️ 运行期间测试服版本变化，本轮结果作废，需重跑")
passed = sum(1 for x in results if x["pass"] is True)
blocked = sum(1 for x in results if x["pass"] is None)
print(f"\n合计 {len(results)} 条，通过 {passed}，失败 {len(results) - passed - blocked}，阻塞 {blocked}")
slow = sorted(c.log, key=lambda x: -x["ms"])[:3]
print("最慢：", [(x["path"], x["ms"]) for x in slow])
json.dump({"version_start": VERSION_START, "version_end": VERSION_END, "sid": SID, "pf": PF, "appVersion": AV, "appBuild": AB, "results": results, "calls": c.log}, open(os.environ.get("AT_OUT", "batch1_result.json"), "w"), ensure_ascii=False, indent=1)
