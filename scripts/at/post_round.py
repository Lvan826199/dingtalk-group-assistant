"""把一轮回归（run_suite.sh 的输出）整理成结果摘要发到「短剧测试群」。

用法：python3 -I post_round.py <run_suite 输出文件> [--dry-run] [--at 姓名=openDingtalkId ...]
消息格式：【OPS-018｜接口自动化回归｜测试服 <commit>】 + 各环境通过数 + 合同 rev。

群里只发送结果，不发送失败原因或失败用例细节；详细原因保留在 runs/scheduled 日志，
由值守会话在调试对话中汇报。
"""
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "../../../backend-server")
TEST_GROUP = os.environ.get("QA_TEST_GROUP", "")
ENV_NAME = {"163": "Android", "164": "iOS", "165": "Android 1010100（048 新分支）", "166": "iOS 1010101（048 新分支）", "168": "Android 1.1.1 / 1010102", "169": "Android 1.1.1 / 1010103"}
# @ 规则（用户 11-11 定：结果要 @ 到人）：每轮都 @QA负责人（QA 准出）和 合同维护人（盯 dev 测试进度）；有新失败再 @ 本轮构建里提交的研发。
# 姓名 → 钉钉 openDingtalkId：本机 ~/.config/qa-workflow/people.json（不进仓库）
PEOPLE = json.load(open(os.path.expanduser("~/.config/qa-workflow/people.json"), encoding="utf-8")) if os.path.exists(os.path.expanduser("~/.config/qa-workflow/people.json")) else {}
DEFAULT_AT = ["QA负责人", "合同维护人"]
GIT_AUTHOR = {"guowei": "研发B", "fcl": "研发A", "jyzhao": "研发C"}   # git 作者名 → 人
LAST = os.path.join(HERE, "../../runs/last_round.json")              # 上一轮的测试服 commit，用来算本轮新提交的作者
# 已知缺陷：失败用例名前缀 → Jira 单号。关单后从这里删掉；再出现就按规则重开旧单。
KNOWN = {}  # act/all/detail 合同已随 1c06e865 补回； act/all/detail 无活动 data {} 已随合同 e5ffdd34 改可选； 779 坏包 10101 已于 9049e10 验证通过；766 已关。再出现按规则重开旧单，不新建


def deployed():
    ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem")  # python.org 版 Python 不带根证书
    with urllib.request.urlopen("https://api-test.example.com/actuator/info", timeout=10, context=ctx) as r:
        return json.load(r)["git"]["commit"]["id"]


def parse(path):
    rounds, cur = [], None
    for line in open(path, encoding="utf-8"):
        m = re.match(r"suite (\d+) env (\d+) exec (\d+) (\w+) (\d+) / (\d+)", line.strip())
        if m:
            cur = {"suite": m[1], "env": m[2], "exec": m[3], "status": m[4], "passed": int(m[5]), "total": int(m[6]), "fails": []}
            rounds.append(cur)
        elif cur is not None and line.startswith("    ") and line.strip():
            cur["fails"].append(line.strip())
    return rounds


def compose(rounds, commit, rev):
    head = f"【OPS-018｜接口自动化回归｜测试服 {commit}】"
    lines = [head, ""]
    for r in rounds:
        lines.append(f"{ENV_NAME.get(r['env'], r['env'])}：{r['passed']}/{r['total']} 通过（平台执行 {r['exec']}）")
        lines.append("")
    has_failures = any(r["status"] == "failed" for r in rounds)
    lines.append("本轮全部通过。" if not has_failures else "本轮有失败项。")
    lines.append("")
    total = rounds[0]["total"] if rounds else "?"
    lines.append(f"套件 72 全量回归 {total} 条（22 个转正接口场景链 + 单接口核实）；合同 app-v1.yaml 版本 {rev}")  # 不用 @，钉钉会当成 @人
    has_new = any(
        f and not any(f.split(": ", 1)[0].startswith(k) for k in KNOWN)
        for r in rounds for f in r["fails"]
    )
    return "\n".join(lines), has_new


