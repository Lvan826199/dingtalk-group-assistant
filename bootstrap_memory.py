"""首次建记忆：协作库预填同事 / 需求负责人 + 选中群最近 N 天历史 + 工作目录下的全部 Codex 会话记录，交给 codex exec（只读）提炼成 memory\\*.draft.md，等本人确认。
用法：python bootstrap_memory.py [天数，默认 30]"""
import datetime as dt, glob, json, os, re, shutil, subprocess, sys

HOME = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(os.path.expanduser("~"), ".qa-agent", "config.json"), encoding="utf-8"))
# ---- 开机自启（LaunchAgent / systemd / 计划任务）带的 PATH 很短，找不到装在用户目录下的 AI 命令和钉钉 CLI
# （macOS 上 claude / codex 默认在 ~/.local/bin，launchd 的 PATH 里没有，11-18 实测）。把常见安装目录补到 PATH 末尾，已有的不重复加。
def _extend_path():
    h = os.path.expanduser("~")
    if os.name == "nt":
        extra = [os.path.join(os.environ.get("APPDATA", ""), "npm"), os.path.join(h, ".local", "bin"), os.path.join(h, "AppData", "Local", "Programs", "Python", "Launcher")]
    else:
        extra = [os.path.join(h, ".local", "bin"), os.path.join(h, ".npm-global", "bin"), "/opt/homebrew/bin", "/usr/local/bin",
                 os.path.join(h, ".bun", "bin"), os.path.join(h, ".cargo", "bin"), os.path.join(h, "bin"), "/snap/bin"]
        extra += sorted(glob.glob(os.path.join(h, ".nvm", "versions", "node", "*", "bin")), reverse=True)[:1]   # nvm 装的 node / npm 全局命令
    cur = os.environ.get("PATH", "").split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join(cur + [d for d in extra if d and os.path.isdir(d) and d not in cur])


_extend_path()


DWS = shutil.which("dws") or shutil.which("dws.cmd")
# 判断用的 AI：与 agent.py 的 AI_PRESETS 一致（v2.7 不限 Codex）；config 的 ai / ai_cmd / ai_prompt / ai_model 同样生效
AI_PRESETS = {"codex": (["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", "{out}"], "arg"),
              "claude": (["claude", "-p", "--permission-mode", "plan", "--output-format", "text"], "stdin"),
              "codebuddy": (["codebuddy", "-p", "--output-format", "text"], "stdin"),
              "qoder": (["qodercli", "-p", "-o", "text"], "stdin"),
              "dsh": (["dsh", "--profile", "headless", "-"], "stdin")}
COORD = os.path.join(HOME, "project-coordination")
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
EXP = os.path.join(HOME, "history"); MEM = os.path.join(HOME, "memory")
for d in (EXP, MEM, os.path.join(HOME, "logs")):
    os.makedirs(d, exist_ok=True)
start = (dt.datetime.now() - dt.timedelta(days=DAYS)).strftime("%Y-%m-%dT00:00:00+08:00")
today = dt.date.today().isoformat()
NOWIN = {}
if os.name == "nt":                                                     # 子进程不弹窗口
    si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
    NOWIN = {"creationflags": 0x08000000, "startupinfo": si}
ROLE_CN = {"project_lead": "项目负责人", "server": "服务端", "android": "Android", "ios": "iOS", "h5": "H5", "web": "网页版", "backoffice": "后台 UI",
           "product": "产品", "qa": "测试", "ops": "运营", "recommendation": "推荐 / 内容分发", "vidstore": "剧中台服务端"}   # 与协作库角色登记对齐（v2.7）

# 1) 协作库预填：同事角色 + 需求单负责人（只读）
seed = []
idf = os.path.join(COORD, "registry", "identities.json")
if os.path.exists(idf):
    ids = json.load(open(idf, encoding="utf-8"))
    for p in (ids.get("people") or []) if isinstance(ids, dict) else ids:   # identities.json 顶层是 {"people": [...]}；以前直接遍历拿到的是键名，预填一直是空的（v2.7 修）
        if isinstance(p, dict) and p.get("status") == "active" and p.get("roles"):
            seed.append({"事项": "、".join(ROLE_CN.get(r, r) for r in p["roles"]) + " 相关", "负责人": p["display_name"], "在哪找": "协作群 / 测试群", "依据": "协作库 identities.json"})
for f in glob.glob(os.path.join(COORD, "features", "*", "feature.yaml")):
    text = open(f, encoding="utf-8", errors="ignore").read()
    title = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", text, re.M)
    owner = re.search(r"^\s*(?:owner|dri|assignee|developer):\s*['\"]?([^\s'\"#]+)", text, re.M)
    if title and owner:
        seed.append({"事项": f"{os.path.basename(os.path.dirname(f))} {title.group(1)[:40]}", "负责人": owner.group(1), "在哪找": "协作群", "依据": "协作库 feature.yaml"})


