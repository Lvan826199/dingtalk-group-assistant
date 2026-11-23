"""把同一类、逐接口的检查（不带 token → 10402、缺参 → 10101 等）合并成「一条用例、多个步骤」，覆盖面不变（用户 2026-11-13 要求精简用例数、不能减覆盖）。

平台行为（11-13 实验）：前置步骤里任何一步断言失败，后面的步骤就不跑了，只报第一个失败。
所以合并时每个前置步骤都不带断言，只把 $.code 提取到变量；最后的主步骤在 teardown 里一次比对全部变量，列出所有不符的接口。
效果：每个接口的请求都照发、返回码都照查；某个接口出问题也不会盖住同组其他接口。
（依赖 uid / token 在环境变量里：run_suite.sh 开跑前 env_tokens.py 已写入。）
"""
import json


def merged_case(flow, name, desc, checks, prefix, priority="medium", case_type="exception", main=None):
    """checks: [(标签, 平台 step dict, 期望 code)]；prefix: 变量名前缀，套件内唯一。
    main: 主步骤（默认用最后一个检查本身当主步骤，不额外多发请求）。返回平台用例元组 (flow, name, priority, case_type, desc, pre, request)。"""
    pre, exp = [], {}
    for i, (label, s, code) in enumerate(checks):
        v = f"{prefix}_{i}"
        s = dict(s)
        s["name"] = label[:120]
        s["assertions"] = [{"type": "status_code", "expected": 200, "mode": "soft"}]   # 只记返回码，不在步骤里断言 code
        s["extract"] = [{"name": v, "type": "json_path", "path": "$.code", "optional": True}]
        pre.append(s)
        exp[v] = [label, code]
    if main is None:
        main = pre.pop()          # 最后一个检查当主步骤：它的返回码也提取到变量，teardown 里一起比
    td = ("exp = %s\n" % json.dumps(exp, ensure_ascii=False) +
          "bad = [ '%s 期望 %s 实际 %s' % (exp[k][0], exp[k][1], self.get_env_value(k)) for k in exp if str(self.get_env_value(k)) != str(exp[k][1]) ]\n"
          "assert not bad, '%d / " + str(len(exp)) + " 项返回码不符：' % len(bad) + '；'.join(bad)")
    main = dict(main)
    main["teardown_script"] = (main.get("teardown_script") or "") + ("\n" if main.get("teardown_script") else "") + td
    full_desc = f"{desc}（合并 {len(exp)} 项，逐项都发请求、逐项比对，失败时列出全部不符项）\n" + "\n".join(f"- {lab} → {c}" for lab, c in exp.values())
    return (flow, name, priority, case_type, full_desc, pre, main)
