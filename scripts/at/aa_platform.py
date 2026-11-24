"""防刷用例改用平台自带能力（11-23 平台 d41cfbf0 上线后，本人同意）：
  setup  给套件 72 的 A01～A11 打上「这条不重试」+ 执行条件 antiAbuseSwitch == 1（只需做一次，可重复执行）
  sync   把测试服当前防刷开关写进各环境的环境变量 antiAbuseSwitch，run_suite 每轮开跑前调用
开关关着时这 11 条在平台上记「跳过」，不发请求、不重试、不算失败；不再需要临时停用用例（aa_items.py 作废）。"""
import os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import series_check as sc

ENVS = os.environ.get("ENVS", "163 164 165 166 168 169").split()
COND = [{"var": "antiAbuseSwitch", "op": "eq", "value": "1"}]


def setup():
    items = sc.req("GET", "/api-suites/72")["data"]["items"]
    n = 0
    for i in items:
        if not re.match(r"A(0\d|1[01]) ", str(i.get("case_name") or "")):
            continue
        cd = sc.req("GET", f"/api-test-cases/{i['case_id']}/case-data")["data"]
        data = cd.get("case_data") or cd
        data["no_retry"] = True
        data["run_if"] = COND
        sc.req("PUT", f"/api-test-cases/{i['case_id']}/case-data", {"case_data": data})
        n += 1
    print("防刷用例已设「不重试」+ 执行条件 antiAbuseSwitch == 1：", n, "条")


def sync():
    out = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "anti_abuse_switch.py"), "status"],
                         capture_output=True, text=True).stdout
    val = "1" if re.search(r"=\s*1\b", out) else "0"
    for env in ENVS:
        for v in sc.env_vars(env):
            if v["name"] == "antiAbuseSwitch":
                if str(v.get("value")) == val:
                    break
                sc.req("DELETE", f"/environments/{env}/variables/{v['id']}")
        else:
            sc.req("POST", f"/environments/{env}/variables", {"name": "antiAbuseSwitch", "value": val, "type": "text",
                                                              "description": "测试服防刷开关当前值，run_suite 开跑前同步；防刷用例按它决定跑或跳过"})
    print("各环境 antiAbuseSwitch 已同步为", val)


if __name__ == "__main__":
    {"setup": setup, "sync": sync}[sys.argv[1]]()
