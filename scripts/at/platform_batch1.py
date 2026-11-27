"""把第一批用例录进测试平台 AiTestProject（项目 APP-API）。可重复执行：按名称/代码查到就更新，不重复建。

用法：python3 -I platform_batch1.py [--dry-run]
令牌：~/.config/aitest/token（Bearer PAT）。合同：backend-server origin/dev 的 api/openapi/app-v1.yaml。
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

API = "http://aitest.example.internal:8000/api/v1"
TOKEN = open(os.path.expanduser("~/.config/aitest/token")).read().strip()
DRY = "--dry-run" in sys.argv
SERVER_REPO = os.environ.get("APP_SERVER_REPO") or os.path.expanduser("~/qa-workflow/mirrors/backend-server")   # 只读镜像，launchd 读不了桌面（11-25）

PROJECT = {"name": "APP 接口自动化（OPS-018）", "code": "APP-API",
           "description": "短剧 App 服务端接口自动化（OPS-018）。接口定义只从 backend-server api/openapi/app-v1.yaml 导入；"
                          "旧项目 ANAMANA 保留为 1.0.6 历史证据。负责人本人。", "is_public": False}
COMMON_VARS = [("lang", "en_US", "text")]
# series 按环境分：每轮金币解锁消耗一集付费集，账号把一部剧解锁完就换剧（11-11 Android 1000058→1000006→1000066，iOS 1000058→1000007→1000059→1000066，series_check.py 自动换；11-16 Android 163→1000007→1000047、165→1000059→1000081）
ENVS = [
    {"name": "tac-android", "desc": "测试服 tac，Android 1.1.0（appBuild 1010001），固定设备 at-sid-01", "default": True,
     "vars": [("sid", "at-sid-01", "text"), ("pf", "a", "text"), ("appVersion", "1.1.0", "text"), ("appBuild", "1010001", "json"), ("series", "1000047", "json")]},
    {"name": "tac-ios", "desc": "测试服 tac，iOS 1.0.9（appBuild 1000901），固定设备 at-sid-02", "default": False,
     "vars": [("sid", "at-sid-02", "text"), ("pf", "i", "text"), ("appVersion", "1.0.9", "text"), ("appBuild", "1000901", "json"), ("series", "1000034", "json")]},
    {"name": "tac-android-1010100", "desc": "测试服 tac，Android 1.1.1（appBuild 1010100，048 新分支），新游客专用号 at-sid-03；只对测试服跑（合同维护人 11-12）", "default": False,
     "vars": [("sid", "at-sid-03", "text"), ("pf", "a", "text"), ("appVersion", "1.1.1", "text"), ("appBuild", "1010100", "json"), ("series", "1000081", "json")]},
    {"name": "tac-ios-1010101", "desc": "测试服 tac，iOS 1.1.1（pf=i，appBuild 1010101，048 新分支），新游客专用号 at-sid-04；只对测试服跑（用户 11-13 同意按版本加环境）", "default": False,
     "vars": [("sid", "at-sid-04", "text"), ("pf", "i", "text"), ("appVersion", "1.1.1", "text"), ("appBuild", "1010101", "json"), ("series", "1000058", "json")]},
    {"name": "tac-android-1010102", "desc": "测试服 Android 1.1.1（appBuild 1010102，11-19 提审），独立自动化专用号 at-sid-05", "default": False,
     "vars": [("sid", "at-sid-05", "text"), ("pf", "a", "text"), ("appVersion", "1.1.1", "text"), ("appBuild", "1010102", "json"), ("series", "1000058", "json")]},
    {"name": "tac-android-1010103", "desc": "测试服 Android 1.1.1（appBuild 1010103，11-19 GP提审），独立自动化专用号 at-sid-06", "default": False,
     "vars": [("sid", "at-sid-06", "text"), ("pf", "a", "text"), ("appVersion", "1.1.1", "text"), ("appBuild", "1010103", "json"), ("series", "1000058", "json")]},
    {"name": "tac-ios-1010002", "desc": "测试服 iOS 1.1.0（appBuild 1010002，11-26 全量上线），独立自动化专用号 at-sid-07", "default": False,
     "vars": [("sid", "at-sid-07", "text"), ("pf", "i", "text"), ("appVersion", "1.1.0", "text"), ("appBuild", "1010002", "json"), ("series", "1000058", "json")]},
]
FLOW = "第一批核心接口（22 个）"
SUITE = {"name": "第一批核心接口回归", "code": "batch1",
         "description": "22 个已转正接口 + 场景 + 反向用例。首尾读 /actuator/info，版本变化则本轮作废。"}


# ---------------------------------------------------------------- 用例定义
def body(auth=True, drop=(), **extra):
    b = {"sid": "{{sid}}", "pf": "{{pf}}", "appVersion": "{{appVersion}}", "appBuild": "{{appBuild}}", "lang": "{{lang}}"}
    if auth:
        b.update({"uid": "{{uid}}", "token": "{{token}}"})
    b.update(extra)
    for k in drop:
        b.pop(k, None)
    return b


def code_is(v):
    return [{"type": "status_code", "expected": 200, "mode": "hard"},
            {"type": "json_path", "path": "$.code", "expected": v, "mode": "soft"}]


def step(name, path, b=None, method="POST", extract=(), asserts=None, setup="", teardown="", params=None):
    return {"name": name, "method": method, "path": path, "base_url": "{{base_url}}",
            "headers": {"Content-Type": "application/json"} if method == "POST" else {},
            "params": params or {}, "body": b if method == "POST" else None,
            "extract": [{"name": n, "type": "json_path", "path": p, "optional": False} for n, p in extract],
            "assertions": code_is(0) if asserts is None else asserts,
            "setup_script": setup, "teardown_script": teardown}


def unlock_eps(ep, sno, coin=None):
    s = '[{"episodeId":{{%s}},"sno":{{%s}}' % (ep, sno)
    return s + (',"coin":{{%s}}}]' % coin if coin else "}]")


# 注意：环境变量即使类型是 json，取出来也是字符串，脚本里比较前要 int()。
# 套件内的脚本：response 是 httpx.Response；self.get/set_env_value 读写变量池（写入的变量导出给后续用例）
PICK_EPISODES = """
d = (response.json().get('data') or {}).get('seriesData') or {}
eds = []
for s in (d.get('seds') or []):
    eds += (s.get('eds') or [])
