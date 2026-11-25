"""把 P0 核实过的单接口用例录进测试平台 APP-API，作为测试存档。可重复执行：按名称更新，不重复建。

每个接口：正向（期望 = 核实后的真实行为）、逐个去掉必填参数、逐个去掉可选参数、不带 token（要登录的）。
期望值以「代码 + 真实返回」为准；合同不一致的写在用例描述里，指向文档修正清单。
返回结构：该接口在修正清单里没有差异的，加 JSON Schema 断言（直接用合同）；有差异的等 合同维护人 改完合同、重新生成时再加。
危险接口（P0 未调用的 18 个）和需要补数据的 3 个不建正向用例。

用法：python3 -I platform_p0.py <android.json> [--dry-run]
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_util import merged_case  # noqa: E402
from platform_batch1 import body, items, req, step  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.environ.get("APP_SERVER_REPO") or os.path.expanduser("~/qa-workflow/mirrors/backend-server")   # 只读镜像，launchd 读不了桌面（11-25）
PID = 903
SUITE = {"name": "单接口全量（P0 核实）", "code": "p0-single",
         "description": "OPS-018 P0：合同 81 个接口里可安全调用的 63 个，每个接口正向 + 去必填 + 去可选 + 不带 token。期望值以代码和真实返回为准。"}
SKIP_POSITIVE = {"/api/act/reward", "/api/v2/thirdPay/stripe/orderResult"}  # 待补数据重测（index/field 11-11 起 foid 从 index/tab 取，正向启用）
REWARD = {"/api/task/ads/reward", "/api/task/ckin/ad/reward", "/api/task/ckin/reward", "/api/task/watch/reward",
          "/api/act/reward"}
QUERY_ONLY = {"/api/open/data", "/api/open/wsp/series"}
DEPRECATED = {"/api/open/data", "/api/open/wsp/series"}  # 11-10 研发B：原给 wsp 用，已废弃，随下线删合同；不建用例

# 套件开头的准备用例：登录 + 取真实数据，导出变量给后面的单接口用例
PREP_PICK = """
d = (response.json().get('data') or {}).get('seriesData') or {}
eds = []
for s in (d.get('seds') or []):
    eds += (s.get('eds') or [])
