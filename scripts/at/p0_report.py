"""把 P0 探测结果（Android + iOS）整理成：文档修正清单（交 合同维护人）、接口台账 csv。

用法：python3 -I p0_report.py <android.json> <ios.json>
输出：qa-notes/runs/p0/文档修正清单-<commit>.md、qa-notes/接口台账.csv
"""
import csv
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
P0 = os.path.join(HERE, "../../runs/p0")

# 读代码确认的「合同缺请求字段 / 位置不对」（探测输入问题已排除）
CODE_NOTES = {
    "/api/device/ios/ua": "合同请求体为空；代码要 uaInfo、params（DeviceApiService.java:40、106），缺了返回 10101 PARAMETER_MISSING_OR_INVALID",
    "/api/device/ios/ua/list": "合同请求体为空；代码要 params / userAgent（DeviceApiService.java:40），缺了返回 10101",
    "/api/device/series/base": "合同请求体为空；代码读 seriesId（必填，<=0 返回 10101 videoId error，DeviceApiService.java:150）、uid、code、security、lang",
    "/api/open/task/test": "合同缺 id（必填，缺了 10101 id error，OpenApiService.java:128）及维度 pf/country/lt/pay/ab；GET 也支持",
    "/api/open/data": "token、cate、pn、ps 只从查询串读（@RequestParam），不读 JSON body；合同写在 body 里",
    "/api/open/wsp/series": "同 /api/open/data：token、cate、pn、ps 只从查询串读",
    "/api/drama/guide/data": "@VerifyToken 已注释（DramaApiController.java:21），不需要登录；合同按登录接口写",
    "/api/v1/member/frozen": "请求必填写成了 code / message / data / user（是响应字段，抄错了）",
}
# 探测本身没覆盖到、要补数据后重测的
PROBE_TODO = {
    "/api/act/reward": "测试服当前没有可领的活动（10404），需要配活动数据后重测",
    "/api/v2/thirdPay/stripe/orderResult": "paymentOrderIds 格式未确认（探测传字符串数组得 10101 request parameter invalid），读代码确认后重测",
}
# 探测顺序造成的假象，不算问题
IGNORE = {("/api/task/ckin/reward", "ts")}  # 正向那次已领奖，去掉 ts 再领自然是 14001


def load(p):
    return {r["path"]: r for r in json.load(open(p))["results"]}, json.load(open(p))


