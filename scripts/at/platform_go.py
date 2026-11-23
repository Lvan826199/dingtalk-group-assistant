"""Go 侧接口（go-server）用例录入测试平台 APP-API，挂到套件 72 regression 末尾（P1 之后）。
合同：Apifox 导出 runs/apifox/export-*.json（研发C 11-12：以 Apifox 为准）；行为按 go_probe.py 11-12 探测（runs/p0/go-修正清单-20261112.md）。

  评论 APP-047：公共参数放 JSON body；链路 发一条 → 重发 duplicated → 回复列表 → 点赞/取消 → 二级回复 → 删除；屏蔽/解除；每个接口不带 token → 10402
  二创 remix：公共参数只从 Header 读（token/uid/sid/pf/appVersion/appBuild/lang）；只读 + 反向，不跑 submit / publish / delete / download 正向
  Stories：/api/go/series/fav|play/list，Header 模式
可重复执行：按名称更新，删过期。用法：python3 -I platform_go.py [--dry-run]
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from go_probe import REMIX_SERIES, Spec  # noqa: E402
from merge_util import merged_case  # noqa: E402
from platform_batch1 import body, items, req, step  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PID = 903
SPEC = Spec(json.load(open(sorted(glob.glob(os.path.join(HERE, "../../runs/apifox/export-*.json")))[-1], encoding="utf-8")))
HDR = {"token": "{{token}}", "uid": "{{uid}}", "sid": "{{sid}}", "pf": "{{pf}}", "appVersion": "{{appVersion}}", "appBuild": "{{appBuild}}", "lang": "{{lang}}"}


def code_assert(code):
    return [{"type": "status_code", "expected": 200, "mode": "hard"},
            {"type": "json_path", "path": "$.code", "expected": code, "mode": "soft"}]


def _loosen(s):
    """给平台 jsonschema 用：oneOf → anyOf（首页/后续页两种形态都可能同时匹配），去掉 additionalProperties（多出来的字段由 go_probe 单独记差异）。"""
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            if k == "additionalProperties":
                continue
            if k == "oneOf":
                k = "anyOf"
            out[k] = _loosen(v)
        return out
    if isinstance(s, list):
        return [_loosen(x) for x in s]
    return s


def schema_assert(path):
    return code_assert(0) + [{"type": "json_schema", "expected": _loosen(SPEC.success_schema(path)), "mode": "soft"}]


def hstep(name, path, b, **kw):
    """Header 模式（remix/*、series/*）：公共参数放头，body 只有业务字段。no_token=True 时带 uid 不带 token。"""
    no_token = kw.pop("no_token", False)
    s = step(name, path, b, **kw)
    s["headers"].update({k: v for k, v in HDR.items() if not (no_token and k == "token")})
    return s


GC = "P0-Go 评论（APP-047）"
GR = "P0-Go 二创（remix）"
GS = "P0-Go Stories 列表"
EP_SETUP = "self.set_env_value('go_req', 'at-go-' + str(global_function.timestamp_ms()))"
CASES = [  # (flow, name, priority, case_type, desc, preconditions, request)
    (GC, "G00 准备：取回归剧第 1 集 → go_ep、生成 clientRequestId", "high", "normal", "评论挂在环境变量 series 的第 1 集。", [],
     step("series detail", "/api/series/detail", body(seriesId="{{series}}"), extract=[("go_ep", "$.data.seriesData.seds[0].eds[0].episodeId")], setup=EP_SETUP)),
    (GC, "G01 comment/entry → 0 且符合合同", "high", "normal", "allowEntry/allowPublish/count/publicCount/myNotPublicCount。", [],
     step("entry", "/api/go/comment/entry", body(seriesId="{{series}}", episodeId="{{go_ep}}"), asserts=schema_assert("/api/go/comment/entry"))),
    (GC, "G02 comment/report/reasons → 0 且符合合同", "medium", "normal", "", [],
     step("reasons", "/api/go/comment/report/reasons", body(), asserts=schema_assert("/api/go/comment/report/reasons"))),
    (GC, "G03 comment/list sort=hot → 0 且符合合同", "high", "normal", "首页固定返回 total/ruleVersion/ruleAccepted（测试服 ruleVersion 为空）。", [],
     step("list hot", "/api/go/comment/list", body(seriesId="{{series}}", episodeId="{{go_ep}}", sort="hot", size=5), asserts=schema_assert("/api/go/comment/list"))),
    (GC, "G04 comment/list sort=latest → 0", "medium", "normal", "", [],
     step("list latest", "/api/go/comment/list", body(seriesId="{{series}}", episodeId="{{go_ep}}", sort="latest", size=5), asserts=schema_assert("/api/go/comment/list"))),
    (GC, "G05 comment/publish 一级 → 0，返回 comment 且 duplicated=false", "high", "normal", "专用号发一条待审核评论（仅自己可见），G16 删。", [],
     step("publish", "/api/go/comment/publish", body(seriesId="{{series}}", episodeId="{{go_ep}}", clientRequestId="{{go_req}}", body="at regression {{go_req}}"),
          extract=[("go_cid", "$.data.comment.id")], asserts=schema_assert("/api/go/comment/publish"),
          teardown="d = response.json().get('data') or {}\nassert d.get('duplicated') is False and (d.get('comment') or {}).get('mine') is True, '首发应 duplicated=false、mine=true：%s' % d")),
    (GC, "G06 comment/publish 同 clientRequestId 重发 → 0 duplicated=true 且是原评论", "high", "normal", "幂等：按 (uid, clientRequestId) 返回原记录。", [],
     step("publish again", "/api/go/comment/publish", body(seriesId="{{series}}", episodeId="{{go_ep}}", clientRequestId="{{go_req}}", body="at regression {{go_req}}"),
          teardown="d = response.json().get('data') or {}\nassert d.get('duplicated') is True and str((d.get('comment') or {}).get('id')) == str(self.get_env_value('go_cid')), '重发应 duplicated=true 且返回原评论：%s' % d")),
    (GC, "G07 comment/replies rootId=本评论 → 0 且符合合同", "high", "normal", "", [],
     step("replies", "/api/go/comment/replies", body(rootId="{{go_cid}}", size=5), asserts=schema_assert("/api/go/comment/replies"))),
    (GC, "G08 comment/like add → 0 liked=true", "high", "normal", "", [],
     step("like", "/api/go/comment/like", body(commentId="{{go_cid}}", action="add"), asserts=schema_assert("/api/go/comment/like"),
          teardown="d = response.json().get('data') or {}\nassert d.get('liked') is True and int(d.get('likeCount') or 0) >= 1, '点赞后应 liked=true：%s' % d")),
    (GC, "G09 comment/like remove → 0 liked=false", "high", "normal", "", [],
     step("unlike", "/api/go/comment/like", body(commentId="{{go_cid}}", action="remove"),
          teardown="d = response.json().get('data') or {}\nassert d.get('liked') is False, '取消后应 liked=false：%s' % d")),
    (GC, "G10 comment/dislike 自己的评论 → 15015 COMMENT_DISLIKE_OWN", "medium", "exception", "合同正文：自己能看见的评论返回 15015。", [],
     step("dislike own", "/api/go/comment/dislike", body(commentId="{{go_cid}}", action="add"), asserts=code_assert(15015))),
    (GC, "G11 comment/dislike 不存在的评论 → 15010", "medium", "exception", "", [],
     step("dislike none", "/api/go/comment/dislike", body(commentId=999999999, action="add"), asserts=code_assert(15010))),
    (GC, "G12 comment/publish 二级回复 → 0 level=2", "high", "normal", "rootId 与 replyToCommentId 同时为正数。", [],
     step("reply", "/api/go/comment/publish", body(seriesId="{{series}}", episodeId="{{go_ep}}", clientRequestId="{{go_req}}-r", rootId="{{go_cid}}", replyToCommentId="{{go_cid}}", body="at reply {{go_req}}"),
          teardown="d = response.json().get('data') or {}\nassert (d.get('comment') or {}).get('level') == 2, '二级回复 level 应为 2：%s' % d")),
    (GC, "G13 comment/replies 含本人待审核回复：list 非空", "medium", "normal", "公开回复和本人待审核回复合并分页。", [],
     step("replies after", "/api/go/comment/replies", body(rootId="{{go_cid}}", size=5),
          teardown="d = response.json().get('data') or {}\nassert d.get('list'), '回复列表应含刚发的二级回复：%s' % d")),
    (GC, "G14 comment/report 举报自己 → 10101", "medium", "exception", "只能举报其他人的公开评论。不跑正向（会给中台记举报）。", [],
     step("report own", "/api/go/comment/report", body(commentId="{{go_cid}}", reasonId=1), asserts=code_assert(10101))),
    (GC, "G15 comment/report 不存在的评论 → 15010", "low", "exception", "", [],
     step("report none", "/api/go/comment/report", body(commentId=999999999, reasonId=1), asserts=code_assert(15010))),
    (GC, "G16 comment/delete 本评论（整楼）→ 0", "high", "normal", "清理本轮评论；删一级后整楼不可见。", [],
     step("delete", "/api/go/comment/delete", body(commentId="{{go_cid}}"))),
    (GC, "G17 comment/delete 重复删 → 0（作者重复删除仍成功）", "low", "normal", "合同正文。", [],
     step("delete again", "/api/go/comment/delete", body(commentId="{{go_cid}}"))),
    (GC, "G18 comment/delete 不存在 → 15010", "medium", "exception", "", [],
     step("delete none", "/api/go/comment/delete", body(commentId=999999999), asserts=code_assert(15010))),
    (GC, "G19 comment/block block → 0", "medium", "normal", "blockedUid 必须是合法 uid（假串 10101）；屏蔽另一个专用号（环境变量 other_uid），G21 解除。", [],
     step("block", "/api/go/comment/block", body(blockedUid="{{other_uid}}", action="block"))),
    (GC, "G20 comment/block/list → 0 且符合合同", "medium", "normal", "", [],
     step("block list", "/api/go/comment/block/list", body(), asserts=schema_assert("/api/go/comment/block/list"))),
    (GC, "G21 comment/block unblock → 0", "medium", "normal", "清理。", [],
     step("unblock", "/api/go/comment/block", body(blockedUid="{{other_uid}}", action="unblock"))),
    (GC, "G22 comment/block 屏蔽自己 → 10101", "low", "exception", "", [],
     step("block self", "/api/go/comment/block", body(blockedUid="{{uid}}", action="block"), asserts=code_assert(10101))),
    (GC, "G23 comment/rule/accept 不存在的 ruleVersion → 10101", "low", "exception", "测试服没配社区规则（list 的 ruleVersion 为空），只做反向。", [],
     step("rule accept bad", "/api/go/comment/rule/accept", body(ruleVersion="at-no-such-rule"), asserts=code_assert(10101))),
    (GC, "G24 comment/list 缺 sort → 10101", "low", "exception", "", [],
     step("list no sort", "/api/go/comment/list", body(seriesId="{{series}}", episodeId="{{go_ep}}"), asserts=code_assert(10101))),
    (GC, "G25 comment/replies 不存在的一级 → 15010", "low", "exception", "", [],
     step("replies none", "/api/go/comment/replies", body(rootId=999999999), asserts=code_assert(15010))),
    # ---- 二创（Header 模式）
    (GR, "R01 remix/config → 0 且符合合同", "high", "normal", "可匿名；实际多返回 coinBalance（已问研发C）。", [],
     hstep("config", "/api/go/remix/config", {}, asserts=schema_assert("/api/go/remix/config"))),
    (GR, "R02 remix/eligibility 非二创剧 1000058 → 0 且符合合同", "medium", "normal", "Go 严格校验类型，环境变量 series 渲染成字符串会 10101，所以用固定剧（1000058 长期保留）。", [],
     hstep("eligibility", "/api/go/remix/eligibility", {"seriesId": 1000058}, asserts=schema_assert("/api/go/remix/eligibility"))),
    (GR, "R03 remix/eligibility 二创开放剧 1000277 → canCreate=true", "medium", "normal", "11-20 研发C给定样本；六个QA环境已复核1000277可创建，旧1000339不再开放；保留true断言。", [],
     hstep("eligibility open", "/api/go/remix/eligibility", {"seriesId": 1000277},
           teardown="assert (response.json().get('data') or {}).get('canCreate') is True, '开放剧应 canCreate=true'")),
    (GR, "R04 remix/characters 非二创剧 1000058 → 15107", "medium", "exception", "开放剧 1000339 也返回 15107（疑问 A 已问研发C），先只做反向。", [],
     hstep("characters", "/api/go/remix/characters", {"seriesId": 1000058}, asserts=code_assert(15107))),
    (GR, "R05 remix/asset/list view=all → 0 且符合合同", "high", "normal", "专用号没有产物，list 为空。", [],
     hstep("asset list", "/api/go/remix/asset/list", {"view": "all"}, asserts=schema_assert("/api/go/remix/asset/list"))),
    (GR, "R06 remix/task/status ids=[] → 0 且符合合同", "medium", "normal", "", [],
     hstep("task status", "/api/go/remix/task/status", {"ids": []}, asserts=schema_assert("/api/go/remix/task/status"))),
    (GR, "R07 remix/series/works 二创剧 → 0 且符合合同", "medium", "normal", "可匿名；实际多返回 total（已问研发C）。", [],
     hstep("series works", "/api/go/remix/series/works", {"seriesId": REMIX_SERIES, "size": 5}, asserts=schema_assert("/api/go/remix/series/works"))),
    (GR, "R08 remix/work/detail 不存在 → 15110", "medium", "exception", "", [],
     hstep("work detail none", "/api/go/remix/work/detail", {"id": 999999999}, asserts=code_assert(15110))),
    (GR, "R09 remix/asset/detail 不存在 → 15110", "medium", "exception", "", [],
     hstep("asset detail none", "/api/go/remix/asset/detail", {"id": 999999999}, asserts=code_assert(15110))),
    (GR, "R10 remix/download 不存在 → 15110", "medium", "exception", "正向需要自己的产物，不跑。", [],
     hstep("download none", "/api/go/remix/download", {"id": 999999999}, asserts=code_assert(15110))),
    (GR, "R11 remix/publish 不存在 → 15110", "medium", "exception", "正向不跑。", [],
     hstep("publish none", "/api/go/remix/publish", {"id": 999999999}, asserts=code_assert(15110))),
    (GR, "R12 remix/delete 不存在 → 15111", "medium", "exception", "正向不跑。", [],
     hstep("delete none", "/api/go/remix/delete", {"ids": [999999999]}, asserts=code_assert(15111))),
    (GR, "R13 remix/submit 缺必填 → 10101", "high", "exception", "正向会扣币生成，不跑；只验必填校验（不预占、不扣币）。", [],
     hstep("submit bad", "/api/go/remix/submit", {"seriesId": 1000058}, asserts=code_assert(10101))),
    (GR, "R14 remix/eligibility 缺 seriesId → 10101", "low", "exception", "", [],
     hstep("eligibility bad", "/api/go/remix/eligibility", {}, asserts=code_assert(10101))),
    (GR, "R15 remix/templates media=0 → 10101", "low", "exception", "合同：media 只能 1/2/省略。", [],
     hstep("templates bad media", "/api/go/remix/templates", {"seriesId": REMIX_SERIES, "characterCount": 2, "media": 0}, asserts=code_assert(10101))),
    # ---- Stories 列表（Header 模式）
    (GS, "T01 series/fav/list source=default → 0 且符合合同", "high", "normal", "", [],
     hstep("fav list", "/api/go/series/fav/list", {"source": "default", "size": 5}, asserts=schema_assert("/api/go/series/fav/list"))),
    (GS, "T02 series/play/list source=default → 0 且符合合同", "high", "normal", "", [],
     hstep("play list", "/api/go/series/play/list", {"source": "default", "size": 5}, asserts=schema_assert("/api/go/series/play/list"))),
    (GS, "T03 series/fav/list source=remix → 0", "medium", "normal", "", [],
     hstep("fav list remix", "/api/go/series/fav/list", {"source": "remix", "size": 5})),
]
# 不带 token → 10402：逐接口检查按服务合并成一条（merge_util，11-13 精简，覆盖不减）。
# 评论类（body 模式）全部 12 个；Header 模式只有必须登录的（config / eligibility / series/works 可匿名；characters / templates / work/detail 先校验剧，实测不是 10402）
CASES.append(merged_case(GC, f"comment：不带 token → 10402（12 个接口）", "评论接口鉴权，逐接口检查。", [
    (f"/api/go/comment/{p} 不带 token", step("no token", f"/api/go/comment/{p}", body(drop=("token",), seriesId="{{series}}", episodeId="{{go_ep}}", commentId=1, rootId=1, action="add", sort="hot", blockedUid="x", reasonId=1, ruleVersion="x", clientRequestId="x", body="x")), 10402)
    for p in ("block", "block/list", "delete", "dislike", "entry", "like", "list", "publish", "replies", "report", "report/reasons", "rule/accept")], "gca"))
CASES.append(merged_case(GR, "remix：带 uid 不带 token → 10402（7 个接口）", "公共参数只从 Header 读；携带 uid 缺 token 返回 10402，逐接口检查。", [
    (f"/api/go/remix/{p} 不带 token", hstep("no token", f"/api/go/remix/{p}", {"id": 1, "ids": [1], "view": "all", "seriesId": 1000058}, no_token=True), 10402)
    for p in ("asset/list", "task/status", "asset/detail", "download", "publish", "delete", "submit")], "gra"))
CASES.append(merged_case(GS, "series：带 uid 不带 token → 10402（2 个接口）", "逐接口检查。", [
    (f"/api/go/series/{p} 不带 token", hstep("no token", f"/api/go/series/{p}", {"source": "default", "size": 5}, no_token=True), 10402)
    for p in ("fav/list", "play/list")], "gsa"))

def main():
    print("Go 用例", len(CASES))
    if "--dry-run" in sys.argv:
        for c in CASES:
            print(" ", c[0], "|", c[1])
        return
    flows = {f["name"]: f for f in items(f"/projects/{PID}/business-flows")}
    existing, order = {}, []
    for flow_name in sorted({c[0] for c in CASES}):
        f = flows.get(flow_name) or req("POST", f"/projects/{PID}/business-flows", {"name": flow_name, "description": "OPS-018 Go 侧接口（合同以 Apifox 为准）"})
        flows[flow_name] = f
        existing.update({(flow_name, c["name"]): c for c in items(f"/projects/{PID}/api-test-cases?business_flow_id={f['id']}")})
    for flow_name, name, prio, ctype, desc, pre, request in CASES:
        meta = {"name": name, "business_flow_id": flows[flow_name]["id"], "description": desc, "priority": prio, "case_type": ctype, "tags": ["OPS-018", "Go"]}
        c = existing.get((flow_name, name))
        if c:
            req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}", meta)
        else:
            c = req("POST", f"/projects/{PID}/api-test-cases", meta)
        req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}/case-data",
            {"case_data": {"name": name, "skip": False, "description": desc, "request": request, "preconditions": pre, "retry": 0}})
        order.append(c["id"])
    wanted = {(c[0], c[1]) for c in CASES}
    stale = [c for key, c in existing.items() if key not in wanted]
    for c in stale:
        req("DELETE", f"/projects/{PID}/api-test-cases/{c['id']}")
    if stale:
        print("删过期 Go 用例", [c["name"] for c in stale])
    suites = {s.get("code"): s for s in items(f"/projects/{PID}/api-suites")}
    reg = req("GET", f"/projects/{PID}/api-suites/{suites['regression']['id']}")
    stale_ids = {c["id"] for c in stale}
    cur = [it["case_id"] for it in sorted(reg["items"], key=lambda x: x["sort_order"]) if it["case_id"] not in stale_ids]
    full = [cid for cid in cur if cid not in order] + order   # Go 固定排在最后
    req("PUT", f"/projects/{PID}/api-suites/{reg['id']}/items", {"items": [{"case_id": cid, "sort_order": i, "enabled": True} for i, cid in enumerate(full)]})
    print("套件", reg["id"], "regression 挂", len(full), "条（Go", len(order), "）")


if __name__ == "__main__":
    main()