hist = self.get_env_value('unlock_hist') or []
done = [h.get('episodeId') for h in hist if h.get('seriesId') == int(self.get_env_value('series'))]
free = [e for e in eds if (e.get('coin') or 0) == 0]
assert free, '没有免费集'
self.set_env_value('free_ep', free[0]['episodeId'])
self.set_env_value('free_sno', free[0]['sno'])
unl = [e for e in eds if e.get('episodeId') in done]
assert unl, '测试账号还没有已解锁的集（先跑一轮 batch1）'
e = unl[0]
self.set_env_value('unl_episodes', '[{"episodeId":%s,"sno":%s,"coin":%s}]' % (e['episodeId'], e['sno'], e.get('coin') or 0))
"""
PREP = [
    ("00 准备：登录", [], step("login", "/api/user/login", body(auth=False), extract=[("token", "$.data.token"), ("uid", "$.data.uid")])),
    ("00 准备：首页取 htId", [], step("index", "/api/drama/index", body(), extract=[("htId", "$.data.tabs[0].htId")])),
    # foid（栏位 id）按 合同维护人 11-11 说法从 index/tab 的 hfds 里取，别写死；两端 tabs[0] 都有 hfds（Android htId 1 → 7，iOS htId 2 → 8）
    ("00 准备：tab 取 foid", [], step("index tab", "/api/drama/index/tab", body(htId="{{htId}}", pn=1, ps=20), extract=[("foid", "$.data.hfds[0].foid")])),
    ("00 准备：选免费集 / 已解锁集",
     [step("unlock history", "/api/user/episode/unlock/history", body(ps=50), extract=[("unlock_hist", "$.data.data")])],
     step("series detail", "/api/series/detail", body(seriesId="{{series}}"), teardown=PREP_PICK)),
    ("00 准备：取 autoUnlock 当前值", [], step("user info", "/api/user/info", body(), extract=[("autoUnlock", "$.user.autoUnlock")])),
]
VALUES = {"seriesId": "{{series}}", "episodeId": "{{free_ep}}", "sno": "{{free_sno}}", "htId": "{{htId}}", "foid": "{{foid}}",
          "episodes": "{{unl_episodes}}", "cate": 2, "autoUnlock": "{{autoUnlock}}", "ts": "{{ts}}"}
ROUTES = json.load(open(os.path.join(HERE, "../../runs/p0/java_routes.json")))
TS_SETUP = "self.set_env_value('ts', global_function.timestamp_ms())"


def contract():
    raw = subprocess.check_output(["git", "-C", SERVER, "show", "origin/dev:api/openapi/app-v1.yaml"])
    out = subprocess.check_output(["uv", "run", "-q", "--no-project", "--with", "pyyaml", "python", "-c",
                                   "import sys,yaml,json;print(json.dumps(yaml.safe_load(sys.stdin.read())))"], input=raw)
    return json.loads(out)


# 合同临时补丁（11-23 本人定）：研发A f45a5d84 让无角标的剧返回 "badge": null（合同 fc3da1ef 仍写 type: object）。
# 先按 null 合法处理；合同维护人 把合同改成允许 null 后删掉这段（合同里出现 null 就不再改）。
def _badge_nullable(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "badge" and isinstance(v, dict) and v.get("type") == "object":
                v["type"] = ["object", "null"]
            else:
                _badge_nullable(v)
    elif isinstance(node, list):
        for v in node:
            _badge_nullable(v)
    return node


def _banner_optional(node):
    """11-23 研发A口径：剧没配横幅图时不返回 bannerUrl（双端已兼容），合同改非必填——先在这里去掉 required。"""
    if isinstance(node, dict):
        req = node.get("required")
        if isinstance(req, list) and "bannerUrl" in req:
            node["required"] = [x for x in req if x != "bannerUrl"]
        for v in node.values():
            _banner_optional(v)
    elif isinstance(node, list):
        for v in node:
            _banner_optional(v)
    return node


_contract_raw = contract
contract = _contract_raw  # 11-23 合同维护人 已把 badge 可空、bannerUrl 非必填落库（c3e30a69），临时补丁停用


def clean_paths():
    """修正清单里没有「返回」差异的接口。"""
    lst = open(os.environ.get("P0_LIST", os.path.join(HERE, "../../runs/p0/文档修正清单-25ebb12.md")), encoding="utf-8").read()
    bad = set()
    for sec in re.split(r"\n### ", lst)[1:]:
        if "- [返回]" in sec:
            bad.add(sec.split("（", 1)[0].strip())
    return bad


def code_assert(code):
    return [{"type": "status_code", "expected": 200, "mode": "hard"},
            {"type": "json_path", "path": "$.code", "expected": code, "mode": "soft"}]


def main():
    probe = json.load(open(sys.argv[1]))
    spec = contract()
    resp_diff = clean_paths()
    cases = []  # (flow, name, priority, case_type, desc, pre, request)
    group = {}  # (flow, "param"|"auth") → [(标签, step, 期望 code)]：11-13 起逐接口检查按模块合并成一条（merge_util），覆盖不减
    for name, pre, request in PREP:
        cases.append(("单接口-00 准备", name, "urgent", "normal", "单接口套件的公共准备，导出变量给后续用例。", pre, request))
    for r in probe["results"]:
        path = r["path"]
        if "skipped" in r:
            continue
        if path in SKIP_POSITIVE or path in DEPRECATED:
            continue  # 正向都没成功，去参数的结果没有参照意义；补数据后再建 / 已废弃接口不建
        tag = r.get("tag") or "其他"
        flow = f"单接口-{tag}"
        doc = "合同草稿" if r.get("draft") else "合同已转正"
        b = {k: VALUES.get(k, v) for k, v in (r.get("body") or {}).items()}
        setup = TS_SETUP if "ts" in b else ""
        params = {}
        pos = r["positive"]
        if path in QUERY_ONLY:  # 只读查询串；没有 open token，只能测拒绝路径
            for nm, prm, exp, why in ((f"{path} 错误 token → 10101", {"cate": 1, "token": "at-invalid"}, 10101, "open 接口只读查询串的 token / cate。"),
                                      (f"{path} 缺 cate → 10101", {"token": "at-invalid"}, 10101, "当前返回 500「未知异常」，已报缺陷，修好后应为 10101。")):
                cases.append((flow, nm, "medium", "exception", why, [], step("query", path, {}, params=prm, asserts=code_assert(exp))))
            continue
        if path not in SKIP_POSITIVE:
            asserts = code_assert(0)
            teardown = ""
            if path in REWARD:  # 奖励类：本档已领也算正常
                asserts = [{"type": "status_code", "expected": 200, "mode": "hard"}]
                teardown = "c = response.json().get('code')\nassert c in (0, 14001, 14003), 'code=%s message=%s' % (c, response.json().get('message'))"  # 14001 本档已领、14003 观看任务已过期
            elif pos["code"] != 0:
                asserts = code_assert(pos["code"])
            if path not in resp_diff and pos["code"] == 0 and path not in REWARD:
                sch = spec["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
                asserts.append({"type": "json_schema", "expected": sch, "mode": "soft"})
            desc = f"{r.get('summary') or ''}。{doc}；P0 核实 code={pos['code']} {pos['message'] or ''}。" + \
                   ("返回结构与合同一致，带 Schema 断言。" if path not in resp_diff else "返回结构与合同有差异，见文档修正清单，合同改完后补 Schema 断言。")
            title = f"{path} 正向" if pos["code"] == 0 or path in REWARD else f"{path} 按合同请求 → {pos['code']}（合同缺请求字段）"
            cases.append((flow, title, "high", "normal", desc, [],
                          step("positive", path, body(**b), params=params, asserts=asserts, setup=setup, teardown=teardown)))
        for k, v in (r.get("drop_required") or {}).items():
            exp = v["code"]
            note = "合同标必填，实际有默认值（文档修正清单）" if exp == 0 else ("缺参返回 500，已报缺陷，修好后应为 10101" if exp == 500 else "")
            if exp == 500:
                exp = 10101  # 期望正确行为：修复前这条会失败，作为缺陷跟踪
            group.setdefault((flow, "param"), []).append((f"{path} 缺必填 {k}" + (f"（{note}）" if note else ""),
                          step(f"drop {k}", path, body(**{x: y for x, y in b.items() if x != k}), params=params, setup=setup), exp))
        for k, v in (r.get("drop_optional") or {}).items():
            if path == "/api/task/ckin/reward":
                continue  # 和正向共用一档奖励，结果取决于顺序，不单独测
            group.setdefault((flow, "param"), []).append((f"{path} 缺可选 {k}",
                          step(f"drop {k}", path, body(**{x: y for x, y in b.items() if x != k}), params=params, setup=setup), v["code"]))
        if r.get("no_token") and (ROUTES.get(path) or {}).get("login"):  # 只对真有 @VerifyToken 的接口
            group.setdefault((flow, "auth"), []).append((f"{path} 不带 token",
                          step("no token", path, body(drop=("token",), **b), params=params, setup=setup), 10402))
    for i, ((flow, kind), checks) in enumerate(sorted(group.items(), key=lambda x: (x[0][0], x[0][1]))):
        if kind == "auth":
            cases.append(merged_case(flow, f"{flow[4:]}：不带 token → 10402（{len(checks)} 个接口）", "@VerifyToken 鉴权拦截，逐接口检查。", checks, f"p0a{i}"))
        else:
            cases.append(merged_case(flow, f"{flow[4:]}：缺参数校验（{len(checks)} 项）", "合同必填缺了应报错、可选缺了应正常，逐项检查。", checks, f"p0p{i}", case_type="boundary"))
    print("用例", len(cases))
    if "--dry-run" in sys.argv:
        for c in cases[:12]:
            print(" ", c[0], "|", c[1])
        return
    flows = {f["name"]: f for f in items(f"/projects/{PID}/business-flows")}
    existing = {}
    order = []
    for flow_name in sorted({c[0] for c in cases}):
        f = flows.get(flow_name) or req("POST", f"/projects/{PID}/business-flows",
                                        {"name": flow_name, "description": "OPS-018 P0 单接口用例（按合同模块分组）"})
        flows[flow_name] = f
        existing.update({(flow_name, c["name"]): c for c in items(f"/projects/{PID}/api-test-cases?business_flow_id={f['id']}")})
    for flow_name, name, prio, ctype, desc, pre, request in cases:
        meta = {"name": name, "business_flow_id": flows[flow_name]["id"], "description": desc, "priority": prio,
                "case_type": ctype, "tags": ["OPS-018", "P0", "单接口"]}
        c = existing.get((flow_name, name))
        if c:
            req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}", meta)
        else:
            c = req("POST", f"/projects/{PID}/api-test-cases", meta)
        req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}/case-data",
            {"case_data": {"name": name, "skip": False, "description": desc, "request": request, "preconditions": pre, "retry": 0}})
        order.append(c["id"])
    # 合同改了（必填变可选等）用例名会变：单接口流程里不在本次 cases 的旧用例一律删掉（平台 + 套件），不留过期用例
    wanted = {(c[0], c[1]) for c in cases}
    stale = [c for key, c in existing.items() if key not in wanted]
    for c in stale:
        req("DELETE", f"/projects/{PID}/api-test-cases/{c['id']}")
    if stale:
        print("删过期单接口用例", len(stale), [c["name"] for c in stale][:8])
    stale_ids = {c["id"] for c in stale}
    # 11-11 用户要求只留一个套件：全量回归 regression(72) = batch1(70 的用例，保持原顺序) + 本脚本的单接口用例。
    # 70 / 71 已停用只留历史；这里只刷新 72，不再碰 71。
    suites = {s.get("code"): s for s in items(f"/projects/{PID}/api-suites")}
    batch1 = [it["case_id"] for it in sorted(req("GET", f"/projects/{PID}/api-suites/{suites['batch1']['id']}")["items"], key=lambda x: x["sort_order"])]
    reg = req("GET", f"/projects/{PID}/api-suites/{suites['regression']['id']}")
    full = batch1 + [cid for cid in order if cid not in batch1]
    # 套件里其它来源的用例（platform_p1.py 的 P1 用例）保留在最后，不被本脚本刷掉
    full += [it["case_id"] for it in sorted(reg["items"], key=lambda x: x["sort_order"]) if it["case_id"] not in full and it["case_id"] not in stale_ids]
    req("PUT", f"/projects/{PID}/api-suites/{reg['id']}/items",
        {"items": [{"case_id": cid, "sort_order": i, "enabled": True} for i, cid in enumerate(full)]})
    print("套件", reg["id"], "regression 挂", len(full), "条（batch1", len(batch1), "+ 单接口", len(order), "）")


if __name__ == "__main__":
    main()