assert eds, '剧详情没有分集'
lock = d.get('lockEpisode')
hist = self.get_env_value('unlock_hist') or []
done = set([i.get('episodeId') for i in hist if i.get('seriesId') == int(self.get_env_value('series'))])
free = [e for e in eds if (e.get('coin') or 0) == 0]
paid = [e for e in eds if e.get('episodeId', 0) >= lock and (e.get('coin') or 0) > 0 and e.get('episodeId') not in done]
assert free, '没有免费集'
assert paid, '这个账号已解锁完所有付费集，需要换剧或换账号（数据问题，不是缺陷）'
self.set_env_value('free_ep', free[0]['episodeId'])
self.set_env_value('free_sno', free[0]['sno'])
ids = set([e.get('episodeId') for e in eds])
cands = [e for e in paid if (e['episodeId'] + 2) in ids and (e['episodeId'] + 2) not in done]
assert cands, '付费未解锁集里找不到"本集+2 也未解锁"的组合，跳集用例无法构造：账号在这部剧快解锁完了，换剧或换账号（数据问题，不是缺陷）'
self.set_env_value('paid_ep', cands[0]['episodeId'])
self.set_env_value('paid_sno', cands[0]['sno'])
skip = [e for e in eds if e.get('episodeId') == cands[0]['episodeId'] + 2]
self.set_env_value('skip_ep', skip[0]['episodeId'])
self.set_env_value('skip_sno', skip[0]['sno'])
self.set_env_value('skip_coin', skip[0].get('coin') or 0)
"""
BALANCE = """
d = response.json().get('data') or {}
assert 'coin' in d and 'bonus' in d, 'rich 缺 coin/bonus'
self.set_env_value('%s', (d.get('coin') or 0) + (d.get('bonus') or 0))
self.set_env_value('%s_bonus', d.get('bonus') or 0)
"""
FAV_HAS = """
items = response.json().get('data') or []
ids = [((x.get('seriesData') or {}).get('seriesId') or (x.get('seData') or {}).get('seriesId')) for x in items]
assert %s (int(self.get_env_value('series')) in ids), '收藏列表%s该剧（收藏是异步写入）'
"""

CASES = [
    # name, priority, case_type, description, preconditions, request, retry
    ("V0 记录测试服部署版本（开始）", "high", "normal", "S1：读 /actuator/info，记 git commit 作为本轮基线。", [],
     step("actuator info", "/actuator/info", method="GET", extract=[("version_start", "$.git.commit.id")],
          asserts=[{"type": "status_code", "expected": 200, "mode": "hard"}])),
    ("A1 登录拿 token/uid", "urgent", "normal", "固定 sid 登录，提取 token/uid 给后续用例。", [],
     step("login", "/api/user/login", body(auth=False), extract=[("token", "$.data.token"), ("uid", "$.data.uid")])),
    ("A2 init 返回配置", "high", "normal", "", [],
     step("init", "/api/init", body(), teardown="assert 'globalConf' in (response.json().get('data') or {}), '缺 globalConf'")),
    ("A3 conf 成功", "high", "normal", "", [],
     step("conf", "/api/conf", body(), teardown="assert isinstance(response.json().get('data'), dict), 'data 不是对象'")),
    ("A4 user/info 结果在 user 字段", "high", "normal", "合同差异：结果在 user，不在 data。", [],
     step("user info", "/api/user/info", body(),
          teardown="r = response.json()\nassert r.get('user'), 'user 为空'\nassert r.get('data') is None, 'data 应为 null'")),
    ("A5 rich 有 coin/bonus（记余额）", "high", "normal", "记解锁前余额 balance0。", [],
     step("rich", "/api/user/rich", body(), teardown=BALANCE % ("balance0", "balance0"))),
    ("B1 首页 tabs 非空", "high", "normal", "", [],
     step("index", "/api/drama/index", body(), extract=[("htId", "$.data.tabs[0].htId")],
          teardown="assert (response.json().get('data') or {}).get('tabs'), 'tabs 为空'")),
    ("B2 tab 详情有剧", "medium", "normal", "", [],
     step("index tab", "/api/drama/index/tab", body(htId="{{htId}}"),
          teardown="assert (response.json().get('data') or {}).get('datas'), 'datas 为空'")),
    ("B3 series/data", "medium", "normal", "", [],
     step("series data", "/api/series/data", body(), teardown="assert 'we' in (response.json().get('data') or {}), '缺 we'")),
    ("B4 剧详情含分集（选本轮的免费集/付费集）", "urgent", "normal",
     "测试剧 1000058（QA负责人 11-10 确认长期保留）。lockEpisode 是首个付费集的 episodeId；取本账号还没解锁的第一个付费集，否则重复解锁不扣费。",
     [step("unlock history", "/api/user/episode/unlock/history", body(ps=50), extract=[("unlock_hist", "$.data.data")])],
     step("series detail", "/api/series/detail", body(seriesId="{{series}}"), teardown=PICK_EPISODES)),
    ("B4- seriesId 放 query 无效（只读 body）", "medium", "exception", "", [],
     step("series detail query", "/api/series/detail", body(seriesId=0), params={"seriesId": "{{series}}"}, asserts=code_is(10101))),
    ("B5 集详情", "high", "normal", "", [],
     step("episode detail", "/api/episode/detail", body(seriesId="{{series}}", episodeId="{{free_ep}}"),
          teardown="assert (response.json().get('data') or {}).get('ed'), 'ed 为空'")),
    ("B5- 不存在的集 → 10404", "medium", "boundary", "", [],
     step("episode detail 404", "/api/episode/detail", body(seriesId="{{series}}", episodeId=999999), asserts=code_is(10404))),
    ("B6 播放上报（ts>0，不加阅读数）", "medium", "normal", "", [],
     step("play", "/api/episode/play", body(seriesId="{{series}}", episodeId="{{free_ep}}", sno="{{free_sno}}", ts=1000))),
    ("B7 搜索", "medium", "normal", "测试服按 uid 限流 100 次/小时。", [],
     step("search", "/api/series/search", body(key="love"),
          teardown="assert isinstance((response.json().get('data') or {}).get('datas'), list), 'datas 不是列表'")),
    ("C0 付费集价格", "urgent", "normal", "", [],
     step("paid episode detail", "/api/episode/detail", body(seriesId="{{series}}", episodeId="{{paid_ep}}"),
          teardown="ed = (response.json().get('data') or {}).get('ed') or {}\nassert (ed.get('coin') or 0) > 0, '付费集价格应 > 0'\n"
                   "self.set_env_value('price', ed.get('coin'))\nself.set_env_value('price_plus', ed.get('coin') + 1)")),
    ("C1- 跳集解锁 → 14005", "high", "exception", "", [],
     step("unlock skip", "/api/episode/unlock",
          body(seriesId="{{series}}", cate=2, episodes=unlock_eps("skip_ep", "skip_sno", "skip_coin")), asserts=code_is(14005))),
    ("C1- 价格不符 → 14004", "high", "exception", "", [],
     step("unlock wrong price", "/api/episode/unlock",
          body(seriesId="{{series}}", cate=2, episodes=unlock_eps("paid_ep", "paid_sno", "price_plus")), asserts=code_is(14004))),
    ("C1- cate 非法 → 10101", "medium", "exception", "", [],
     step("unlock cate 3", "/api/episode/unlock",
          body(seriesId="{{series}}", cate=3, episodes=unlock_eps("paid_ep", "paid_sno", "price")), asserts=code_is(10101))),
    ("C1- cate=1 不属于该剧的集 → 10101", "high", "exception", "37921f4d 修复的集数校验漏洞。看广告校验与次数上限见 OPS-019。", [],
     step("unlock cate1 foreign ep", "/api/episode/unlock",
          body(seriesId="{{series}}", cate=1, episodes='[{"episodeId":999999,"sno":1}]'), asserts=code_is(10101))),
    ("C1- episodes 为空 → 10101", "medium", "boundary", "", [],
     step("unlock empty", "/api/episode/unlock", body(seriesId="{{series}}", cate=2, episodes="[]"), asserts=code_is(10101))),
    ("C1 金币解锁成功", "urgent", "normal", "余额不足会返回 14002：那是测试数据问题，用后台 addGem 补币后重跑，不提缺陷。", [],
     step("unlock coin", "/api/episode/unlock",
          body(seriesId="{{series}}", cate=2, episodes=unlock_eps("paid_ep", "paid_sno", "price")), asserts=[],
          teardown="r = response.json()\nassert r.get('code') != 14002, '余额不足（14002）：先用后台补币再重跑，不是缺陷'\n"
                   "assert r.get('code') == 0, 'code=%s message=%s' % (r.get('code'), r.get('message'))")),
    ("D1 收藏", "high", "normal", "收藏异步写入，列表检查放在后面。", [],
     step("fav", "/api/series/fav", body(seriesId="{{series}}", fav=1))),
    ("E1 任务墙", "medium", "normal", "", [], step("task list", "/api/task/list", body())),
    ("E2 签到列表", "medium", "normal", "", [], step("checkin list", "/api/task/chin/list", body())),
    ("C1 余额减少 = 价格", "urgent", "normal", "bonus 先扣、再扣 coin；测试服 bonus 10 分钟过期。", [],
     step("rich after unlock", "/api/user/rich", body(),
          teardown=BALANCE % ("balance1", "balance1") + "assert abs((self.get_env_value('balance0') - self.get_env_value('balance1')) - self.get_env_value('price')) < 1e-6, "
                   "'余额 %s → %s，价格 %s' % (self.get_env_value('balance0'), self.get_env_value('balance1'), self.get_env_value('price'))\n"
                   "b0, b1, pr = float(self.get_env_value('balance0_bonus')), float(self.get_env_value('balance1_bonus')), float(self.get_env_value('price'))\n"
                   "assert b0 - b1 >= min(pr, b0) - 1e-6, 'bonus 应先扣：bonus %s → %s，价格 %s' % (b0, b1, pr)")),  # S5：bonus 先扣（bonus 过期只会扣更多，不会误判）
    ("C1 重复解锁不再扣费", "high", "normal", "",
     [step("unlock again", "/api/episode/unlock", body(seriesId="{{series}}", cate=2, episodes=unlock_eps("paid_ep", "paid_sno", "price")))],
     step("rich after repeat", "/api/user/rich", body(),
          teardown=BALANCE % ("balance2", "balance2") + "assert abs(self.get_env_value('balance2') - self.get_env_value('balance1')) < 1e-6, "
                   "'重复解锁又扣了：%s → %s' % (self.get_env_value('balance1'), self.get_env_value('balance2'))")),
    ("F1 商品列表", "medium", "normal", "", [], step("goods", "/api/goods/list", body())),
    ("F2 VIP 规则", "medium", "normal", "", [], step("vip rules", "/api/vip/rules", body())),
    ("C2 解锁历史有该集", "high", "normal", "", [],
     step("unlock history", "/api/user/episode/unlock/history", body(),
          teardown="items = (response.json().get('data') or {}).get('data') or []\n"
                   "assert [i for i in items if i.get('seriesId') == int(self.get_env_value('series')) and i.get('episodeId') == self.get_env_value('paid_ep')], '解锁历史没有本轮解锁的集'")),
    ("D2 收藏列表含该剧", "high", "normal", "异步写入，失败自动重试 3 次。", [],
     step("fav list", "/api/series/fav/list", body(), teardown=FAV_HAS % ("", "应含"))),
    ("D1 取消收藏（复原）", "medium", "normal", "", [],
     step("unfav", "/api/series/fav", body(seriesId="{{series}}", fav=0))),
    ("D3 播放列表含该剧", "medium", "normal", "", [],
     step("play list", "/api/series/play/list", body(),
          teardown="items = response.json().get('data') or []\n"
                   "ids = [((x.get('seriesData') or {}).get('seriesId') or (x.get('seData') or {}).get('seriesId')) for x in items]\n"
                   "assert int(self.get_env_value('series')) in ids, '播放列表没有该剧'")),
    ("E3 签到领取（成功或本档已领）", "medium", "normal", "测试服签到按 UTC 15 分钟一档。", [],
     step("checkin reward", "/api/task/ckin/reward", body(), asserts=[{"type": "status_code", "expected": 200, "mode": "hard"}],
          teardown="assert response.json().get('code') in (0, 14001), 'code=%s' % response.json().get('code')")),
    ("E3- 同一档再领 → 14001", "medium", "exception", "", [],
     step("checkin reward again", "/api/task/ckin/reward", body(), asserts=code_is(14001))),
    ("F- 缺 token → 10402", "high", "exception", "", [], step("no token", "/api/user/rich", body(drop=("token",)), asserts=code_is(10402))),
    ("F- 缺 uid → 10403", "high", "exception", "", [], step("no uid", "/api/user/rich", body(drop=("uid",)), asserts=code_is(10403))),
    ("F- 缺 sid → 10101", "high", "exception", "", [], step("no sid", "/api/user/rich", body(drop=("sid",)), asserts=code_is(10101))),
    ("F- 缺 pf → 10101", "high", "exception", "", [], step("no pf", "/api/user/rich", body(drop=("pf",)), asserts=code_is(10101))),
    ("F- token 篡改 → 10401", "high", "exception", "", [],
     step("bad token", "/api/user/rich", body(token="{{bad_token}}"), asserts=code_is(10401),
          setup="t = self.get_env_value('token') or ''\nself.set_env_value('bad_token', t[:-4] + 'abcd')")),
    ("F- 登录缺 appVersion → 10101", "medium", "exception", "", [],
     step("login no appVersion", "/api/user/login", body(auth=False, drop=("appVersion",)), asserts=code_is(10101))),
    ("F- init appBuild=0 → 10101", "medium", "boundary", "", [],
     step("init appBuild 0", "/api/init", body(appBuild=0), asserts=code_is(10101))),
    ("D1 取消收藏后列表不含", "medium", "normal", "异步写入，失败自动重试 3 次。", [],
     step("fav list after unfav", "/api/series/fav/list", body(), teardown=FAV_HAS % ("not", "不应含"))),
    ("V9 部署版本未变化（变了本轮作废）", "urgent", "normal", "和 V0 比对；不一致说明跑的过程中测试服重新部署了，本轮结果作废重跑。", [],
     step("actuator info end", "/actuator/info", method="GET",
          asserts=[{"type": "status_code", "expected": 200, "mode": "hard"},
                   {"type": "json_path", "path": "$.git.commit.id", "expected": "{{version_start}}", "mode": "hard"}])),
]
RETRY = {"D2 收藏列表含该剧": 3, "D1 取消收藏后列表不含": 3}


# ---------------------------------------------------------------- HTTP
def req(method, path, data=None, files=None):
    url = API + path
    headers = {"Authorization": "Bearer " + TOKEN}
    payload = None
    if files:
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in (data or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for k, (fname, content) in files.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'
                         f'Content-Type: application/yaml\r\n\r\n'.encode() + content + b"\r\n")
        payload = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    elif data is not None:
        payload = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if DRY and method != "GET":
        print("  [dry-run]", method, path, (json.dumps(data, ensure_ascii=False)[:160] if data and not files else ""))
        return {"id": -1}
    r = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            d = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} → HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")
    if d.get("code") not in (200, 201, None):
        raise SystemExit(f"{method} {path} → {json.dumps(d, ensure_ascii=False)[:500]}")
    return d.get("data")


def items(path):
    out, page = [], 1
    while True:
        d = req("GET", f"{path}{'&' if '?' in path else '?'}page={page}&page_size=100")
        if isinstance(d, list):
            return d
        out += d.get("items") or []
        if len(out) >= (d.get("total") or 0) or not d.get("items"):
            return out
        page += 1


# ---------------------------------------------------------------- 主流程
def main():
    proj = next((p for p in items("/projects") if p["code"] == PROJECT["code"]), None)
    if not proj:
        print("建项目", PROJECT["code"])
        proj = req("POST", "/projects", PROJECT)
    pid = proj["id"]
    print("项目", pid, PROJECT["code"])
    if DRY and pid == -1:
        print("（dry-run：项目尚不存在，后续步骤只打印用例清单）")
        for c in CASES:
            print("  case", c[0])
        print(f"共 {len(CASES)} 条")
        return

    envs = {e["name"]: e for e in items(f"/projects/{pid}/environments")}
    for e in ENVS:
        env = envs.get(e["name"])
        if not env:
            print("建环境", e["name"])
            env = req("POST", f"/projects/{pid}/environments",
                      {"name": e["name"], "base_url": "https://api-test.example.com", "description": e["desc"],
                       "is_default": e["default"], "timeout": 30})
        have = {v["name"]: v for v in items(f"/projects/{pid}/environments/{env['id']}/variables")}
        for name, value, typ in e["vars"] + COMMON_VARS:
            v = have.get(name)
            if not v:
                req("POST", f"/projects/{pid}/environments/{env['id']}/variables", {"name": name, "value": value, "type": typ})
            elif str(v.get("value")) != value:
                print(f"  ⚠ 变量 {name} 平台上是 {v.get('value')!r}，脚本里是 {value!r}，未改动，请在平台上核对")
        print("环境", env["id"], e["name"], "变量已同步")

    if "--import" in sys.argv:
        rev = subprocess.check_output(["git", "-C", SERVER_REPO, "rev-parse", "--short", "origin/dev"]).decode().strip()
        spec = subprocess.check_output(["git", "-C", SERVER_REPO, "show", "origin/dev:api/openapi/app-v1.yaml"])
        res = req("POST", f"/projects/{pid}/api-imports/upload",
                  {"import_type": "openapi", "merge_strategy": "merge", "auto_module_by_tag": "true"},
                  files={"file": (f"app-v1@{rev}.yaml", spec)})
        print("导入合同 app-v1.yaml @", rev, "→ 导入记录", (res or {}).get("id"), (res or {}).get("status"))

    flows = {f["name"]: f for f in items(f"/projects/{pid}/business-flows")}
    flow = flows.get(FLOW) or req("POST", f"/projects/{pid}/business-flows",
                                  {"name": FLOW, "description": "OPS-018 第一批：22 个已转正接口的冒烟、场景与反向用例。"})
    existing = {c["name"]: c for c in items(f"/projects/{pid}/api-test-cases?business_flow_id={flow['id']}")}
    order = []
    for name, prio, ctype, desc, pre, request in CASES:
        meta = {"name": name, "business_flow_id": flow["id"], "description": desc or None, "priority": prio,
                "case_type": ctype, "tags": ["OPS-018", "batch1"]}
        c = existing.get(name)
        if c:
            req("PUT", f"/projects/{pid}/api-test-cases/{c['id']}", meta)
        else:
            c = req("POST", f"/projects/{pid}/api-test-cases", meta)
        data = {"name": name, "skip": False, "description": desc or None, "request": request,
                "preconditions": pre, "retry": RETRY.get(name, 0)}
        req("PUT", f"/projects/{pid}/api-test-cases/{c['id']}/case-data", {"case_data": data})
        order.append(c["id"])
    print("用例", len(order), "条已写入")

    suites = {s.get("code"): s for s in items(f"/projects/{pid}/api-suites")}
    suite = suites.get(SUITE["code"]) or req("POST", f"/projects/{pid}/api-suites",
                                             {**SUITE, "tags": ["OPS-018"]})
    req("PUT", f"/projects/{pid}/api-suites/{suite['id']}/items",
        {"items": [{"case_id": cid, "sort_order": i, "enabled": True} for i, cid in enumerate(order)]})
    print("套件", suite["id"], SUITE["code"], "已按顺序挂", len(order), "条")


if __name__ == "__main__":
    main()