def main():
    a, ameta = load(sys.argv[1])
    i, imeta = load(sys.argv[2])
    commit = ameta["version_start"] + (f"-合同{ameta['contract']}" if ameta.get("contract") else "") + (sys.argv[3] if len(sys.argv) > 3 else "")
    routes = json.load(open(os.path.join(P0, "java_routes.json")))
    lines = [f"# 文档修正清单（P0，测试服 {commit}，{time.strftime('%Y-%m-%d')}）", "",
             "来源：OPS-018 P0 接口核实。对照 backend-server `api/openapi/app-v1.yaml`（origin/dev）逐个接口真实调用：",
             "正向一次、逐个去掉必填 / 可选业务参数、返回结构逐字段比对；Android（at-sid-01）、iOS（at-sid-02）各跑一遍，差异合并。",
             "口径（合同维护人 11-09）：代码对、合同错 → 这里，由 合同维护人 改合同；代码错 → Jira；判断不了 → 问接口负责人。", "",
             "## 全局", "",
             "- 公共参数（uid / token / sid / pf / appVersion / appBuild / lang）合同都写在 `in: query`。实际 Java 业务接口从 JSON body 读（`parseBody`），查询串只是兜底；`/api/open/*` 相反，只读查询串。建议合同统一写进 requestBody，并单独标出 open 接口。",
             "- 「合同 required、实际没返回」不一定是少返回：服务端用 fastjson 序列化，值为 null 的字段默认不输出。合同里这类字段要么去掉 required，要么标 nullable。",
             "- 18 个接口 P0 没有调用（注销、第三方登录、真实支付 / 推送、内部扣币、投币、渠道屏蔽、废弃写接口），留到 P1 用一次性账号或沙盒核实，本清单不含。", ""]
    rows = []
    n_items = 0
    for path in sorted(set(a) | set(i)):
        ra, ri = a.get(path) or {}, i.get(path) or {}
        items = []
        if path in CODE_NOTES and not ameta.get("contract"):  # 读代码得出的备注只对 25ebb12 时的旧合同有效；新合同（3ffe15be 起）已逐条核过改掉
            items.append(("请求", CODE_NOTES[path]))
        for k in ra.get("required") or []:
            ca = ((ra.get("drop_required") or {}).get(k) or {}).get("code")
            ci = ((ri.get("drop_required") or {}).get(k) or {}).get("code")
            if ca == 0 and ci in (0, None) and (ra.get("positive") or {}).get("code") == 0:
                items.append(("请求", f"`{k}` 合同标必填，去掉后仍成功（code 0），实际是可选（服务端给默认值）"))
        for k in ra.get("optional") or []:
            if (path, k) in IGNORE:
                continue
            ca = ((ra.get("drop_optional") or {}).get(k) or {}).get("code")
            if (ra.get("positive") or {}).get("code") == 0 and ca not in (0, None):
                items.append(("请求", f"`{k}` 合同标可选，去掉后失败（{ca}），实际是必填"))
        seen = set()
        for side, r in (("A", ra), ("i", ri)):
            if (r.get("positive") or {}).get("code") != 0:
                continue  # 正向没成功的，返回结构不比（比的是错误返回）
            for p, kind, d in r.get("schema_diff") or []:
                key = (p, kind)
                if key in seen:
                    continue
                seen.add(key)
                both = any(q[0] == p and q[1] == kind for q in ((ri if side == "A" else ra).get("schema_diff") or []))
                tag = "" if both else ("（仅 Android）" if side == "A" else "（仅 iOS）")
                word = {"missing": "合同 required、实际没返回", "extra": f"实际返回、合同没写（{d[-7:].split('，')[-1].replace('实际 ', '')}）",
                        "null": f"实际为 null，合同不允许（{d.split('，')[0].replace('合同 ', '')}）",
                        "type": f"类型不符（{d}）"}[kind]
                items.append(("返回", f"`{p}` {word}{tag}"))
        if items:
            n_items += len(items)
            draft = "草稿" if ra.get("draft") else "已转正"
            lines += [f"### {path}（{ra.get('summary') or ''}，{draft}）", ""]
            lines += [f"- [{t}] {x}" for t, x in items]
            if path in PROBE_TODO:
                lines.append(f"- [待重测] {PROBE_TODO[path]}")
            lines.append("")
        rt = routes.get(path) or {}
        rows.append({
            "路径": path, "服务": "Java", "模块": ra.get("tag", ""), "合同状态": "草稿" if ra.get("draft") else "正式",
            "需登录": {True: "是", False: "否"}.get(rt.get("login"), "?"), "代码位置": f"{rt.get('file', '')}:{rt.get('line', '')}",
            "P0": ra.get("skipped") and f"未调用：{ra['skipped']}" or f"A={ra.get('positive', {}).get('code')} i={ri.get('positive', {}).get('code')}",
            "请求参数核实": "未核" if ra.get("skipped") else ("有差异" if any(t == "请求" for t, _ in items) else "一致"),
            "返回字段核实": "未核" if ra.get("skipped") else ("有差异" if any(t == "返回" for t, _ in items) else "一致"),
            "错误码核实": "未核", "待重测": PROBE_TODO.get(path, ""), "差异条数": len(items),
        })
    lines.insert(4, f"共 {sum(1 for r in rows if r['差异条数'])} 个接口、{n_items} 条差异。")
    out = os.path.join(P0, f"文档修正清单-{commit}.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    # 台账：合同里的接口 + 代码里有、合同没有的（白名单）
    allow = set()
    for path in routes:
        if path not in a:
            rows.append({"路径": path, "服务": "Java", "模块": "", "合同状态": "不在合同（白名单 / 待下线）",
                         "需登录": "是" if routes[path]["login"] else "否",
                         "代码位置": f"{routes[path]['file']}:{routes[path]['line']}", "P0": "不测", "请求参数核实": "",
                         "返回字段核实": "", "错误码核实": "", "待重测": "", "差异条数": ""})
            allow.add(path)
    led = os.path.join(HERE, "../../接口台账.csv")
    with open(led, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(out, "\n", os.path.normpath(led), f"\n合同接口 {len(a)}，有差异 {sum(1 for r in rows if r['差异条数'])}，差异 {n_items} 条；台账另含不在合同的 {len(allow)} 条")


if __name__ == "__main__":
    main()