def validate_round(rounds, expected_envs):
    if not rounds:
        return "没有完整执行结果"
    actual = [r["env"] for r in rounds]
    if len(actual) != len(set(actual)) or set(actual) != set(expected_envs):
        return "环境结果缺失、重复或范围不符"
    if any(r["status"] != "passed" or r["total"] <= 0 or r["passed"] != r["total"] for r in rounds):
        return "存在失败、未完成或无效统计"
    if len({r["total"] for r in rounds}) != 1:
        return "各环境覆盖数量不一致"
    return None


def main():
    path = sys.argv[1]
    dry = "--dry-run" in sys.argv
    ats = [a.split("=", 1) for a in sys.argv[sys.argv.index("--at") + 1:] if "=" in a] if "--at" in sys.argv else []
    rounds = parse(path)
    error = validate_round(rounds, os.environ.get("ENVS", "163 164 165 166 168 169").split())
    if re.search(r"^suite .* blocked ", open(path, encoding="utf-8").read(), re.M):
        error = "存在前置阻塞，尚未完成回归"
    if error:
        raise SystemExit("不发送最终通过结果：" + error)
    if "--check" in sys.argv:
        print("结果检查通过：全部预期环境均通过")
        return
    commit = deployed()
    # 合同 rev 取最后一次改 api/openapi 的提交，不是 dev 顶端
    rev = subprocess.check_output(["git", "-C", SERVER, "log", "-1", "--format=%h", "origin/dev", "--", "api/openapi/"]).decode().strip()
    text, has_new = compose(rounds, commit, rev)
    names = list(DEFAULT_AT)
    if has_new:   # 新失败：加上本轮构建里提交的研发
        prev = json.load(open(LAST)).get("commit") if os.path.exists(LAST) else None
        rng = f"{prev}..{commit}" if prev else f"{commit}~10..{commit}"
        try:
            authors = subprocess.check_output(["git", "-C", SERVER, "log", "--format=%an", rng]).decode().split()
        except subprocess.CalledProcessError:
            authors = []
        names += [GIT_AUTHOR[a] for a in dict.fromkeys(authors) if a in GIT_AUTHOR and GIT_AUTHOR[a] not in names]
    ats = [(n, PEOPLE[n]) for n in names if n in PEOPLE] + ats
    text = text.replace("】", "】" + "".join(f"@{n} " for n, _ in ats), 1)
    text = re.sub(r"\n+", "\n\n", text.strip())   # 钉钉 markdown 单个换行不换行（用户 11-18 指出），统一空行
    print(text)
    if dry:
        return
    cmd = ["dws", "chat", "message", "send", "--conversation-id", TEST_GROUP, "--title", f"OPS-018｜接口自动化回归｜测试服 {commit}",
           "--content", text, "--uuid", f"ops018-round-{commit}-{int(time.time())}", "--yes", "--format", "json"]
    if ats:
        cmd += ["--at-open-dingtalk-ids", ",".join(i for _, i in ats)]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    try:
        res = json.loads(out)
        ok = res.get("success") is True or res.get("ok") is True
        print("发送:", ok, (res.get("result") or {}).get("openTaskId"))
    except ValueError:
        ok = False; print(out[:400])
    if not ok:   # 发不进测试群（dws 故障等）：用调试群机器人把整条结果发给用户（11-18 用户定）
        err = re.search(r'"message": "([^"]*)', out)
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "send_failed.py"), "短剧测试群（回归结果）", text, err.group(1) if err else out[:200]])
    print("有新失败" if has_new else "无新失败")
    json.dump({"commit": commit, "time": time.strftime("%Y-%m-%d %H:%M"), "new_fail": has_new}, open(LAST, "w"))
    # 定时回归（scheduled_round.sh）用它判断 15:00 / 18:30 有没有新提交：手动轮发群后也算「跑过」
    os.makedirs(os.path.join(HERE, "../../runs/scheduled"), exist_ok=True)
    json.dump({"build": commit, "rev": rev, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "slot": "post_round"}, open(os.path.join(HERE, "../../runs/scheduled/state.json"), "w"))


if __name__ == "__main__":
    main()