def codex(prompt):
    """跑一次判断用的 AI（名字沿用 codex，实际按 config 选 / 自动找本机装了的）。"""
    out = os.path.join(HOME, "logs", "bootstrap_last.txt")
    if os.path.exists(out):
        os.remove(out)
    if CFG.get("ai_cmd"):
        args, how = list(CFG["ai_cmd"]), CFG.get("ai_prompt", "stdin")
    else:
        names = [CFG["ai"]] if CFG.get("ai") in AI_PRESETS else list(AI_PRESETS)
        found = [k for k in names if shutil.which(AI_PRESETS[k][0][0]) or shutil.which(AI_PRESETS[k][0][0] + ".cmd")]
        if not found:
            print("没找到可用的 AI 命令行（codex / claude / codebuddy / qodercli / dsh），请在 config.json 填 ai_cmd"); return ""
        args, how = AI_PRESETS[found[0]]
        args = [shutil.which(args[0]) or shutil.which(args[0] + ".cmd")] + args[1:]
    args = [out if a == "{out}" else a for a in args]
    if how == "arg":
        args = [prompt if a == "{prompt}" else a for a in args] if "{prompt}" in args else args + [prompt]
    try:
        r = subprocess.run(args, cwd=HOME, capture_output=True, text=True, encoding="utf-8", timeout=900, **NOWIN, **({"input": prompt} if how == "stdin" else {"stdin": subprocess.DEVNULL}))
    except subprocess.TimeoutExpired:
        print("AI 15 分钟没返回（命令卡住），这一块跳过"); return ""
    return open(out, encoding="utf-8").read() if os.path.exists(out) else (r.stdout or "")


# 2) 导出选中群的历史（只读，参数以 `dws chat +chat-messages --help` 为准）
msgs = []
for cid, name in {**CFG["groups"], **CFG.get("readonly_groups", {})}.items():
    f = os.path.join(EXP, re.sub(r'[\\/:*?"<>|]', "_", name) + ".json")
    with open(f, "w", encoding="utf-8") as out:
        subprocess.run([DWS, "chat", "+chat-messages", "--group", cid, "--start", start, "--order", "asc", "--page-all",
                        "--page-limit", "200", "--max-items", "5000", "--format", "json"], stdout=out, timeout=900, **NOWIN)
    try:
        data = json.load(open(f, encoding="utf-8"))
    except ValueError:
        print("导出失败：", name); continue
    for m in data.get("messages") or []:     # dws 的姓名字段是 sender；以前读 senderName 拿不到、退成 senderId 乱码，模型按内容猜人，把 项目助手 认成一位同事（11-18 一位同事反馈）
        msgs.append({"群": name, "id": m.get("messageId"), "时间": m.get("createTime") or m.get("createAt"),
                     "人": m.get("sender") or m.get("senderName") or m.get("senderNick") or "（未知）", "内容": str(m.get("text") or m.get("content") or "")[:800]})
