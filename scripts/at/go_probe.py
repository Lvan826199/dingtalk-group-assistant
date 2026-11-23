"""Go 侧接口（go-server，研发C 11-12 14:48：合同以 Apifox 为准）P0 合同核实：调测试服 tac 同一网关的 /api/go/*，
对照 Apifox 导出（runs/apifox/export-*.json）的 schema 列差异；每个接口再探一次「不带 token」。

只用专用账号；写操作只在自己的数据上并当场清理：发一条评论 → 点赞/不喜欢/回复列表 → 删除；屏蔽另一个专用号 → 解除。
不跑：remix/submit 正向（扣币生成）、remix/publish|delete|download 正向（没有自己的产物）、comment/report 正向（会给中台记举报）。
用法：python3 -I go_probe.py [android|ios] [--tag xx]   输出 runs/p0/go-<pf>-<tag>.json 和 runs/p0/go-修正清单-<tag>.md
"""
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from client import Client  # noqa: E402
from schema_diff import collapse, diff  # noqa: E402

RUNS = os.path.join(HERE, "../../runs")
ACCOUNTS = {"android": dict(sid="at-sid-01", pf="a", app_version="1.1.0", app_build=1010001),
            "ios": dict(sid="at-sid-02", pf="i", app_version="1.0.9", app_build=1000901)}
OTHER = {"android": "at-sid-02", "ios": "at-sid-01"}
GO_PATHS_PREFIX = ("/api/go/",)
REMIX_SERIES = 1000339   # 测试服 eligibility canCreate=true 的剧（11-12 扫 1000001–1000400 得 11 部，Apifox 示例也用它）


def load_spec():
    f = sorted(glob.glob(os.path.join(RUNS, "apifox/export-*.json")))[-1]
    d = json.load(open(f, encoding="utf-8"))
    return f, d


class Spec:
    def __init__(self, d):
        self.paths = d["paths"]
        self.comps = d.get("components", {}).get("schemas", {})

    def resolve(self, s, depth=0):
        """展开 $ref / allOf；oneOf 留给 pick()。"""
        if not isinstance(s, dict) or depth > 30:
            return s
        if "$ref" in s:
            return self.resolve(self.comps.get(s["$ref"].split("/")[-1], {}), depth + 1)
        if "allOf" in s:
            m = {"type": "object", "properties": {}, "required": []}
            for x in s["allOf"]:
                x = self.resolve(x, depth + 1)
                m["properties"].update(x.get("properties", {}))
                m["required"] += x.get("required", [])
            return m
        out = dict(s)
        if "properties" in s:
            out["properties"] = {k: self.resolve(v, depth + 1) for k, v in s["properties"].items()}
        if isinstance(s.get("items"), dict):
            out["items"] = self.resolve(s["items"], depth + 1)
        if "oneOf" in s:
            out["oneOf"] = [self.resolve(x, depth + 1) for x in s["oneOf"]]
        return out

    def success_schema(self, path):
        op = self.paths[path]["post"]
        resp = op.get("responses", {}).get("200", {}).get("content", {})
        rs = self.resolve(next(iter(resp.values()), {}).get("schema", {}) if resp else {})
        # 成功信封：oneOf 里 code 含 0 的那一个；没有 oneOf 就是自己
        cands = rs.get("oneOf") or [rs]
        for c in cands:
            code = (c.get("properties") or {}).get("code", {})
            if 0 in (code.get("enum") or [0]):
                return c
        return cands[0]


def pick(schema, value):
    """schema 有 oneOf 时挑差异最少的分支。"""
    if isinstance(schema, dict) and "oneOf" in schema:
        best = None
        for c in schema["oneOf"]:
            d = diff(c, value)
            if best is None or len(d) < len(best[1]):
                best = (c, d)
        return best[0]
    return schema


def deep_pick(schema, value):
    """递归把 oneOf 按实际值定下来，再交给 diff。"""
    schema = pick(schema, value)
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if isinstance(value, dict) and "properties" in schema:
        out["properties"] = {k: (deep_pick(v, value[k]) if k in value else v) for k, v in schema["properties"].items()}
    if isinstance(value, list) and isinstance(schema.get("items"), dict) and value:
        out["items"] = deep_pick(schema["items"], value[0])
    return out


