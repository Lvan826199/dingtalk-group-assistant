"""推荐侧接口（OPS-018 推荐侧第一批，11-18）：独立环境 + 独立套件，不进套件 72。
依据：协作库 e29ac31c team-requests/recommendation/TR-RECOMMENDATION-2026-002/api/调用说明.md 第 7 节（按规则断言，不比固定顺序）；
092 用例：features/REQ-092/lanes/recommendation/delivery.md（AC-02 对照组 / 只动 HOT，AC-04 前半在追上限）。
测试服 https://rec.example.com，/v1/* 无鉴权，请求一律带 test=1；不对正式服跑。
平台脚本禁止 type / import；用例只能单步：R01 把版位目录写进变量 reco_topn（"slot:topN,..."，rank 榜 topN 记 0），后面用例读它；092 三组对比用 set_env_value 串起来。
用法：python3 -I platform_reco.py [--dry-run]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from platform_batch1 import items, req  # noqa: E402

PID = 903
BASE = "https://rec.example.com"
ENV = {"name": "reco-test", "desc": "推荐侧测试服（manmiao-series-recom-test），/v1/* 无鉴权，必带 test=1；只跑套件 recommendation"}
ENV_VARS = [("reco_uid_new", "qa092_new_0001", "text"), ("reco_uid_heavy", "ht4sAWrAg3", "text"),
            ("reco_ab_exp", "600444_497_1057", "text"), ("reco_ab_ctrl", "600444_497_1056", "text"), ("reco_seed", "1000231", "json")]
FLOW = "推荐侧 recommendation"
SUITE = {"name": "推荐侧接口回归", "code": "recommendation",
         "description": "推荐侧 /v1/slots、recommend、similar、rank + 负向 + 092 AC-02 / AC-04 前半。按规则断言，不比固定顺序。"}


def ok(code=200):
    return [{"type": "status_code", "expected": code, "mode": "hard"},
            {"type": "json_path", "path": "$.code", "expected": code, "mode": "soft"}]


def bad(code, msg=None):
    a = ok(code)
    if msg:
        a.append({"type": "json_path", "path": "$.msg", "expected": msg, "mode": "soft"})
    return a


def get(name, path, params, asserts=None, teardown=""):
    return {"name": name, "method": "GET", "path": path, "base_url": "{{base_url}}", "headers": {},
            "params": {"test": "1", **params}, "body": None, "extract": [],
            "assertions": ok() if asserts is None else asserts, "setup_script": "", "teardown_script": teardown}


def post(name, path, body, asserts=None, teardown=""):
    return {"name": name, "method": "POST", "path": path, "base_url": "{{base_url}}",
            "headers": {"Content-Type": "application/json"}, "params": {"test": "1"}, "body": body, "extract": [],
            "assertions": ok() if asserts is None else asserts, "setup_script": "", "teardown_script": teardown}


# 读 R01 写的版位目录：topn = {slot: topN}，recs = 启用的 recommend 版位，ranks = 全部 rank 榜
TOPN = r'''
topn, recs, ranks = {}, [], []
for kv in (self.get_env_value('reco_topn') or '').split(','):
    if ':' in kv:
        k, kind, n = kv.split(':')
        topn[k] = int(n)
        (ranks if kind == 'rank' else recs).append(k)
assert recs, '没有版位目录（R01 先跑）'
'''

# 通用 recommend 规则：limit 由调用方先赋值
REC_RULES = TOPN + r'''
r = response.json()
for k in ('code', 'msg', 'requestId', 'recom_ab', 'data'):
    assert k in r, '顶层缺 %s' % k
d = r['data']
assert 'tagIds' in d, 'data 缺 tagIds'
for s, cards in d.items():
    if s == 'tagIds':
        continue
    assert s in recs, '版位 %s 不是启用的 recommend 版位' % s
    assert len(cards) <= min(limit, topn[s]), '%s 条数 %d > min(limit %d, topN %d)' % (s, len(cards), limit, topn[s])
    ids = [c.get('seriesId') for c in cards]
    assert len(ids) == len(set(ids)), '%s 同版位重复剧：%s' % (s, ids)
    for c in cards:
        assert sorted(c.keys()) == ['episodeId', 'seriesId'], '%s 卡片字段应只有 seriesId/episodeId：%s' % (s, c)
        assert all([str(v).isdigit() and v == int(str(v)) for v in (c['seriesId'], c['episodeId'])]) and c['episodeId'] >= 1, '%s 卡片类型/集号不对：%s' % (s, c)
'''

INT_LIST = r'''
assert all([str(x).isdigit() and x == int(str(x)) for x in xs]), '应全为整数 ID：%s' % xs
assert len(xs) == len(set(xs)), '有重复：%s' % xs
'''

CASES = [
    # ---- slots
    ("R01 slots 版位目录：kind/status 合法、rank 榜 topN 为 null、HOT=tripleColumn 启用（写 reco_topn）", "high", "normal",
     "先跑：后面用例按这里的 topN 断言条数。configVersion 记在响应里，取证用。",
     get("slots", "/v1/slots", {}, teardown=r'''
r = response.json(); d = r.get('data') or {}
sl = d.get('slots') or []
assert sl and d.get('configVersion'), '版位目录为空或缺 configVersion'
out = []
for x in sl:
    assert x.get('kind') in ('recommend', 'rank') and x.get('status') in ('active', 'disabled'), '版位字段不合法：%s' % x
    if x['kind'] == 'rank':
        assert x.get('topN') is None, 'rank 榜 topN 应为 null：%s' % x
        out.append('%s:rank:0' % x['slot'])
    elif x['status'] == 'active':
        out.append('%s:rec:%d' % (x['slot'], x.get('topN') or 200))
assert [x for x in sl if x['slot'] == 'tripleColumn' and x['status'] == 'active' and x['kind'] == 'recommend'], 'HOT 版位 tripleColumn 应启用'
self.set_env_value('reco_topn', ','.join(out))''')),
    ("R02 slots 只支持 GET：POST → 404", "low", "exception", "", post("slots post", "/v1/slots", {}, asserts=bad(404, "not found"))),
    # ---- recommend
    ("R03 recommend 不传 slots：返回全部启用版位，条数 ≤ min(20, topN)、版位内不重复、卡片只有 seriesId/episodeId", "high", "normal",
     "limit 默认 20。recom_ab 不传 ab 时为 default，tagIds 不传时恒为 []。",
     get("recommend all", "/v1/recommend", {"uid": "{{reco_uid_new}}", "language": "en", "os": "a"}, teardown="limit = 20\n" + REC_RULES + r'''
assert r['recom_ab'] == 'default', 'recom_ab 应为 default：%s' % r['recom_ab']
assert d['tagIds'] == [], '没传 tagIds 时应为 []'
assert d.get('tripleColumn'), 'HOT 不应为空' ''')),
    ("R04 recommend 指定 slots + limit=5 + request_id：只返回请求且启用的版位，不认识的丢掉不报错，requestId 回显", "high", "normal", "",
     get("recommend slots", "/v1/recommend", {"uid": "{{reco_uid_new}}", "slots": "tripleColumn,forY,searchRs,at_bogus_slot", "limit": "5", "request_id": "qa-at-reco-04"},
         teardown="limit = 5\n" + REC_RULES + r'''
want = set([s for s in ('tripleColumn', 'forY', 'searchRs') if s in recs])
assert set(d.keys()) - set(['tagIds']) <= want, '多出未请求的版位：%s' % list(d.keys())
assert 'at_bogus_slot' not in d, '不认识的版位不应出现'
assert r['requestId'] == 'qa-at-reco-04', 'requestId 应回显：%s' % r['requestId']''')),
    ("R05 recommend 只请求不认识的版位：data 只剩 tagIds", "medium", "normal", "",
     get("recommend unknown slot", "/v1/recommend", {"uid": "{{reco_uid_new}}", "slots": "at_bogus_slot"},
         teardown="d = response.json()['data']\nassert d == {'tagIds': []}, 'data 应只剩 tagIds：%s' % d")),
    ("R06 recommend POST JSON（slots 数组、limit=3）：请求体生效", "high", "normal", "网址上的 test=1 也生效。",
     post("recommend post", "/v1/recommend", {"uid": "{{reco_uid_new}}", "language": "en", "os": "a", "slots": ["tripleColumn"], "limit": 3},
          teardown="limit = 3\n" + REC_RULES + "\nassert set(d.keys()) == set(['tripleColumn', 'tagIds']), '应只有 tripleColumn：%s' % list(d.keys())\nassert d['tripleColumn'], 'HOT 不应为空'")),
    ("R07 recommend limit=0 按 1 处理：每个版位最多 1 条", "medium", "normal", "宽容处理：0 → 1。",
     get("recommend limit0", "/v1/recommend", {"uid": "{{reco_uid_new}}", "slots": "tripleColumn,forY", "limit": "0"}, teardown="limit = 1\n" + REC_RULES)),
    ("R08 recommend 传 tagIds：data.tagIds ⊆ 请求的 tagIds", "medium", "normal", "",
     get("recommend tagids", "/v1/recommend", {"uid": "{{reco_uid_new}}", "slots": "tripleColumn", "tagIds": "6,8"},
         teardown="limit = 20\n" + REC_RULES + "\nassert set([str(t).split(':')[0] for t in d['tagIds']]) <= set(['6', '8']), 'tagIds 应是请求的子集：%s' % d['tagIds']")),
    ("R09 recommend debug=1：debug.scenes.<版位>.items 与 data 同序同数", "medium", "normal", "debug.scenes 可能多出同组版位（items 为空），只核 data 里有的。",
     get("recommend debug", "/v1/recommend", {"uid": "{{reco_uid_new}}", "slots": "tripleColumn,forY", "limit": "9", "debug": "1"}, teardown=r'''
r = response.json(); d = r['data']; sc = (r.get('debug') or {}).get('scenes') or {}
for s, cards in d.items():
    if s == 'tagIds':
        continue
    its = (sc.get(s) or {}).get('items') or []
    assert [(i.get('seriesId'), i.get('episodeId')) for i in its] == [(c['seriesId'], c['episodeId']) for c in cards], '%s debug.items 与 data 不一致' % s
    assert all([i.get('dominant') for i in its]), '%s debug 卡片缺 dominant' % s''')),
    # ---- similar / rank
    ("R10 similar limit=8：纯整数剧 ID、不重复、≤ 8", "high", "normal", "种子剧不存在也会全库补足，所以不断言非空以外的内容。",
     get("similar", "/v1/similar", {"uid": "{{reco_uid_new}}", "seriesId": "{{reco_seed}}", "lang": "en", "os": "android", "limit": "8"},
         teardown="xs = (response.json().get('data') or {}).get('similar')\nassert xs and xs == list(xs), 'similar 应为非空数组：%s' % xs\nassert len(xs) <= 8, '超过 limit：%d' % len(xs)\n" + INT_LIST)),
    ("R11 similar 不传 limit：默认 ≤ 15", "low", "normal", "",
     get("similar default", "/v1/similar", {"uid": "{{reco_uid_new}}", "seriesId": "{{reco_seed}}"},
         teardown="xs = response.json()['data']['similar']\nassert len(xs) <= 15, '默认最多 15：%d' % len(xs)\n" + INT_LIST)),
    ("R12 rank 不传 slots：返回全部 rank 榜，每榜 ≤ 20、不重复", "high", "normal", "和 recommend 相反：不传 = 全部。",
     get("rank all", "/v1/rank", {"language": "en", "os": "a"}, teardown=TOPN + r'''
d = response.json()['data']
assert set([k for k in d.keys() if k != 'debug']) == set(ranks), '应返回全部 rank 榜 %s：%s' % (ranks, list(d.keys()))
for k in ranks:
    xs = d[k]
    assert len(xs) <= 20, '%s 超过默认 20：%d' % (k, len(xs))
''' + INT_LIST.replace("\n", "\n    ").rstrip())),
    ("R13 rank slots 不分大小写（RANKHOT）+ limit=5：只返回 rankHot、≤ 5", "medium", "normal", "",
     get("rank one", "/v1/rank", {"slots": "RANKHOT", "limit": "5"},
         teardown="d = response.json()['data']\nassert list(d.keys()) == ['rankHot'], '应只返回 rankHot：%s' % list(d.keys())\nxs = d['rankHot']\nassert len(xs) <= 5\n" + INT_LIST)),
    # ---- 连通
    ("R14 /health 连通：ok=true", "low", "normal", "只做连通。", {**get("health", "/health", {}, asserts=[{"type": "status_code", "expected": 200, "mode": "hard"}],
                                                               teardown="assert response.json().get('ok') is True"), "params": {}}),
    ("R15 /ready 连通：ok=true", "low", "normal", "只做连通。", {**get("ready", "/ready", {}, asserts=[{"type": "status_code", "expected": 200, "mode": "hard"}],
                                                              teardown="assert response.json().get('ok') is True"), "params": {}}),
    # ---- 负向（调用说明第 7 节「稳定可断言」）
    ("N01 recommend 缺 uid → 400 uid is required", "medium", "exception", "", get("no uid", "/v1/recommend", {}, asserts=bad(400, "uid is required"))),
    ("N02 recommend uid 129 字符 → 400 uid_too_long", "medium", "exception", "",
     get("uid 129", "/v1/recommend", {"uid": "u" * 129}, asserts=bad(400, "invalid request: uid_too_long"))),
    ("N03 recommend slots 33 个 → 400 slots_too_many", "medium", "exception", "上限 32 个。",
     get("slots 33", "/v1/recommend", {"uid": "{{reco_uid_new}}", "slots": ",".join("s%d" % i for i in range(33))}, asserts=bad(400, "invalid request: slots_too_many"))),
    ("N04 recommend POST 数组体 → 400 request body must be a JSON object", "medium", "exception", "",
     post("array body", "/v1/recommend", [1], asserts=bad(400, "invalid json: request body must be a JSON object"))),
    ("N05 recommend POST 请求体 > 64KB → 413 payload too large", "medium", "exception", "",
     post("payload 413", "/v1/recommend", {"uid": "{{reco_uid_new}}", "pad": "a" * 70000}, asserts=bad(413, "payload too large"))),
    ("N06 similar 缺 seriesId → 400 bad request", "medium", "exception", "", get("similar no seed", "/v1/similar", {"uid": "{{reco_uid_new}}"}, asserts=bad(400, "bad request"))),
    ("N07 similar 种子写成 series_id → 400 bad request", "low", "exception", "种子剧只认 seriesId。",
     get("similar series_id", "/v1/similar", {"uid": "{{reco_uid_new}}", "series_id": "{{reco_seed}}"}, asserts=bad(400, "bad request"))),
    ("N08 未知路径 → 404 not found", "low", "exception", "", get("unknown path", "/v1/at-unknown", {}, asserts=bad(404, "not found"))),
]

# ---- 092：同一用户「不带分组 → 对照组 → 实验组」，平台单步用例用变量串起来
CMP = ''
for tag, uid in (("重度在追 ht4sAWrAg3", "{{reco_uid_heavy}}"), ("全新用户 qa092_new_0001", "{{reco_uid_new}}")):
    p = {"uid": uid, "language": "en", "os": "a", "slots": "tripleColumn,searchRs", "limit": "9", "debug": "1"}
    k = "h" if "heavy" in uid else "n"
    CASES += [
        (f"092-{k}1 {tag}：不带分组请求 HOT + searchRs（记下顺序）", "medium", "normal", "AC-02 基准。",
         get("no group", "/v1/recommend", p, teardown=CMP + f'''
d = response.json()['data']
assert d.get('tripleColumn'), 'HOT 不应为空'
self.set_env_value('reco_{k}_none', ','.join(['%s/%s' % (c['seriesId'], c['episodeId']) for c in (d.get('tripleColumn') or [])]))
self.set_env_value('reco_{k}_none_rs', ','.join(['%s/%s' % (c['seriesId'], c['episodeId']) for c in (d.get('searchRs') or [])]))''')),
        (f"092-{k}2 {tag}：对照组（_1056）HOT 与不带分组逐位相同（AC-02）", "high", "normal", "对照组不变：剧和集逐位相同。",
         get("ctrl group", "/v1/recommend", {**p, "ab": "{{reco_ab_ctrl}}"}, teardown=CMP + f'''
d = response.json()['data']
a = ','.join(['%s/%s' % (c['seriesId'], c['episodeId']) for c in (d.get('tripleColumn') or [])]); b = self.get_env_value('reco_{k}_none')
assert a == b, '对照组 HOT 与不带分组不同：\\n对照 %s\\n无组 %s' % (a, b)
self.set_env_value('reco_{k}_ctrl_rs', ','.join(['%s/%s' % (c['seriesId'], c['episodeId']) for c in (d.get('searchRs') or [])]))''')),
        (f"092-{k}3 {tag}：实验组（_1057）用成绩表时按分排、在追 ≤ 2；规则未发布/成绩表过期时退回原规则与不带分组相同；searchRs 两组相同（AC-02 / AC-04 前半 / AC-06）", "high", "normal",
         "rank_mode.actual = table 才断言成绩表规则（AC-03 规则由 QA 在测试后台发布，成绩表 48 小时过期）；否则断言退回原规则。置顶（pinned）和试用卡不参与分数排序。测试服试用位预期暂停（trial_state 不是 ok）。",
         get("exp group", "/v1/recommend", {**p, "ab": "{{reco_ab_exp}}"}, teardown=CMP + f'''
r = response.json(); d = r['data']
sc = ((r.get('debug') or {{}}).get('scenes') or {{}}).get('tripleColumn') or {{}}
rm = sc.get('rank_mode') or {{}}
rs = ','.join(['%s/%s' % (c['seriesId'], c['episodeId']) for c in (d.get('searchRs') or [])])
assert rs == self.get_env_value('reco_{k}_ctrl_rs'), '只动 HOT：searchRs 实验组与对照组应相同'
if rm.get('actual') == 'table':
    its = sc.get('items') or []
    sc_ = [i.get('final_score') for i in its if i.get('dominant') != 'pinned' and 'trial_new' not in (i.get('reason_codes') or []) and 'trial_reeval' not in (i.get('reason_codes') or [])]
    assert sc_ == sorted(sc_, reverse=True), '成绩表模式下非置顶卡应按 final_score 从高到低：%s' % sc_
    inprog = [i for i in its if (i.get('rank') or {{}}).get('kind') == 'in_progress']
    assert len(inprog) <= 2, '首屏在追剧 %d 张 > 2' % len(inprog)
    assert rm.get('inprog_max') == 2, 'inprog_max 应为 2：%s' % rm.get('inprog_max')
else:
    a = ','.join(['%s/%s' % (c['seriesId'], c['episodeId']) for c in (d.get('tripleColumn') or [])])
    assert a == self.get_env_value('reco_{k}_none'), '未用成绩表（actual=%s）时实验组应退回原规则、与不带分组相同' % rm.get('actual')''')),
    ]


def main():
    dry = "--dry-run" in sys.argv
    print("推荐侧用例", len(CASES))
    if dry:
        for c in CASES:
            print(" ", c[0])
        return
    envs = {e["name"]: e for e in items(f"/projects/{PID}/environments")}
    env = envs.get(ENV["name"]) or req("POST", f"/projects/{PID}/environments",
                                       {"name": ENV["name"], "base_url": BASE, "description": ENV["desc"], "is_default": False, "timeout": 30})
    have = {v["name"]: v for v in items(f"/projects/{PID}/environments/{env['id']}/variables")}
    for name, value, typ in ENV_VARS:
        if name not in have:
            req("POST", f"/projects/{PID}/environments/{env['id']}/variables", {"name": name, "value": value, "type": typ})
    print("环境", env["id"], ENV["name"])
    flows = {f["name"]: f for f in items(f"/projects/{PID}/business-flows")}
    flow = flows.get(FLOW) or req("POST", f"/projects/{PID}/business-flows", {"name": FLOW, "description": "OPS-018 推荐侧第一批（11-18）"})
    existing = {c["name"]: c for c in items(f"/projects/{PID}/api-test-cases?business_flow_id={flow['id']}")}
    order = []
    for name, prio, ctype, desc, request in CASES:
        meta = {"name": name, "business_flow_id": flow["id"], "description": desc or None, "priority": prio, "case_type": ctype, "tags": ["OPS-018", "recommendation"]}
        c = existing.get(name)
        if c:
            req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}", meta)
        else:
            c = req("POST", f"/projects/{PID}/api-test-cases", meta)
        req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}/case-data",
            {"case_data": {"name": name, "skip": False, "description": desc or None, "request": request, "preconditions": [], "retry": 0}})
        order.append(c["id"])
    for n, c in existing.items():
        if n not in {x[0] for x in CASES}:
            req("DELETE", f"/projects/{PID}/api-test-cases/{c['id']}")
            print("删过期", n)
    suites = {s.get("code"): s for s in items(f"/projects/{PID}/api-suites")}
    suite = suites.get(SUITE["code"]) or req("POST", f"/projects/{PID}/api-suites", {**SUITE, "tags": ["OPS-018"]})
    req("PUT", f"/projects/{PID}/api-suites/{suite['id']}/items",
        {"items": [{"case_id": cid, "sort_order": i, "enabled": True} for i, cid in enumerate(order)]})
    print("套件", suite["id"], SUITE["code"], "挂", len(order), "条")


if __name__ == "__main__":
    main()