# 2b) 工作目录下的全部 Codex 会话记录（默认读；config.json 的 workspace = 部署时使用者打开 Codex 的目录）
WS = os.path.normcase(os.path.abspath(CFG.get("workspace") or os.getcwd()))
skip = ("# AGENTS.md instructions", "<environment_context", "<user_instructions", "<skills_instructions")
ncodex = 0
for f in glob.glob(os.path.join(os.path.expanduser("~"), ".codex", "sessions", "**", "*.jsonl"), recursive=True):   # 归档的 .jsonl.zst 不读
    cwd, rows = None, []
    for line in open(f, encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        pl = d.get("payload") or {}
        if d.get("type") == "session_meta":
            cwd = os.path.normcase(os.path.abspath(pl.get("cwd") or ""))
        elif d.get("type") == "response_item" and pl.get("type") == "message" and pl.get("role") in ("user", "assistant"):
            text = "\n".join(x.get("text", "") for x in pl.get("content") or [] if isinstance(x, dict))
            if text.strip() and not text.lstrip().startswith(skip):
                rows.append({"群": "Codex 会话", "id": os.path.basename(f)[:40], "时间": d.get("timestamp"),
                             "人": "我" if pl["role"] == "user" else "Codex", "内容": text[:800]})
    if cwd and (cwd == WS or cwd.startswith(WS + os.sep)):
        msgs += rows; ncodex += len(rows)
# 2c) 工作目录下的 Claude Code 会话记录（v2.7：用 Claude Code 的同事也有对话可读；~/.claude/projects/*/*.jsonl）
#     只取本人打的字（content 是字符串、不是工具结果 / 系统注入）和 Claude 的正文（text 段，不要思考和工具调用）
nclaude = 0
for f in glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", "*.jsonl")):
    rows, inws = [], False
    for line in open(f, encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") not in ("user", "assistant") or d.get("isSidechain"):
            continue
        cwd = os.path.normcase(os.path.abspath(d.get("cwd") or ""))
        if d.get("cwd") and (cwd == WS or cwd.startswith(WS + os.sep)):
            inws = True
        m = d.get("message") or {}
        c = m.get("content")
        if d["type"] == "user":
            text = c if isinstance(c, str) else ""
            if d.get("isMeta") or d.get("isCompactSummary") or text.lstrip().startswith(("<", "[", "This session is being continued", "Your claude.ai")):
                text = ""                                             # 系统注入、上下文压缩摘要、额度提示、图片占位，不是本人打的字
        else:
            text = "\n".join(x.get("text", "") for x in (c or []) if isinstance(x, dict) and x.get("type") == "text")
        if text.strip():
            rows.append({"群": "Claude Code 会话", "id": os.path.basename(f)[:40], "时间": d.get("timestamp"),
                         "人": "我" if d["type"] == "user" else "Claude", "内容": text[:800]})
    if inws:
        msgs += rows; nclaude += len(rows)
print("协作库预填", len(seed), "条；导出群消息", len(msgs) - ncodex - nclaude, "条；工作目录", WS, "下的 Codex 会话记录", ncodex, "条、Claude Code 会话记录", nclaude, "条")

# 3) 分块提炼（每块 300 条）
facts = {"负责人": list(seed), "问题处理": [], "偏好与禁区": [], "角色线索": []}
for i in range(0, len(msgs), 300):
    raw = codex(f"""下面是我（{CFG['my_name']}，角色 {CFG.get('roles')}）在工作群里的历史消息（「人」= 发送者姓名，以它为准，不要按内容或语气猜是谁说的；「（未知）」就当不知道是谁），以及我和 AI 助手的对话记录（「群」= Codex 会话 / Claude Code 会话）（JSON）。只根据消息内容提炼，不要推测、不要编造。
只输出一个 JSON 对象，键固定为：
"负责人": [{{"事项": "模块/服务/环境/单据类型", "负责人": "姓名", "在哪找": "群名", "依据": "日期 消息id"}}],
"问题处理": [{{"问题": "...", "处理": "怎么解决的", "谁": "姓名", "结论": "...", "依据": "日期 消息id"}}],
"偏好与禁区": [{{"规矩": "我本人说过的要求或做法", "依据": "日期 消息id"}}],
"角色线索": ["我负责什么、常被问什么（每条一句，带依据）"]
消息：
{json.dumps(msgs[i:i + 300], ensure_ascii=False)}""")
    try:
        part = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        for k in facts:
            facts[k] += part.get(k) or []
    except ValueError:
        print("第", i // 300 + 1, "块解析失败，跳过")


def table(rows, cols):
    seen, lines = set(), ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        key = tuple(str(r.get(c, "")) for c in cols[:2])
        if key in seen:
            continue
        seen.add(key); lines.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + " |")
    return "\n".join(lines)


# 4) 写草稿，等本人在部署第 4 步确认后改名为正式文件
open(os.path.join(MEM, "负责人.draft.md"), "w", encoding="utf-8").write(f"# 负责人（{today}：协作库 + 近 {DAYS} 天群历史）\n\n" + table(facts["负责人"], ["事项", "负责人", "在哪找", "依据"]) + "\n")
open(os.path.join(MEM, "问题处理.draft.md"), "w", encoding="utf-8").write(f"# 问题处理（{today}）\n\n" + table(facts["问题处理"], ["问题", "处理", "谁", "结论", "依据"]) + "\n")
open(os.path.join(MEM, "偏好与禁区.draft.md"), "w", encoding="utf-8").write(f"# 偏好与禁区（{today}）\n\n" + "\n".join(f"- {r.get('规矩')}（{r.get('依据')}）" for r in facts["偏好与禁区"]) + "\n")
open(os.path.join(MEM, "角色.draft.md"), "w", encoding="utf-8").write(
    f"# 角色（{today}）\n\n- 我是：{CFG['my_name']}，角色 {CFG.get('roles')}，负责 {CFG.get('project')}。\n\n## 各群用途\n（部署第 3 步写入）\n\n## 线索\n"
    + "\n".join(f"- {x}" for x in facts["角色线索"]) + "\n")
print("草稿已写入 memory\\*.draft.md")