def main():
    pf = next((a for a in sys.argv[1:] if a in ACCOUNTS), "android")
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else time.strftime("%m%d-%H%M")
    spec_file, raw = load_spec()
    spec = Spec(raw)
    c = Client(**ACCOUNTS[pf])
    assert c.login().get("code") == 0, "登录失败"
    other = Client(sid=OTHER[pf]); other.login()
    series = int(open(os.path.join(RUNS, "series.txt")).read().strip()) if os.path.exists(os.path.join(RUNS, "series.txt")) else 1000066
    det, eds = series_eps(c, series)
    ep = (eds[0] or {}).get("episodeId") if eds else None
    print(f"[{pf}] uid {c.uid} series {series} ep {ep} eps {len(eds)}")
    ts = int(time.time() * 1000)
    rows = []   # {path, case, code, message, diffs, data_keys}

    def hcall(path, body, auth=True, drop=()):
        """公共参数放 Header 的调法（remix/*、series/*）。drop 里的公共参数不发该头。"""
        import urllib.request, urllib.error
        from client import BASE, CTX
        h = {"Content-Type": "application/json"}
        h.update({k: str(v) for k, v in c.common.items()})
        if auth:
            h.update({"uid": c.uid, "token": c.token})
        for k in drop:
            h.pop(k, None)
        req = urllib.request.Request(BASE + path, data=json.dumps(body or {}).encode(), method="POST", headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20, context=CTX) as resp:
                text = resp.read().decode()
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
        try:
            return json.loads(text)
        except ValueError:
            return {"_raw": text[:300]}

    def probe(path, body, case="正向", expect=0, auth=True, drop=(), diff_data=True):
        header_mode = path.startswith(("/api/go/remix/", "/api/go/series/"))
        res = hcall(path, body, auth=auth, drop=drop) if header_mode else c.call(path, body, auth=auth, drop=drop)
        code = res.get("code")
        diffs = []
        if diff_data and code == 0:
            sch = deep_pick(spec.success_schema(path), res)
            diffs = collapse(diff(sch, res))
            diffs = [d for d in diffs if not d[0].startswith("$.user")]   # 固定 null 的 user 信封字段不计
        rows.append({"path": path, "case": case, "expect": expect, "common_in": "header" if header_mode else "body", "code": code, "message": res.get("message"), "ok": code == expect,
                     "diffs": diffs, "data": res.get("data") if isinstance(res.get("data"), (dict, list)) and len(json.dumps(res.get("data"))) < 4000 else None})
        flag = "✓" if code == expect else "✗"
        print(f"  {flag} {path} [{case}] → {code} {res.get('message')} 差异 {len(diffs)}")
        return res

    # ---- 评论（APP-047）
    entry = probe("/api/go/comment/entry", {"seriesId": series, "episodeId": ep})
    reasons = probe("/api/go/comment/report/reasons", {})
    lst = probe("/api/go/comment/list", {"seriesId": series, "episodeId": ep, "sort": "hot", "size": 5})
    probe("/api/go/comment/list", {"seriesId": series, "episodeId": ep, "sort": "latest", "size": 5}, case="latest")
    rule_version = (lst.get("data") or {}).get("ruleVersion")
    if rule_version:
        probe("/api/go/comment/rule/accept", {"ruleVersion": rule_version})
    else:
        print("  - comment/list ruleVersion 为空（测试服没配社区规则），rule/accept 只做反向")
    probe("/api/go/comment/rule/accept", {"ruleVersion": "at-no-such-rule"}, case="不存在的 ruleVersion → 记实际（合同未写）", expect=10101)
    cid_req = f"at-go-{ts}"
    pub = probe("/api/go/comment/publish", {"seriesId": series, "episodeId": ep, "clientRequestId": cid_req, "body": f"at regression {ts}"})
    my = ((pub.get("data") or {}).get("comment") or {}).get("id") or (pub.get("data") or {}).get("id")
    probe("/api/go/comment/publish", {"seriesId": series, "episodeId": ep, "clientRequestId": cid_req, "body": f"at regression {ts}"}, case="同 clientRequestId 重发 duplicated")
    if my:
        probe("/api/go/comment/replies", {"rootId": my, "size": 5})
        probe("/api/go/comment/like", {"commentId": my, "action": "add"}, case="add")
        probe("/api/go/comment/like", {"commentId": my, "action": "remove"}, case="remove")
        probe("/api/go/comment/dislike", {"commentId": my, "action": "add"}, case="不喜欢自己的 → 15015（合同：自己能看见的评论返回 15015）", expect=15015)
        probe("/api/go/comment/dislike", {"commentId": 999999999, "action": "add"}, case="不存在 → 15010", expect=15010)
        probe("/api/go/comment/report", {"commentId": my, "reasonId": 1}, case="举报自己 → 10101（不做正向）", expect=10101)
        probe("/api/go/comment/publish", {"seriesId": series, "episodeId": ep, "clientRequestId": f"{cid_req}-r", "rootId": my, "replyToCommentId": my, "body": f"at reply {ts}"}, case="二级回复")
        probe("/api/go/comment/delete", {"commentId": my}, case="删自己的一级（整楼）")
        probe("/api/go/comment/delete", {"commentId": my}, case="作者重复删除仍成功 → 0")
        probe("/api/go/comment/delete", {"commentId": 999999999}, case="不存在 → 15010", expect=15010)
    else:
        print("  - publish 没拿到评论 id，互动用例跳过")
    probe("/api/go/comment/block", {"blockedUid": other.uid, "action": "block"}, case="block")
    probe("/api/go/comment/block/list", {})
    probe("/api/go/comment/block", {"blockedUid": other.uid, "action": "unblock"}, case="unblock")
    probe("/api/go/comment/block", {"blockedUid": c.uid, "action": "block"}, case="屏蔽自己 → 10101", expect=10101)
    probe("/api/go/comment/report", {"commentId": 999999999, "reasonId": 1}, case="不存在的评论 → 15010", expect=15010)
    probe("/api/go/comment/replies", {"rootId": 999999999}, case="不存在的一级 → 15010", expect=15010)
    probe("/api/go/comment/list", {"seriesId": series, "episodeId": ep}, case="缺 sort → 10101", expect=10101)
    # ---- 二创（remix）：只读 + 反向
    probe("/api/go/remix/config", {})
    elig = probe("/api/go/remix/eligibility", {"seriesId": series})
    probe("/api/go/remix/characters", {"seriesId": series}, case="回归剧不在二创名单 → 15107", expect=15107)
    probe("/api/go/remix/eligibility", {"seriesId": REMIX_SERIES}, case="二创开放剧 canCreate=true")
    probe("/api/go/remix/characters", {"seriesId": REMIX_SERIES}, case="二创开放剧正向（11-12 实际 15107，疑问已问研发C）")
    probe("/api/go/remix/templates", {"seriesId": REMIX_SERIES, "characterCount": 2}, case="二创开放剧正向（11-12 实际 15107）")
    probe("/api/go/remix/templates", {"seriesId": REMIX_SERIES, "characterCount": 2, "media": 1}, case="media=1（11-12 实际 15107）")
    probe("/api/go/remix/templates", {"seriesId": REMIX_SERIES, "characterCount": 1}, case="characterCount=1 → 10101 templates parameters INVALID（疑问）", expect=10101)
    probe("/api/go/remix/templates", {"seriesId": REMIX_SERIES, "characterCount": 2, "media": 0}, case="media=0 → 10101", expect=10101)
    probe("/api/go/remix/series/works", {"seriesId": REMIX_SERIES, "size": 5}, case="二创开放剧")
    probe("/api/go/remix/asset/list", {"view": "all"})
    works = probe("/api/go/remix/series/works", {"seriesId": series, "size": 5})
    probe("/api/go/remix/task/status", {"ids": []})
    wid = (((works.get("data") or {}).get("list") or [{}])[0] or {}).get("id")
    if wid:
        probe("/api/go/remix/work/detail", {"id": wid})
    probe("/api/go/remix/work/detail", {"id": 999999999}, case="不存在 → 15110", expect=15110)
    probe("/api/go/remix/asset/detail", {"id": 999999999}, case="不存在 → 15110", expect=15110)
    probe("/api/go/remix/download", {"id": 999999999}, case="不存在 → 15110", expect=15110)
    probe("/api/go/remix/publish", {"id": 999999999}, case="不存在 → 15110", expect=15110)
    probe("/api/go/remix/delete", {"ids": [999999999]}, case="不存在 → 15111/0 记实际", expect=15111)
    probe("/api/go/remix/submit", {"seriesId": series}, case="缺必填 → 10101（不跑正向：扣币生成）", expect=10101)
    probe("/api/go/remix/eligibility", {}, case="缺 seriesId → 10101", expect=10101)
    # ---- Stories 列表
    probe("/api/go/series/fav/list", {"source": "default", "size": 5})
    probe("/api/go/series/play/list", {"source": "default", "size": 5})
    probe("/api/go/series/fav/list", {"source": "remix", "size": 5}, case="source=remix")
    # ---- 每个 Go 接口不带 token → 10402
    for p in sorted(x for x in spec.paths if x.startswith(GO_PATHS_PREFIX)):
        probe(p, {"seriesId": series, "episodeId": ep, "id": 1, "ids": [], "commentId": 1, "rootId": 1, "action": "add", "sort": "hot", "blockedUid": "x", "reasonId": 1, "ruleVersion": "x", "characterCount": 1, "clientRequestId": "x", "body": "x", "view": "all", "source": "default"},
              case="带 uid 不带 token → 10402", expect=10402, drop=("token",), diff_data=False)

    out = {"pf": pf, "uid": c.uid, "series": series, "episode": ep, "spec": os.path.basename(spec_file), "time": time.strftime("%Y-%m-%d %H:%M"), "rows": rows}
    os.makedirs(os.path.join(RUNS, "p0"), exist_ok=True)
    jf = os.path.join(RUNS, "p0", f"go-{pf}-{tag}.json")
    json.dump(out, open(jf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = [r for r in rows if not r["ok"]]
    dif = [r for r in rows if r["diffs"]]
    print(f"[{pf}] 调用 {len(rows)}，码不符 {len(bad)}，有字段差异 {len(dif)} → {jf}")
    for r in bad:
        print(f"   码不符 {r['path']} [{r['case']}] 期望 {r['expect']} 实际 {r['code']} {r['message']}")
    for r in dif:
        print(f"   差异 {r['path']} [{r['case']}]")
        for p, k, d in r["diffs"][:12]:
            print(f"      {k:7} {p}  {d}")


def series_eps(c, sid):
    d = (c.call("/api/series/detail", {"seriesId": int(sid)}).get("data") or {}).get("seriesData") or {}
    eds = [e for s in (d.get("seds") or []) for e in (s.get("eds") or [])]
    return d, eds


if __name__ == "__main__":
    main()
