"""群消息助手 v2（Windows / macOS / Linux，默认实时汇报；v2.7 起不限 QA，按协作库角色适配全部角色）：dws 长连接监听 → 过滤 → AI 只读决策（Codex / Claude Code / WorkBuddy / Qoder / Trae 等，使用者自己装的那个）→ 脚本执行 → 记忆追加。
v2（2026-11-13）：全程不弹窗口（pythonw + 子进程隐藏 + 系统通知）；两路并行处理、同会话 20 秒内连发合并一次判断；
积压时自动开子 Agent（临时多开 Codex 处理通道，最多 max_workers 个，空了自动退出）；
每天上班把前一天总结发到本人自己的钉钉私聊；钉钉监听连续断开会提醒本人；
v2.8（内网版，项目负责人 11-18：决策权交给人）：取消自动回复——任何消息都先写成草稿，本人确认后才发；连「收到，我确认一下」回执和自动点表情也取消。
  超过 2 小时（remind_after_minutes，可改，提醒群「提醒间隔 3小时 / 关」）还没处理的事，合并再提醒一次。
  提醒群「#编号 问：…」可以先问清楚 AI（依据、背景、改写），再决定发不发；每条发出的消息都留痕（谁、何时确认、问过什么、依据），存 audit/发出留痕.jsonl，不随保留期清理。
v2.9（内网版，11-19）：状态可见——启动、收到相关消息、开始处理、处理完成、监听异常、独立心跳和停止都写入 logs/status.jsonl；状态通知默认发提醒群，心跳默认每 15 分钟一次。
v2.7（梦无矶 11-18）：不限 QA——部署时按协作库 registry\roles.yaml 认全部角色（产品、Android、iOS、H5、网页版、服务端、剧中台、推荐、测试、运营、后台 UI、项目负责人），工作手册每个角色一段规则；名字改为「群消息助手」。
v2.6（梦无矶 11-18）：回复更短、分行（每条 1～3 行，几件事一行一件；发出前把换行统一变成空行，钉钉单个换行会连成一坨）；
  别人之间的对话不插话：消息 @ 的是别人、没 @ 本人，代码层直接不回，也不打扰本人。
  表情（一位同事提议，梦无矶 11-18 测过同意）：开关默认关，提醒群发「表情 开 / 关」切换。开了以后可以给消息点原生表情（白名单），也可以发内置表情包：
  ChineseBQB 开源表情包里 21 个可爱动物 / 卡通 / 程序员包，只留文件名有含义、去掉粗口暧昧的（约 890 张），走 jsDelivr 国内能看；钉钉只显示第一帧。
  按群开关自动回复（梦无矶 11-18 定）：新部署群聊默认只提醒、不回复；从旧版升上来不改原设置，启动时在提醒群问本人「保持现状 / 全部只提醒」；提醒群发「<群名> 自动回复」再回「确认开启 <群名>」二次确认后才开；
  「<群名> 只提醒」立即关；「群列表」看状态。写回 config.json，不用重启。表情也默认关，本人自己发「表情 开」才开。
  每人不用配置：python agent.py stickers 下载索引到 memory\表情包.json（部署时 Codex 跑）；提醒群「表情包」看张数，「删表情包 名字」拉黑。
v2.5.1：不确定是不是归本人的事，群里一个字都不回，只在提醒群问本人「是否归你」；「收到，我确认一下再回复」只在明确 @ 本人、且确定归本人时才回。
v2.5（一位同事试用后提议）：提醒群「待回复」看全部没处理完的事（含暂存草稿）；「清空」一键清掉待回复；「#编号 暂存：…」只存草稿不发，之后「#编号 可以发送」再发。
v2.4：部署先明确职责范围（协作库读取 → 本人补充 → 本人确认）并确认通知 / 自动回复规则；没确认前只写草稿；派活、要负责、要排期、要承诺、超出职责范围的一律交给本人，绝不替本人接。
v2.3：自动回复后在提醒群发「💬 已自动回复」；草稿发到提醒群，监听本人在提醒群里的回复：「#编号 可以发送」发出、「#编号 不发」作废、「#编号 改成：…」按改后的发出。
v2.2：提醒只走本人专属群的机器人（Webhook + 加签，必配）：交给本人的事、草稿待确认、处理完成、监听异常、每天上班汇报都发进这个群，有推送、有历史；
交给本人时先引用回复对方「收到，我确认一下再回复」；本人在该会话亲自回复 / review 发出或删除草稿后，机器人群里补一条「已处理」；status 命令看当天处理情况。
只带相关记忆进提示词；两种模式：auto（默认，能回的直接回、拿不准交给本人）/ draft（全部写草稿等确认）；review 命令批量确认草稿。
用法：pythonw agent.py            后台运行并自动打开汇报窗口（Windows 计划任务；macOS / Linux 用 python3，由 launchd / systemd 托管）
      python agent.py review     列出草稿，回编号批量发送 / 删除
      python agent.py send <草稿> 发送一条草稿
      python agent.py check      自检（环境、登录、配置）
      python agent.py status     今天处理了多少、还有几件没处理
      python agent.py watch      打开只读实时汇报窗口，不重复启动监听
      python agent.py watch --once  查看最近 20 条状态后退出
      python agent.py clear      清空待回复（没处理完的事和草稿全部清掉，不发出）
      python agent.py stickers   下载 / 更新内置表情包索引（v2.6）
      python agent.py audit [N]  看最近 N 条发出留痕（谁、何时确认、问过 AI 什么）（v2.8）
      python agent.py purge      立刻清掉原始记录（消息原文、群历史导出、旧日志），记忆和草稿不动（v2.7）
配置 ~/.qa-agent/config.json（Windows 是 %USERPROFILE%\\.qa-agent\\config.json）；记忆在安装目录的 memory/（Windows C:\\qa-agent\\memory\\，macOS / Linux ~/qa-agent/memory/）。"""
import atexit, base64, datetime as dt, glob, signal, hashlib, hmac, json, os, queue, re, shlex, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request
from collections import deque

VERSION = "v3.0 2026-11-19"
HOME = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(os.path.expanduser("~"), ".qa-agent", "config.json")
DEFAULTS = {"my_name": "", "person_id": "", "roles": [], "project": "", "groups": {}, "readonly_groups": {}, "keywords": [], "people": [],
            "listen_dm": False, "mode": "auto", "max_auto_replies_per_10min": 3, "daily_codex_limit": 300, "workers": 2, "merge_seconds": 20,
            "burst_threshold": 3, "max_workers": 4, "ack_on_escalate": True, "notify_group": "", "scope_confirmed": False,
            "codex_model": "", "webhook": "", "secret": "", "window": ["09:00", "21:00"],
            "emoji": False, "emoji_names": ["赞", "OK", "收到", "谢谢", "辛苦了", "加油", "鼓掌"],
            "keep_days": 30, "remind_after_minutes": 120, "status_notifications": False, "status_heartbeat_minutes": 15, "report_window": False,
            "update_url": "https://raw.githubusercontent.com/Lvan826199/dingtalk-group-assistant/main/agent.py", "update_page": "https://github.com/Lvan826199/dingtalk-group-assistant"}
CFG = {**DEFAULTS, **json.load(open(CFG_PATH, encoding="utf-8"))}
COORD = os.path.join(HOME, "project-coordination")
MEMDIR = os.path.join(HOME, "memory")
for d in ("logs", "drafts", "memory"):
    os.makedirs(os.path.join(HOME, d), exist_ok=True)

# ---- Windows 下所有子进程都不弹窗口
NOWIN = {}
if os.name == "nt":
    si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
    NOWIN = {"creationflags": 0x08000000, "startupinfo": si}          # CREATE_NO_WINDOW

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


def which(name):
    return shutil.which(name) or shutil.which(name + ".cmd") or shutil.which(name + ".exe") or name


DWS, GIT, NODE = which("dws"), which("git"), which("node")

# ---- 判断用的 AI（v2.7：不限 Codex）。使用者自己选、自己装；config 里 "ai" 指定，不指定就用本机装了的第一个。
# 都用只读 / 计划模式跑一次就退出；prompt 长的走 stdin（Windows 命令行长度有限）。参数以本机 --help 为准，对不上用 ai_cmd 自定义。
AI_PRESETS = {
    "codex": {"name": "Codex", "bin": "codex", "args": ["exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", "{out}"], "prompt": "arg", "model": ["-m"]},
    "claude": {"name": "Claude Code", "bin": "claude", "args": ["-p", "--permission-mode", "plan", "--output-format", "text"], "prompt": "stdin", "model": ["--model"]},
    "codebuddy": {"name": "WorkBuddy / CodeBuddy", "bin": "codebuddy", "args": ["-p", "--output-format", "text"], "prompt": "stdin", "model": ["--model"]},
    "qoder": {"name": "Qoder", "bin": "qodercli", "args": ["-p", "-o", "text"], "prompt": "stdin", "model": ["--model"]},
    # DSH（DeepSeek Harness）：官方 headless 模式「答一个任务就退出」，任务从 stdin 读（参数 -）；没有只读开关，提示词只要它输出 JSON，执行都由脚本做
    "dsh": {"name": "DSH", "bin": "dsh", "args": ["--profile", "headless", "-"], "prompt": "stdin", "model": []},
}


def ai_engine(only=None):
    """返回 (显示名, 参数模板, prompt 传法)。ai_cmd 自定义优先（如 Trae：部署时按 traecli --help 填），其次 ai 指定的，最后自动找本机装了的。
    only=预设名时只看这一个（备用 AI 用）。"""
    if CFG.get("ai_cmd") and not only:
        return CFG.get("ai", "自定义"), list(CFG["ai_cmd"]), CFG.get("ai_prompt", "stdin")
    names = [only] if only else ([CFG["ai"]] if CFG.get("ai") in AI_PRESETS else list(AI_PRESETS))
    for k in names:
        pr = AI_PRESETS[k]
        exe = which(pr["bin"])
        if shutil.which(exe) or os.path.exists(exe):
            model = CFG.get("ai_model") or CFG.get("codex_model")
            return pr["name"], [exe] + pr["args"] + ((pr["model"] + [model]) if model and pr["model"] else []), pr["prompt"]
    return "（没找到）", [], "stdin"


def ai_exec(prompt, timeout=300):
    """跑一次 AI，返回它的最后输出文本。主 AI 没结果（没装、报错、卡住）时，按顺序试本机装了的其他 AI（v2.7；config "ai_fallback": false 关掉）。都不行返回空串。"""
    name, args, how = ai_engine()
    text = _ai_once(name, args, how, prompt, timeout)
    if text.strip() or CFG.get("ai_fallback") is False:
        return text
    for k in AI_PRESETS:
        n2, a2, h2 = ai_engine(only=k)
        if not a2 or n2 == name:
            continue
        log(name, "没结果，改用备用", n2)
        text = _ai_once(n2, a2, h2, prompt, timeout)
        if text.strip():
            if not STATE.get("fallback_told"):
                STATE["fallback_told"] = True
                notify("🔁 判断用的 AI 换成了备用", f"{name} 没给出结果（没装好、报错或卡住），这次改用 {n2}。经常这样的话，检查一下 {name} 在终端里能不能用。今天不再重复提醒。")
            return text
    return text


def _ai_once(name, args, how, prompt, timeout):
    if not args:
        log("没找到可用的 AI 命令行（codex / claude / codebuddy / qodercli / dsh）"); return ""
    out = os.path.join(HOME, "logs", f"ai-{threading.get_ident()}-{time.time_ns()}.txt")
    args = [out if a == "{out}" else a for a in args]
    if how == "arg":
        args = [prompt if a == "{prompt}" else a for a in args] if "{prompt}" in args else args + [prompt]
    r = run(args, cwd=HOME, timeout=timeout, **({"input": prompt} if how == "stdin" else {"stdin": subprocess.DEVNULL}))
    text = open(out, encoding="utf-8").read() if os.path.exists(out) else (r.stdout or "")
    if os.path.exists(out):
        os.remove(out)                                                     # 以前固定文件名：这次失败会读到上次的结果
    if r.returncode != 0 and not text.strip():
        log(name, "执行失败", (r.stderr or "")[:200])
    return text
import ssl
SSLCTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem") if os.path.exists("/etc/ssl/cert.pem") and os.name != "nt" else ssl.create_default_context()


def run(args, **kw):
    """找不到命令（没装 dws / codex 等）时不崩，返回 127，由调用方当失败处理（v2.7，Linux 实测发现自检直接崩）。"""
    try:
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **NOWIN, **kw)
    except FileNotFoundError as ex:
        return subprocess.CompletedProcess(args, 127, "", f"找不到命令：{args[0]}（{ex}）")
    except subprocess.TimeoutExpired:                                      # 超时（如 AI 命令卡住）不崩，按失败处理
        return subprocess.CompletedProcess(args, 124, "", f"超时：{args[0]}")


CHILDREN = []   # 监听子进程：助手被停掉（计划任务结束 / launchctl bootout / systemctl stop / Ctrl+C）时一起结束，不留孤儿进程（v2.7）


def popen(args, **kw):
    p = subprocess.Popen(args, text=True, encoding="utf-8", errors="replace", **NOWIN, **({} if os.name == "nt" else {"start_new_session": True}), **kw)
    CHILDREN.append(p)
    return p


def _stop_children(*_):
    """dws 是 node 包装 + 真正的程序两层，只结束外层会留下里层：Windows 用 taskkill /T 连子进程一起结束，macOS / Linux 结束整个进程组。"""
    for p in CHILDREN:
        if p.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, **NOWIN)
                else:
                    os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                pass
    if _:
        sys.exit(0)


atexit.register(_stop_children)
for _sig in ("SIGTERM", "SIGHUP", "SIGINT"):
    if hasattr(signal, _sig):
        try:
            signal.signal(getattr(signal, _sig), _stop_children)
        except (ValueError, OSError):
            pass


HANDBOOK = open(os.path.join(HOME, "工作手册.md"), encoding="utf-8").read()
Q = queue.Queue()
SEEN, SENT, LOCK = set(), [], threading.Lock()
LOG = open(os.path.join(HOME, "logs", dt.date.today().isoformat() + ".log"), "a", encoding="utf-8")
STATE = {"calls": 0, "todo_t": 0, "todo": ""}
FAILS = {}
OUT = {}            # 助手自己发出的文字 → 发出时间；监听再收到时不当作本人亲自回复
STATUS_LOG = os.path.join(HOME, "logs", "status.jsonl")
LISTENERS = {}      # tag -> {started, alive}
LAST_EVENT = {"t": 0, "summary": ""}


def log(*a, console=True):
    line = dt.datetime.now().strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    with LOCK:
        LOG.write(line + "\n"); LOG.flush()
    if console and sys.stdout and sys.stdout.isatty():
        console_write(line)


def report_text(value, limit=800):
    """运行窗口只展示摘要；配置中的机器人凭据和常见密钥字段打码。"""
    text = str(value or "")
    for key in ("webhook", "secret"):
        if CFG.get(key):
            text = text.replace(str(CFG[key]), "[已隐藏]")
    text = re.sub(r"(?i)(\b(?:access_token|token|secret|password|x-internal-key)\b[\"']?\s*[:=]\s*[\"']?)[^\s,\"'}]+", r"\1[已隐藏]", text)
    text = re.sub(r"(?i)(\bauthorization\s*[:=]\s*)(?:Bearer\s+)?[^\s,]+", r"\1[已隐藏]", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x1f\x7f-\x9f]", " ", text)
    return " ".join(text.split())[:limit]


def console_write(text):
    if sys.stdout is None:
        return
    try:
        try:
            print(text, flush=True)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            print(text.encode(encoding, errors="backslashreplace").decode(encoding), flush=True)
    except (BrokenPipeError, OSError):
        pass


def format_report(rec):
    stamp = report_text(rec.get("time"), 30)
    stage = report_text(rec.get("stage"), 40)
    context = " / ".join(report_text(rec.get(k), 80) for k in ("group", "sender") if rec.get(k))
    ref = report_text(rec.get("message_id"), 100)
    title = f"[{stamp}] {stage}" + (f" · {context}" if context else "") + (f" · msg={ref}" if ref else "")
    lines = [title]
    if rec.get("preview"):
        lines.append("  原消息：" + report_text(rec["preview"], 180))
    if rec.get("detail"):
        lines.append("  " + report_text(rec["detail"]))
    return "\n".join(lines)


def status_event(stage, detail="", announce=False, event=None):
    """把值守状态落盘；announce=True 时同步发提醒群，避免助手静默卡住。"""
    rec = {"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "stage": stage,
           "detail": report_text(detail), "pid": os.getpid(), "version": VERSION}
    if event:
        cid = event.get("conversation_id")
        rec.update(group=report_text({**CFG["groups"], **CFG["readonly_groups"]}.get(cid, "提醒群" if cid == CFG.get("notify_group") else "私聊/其他会话"), 80),
                   sender=report_text(event.get("sender"), 80), message_id=report_text(event.get("message_id"), 100))
        if stage in ("收到消息", "开始处理"):
            rec["preview"] = report_text(event.get("content"), 180)
    with LOCK:
        with open(STATUS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log("状态", stage, rec["detail"], console=False)
    if sys.stdout and sys.stdout.isatty():
        console_write(format_report(rec))
    # v3.0：值守状态改在操作台顶栏看（绿点），提醒群默认不再刷「收到消息 / 心跳」；出问题的还照发
    if announce and (CFG.get("status_notifications") or stage in ("监听异常", "发送失败", "处理失败", "汇报窗口未打开")):
        notify(f"📡 {stage}", format_report(rec) if event else rec["detail"])


def report_records(path, follow=True, tail=20):
    """只读状态日志；保留半行，支持文件截断/替换，不碰监听或消费游标。"""
    offset, identity, initial = 0, None, True
    while True:
        records = deque(maxlen=tail) if initial else []
        try:
            with open(path, "rb") as f:
                st = os.fstat(f.fileno())
                current = (st.st_dev, st.st_ino)
                if current != identity or st.st_size < offset:
                    offset = 0
                identity = current
                f.seek(offset)
                while True:
                    line = f.readline()
                    if not line or not line.endswith(b"\n"):
                        break
                    offset = f.tell()
                    try:
                        rec = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(rec, dict):
                        records.append(rec)
        except FileNotFoundError:
            pass
        yield from records
        initial = False
        if not follow:
            return
        yield None


def report_window_lock():
    """一个安装目录只保留一份自动查看器；锁随进程退出释放，不触碰事件。"""
    f = open(os.path.join(HOME, "logs", "report-window.lock"), "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if os.fstat(f.fileno()).st_size == 0:
                f.write(b"0"); f.flush()
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        f.close()
        return None


def open_report_window():
    """默认随后台打开只读查看器。已有交互终端直接输出；查看器不属于监听子进程。"""
    if CFG.get("report_window") is False:
        status_event("汇报窗口", "已按本机设置关闭自动开窗，状态仍写入日志")
        return
    if sys.stdout and sys.stdout.isatty():
        status_event("汇报窗口", "实时汇报已在当前终端显示")
        return
    try:
        lock = report_window_lock()
        if lock is None:
            status_event("汇报窗口", "已有自动汇报窗口，继续使用，不重复打开")
            return
        lock.close()
        args = [sys.executable, "-u", os.path.abspath(__file__), "watch", "--auto"]
        if sys.platform == "win32":
            # pythonw 不附带控制台；查看器必须用同目录的 python.exe，且不能套 NOWIN。
            if os.path.basename(args[0]).lower() == "pythonw.exe":
                args[0] = os.path.join(os.path.dirname(args[0]), "python.exe")
            subprocess.Popen(args, cwd=HOME, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10))
        elif sys.platform == "darwin":
            script = os.path.join(HOME, "logs", "实时汇报.command")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nexec " + shlex.join(args) + "\n")
            os.chmod(script, 0o700)
            r = run(["/usr/bin/open", "-a", "Terminal", script], timeout=15)
            if r.returncode:
                raise OSError((r.stderr or r.stdout or "Terminal 启动失败")[:200])
        else:
            if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                raise OSError("没有图形桌面会话，无法开终端窗口；后台继续运行，状态写入 logs/status.jsonl")
            terminals = [("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"), ("xterm", "-e")]
            terminal = next(([exe, sep] for name, sep in terminals if (exe := shutil.which(name))), None)
            if not terminal:
                raise OSError("未找到终端程序；请安装桌面终端或在本机终端运行 agent.py watch")
            subprocess.Popen(terminal + args, cwd=HOME, start_new_session=True)
        status_event("汇报窗口", "已请求打开实时汇报窗口；窗口会自行显示最近记录和新状态")
    except (OSError, subprocess.SubprocessError) as ex:
        detail = report_text(ex)
        status_event("汇报窗口未打开", detail)
        notify("⚠️ 实时汇报窗口未打开", detail + "。后台继续运行；查看日志或在终端运行 agent.py watch。")


def watch(once=False, auto=False):
    lock = report_window_lock() if auto else None
    if auto and lock is None:
        console_write("已有自动汇报窗口，本窗口退出，不启动监听。")
        return
    console_write("群消息助手 · 实时汇报（只读查看，不启动第二套监听；Ctrl+C 只关闭查看窗口）")
    last, shown, pulse = None, 0, time.monotonic()
    try:
        for rec in report_records(STATUS_LOG, follow=not once):
            if rec is not None:
                console_write(format_report(rec)); last = rec; shown += 1; pulse = time.monotonic()
            else:
                if time.monotonic() - pulse >= 60:
                    console_write("等待新状态；最后记录：" + report_text((last or {}).get("time") or "暂无") + "。此窗口仅展示日志，进程存活和处理结果需结合状态核对。")
                    pulse = time.monotonic()
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if lock:
            lock.close()
    if not shown:
        console_write("尚无状态记录；请确认后台助手已启动，升级后已重启运行。")


def status_snapshot():
    alive = [name for name, x in LISTENERS.items() if x.get("alive")]
    opened = len(_open_load())
    last = LAST_EVENT.get("summary") or "无"
    return f"监听 {len(alive)}/{len(LISTENERS)}（{'、'.join(alive) or '无'}）；处理通道 {ACTIVE['n']}；队列 {Q.qsize() + READY.qsize()}；待处理 {opened}；最近事件 {last}"


def heartbeat_loop():
    """独立线程定期报告；Codex / 监听线程卡住时，外部 watchdog 仍可依靠 status.jsonl 判断最后心跳。"""
    while in_window():
        mins = max(1, int(CFG.get("status_heartbeat_minutes") or 15))
        time.sleep(mins * 60)
        if in_window():
            status_event("心跳", status_snapshot(), announce=bool(CFG.get("status_notifications")))


def in_window():
    s, e = CFG["window"]; now = dt.datetime.now().strftime("%H:%M")
    return s <= now < e


def minutes_left():
    e = dt.datetime.combine(dt.date.today(), dt.time.fromisoformat(CFG["window"][1]))
    return max(0, int((e - dt.datetime.now()).total_seconds() // 60))


def notify(title, text):
    """提醒本人：只走本人专属群的机器人（有推送、有历史）。机器人没配或发送失败时记进 待处理.md 和日志，第二天的汇报里会写出来。"""
    ok = False
    if CFG.get("quiet_new_items") and title[:1] in ("🔔", "❓", "📝"):
        log("新事项只进操作台，不发提醒群", title); return True          # 和别的值守并行时避免提醒群重复（11-19）
    if CFG.get("webhook") and CFG.get("secret"):
        ts = str(int(time.time() * 1000)); sec = CFG["secret"]
        sign = base64.b64encode(hmac.new(sec.encode(), f"{ts}\n{sec}".encode(), hashlib.sha256).digest()).decode()
        url = f"{CFG['webhook']}&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"
        body = {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n" + text.replace("\n", "\n\n")}}
        for _ in (1, 2):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=15, context=SSLCTX) as r:
                    ok = json.loads(r.read().decode()).get("errcode") == 0
                if ok:
                    break
            except Exception as ex:
                log("机器人发送失败", repr(ex))
            time.sleep(3)
    if not ok:
        log("提醒没发出去（机器人未配置或发送失败）", title)
        with LOCK, open(os.path.join(HOME, "待处理.md"), "a", encoding="utf-8") as f:
            f.write(f"\n## {dt.datetime.now():%m-%d %H:%M} {title}（机器人没发出去）\n{text}\n")
    return ok


def _resolve_group(q):
    """群名或 openConversationId → openConversationId（群名要唯一命中）。"""
    if q.startswith("cid"):
        return q
    r = run([DWS, "chat", "+chat-search", "--query", q, "--format", "json"], timeout=60)
    ids = list(dict.fromkeys(re.findall(r'"openConversationId"\s*:\s*"([^"]+)"', r.stdout or "")))
    return ids[0] if len(ids) == 1 else None


def setup_notify(wait_minutes=15, group="", webhook="", secret=""):
    """v3.0：提醒群自动建好（dws 建群，只有本人），再引导本人在群里加自定义机器人。
    钉钉开放接口不支持创建自定义机器人、也拿不到它的地址和密钥，这一步只能本人在群设置里点（约 1 分钟）；
    本人把地址和加签密钥直接发在这个群里，助手读到后自己写进配置、发一条自检，不用手改任何文件。"""
    # 已有提醒群 / 机器人的直接绑定，不强制新建（11-19 梦无矶）：--group 群名或 cid；--webhook 地址 --secret SEC 密钥
    if group:
        cid = _resolve_group(group)
        if not cid:
            print(f"没找到唯一的群「{group}」，换个更完整的群名，或直接给 openConversationId"); return False
        save_cfg("notify_group", cid); print("已绑定提醒群", group)
    if webhook and secret:
        save_cfg("webhook", webhook); save_cfg("secret", secret)
    if CFG.get("notify_group") and CFG.get("webhook") and CFG.get("secret"):
        ok = notify("🧪 助手自检", "已绑定你现有的提醒群和机器人：以后草稿、提醒、日报都从这里发。")
        print("已用现有的群和机器人，自检", "成功" if ok else "失败（核对地址、密钥是否对应这个群的机器人）"); return ok
    cid = CFG.get("notify_group")
    if not cid:
        name = f"群消息助手·{CFG.get('my_name') or '提醒'}"
        r = run([DWS, "chat", "+chat-create", "--name", name, "--yes", "--format", "json"], timeout=90)
        m = re.search(r'"openConversationId"\s*:\s*"([^"]+)"', r.stdout or "")
        if not m:
            print("建群失败：", (r.stdout or r.stderr or "")[:300]); return False
        cid = m.group(1); save_cfg("notify_group", cid); print(f"已建好提醒群「{name}」（只有你一个人）")
    steps = ("这是你的群消息助手提醒群，只有你自己。还差一步（钉钉不允许程序代建机器人，要你点一下，约 1 分钟）：\n"
             "1. 电脑钉钉打开本群 → 右上角「群设置」→「机器人」→「添加机器人」→「自定义」\n"
             "2. 名字随便填（比如「助手」），安全设置勾「加签」，复制那串以 SEC 开头的密钥\n"
             "3. 点「完成」，复制 Webhook 地址\n"
             "4. 把 **Webhook 地址** 和 **SEC 密钥** 直接发在本群（一条或两条都行）\n"
             "助手读到后自动写进配置，再发一条「🧪 助手自检」，你在群里看到就好了。")
    run([DWS, "chat", "+messages-send", "--group", cid, "--markdown", steps, "--yes", "--format", "json"], timeout=60)
    print("已在提醒群发了加机器人的步骤；把 Webhook 地址和 SEC 密钥发进群里，我等你", wait_minutes, "分钟")
    since, hook, sec, end = dt.datetime.now() - dt.timedelta(minutes=1), CFG.get("webhook") or "", CFG.get("secret") or "", time.time() + wait_minutes * 60
    while time.time() < end and not (hook and sec):
        time.sleep(10)
        r = run([DWS, "chat", "message", "list", "--group", cid, "--time", f"{since:%Y-%m-%d %H:%M:%S}", "--direction", "newer", "--limit", "20", "--format", "json"], timeout=60)
        text = r.stdout or ""
        m = re.search(r"https://oapi\.dingtalk\.com/robot/send\?access_token=[0-9a-f]{20,}", text)
        hook = m.group(0) if m else hook
        m = re.search(r"\bSEC[0-9a-f]{40,}\b", text)
        sec = m.group(0) if m else sec
    if not (hook and sec):
        print("没等到地址和密钥；发进群后再运行一次：python agent.py setup-notify"); return False
    save_cfg("webhook", hook); save_cfg("secret", sec)
    ok = notify("🧪 助手自检", "提醒机器人配好了：以后草稿、提醒、日报都从这里发。\n建议把群里那两条带地址和密钥的消息撤回或删除。")
    print("机器人已配置，自检", "成功" if ok else "失败（核对是否勾了「加签」、地址是否完整）"); return ok


OPEN_PATH = os.path.join(HOME, "logs", "open.json")      # 还没处理完的事：{编号: {...}}


def _open_load():
    try:
        return json.load(open(OPEN_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _open_save(d):
    with LOCK:
        json.dump(d, open(OPEN_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def open_add(e, kind, why):
    """交给本人 / 草稿待确认 → 记一个编号（本地 open.json），机器人消息里带上，处理完再发一条「已处理」。"""
    no = "#" + re.sub(r"[^A-Za-z0-9]", "", e.get("message_id", ""))[-5:]
    d = _open_load(); d[no] = {"cid": e.get("conversation_id"), "kind": kind, "who": e.get("sender"),
                               "what": str(e.get("content") or "")[:60], "why": why[:60], "at": f"{dt.datetime.now():%m-%d %H:%M}", "ts": time.time(), "event": e}
    _open_save(d)
    return no


def open_close(no, why):
    d = _open_load()
    x = d.pop(no, None)
    if x:
        _open_save(d); log("已处理", no, why)
        status_event("事项已关闭", f"{no}：{why}", event=x.get("event"))
        notify(f"✅ {no} 已处理", f"{x['who']}：{x['what']}\n{why}")


def close_by_conversation(cid):
    """本人在这个会话里亲自回复了 → 这个会话里交给本人的事都算处理了。"""
    for no, x in list(_open_load().items()):
        if x.get("cid") == cid:                                           # 本人（或代本人值守的程序）已在原会话回复：草稿也作废
            f, _ = draft_by_no(no)
            if f:
                os.remove(f)
            open_close(no, "你已在该会话回复")


# ---- 表情（v2.6）：原生表情回应 + 内置表情包（ChineseBQB）
STICKERS = os.path.join(MEMDIR, "表情包.json")     # {名字: 图片地址}
BQB_TREE = "https://api.github.com/repos/zhaoolee/ChineseBQB/git/trees/master?recursive=1"
BQB_CDN = "https://cdn.jsdelivr.net/gh/zhaoolee/ChineseBQB@master/"
BQB_PACKS = ("001", "007", "008", "009", "010", "011", "023", "024", "026", "031", "034", "035", "049", "052", "054", "055", "056", "057", "060", "108", "109")
BQB_BAD = ("TM|tm|装B|装逼|B|屁|死|滚|婊|崽种|傻|操|尼玛|妈|日你|骚|丑|蠢|智障|脑残|打你|踹|杀|血|枪|刀|弄死|去你|老子|爸爸|爷|撕|色|胸|亲我|亲亲|嫁|"
           "老婆|老公|约|睡你|舔|恶心|呕|吐|绿|穷|胖|秃|蛇精|污|鸡儿|蛋疼|凉凉|凉了|心机|闭嘴|管我|凭什么|上吊|来玩|马子|找抽|别爱我|配不上|小可爱|"
           "撩|宝贝|爱我|魅力|甜蜜|网线|打我|生气|闹|钱|排位|卵|肾|么么哒|兄弟你这")


def build_stickers():
    """下载 ChineseBQB 目录，按推荐包 + 过滤规则生成 memory\表情包.json；已拉黑的（「删表情包」）不再加回来。"""
    with urllib.request.urlopen(urllib.request.Request(BQB_TREE, headers={"User-Agent": "qa-agent"}), timeout=60, context=SSLCTX) as r:
        tree = json.loads(r.read().decode())["tree"]
    black = set(json.load(open(STICKERS + ".blacklist", encoding="utf-8"))) if os.path.exists(STICKERS + ".blacklist") else set()
    lib = {}
    for x in tree:
        p = x["path"]
        if x["type"] != "blob" or "/" not in p or p[:3] not in BQB_PACKS or x.get("size", 0) > 1_500_000 or not p.lower().endswith((".gif", ".jpg", ".jpeg", ".png", ".webp")):
            continue
        name = os.path.splitext(p.split("/")[-1])[0].split("-", 1)[-1]
        if re.search(r"[一-鿿]{2,}", name) and not re.search(BQB_BAD, name) and name not in black and name not in lib:
            lib[name] = BQB_CDN + urllib.parse.quote(p)
    json.dump(lib, open(STICKERS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return len(lib)


def stickers():
    return json.load(open(STICKERS, encoding="utf-8")) if os.path.exists(STICKERS) else {}


def save_cfg(key, value):
    """提醒群里切开关时写回 config.json（只改这一项）。"""
    CFG[key] = value
    with LOCK:
        c = json.load(open(CFG_PATH, encoding="utf-8")); c[key] = value
        json.dump(c, open(CFG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


PENDING_ON = {}   # 等二次确认开自动回复的群：cid → 时间


def can_reply(cid):
    """这个群能不能往里发消息（只发本人确认过的草稿）。v2.8 起没有自动回复：groups 里的群可发草稿，readonly_groups 只看。"""
    return cid in CFG["groups"]


def upgrade_ask():
    """v2.8 升级提示：以前开过自动回复的，告诉本人现在一律改成草稿确认（公司要求：决策权交给人）。只提示一次。"""
    mark = os.path.join(HOME, "logs", "v2.8-notice")
    if os.path.exists(mark) or not CFG["groups"]:
        return
    open(mark, "w").close()
    notify("ℹ️ v2.8：不再自动回复", "从这一版起，助手不在群里自动回复任何消息：能答的写成草稿发到这里，你确认后才发；回执「收到，我确认一下」和自动点表情也取消了。\n"
           "拿不准可以先问：「#编号 问：依据是什么？」。每条发出的消息都会留痕。")


def group_command(text):
    """「群列表」看监听的群；「<群名> 只看」以后这个群的草稿也不发（只提醒）；「<群名> 可发草稿」恢复。v2.8 起没有自动回复。"""
    allg = {**CFG["groups"], **CFG["readonly_groups"]}
    if text in ("清理记录", "清理原始记录"):
        n = purge_now()
        notify("🧹 原始记录已清理", f"清掉 {n} 条 / 个（收到的消息原文、群历史导出、旧日志）。提炼好的记忆、草稿和发出留痕没动。平时会自动只保留最近 {CFG.get('keep_days') or '不限'} 天。"); return True
    m = re.fullmatch(r"提醒间隔\s*(关|关闭|0|\d+(?:\.\d+)?)\s*(小时|h|分钟|分|min)?", text, re.I)
    if m:
        v = m.group(1)
        mins = 0 if v in ("关", "关闭", "0") else int(float(v) * (60 if (m.group(2) or "小时").lower() in ("小时", "h") else 1))
        save_cfg("remind_after_minutes", mins)
        notify("⏰ 已设置", "超时不再重复提醒" if not mins else f"没处理的事超过 {mins // 60 if mins % 60 == 0 else mins} {'小时' if mins % 60 == 0 else '分钟'}会再提醒一次"); return True
    if text in ("群列表", "监听群", "看群"):
        rows = [f"{n}：{'可发草稿（你确认后发）' if can_reply(c) else '只看'}" for c, n in allg.items()]
        notify("👥 监听的群", "\n".join(rows) + "\n改：发「群名 只看」或「群名 可发草稿」。所有消息都要你确认才会发出。"); return True
    if re.search(r"自动回复|确认开启", text):
        notify("ℹ️ 不提供自动回复", "按公司要求，决策权交给人：助手只写草稿，你确认后才发。拿不准可以先问「#编号 问：……」。"); return True
    m = re.fullmatch(r"(.+?)\s*(只看|只提醒|不回复|可发草稿|可以发)", text)
    if not m:
        return False
    name, ro = m.group(1).strip(), m.group(2) in ("只看", "只提醒", "不回复")
    hit = [c for c, n in allg.items() if name == n] or [c for c, n in allg.items() if name in n]
    if len(hit) != 1:
        notify("❓ 没认出是哪个群", f"「{name}」匹配到 {len(hit)} 个。发「群列表」看准确群名。"); return True
    cid = hit[0]; gname = allg[cid]
    g, rog = dict(CFG["groups"]), dict(CFG["readonly_groups"])
    g.pop(cid, None); rog.pop(cid, None)
    (rog if ro else g)[cid] = gname
    save_cfg("groups", g); save_cfg("readonly_groups", rog)
    notify("👥 已切换", f"{gname}：" + ("只看，草稿也不往这个群发" if ro else "可发草稿，你确认后发")); return True


def sticker_command(text):
    """提醒群表情指令，认了就返回 True。"""
    m = re.fullmatch(r"表情\s*(开|关|打开|关闭|on|off)", text, re.I)
    if m:
        on = m.group(1).lower() in ("开", "打开", "on")
        save_cfg("emoji", on)
        notify("😀 表情包已" + ("打开" if on else "关闭"), f"表情包{'会在轻松的场合附在草稿里建议，你确认发送时才一起发' if on else '不再建议'}。表情包 {len(stickers())} 张" + ("" if stickers() else "，还没下载：在电脑上运行 python agent.py stickers") + "。")
        return True
    if text in ("表情包", "表情包库", "看表情包"):
        lib = stickers()
        notify(f"🖼 表情包 {len(lib)} 张", "随便看几个：" + "、".join(list(lib)[::max(1, len(lib) // 20)][:20]) + "\n不喜欢哪张就发「删表情包 名字」。"); return True
    m = re.fullmatch(r"删(除)?表情包?\s*(\S+)", text)
    if m:
        lib = stickers(); gone = lib.pop(m.group(2), None)
        bl = STICKERS + ".blacklist"
        black = json.load(open(bl, encoding="utf-8")) if os.path.exists(bl) else []
        with LOCK:
            json.dump(lib, open(STICKERS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            json.dump(sorted(set(black + [m.group(2)])), open(bl, "w", encoding="utf-8"), ensure_ascii=False)
        notify("🗑 表情包", f"「{m.group(2)}」" + ("已删除，以后不会再用" if gone else "不在库里（已记黑名单）")); return True
    return False


def react(e, emoji):
    """给原消息点表情回应：只用白名单里的（钉钉不校验名字，乱写也能点上）。"""
    if emoji not in CFG["emoji_names"]:
        return False
    r = run([DWS, "chat", "message", "add-emoji", "--conversation-id", e["conversation_id"], "--msg-id", e["message_id"], "--emoji", emoji, "--format", "json"], timeout=60)
    return r.returncode == 0 and '"success": false' not in (r.stdout or "")


def send_sticker(e, name):
    """内置表情包：Markdown 图片（钉钉只显示第一帧，一位同事 11-18 实验）。"""
    url = stickers().get(name)
    if not url:
        return False
    r = run([DWS, "chat", "message", "send", "--group", e["conversation_id"], "--title", name, "--text", f"![{name}]({url})", "--format", "json"], timeout=60)
    return r.returncode == 0 and '"success": false' not in (r.stdout or "")


def ack(e):
    """v2.8 起取消：「收到，我确认一下再回复」也是没经本人确认就发出的话，不再发。保留函数名兼容旧调用。"""
    return


def related_memory(text):
    """只带和这条消息相关的记忆：角色.md 全带（短）；其余按消息里的词命中行，最多 3000 字。"""
    parts = []
    scope = os.path.join(MEMDIR, "职责范围.md")
    if os.path.exists(scope):
        parts.append("## 我的职责范围（本人已确认）\n" + open(scope, encoding="utf-8").read()[:2500])
    p = os.path.join(MEMDIR, "角色.md")
    if os.path.exists(p):
        parts.append("## 角色\n" + open(p, encoding="utf-8").read()[:1500])
    words = {w for w in re.findall(r"[A-Za-z][A-Za-z0-9_\-/.]{2,}|[\u4e00-\u9fff]{2,4}", text)}
    hits = []
    for name in ("负责人.md", "问题处理.md", "偏好与禁区.md"):
        p = os.path.join(MEMDIR, name)
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.startswith(("|", "-")) and any(w in line for w in words):
                    hits.append(f"[{name[:-3]}] {line.strip()}")
    pref = os.path.join(MEMDIR, "偏好与禁区.md")
    if os.path.exists(pref):                                              # 规矩永远带上（通常不长）
        parts.append("## 偏好与禁区\n" + open(pref, encoding="utf-8").read()[:1500])
    if hits:
        parts.append("## 相关记忆\n" + "\n".join(hits)[:3000])
    return "\n\n".join(parts)


def todo_text():
    """协作库里本人的待办，每小时刷新一次；只在消息像是问待办 / 进度时才带进提示词。"""
    if time.time() - STATE["todo_t"] > 3600 and os.path.isdir(COORD):
        run([GIT, "-C", COORD, "pull", "--ff-only", "-q"], timeout=120)
        r = run([NODE, "tools/todo-report.mjs", "--ref", "WORKTREE", "--person", CFG["my_name"]], cwd=COORD, timeout=120)
        STATE.update(todo_t=time.time(), todo=(r.stdout or "")[-3000:])
    return STATE["todo"]


def draft_by_no(no):
    for f in glob.glob(os.path.join(HOME, "drafts", "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if d.get("todo") == no:
            return f, d
    return None, None


def stash(no, text):
    """「#编号 暂存：内容」：只存草稿不发。已有草稿就改内容；交给本人的事（没有草稿）就新建一份草稿挂在这个编号上。"""
    f, d = draft_by_no(no)
    if f:
        d["draft"] = text; json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        x = _open_load().get(no)
        if not x or not x.get("event"):
            notify(f"❓ 没找到 {no}", "可能已经处理过；在提醒群发「待回复」看还有哪些。"); return
        name = save_draft(x["event"], text)
        p = os.path.join(HOME, "drafts", name); dd = json.load(open(p, encoding="utf-8")); dd["todo"] = no
        json.dump(dd, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    notify(f"📌 {no} 草稿已暂存（没发）", f"{text[:200]}\n要发时回「{no} 可以发送」；再改回「{no} 暂存：新内容」。")


def clear_all():
    """清空待回复：没处理完的事和草稿全部清掉，什么都不发。"""
    n = len(_open_load()); fs = glob.glob(os.path.join(HOME, "drafts", "*.json"))
    for f in fs:
        os.remove(f)
    _open_save({}); log("清空待回复", n, "件", len(fs), "份草稿")
    return n, len(fs)


AUDIT = os.path.join(HOME, "audit", "发出留痕.jsonl")    # v2.8：每条发出的消息谁确认的、问过什么、依据；不随保留期清理


def audit(no, ev, text, confirm, sticker="", reason=""):
    os.makedirs(os.path.dirname(AUDIT), exist_ok=True)
    x = _open_load().get(no, {})
    rec = {"发出时间": f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}", "编号": no, "群": {**CFG["groups"], **CFG["readonly_groups"]}.get(ev.get("conversation_id"), ev.get("conversation_id")),
           "原消息": {"谁": ev.get("sender"), "内容": str(ev.get("content") or "")[:500], "消息ID": ev.get("message_id")},
           "发出内容": text, "表情包": sticker, "确认人": CFG["my_name"], "确认方式": confirm[:200],
           "AI 依据": reason or x.get("reason", ""), "确认前问过 AI": x.get("qa", [])}
    with LOCK, open(AUDIT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ask_ai(no, question):
    """「#编号 问：……」：带着原消息、草稿、依据、记忆去问 AI；AI 可以给答复，也可以按要求改草稿。只回提醒群，不往原会话发任何东西。"""
    x = _open_load().get(no)
    f, d = draft_by_no(no)
    if not x and not d:
        notify(f"❓ 没找到 {no}", "可能已经处理完了。发「待回复」看还有哪些。"); return
    ev = (d or {}).get("event") or x.get("event") or {}
    status_event("正在回答追问", f"{no}：{question}", event=ev)
    draft = (d or {}).get("draft", "")
    qa = (x or {}).get("qa", [])
    prompt = ("你是我的群消息助手。我在决定怎么处理下面这条群消息前，想先问清楚。只输出一行 JSON："
              '{"answer": "直接回答我的问题，1～5 行，有依据就写出处，没依据就说不知道", "new_draft": "只有我要求改写 / 起草回复时才填，否则留空"}\n'
              "不要替我做决定，不要承诺任何事；new_draft 也只是草稿，我确认后才会发。\n\n"
              f"## 工作手册\n{HANDBOOK}\n\n{related_memory(str(ev.get('content') or '') + question)}\n\n"
              f"## 原消息\n{json.dumps(ev, ensure_ascii=False)}\n\n## 现在的草稿\n{draft or '（还没有）'}\n\n## 之前的判断依据\n{(x or {}).get('reason') or (d or {}).get('reason') or ''}\n\n"
              f"## 之前问过的\n{json.dumps(qa, ensure_ascii=False)}\n\n## 我的问题\n{question}")
    raw = ai_exec(prompt)
    try:
        r = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except ValueError:
        r = {"answer": raw.strip()[:800] or "AI 没给出回答，稍后再问一次。", "new_draft": ""}
    ans, nd = str(r.get("answer") or "").strip(), str(r.get("new_draft") or "").strip()
    if x is not None:
        y = _open_load()
        if no in y:
            y[no].setdefault("qa", []).append({"问": question, "答": ans[:500], "改写": nd[:300], "时间": f"{dt.datetime.now():%H:%M}"}); _open_save(y)
    if nd:
        if f:
            d["draft"] = nd; json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        elif ev:
            name = save_draft(ev, nd, reason=(x or {}).get("reason", ""))
            dd = json.load(open(os.path.join(HOME, "drafts", name), encoding="utf-8")); dd["todo"] = no
            json.dump(dd, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    notify(f"💡 {no} AI 的回答", (ans or "（没有回答）") + (f"\n\n新草稿：{nd}\n要发就回「{no} 可以发送」，再改回「{no} 改成：…」，继续问回「{no} 问：…」。" if nd else f"\n\n还想问就继续「{no} 问：…」；决定好了回「{no} 可以发送」/「{no} 不发」，或自己在原会话回。"))
    status_event("追问已回答", f"{no}：{ans}" + ("；草稿已更新，待本人确认" if nd else ""), event=ev)


def command(e):
    """本人在提醒群里回草稿：「#编号 可以发送 / 发送 / 发」「#编号 不发 / 删除 / 作废」「#编号 改成：新内容」「#编号 暂存：内容」「#编号 不归我」「全部发送」「清空」。"""
    text = str(e.get("content") or "").strip()
    if re.fullmatch(r"(一键)?清空(待回复)?", text):
        n, k = clear_all(); notify("🧹 待回复已清空", f"清掉 {n} 件没处理完的事、{k} 份草稿，都没有发出。"); return
    m = re.match(r"(#[A-Za-z0-9]{3,8})\s*不归我", text)
    if m:
        f, _ = draft_by_no(m.group(1))
        if f:
            os.remove(f)
        open_close(m.group(1), "你说不归你，群里不回"); return
    m = re.match(r"(#[A-Za-z0-9]{3,8})\s*(?:问|请问|问一下)[：:]\s*(.+)", text, re.S)
    if m:
        ask_ai(m.group(1), m.group(2).strip()); return
    m = re.match(r"(#[A-Za-z0-9]{3,8})\s*暂存[：:]\s*(.+)", text, re.S)
    if m:
        stash(m.group(1), m.group(2).strip()); return
    if re.search(r"全部(可以)?发(送)?", text):
        nos = [json.load(open(f, encoding="utf-8")).get("todo") for f in glob.glob(os.path.join(HOME, "drafts", "*.json"))]
    else:
        nos = ["#" + x for x in re.findall(r"#([A-Za-z0-9]{3,8})", text)]
    if not nos:
        return
    for no in nos:
        f, d = draft_by_no(no)
        if not f:
            notify(f"❓ 没找到草稿 {no}", "可能已经发过或删了；看还有哪些：在提醒群发「草稿」两个字。"); continue
        m = re.search(r"改成[：:]\s*(.+)", text, re.S)
        if m:
            d["draft"] = m.group(1).strip()
        if re.search(r"不发|删除|作废|算了", text):
            os.remove(f); open_close(no, "你说不发，草稿已作废")
        elif m or re.search(r"可以|发送|发出|发吧|^发", text):
            try:
                reply(d["event"], d["draft"], keep_draft=False)
                st = d.get("sticker") if CFG.get("emoji") else ""
                if st:
                    send_sticker(d["event"], st)
                audit(no, d["event"], d["draft"], text, sticker=st, reason=d.get("reason", ""))
                os.remove(f); open_close(no, "已按你确认发出：" + d["draft"][:100])
            except SendFailed:
                pass                                                       # 已用机器人通知过；草稿还在，恢复后再回「可以发送」
            except Exception as ex:
                notify(f"⚠️ {no} 发送失败", repr(ex)[:200])


def list_drafts_to_group():
    """「待回复」/「草稿」：列出全部没处理完的事，有草稿（含暂存）的带上草稿内容。"""
    drafts = {d.get("todo"): d["draft"] for d in (json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(HOME, "drafts", "*.json")))}
    rows = [f"{no} {x['at']} {x['who']}：{x['what'][:40]}" + (f" → 草稿：{drafts[no][:60]}" if no in drafts else "（还没草稿）")
            for no, x in _open_load().items()]
    link = ""
    try:
        import console                                                     # v3.0：附上操作台链接，点开在页面里处理
        if console.A:
            link = f"\n\n[打开操作台看全部、直接处理]({console.url()})"
    except Exception:
        pass
    notify(f"📋 待回复 {len(rows)} 件", "\n".join(rows) + "\n回「#编号 暂存：内容」存草稿不发，「#编号 可以发送」发出，「清空」全部清掉" + link if rows else "没有" + link)


def relevant(e):
    sender = str(e.get("sender") or "")
    if CFG.get("notify_group") and e.get("conversation_id") == CFG["notify_group"]:
        if sender == CFG["my_name"] and e.get("message_id") not in SEEN:
            SEEN.add(e.get("message_id"))
            status_event("收到消息", "收到本人在提醒群的指令", event=e)
            try:
                if sticker_command(str(e.get("content") or "").strip()) or group_command(str(e.get("content") or "").strip()):
                    return False
                list_drafts_to_group() if re.fullmatch(r"(看)?草稿|待回复(详细)?|.{0,6}(待办|待处理|要处理|没处理|没回)(的)?(事|消息)?(有哪些|有什么|吗|呢)?[？?]?|还有(什么|啥|哪些)(事|要处理的|没处理的)?[？?]?", str(e.get("content") or "").strip()) else command(e)
            except Exception as ex:
                log("提醒群指令处理失败", repr(ex))
                status_event("处理失败", f"提醒群指令：{ex!r}", event=e)
        return False                                                       # 提醒群里的消息不交给 AI
    if sender == CFG["my_name"] and e.get("conversation_id"):
        if BQB_CDN in str(e.get("content") or ""):
            return False                                                   # 助手发的表情包（以本人身份发），不算本人亲自回复
        mine = re.sub(r"\s+", "", str(e.get("content") or ""))
        if not any(mine and (mine in k or k in mine) for k, t in OUT.items() if time.time() - t < 900):
            close_by_conversation(e.get("conversation_id"))                # 本人亲自回了（不是助手发的），待办自动完成
        return False
    if not sender or "机器人" in sender:
        return False
    if e.get("message_id") in SEEN:
        return False
    text = str(e.get("content") or "") + json.dumps(e.get("quoted_message") or "", ensure_ascii=False)
    return any(k in text for k in CFG["keywords"] + [CFG["my_name"], "@所有人", "@全体成员"]) or sender in CFG["people"]   # @所有人 也要看（11-19：「@所有人 安卓 1.1.1 已提审」被漏）


def backfill_loop():
    """兜底补读（11-19）：实时监听每 29 分钟续一次期，续期间隙、断线、订阅冷却时的消息会丢。
    每 backfill_minutes 分钟（默认 30）把各群从上次补读起的消息不过滤地拉一遍，没见过、又和我有关的照常交给 AI。"""
    since = dt.datetime.now() - dt.timedelta(minutes=30)
    while in_window():
        time.sleep(max(5, int(CFG.get("backfill_minutes") or 30)) * 60)
        now = dt.datetime.now()
        for cid, name in {**CFG["groups"], **CFG["readonly_groups"]}.items():
            r = run([DWS, "chat", "message", "list", "--group", cid, "--time", f"{since:%Y-%m-%d %H:%M:%S}", "--direction", "newer", "--limit", "50"], timeout=60)
            try:
                msgs = json.loads(r.stdout).get("messages") or []
            except (ValueError, AttributeError):
                log("补读失败", name, str(getattr(r, "stdout", ""))[:120]); continue
            for m in msgs:
                e = {"sender": m.get("sender"), "content": m.get("content") or m.get("text"), "conversation_id": m.get("openConversationId") or cid,
                     "message_id": m.get("openMessageId") or m.get("messageId"), "quoted_message": m.get("quotedMessage")}
                if e["message_id"] and relevant(e):
                    SEEN.add(e["message_id"]); Q.put(e)
                    log("补读到漏掉的消息", name, e["sender"], str(e["content"])[:60])
                    status_event("收到消息", "断线/续期间隙补读，已加入处理队列", event=e)
        since = now - dt.timedelta(minutes=2)   # 和上一轮留 2 分钟重叠，SEEN 去重


def listen(args, tag):
    LISTENERS[tag] = {"started": time.time(), "alive": True}
    status_event("监听已启动", tag, announce=True)
    try:
        while in_window():
            dur = min(29, minutes_left())
            if dur < 1:
                break
            try:
                p = popen([DWS, "event", "+listen-im", *args, "--duration", f"{dur}m"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            except FileNotFoundError:
                log(tag, "找不到钉钉 CLI（dws），10 分钟后再试")
                if FAILS.get(tag) != -1:
                    FAILS[tag] = -1
                    status_event("监听异常", f"{tag}：找不到 dws 命令", announce=True)
                time.sleep(600); continue
            t0, got, err = time.time(), 0, ""
            for line in p.stdout:
                try:
                    e = json.loads(line)
                    got += 1
                except ValueError:
                    if "cooldown" in line:
                        log(tag, "订阅冷却，60 秒后重连"); time.sleep(60)
                    elif line.strip():
                        err = line.strip()[:200]
                    continue
                if isinstance(e, dict) and "error" in e:
                    err = json.dumps(e["error"], ensure_ascii=False)[:200]; continue
                if relevant(e):
                    SEEN.add(e.get("message_id")); Q.put(e)
                    LAST_EVENT.update(t=time.time(), summary=f"{tag} / {e.get('sender')}：{str(e.get('content') or '')[:80]}")
                    status_event("收到消息", "已加入处理队列，等待合并同一会话的消息", announce=True, event=e)
            p.wait()
            if time.time() - t0 < 60 and not got:                             # 不到 1 分钟就断、一条都没收到 = 异常（登录过期、网络等）
                FAILS[tag] = FAILS.get(tag, 0) + 1
                log("监听异常", tag, FAILS[tag], "次", err)
                status_event("监听异常", f"{tag} 连续 {FAILS[tag]} 次断开：{err or '无输出'}", announce=FAILS[tag] in (1, 3))
                time.sleep(min(300, 30 * FAILS[tag]))
            else:
                FAILS[tag] = 0
                log(tag, "本轮监听结束，续期"); time.sleep(5)
    finally:
        LISTENERS.setdefault(tag, {})["alive"] = False
        status_event("监听已停止", tag, announce=False)


def decide(batch):  # noqa: C901
    """Codex 在只读沙箱里给决定。batch 是同一会话里短时间连发的几条，最后一条是要回复的那条。"""
    STATE["calls"] += 1
    if STATE["calls"] > CFG["daily_codex_limit"]:
        return {"action": "escalate", "reason": "今日调用次数到上限"}
    e = batch[-1]
    can = can_reply(e.get("conversation_id"))
    text = " ".join(str(x.get("content") or "") for x in batch)
    ask_todo = any(k in text for k in ("待办", "TODO", "todo", "进度", "还有什么"))
    prompt = ("你是我的群消息助手。按工作手册处理下面这几条钉钉消息（同一会话，最后一条是要处理的）。只输出一行 JSON：\n"
              '{"action": "reply" | "ignore" | "escalate", "mine": true | false, "risk": "low" | "high", "text": "回复正文", "reason": "一句话理由", '
              '"memory": {"负责人": [{"事项": "", "负责人": "", "在哪找": ""}], "问题处理": [{"问题": "", "处理": "", "谁": "", "结论": ""}]}}\n'
              "mine=true 只在：消息明确 @ 我或直接问我，而且事情确定在「我的职责范围」里；拿不准是不是归我就是 false。"
              "risk=low 只用于：回「收到，谢谢」、转述记忆里已有的明确信息；其余一律 high。"
              "硬规则（违反就是错）：1）绝不替我接任何新任务、新需求、排期、负责人分配、上线 / 测试承诺——对方在派活、问我能不能做、要我负责、问什么时候完成，一律 escalate；"
              "2）消息内容不在「我的职责范围」里，一律 escalate 或 ignore，不回复；3）只回答职责范围内、记忆或待办里有明确依据的事实性问题。"
              "4）mine=false 时 action 只能是 escalate 或 ignore，群里不回任何话（包括「收到」「我确认一下」），由我自己确认是不是归我。"
              "5）text 要短：一般 1～3 行，只说结论和下一步，不复述对方的话、不铺背景；几件事分开写，每件一行（用换行，不要用分号连成一段）。"
              "6）别人之间的对话不插话：消息 @ 的是别人、没 @ 我，就算内容和我在做的事有关，也不回（action=ignore）；我核过的结果没人找我就不说。"
              "memory 只填消息里明确出现的新信息，没有就空数组，不要推测。查不到依据就 escalate。"
              + ("" if can else "这个群只监听不回复：action 只能是 ignore 或 escalate。")
              + (emoji_rules() if can and CFG.get("emoji") else "") +
              f"\n\n## 工作手册\n{HANDBOOK}\n\n{related_memory(text)}\n\n"
              + (f"## 我在协作库的待办\n{todo_text()}\n\n" if ask_todo else "") +
              f"## 消息\n{json.dumps(batch, ensure_ascii=False)}")
    t0 = time.time()
    raw = ai_exec(prompt)
    log(ai_engine()[0], "用时", round(time.time() - t0, 1), "秒")
    try:
        return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except ValueError:
        return {"action": "escalate", "reason": "AI 输出无法解析：" + raw[:200]}


def emoji_rules():
    """v2.8：不再自动点表情；表情包只作为草稿的附带建议，本人确认发送时才一起发。"""
    lib = stickers()
    if not lib:
        return ""
    return ("\n表情包（可选）：action=reply 时 JSON 里可以再加 \"sticker\"（随草稿建议的表情包，必须一字不差地从这个名单里选："
            + "、".join(lib) + "；不用就留空）。只在 mine=true、气氛轻松时建议；正式通知、问题、派活、有争议的一律留空。")


def remember(e, d):
    m = d.get("memory") or {}
    src = f"{dt.date.today()} {e.get('message_id')}"
    for kind, cols in (("负责人", ["事项", "负责人", "在哪找"]), ("问题处理", ["问题", "处理", "谁", "结论"])):
        rows = [r for r in (m.get(kind) or []) if all(str(r.get(c, "")).strip() for c in cols[:2])]
        if not rows:
            continue
        p = os.path.join(MEMDIR, kind + ".md")
        with LOCK:
            old = open(p, encoding="utf-8").read() if os.path.exists(p) else f"# {kind}\n"
            with open(p, "a", encoding="utf-8") as f:
                for r in rows:
                    if f"| {r.get(cols[0])} | {r.get(cols[1])} |" in old:
                        continue
                    f.write("| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + f" | {src} |\n")
        log("记忆追加", kind, len(rows), "条")


def tidy(text):
    """钉钉里单个换行不换行，整段会连成一坨（11-18 梦无矶截图指出）：每行之间统一空一行；AI 偶尔把换行写成字面 \\n，也一并还原。"""
    text = str(text or "").replace("\\n", "\n")
    return "\n\n".join(x.strip() for x in text.splitlines() if x.strip())


class SendFailed(RuntimeError):
    """钉钉 CLI 以本人身份发消息失败（已经用机器人通知过本人）。"""


SEND_FAIL = {"t": 0, "n": 0}


def send_failed(e, text, err, no=""):
    """dws 出故障 / 版本不兼容 / 服务端报错时消息发不出去：用提醒群机器人同步通知本人，30 分钟内只提醒一次（v2.7，11-18 全公司 dws 发消息报「请求参数不能为空」）。"""
    SEND_FAIL["n"] += 1
    log("钉钉消息没发出去", e.get("conversation_id"), err[:200])
    if time.time() - SEND_FAIL["t"] < 1800:
        return
    SEND_FAIL["t"] = time.time()
    group = {**CFG["groups"], **CFG["readonly_groups"]}.get(e.get("conversation_id"), e.get("conversation_id"))
    notify("⚠️ 钉钉消息没发出去" + (f"（{no}）" if no else ""), f"群：{group}\n原消息：{e.get('sender')}：{str(e.get('content'))[:100]}\n要发的内容：{text[:500]}\n错误：{err[:200]}\n"
           "可能是钉钉 CLI（dws）故障或版本太旧：在电脑上运行 dws doctor 检查，dws upgrade -y 升级；如果同事也都发不出去，就是钉钉那边的问题，等恢复。"
           + (f"要紧的先手动发；内容已存成草稿，恢复后在这里回「{no} 可以发送」重发。" if no else "要紧的先手动发。") + "30 分钟内再失败不重复提醒（发「待回复」能看到全部没发出去的）。")


def reply(e, text, keep_draft=True):
    text = tidy(text)
    OUT[re.sub(r"\s+", "", text)] = time.time()
    r = run([DWS, "chat", "+messages-reply", "--conversation-id", e["conversation_id"], "--message-id", e["message_id"],
             "--text", text, "--uuid", f"qa-agent-{time.time_ns()}", "--yes", "--format", "json"], timeout=60)
    out = r.stdout or ""
    if r.returncode != 0 or not re.search(r'"(success|ok)":\s*true', out):
        err = re.search(r'"message":\s*"([^"]*)', out + (r.stderr or ""))
        err = err.group(1) if err else (out or r.stderr or "")[:200]
        no = ""
        if keep_draft:                                                   # 发不出去的回复存成草稿，恢复后一句话重发
            name = save_draft(e, text); no = open_add(e, "draft", "发送失败待重发：" + text[:20])
            dd = json.load(open(os.path.join(HOME, "drafts", name), encoding="utf-8")); dd["todo"] = no
            json.dump(dd, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        send_failed(e, text, err, no)
        status_event("发送失败", f"{no}：{err}；草稿保留，尚未发出", event=e)
        raise SendFailed("回复失败：" + err)
    status_event("已发送", "钉钉返回发送成功：" + text, event=e)


def save_draft(e, text, sticker="", reason=""):
    name = dt.datetime.now().strftime("%m%d-%H%M%S-") + re.sub(r"[^A-Za-z0-9]", "", e["message_id"])[:12] + ".json"
    json.dump({"event": e, "draft": text, "sticker": sticker, "reason": reason}, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return name


def handle(batch):
    """v2.8：任何回复都先写草稿交本人确认，不自动发出任何消息（包括表情）。"""
    e = batch[-1]
    d = decide(batch)
    remember(e, d)
    log("决定", e.get("sender"), d.get("action"), d.get("risk"), d.get("reason"), d.get("emoji") or "", d.get("sticker") or "")
    ats = re.findall(r"@([^\s@]+)", str(e.get("content") or ""))
    if ats and CFG["my_name"] not in ats and "所有人" not in ats:              # @ 的是别人：不插话（v2.6，11-18 梦无矶回了 项目助手 @ 另一位同事 的消息）
        log("别人之间的对话，不回", e.get("sender"), ats[:3]); return "别人之间的对话，不回复、不生成草稿"
    if d.get("action") == "ignore":
        return "不回复：" + (d.get("reason") or "按职责和群规则跳过")
    brief = f"{e.get('sender')}：{str(e.get('content'))[:200]}"
    if d.get("mine") is not True and d.get("action") == "reply":
        d["action"] = "escalate"                                           # 不确定归我就不替我回（v2.5.1）
    if d.get("action") != "reply" or not can_reply(e.get("conversation_id")):
        no = open_add(e, "escalate", d.get("reason") or "")
        x = _open_load(); x[no]["reason"] = d.get("reason") or ""; _open_save(x)
        if d.get("mine") is True:
            notify(f"🔔 {no} 需要你处理", f"{brief}\n原因：{d.get('reason')}\n想先问清楚：回「{no} 问：……」。你在原会话回复后，这里会自动补一条「已处理」。")
        else:
            notify(f"❓ {no} 是不是归你？", f"{brief}\n原因：{d.get('reason')}\n群里没回任何话。归你就在原会话自己回；不归你在这里回「{no} 不归我」；拿不准回「{no} 问：……」。")
        return f"{no} 等待本人处理，原群未回复；原因：" + (d.get("reason") or "需要本人判断")
    sticker = d.get("sticker") if CFG.get("emoji") and d.get("sticker") in stickers() else ""
    name = save_draft(e, d.get("text", ""), sticker=sticker, reason=d.get("reason") or "")
    no = open_add(e, "draft", "草稿：" + d.get("text", "")[:20])
    dd = json.load(open(os.path.join(HOME, "drafts", name), encoding="utf-8")); dd["todo"] = no
    json.dump(dd, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    notify(f"📝 {no} 草稿待你确认", f"{brief}\n草稿：{d.get('text', '')[:200]}" + (f"\n配表情包：{sticker}" if sticker else "") + f"\n依据：{(d.get('reason') or '')[:120]}"
           f"\n回：「{no} 可以发送」/「{no} 不发」/「{no} 改成：新内容」/「{no} 问：……」")
    return f"{no} 草稿待确认，尚未发送；依据：{d.get('reason') or 'AI 未提供依据'}；草稿：{d.get('text', '')}"


ACTIVE = {"n": 0}
READY = queue.Queue()          # 攒好的批次（同一会话 merge_seconds 秒内的消息）


def batcher():
    """分拣：按会话攒批，第一条进来后等 merge_seconds 秒，把这段时间同一会话的消息合成一批放进 READY。"""
    pending = {}               # conversation_id -> [首条时间, [消息…]]
    while in_window():
        try:
            e = Q.get(timeout=1)
            pending.setdefault(e.get("conversation_id"), [time.time(), []])[1].append(e)
        except queue.Empty:
            pass
        now = time.time()
        for cid in [c for c, (t, _) in pending.items() if now - t >= CFG["merge_seconds"]]:
            READY.put(pending.pop(cid)[1])


def worker(temp=False):
    """处理通道：从 READY 取一批，一次判断。temp=True 是积压时临时开的子 Agent，没活了就退出。"""
    with LOCK:
        ACTIVE["n"] += 1
    try:
        while in_window():
            try:
                batch = READY.get(timeout=5 if temp else 30)
            except queue.Empty:
                if temp:
                    return
                continue
            with LOCK, open(os.path.join(HOME, "inbox.jsonl"), "a", encoding="utf-8") as f:
                for x in batch:
                    f.write(json.dumps({**x, "_t": int(time.time())}, ensure_ascii=False) + "\n")   # _t：保留期清理用
            status_event("开始处理", f"合并同一会话 {len(batch)} 条消息，正在核对职责、记忆和判断依据", announce=True, event=batch[-1])
            try:
                result = handle(batch)
                status_event("处理完成", result or "本批处理结束，具体发送/待办状态见记录", announce=True, event=batch[-1])
            except SendFailed:
                status_event("等待重发", "消息已转为草稿，等待发送恢复或本人确认，尚未发出", announce=True, event=batch[-1])
                pass                                                       # 发不出去已用机器人通知本人，回复存成了草稿
            except Exception as ex:
                e = batch[-1]
                log("处理失败", repr(ex)); status_event("处理失败", repr(ex)[:300], announce=True, event=e)
    finally:
        with LOCK:
            ACTIVE["n"] -= 1


def supervisor():
    """一次收到太多任务时开子 Agent：待处理批次超过 burst_threshold，就临时加处理通道，最多 max_workers 个。"""
    while in_window():
        backlog = READY.qsize()
        with LOCK:
            n = ACTIVE["n"]
        if backlog > CFG["burst_threshold"] and n < CFG["max_workers"]:
            add = max(1, min(CFG["max_workers"] - n, backlog // max(1, CFG["burst_threshold"])))
            for _ in range(add):
                threading.Thread(target=worker, args=(True,), daemon=True).start()
            log("积压", backlog, "批，开子 Agent", add, "个，当前共", n + add, "个")
        time.sleep(5)


def remind_due(now=None):
    """超过 remind_after_minutes（默认 120 分钟，0 = 不再提醒）还没处理的事，在提醒群合并再提醒一次；之后每隔同样时间再提醒（v2.8，梦无矶 11-18）。"""
    mins = int(CFG.get("remind_after_minutes") or 0)
    if mins <= 0:
        return []
    now = now or time.time(); due = []
    d = _open_load()                                                       # _open_save 自己会加锁，这里不能再套 LOCK（会死锁）
    for no, x in d.items():
        last = x.get("reminded") or x.get("ts")
        if last and now - last >= mins * 60:
            due.append((no, x)); x["reminded"] = now
    if due:
        _open_save(d)
    if due:
        hrs = f"{mins // 60} 小时" if mins % 60 == 0 else f"{mins} 分钟"
        rows = [f"{no} {x['who']}：{x['what'][:40]}（{x['at']}）" for no, x in due]
        notify(f"⏰ {len(due)} 件超过 {hrs}还没处理", "\n".join(rows) + f"\n处理：回「#编号 可以发送 / 不发 / 问：…」，或在原会话自己回。改提醒间隔：发「提醒间隔 3小时」，关掉发「提醒间隔 关」。")
    return due


def reminder_loop():
    while in_window():
        try:
            remind_due()
        except Exception as ex:
            log("超时提醒失败", repr(ex))
        time.sleep(300)


def daily_summary():
    """21:00 退出前写当天总结（结构化），第二天上班由 morning_report() 发到本人私聊。"""
    today = dt.date.today().isoformat()
    p = os.path.join(HOME, "logs", today + ".log")
    lines = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []
    cnt = lambda k: sum(1 for l in lines if k in l)
    acts = [l.split("决定 ", 1)[1] for l in lines if "决定 " in l]
    body = [f"- 处理相关消息 {len(acts)} 批：写草稿 {sum(1 for a in acts if ' reply ' in a)}（都由你确认后才发），"
            f"交给我 {sum(1 for a in acts if ' escalate ' in a)}，忽略 {sum(1 for a in acts if ' ignore ' in a)}",
            f"- 新记的负责人 / 问题处理：{cnt('记忆追加')} 次",
            f"- 异常：处理失败 {cnt('处理失败')} 次，监听异常 {cnt('监听异常')} 次",
            f"- 还没确认的草稿：{len(glob.glob(os.path.join(HOME, 'drafts', '*.json')))} 条"]
    body += ["- 交给我的事："] + [f"  - {a[:120]}" for a in acts if " escalate " in a][-10:]
    with open(os.path.join(MEMDIR, "每日总结.md"), "a", encoding="utf-8") as f:
        f.write(f"\n## {today}\n" + "\n".join(body) + "\n")


def morning_report():
    """每天第一次启动（≥ 09:00）：把前一天的每日总结发到本人的提醒群（机器人发，有推送、有历史）。"""
    mark = os.path.join(HOME, "logs", f"morning-{dt.date.today()}.sent")
    if os.path.exists(mark):
        return
    open(mark, "w").close()
    p = os.path.join(MEMDIR, "每日总结.md")
    text = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    secs = [(m.group(1), m.start()) for m in re.finditer(r"^## (\d{4}-\d{2}-\d{2})", text, re.M)]
    prev = [x for x in secs if x[0] < dt.date.today().isoformat()]
    if prev:
        day, start = max(prev)
        nxt = [st for d, st in secs if st > start]
        body = text[start: min(nxt) if nxt else len(text)].split("\n", 1)[1].strip()
    else:
        day, body = "无", "（还没有前一天的总结）"
    msg = f"【群消息助手每日汇报｜{dt.date.today():%m-%d}】\n前一天（{day}）：\n{body}\n今天：09:00–21:00 监听，所有回复都先写草稿，你确认后才发。"
    op = _open_load()
    if op:
        msg += f"\n还没处理完 {len(op)} 件：" + "；".join(f"{no} {x['who']}：{x['what'][:20]}" for no, x in list(op.items())[:10])
    if notify(f"☀️ 每日汇报 {dt.date.today():%m-%d}", msg):
        log("每日汇报已发到提醒群")


def review():
    files = sorted(glob.glob(os.path.join(HOME, "drafts", "*.json")))
    if not files:
        print("没有待确认的草稿。"); return
    items = [json.load(open(f, encoding="utf-8")) | {"_f": f} for f in files]
    for i, d in enumerate(items, 1):
        e = d["event"]
        print(f"\n[{i}] {e.get('sender')}：{str(e.get('content'))[:120]}\n    草稿：{d['draft']}")
    ans = input("\n回编号发送（如 1 3）；a = 全部发送；d + 编号删除（如 d2）；直接回车退出：").strip().lower()
    if not ans:
        return
    if ans.startswith("d"):
        for n in ans[1:].split():
            d = items[int(n) - 1]
            os.remove(d["_f"]); open_close(d.get("todo", ""), "草稿已删除"); print("已删除", n)
        return
    picks = range(1, len(items) + 1) if ans == "a" else [int(n) for n in ans.split()]
    for n in picks:
        d = items[n - 1]
        reply(d["event"], d["draft"]); audit(d.get("todo", ""), d["event"], d["draft"], "命令行 review 确认", reason=d.get("reason", "")); os.remove(d["_f"]); open_close(d.get("todo", ""), "草稿已发送"); print("已发送", n)


def status():
    today = dt.date.today().isoformat()
    p = os.path.join(HOME, "logs", today + ".log")
    lines = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []
    acts = [l for l in lines if "决定 " in l]
    print(f"今天（{today}）：处理 {len(acts)} 批，你确认后发出 {sum(1 for l in (open(AUDIT, encoding='utf-8') if os.path.exists(AUDIT) else []) if today in l)} 条，"
          f"交给你 {sum(' escalate ' in l for l in acts)} 件，忽略 {sum(' ignore ' in l for l in acts)} 批，失败 {sum('处理失败' in l for l in lines)} 次")
    op = _open_load()
    print(f"还没处理完：{len(op)} 件（提醒群里也有）")
    for no, x in op.items():
        print(f"  {no} {x['at']} {x['who']}：{x['what']}｜{x['why']}")
    print("最近 5 条记录：")
    for l in acts[-5:]:
        print(" ", l[:150])


def _ver(v):
    m = re.search(r"v?(\d+(?:\.\d+)*)", str(v or ""))
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def self_update_check():
    """每天第一次启动时查一次助手有没有新版本（v2.7）：读 update_url（内网网页的 version.json，或开源仓库的 agent.py），比本机 VERSION 新就在提醒群说一声；同一个新版本只提醒一次。"""
    url = CFG.get("update_url")
    if not url:
        return
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "group-assistant"}), timeout=20, context=SSLCTX) as r:
            text = r.read(200000).decode("utf-8", "replace")
    except Exception as ex:
        log("新版本检查失败", repr(ex)[:120]); return
    m = re.search(r'(?i)"?version"?\s*[:=]\s*"(v[\d.]+)', text)
    if not m or _ver(m.group(1)) <= _ver(VERSION):
        log("新版本检查", "已是最新" if m else "没读到版本号"); return
    mark = os.path.join(HOME, "logs", f"update-told-{m.group(1)}")
    if os.path.exists(mark):
        return
    open(mark, "w").close()
    notify(f"⬆️ 群消息助手有新版本 {m.group(1)}", f"你现在是 {VERSION.split()[0]}。升级：下载最新部署文档（{CFG.get('update_page') or url}），拖进你的 AI 助手，发「升级到 {m.group(1)}」。升级不会覆盖你已有的规则。")


def cleanup_old():
    """保留期（v2.7，config keep_days，默认 30 天，0 = 不清）：只清原始记录——收到的消息原文 inbox.jsonl、建记忆导出的群历史 history/、旧日志；
    提炼好的记忆（memory/）和没处理完的草稿不动。"""
    days = int(CFG.get("keep_days") or 0)
    if days <= 0:
        return 0
    cut = time.time() - days * 86400; n = 0
    inbox = os.path.join(HOME, "inbox.jsonl")
    if os.path.exists(inbox):
        with LOCK:
            def _t(line):
                try:
                    return json.loads(line).get("_t") or 0
                except ValueError:
                    return 0
            keep = [l for l in open(inbox, encoding="utf-8") if _t(l) >= cut]
            n += sum(1 for _ in open(inbox, encoding="utf-8")) - len(keep)
            open(inbox, "w", encoding="utf-8").writelines(keep)
    for f in glob.glob(os.path.join(HOME, "history", "*")) + glob.glob(os.path.join(HOME, "logs", "*")):
        if os.path.isfile(f) and os.path.getmtime(f) < cut and not f.endswith(dt.date.today().isoformat() + ".log"):
            os.remove(f); n += 1
    log("保留期清理", days, "天，清掉", n, "条 / 个")
    return n


def purge_now():
    """「清理记录」：立刻清掉全部原始记录（消息原文、群历史导出、今天以前的日志）；提炼好的记忆和草稿不动。"""
    n = 0
    inbox = os.path.join(HOME, "inbox.jsonl")
    if os.path.exists(inbox):
        n += sum(1 for _ in open(inbox, encoding="utf-8")); open(inbox, "w").close()
    for f in glob.glob(os.path.join(HOME, "history", "*")) + [x for x in glob.glob(os.path.join(HOME, "logs", "*.log")) if not x.endswith(dt.date.today().isoformat() + ".log")]:
        if os.path.isfile(f):
            os.remove(f); n += 1
    return n


def dws_version_check():
    """每天第一次启动时查一次钉钉 CLI 有没有新版本，有就在提醒群说一声（v2.7：11-18 钉钉发消息故障，旧版 CLI 和服务端对不上时症状一样，早知道早升级）。"""
    mark = os.path.join(HOME, "logs", f"dws-version-{dt.date.today()}.checked")
    if os.path.exists(mark):
        return
    open(mark, "w").close()
    up = run([DWS, "upgrade", "--check"], timeout=90)
    out = (up.stdout or "") + (up.stderr or "")
    if re.search(r"新版本可用|→", out) and "已是最新" not in out:
        line = next((x.strip() for x in out.splitlines() if "→" in x), "")
        notify("⬆️ 钉钉 CLI 有新版本", f"{line}\n消息发不出去、监听异常时先升级：在电脑上运行 dws upgrade -y，然后重启助手。没问题可以先不升。")
    log("钉钉 CLI 版本检查", "有新版本" if "→" in out else "已是最新或查不到")


def check():
    print("版本", VERSION)
    ai_name, ai_args, _ = ai_engine()
    pong = _ai_once(ai_name, ai_args, _, "只回复两个字：正常", 120) if ai_args else ""   # 只测主 AI，不走备用
    print(("✅ " if pong.strip() else "❌ ") + f"判断用的 AI：{ai_name}" + ("" if pong.strip() else "（命令行调用失败：确认你平时用的这个 AI 工具在终端里能用；用的是别的工具就在 config.json 改 ai）"))
    for name, args in (("dws 登录", [DWS, "auth", "status"]), ("git", [GIT, "--version"]), ("node", [NODE, "--version"])):
        r = run(args, timeout=60)
        ok = r.returncode == 0 and ('"authenticated": true' in r.stdout if name == "dws 登录" else True)
        print(("✅ " if ok else "❌ ") + name)
    up = run([DWS, "upgrade", "--check"], timeout=60)
    if re.search(r"新版本可用|→", (up.stdout or "") + (up.stderr or "")) and "已是最新" not in (up.stdout or ""):   # 「已是最新版本」里也有「新版本」三个字
        print("⚠️ 钉钉 CLI 有新版本：消息发不出去时先 dws upgrade -y 升级（" + ((up.stdout or "").strip().splitlines() or [""])[-1][:60] + "）")
    print(("✅ " if notify("助手自检", f"{VERSION} 自检消息，看到这条说明提醒群机器人正常。") else "❌ ") + "提醒群机器人（发了一条自检消息）")
    print(("✅ " if CFG["groups"] or CFG["readonly_groups"] else "❌ ") + f"监听群 {len(CFG['groups'])} 个可回复、{len(CFG['readonly_groups'])} 个只看")
    print(("✅ " if CFG.get("scope_confirmed") and os.path.exists(os.path.join(MEMDIR, "职责范围.md")) else "❌ ") + "职责范围和回复规则已确认（没确认前只写草稿）")
    print("表情", "开" if CFG.get("emoji") else "关", "| 表情包", len(stickers()), "张" + ("" if stickers() else "（未下载：python agent.py stickers）"))
    print("回复方式：一律草稿，本人确认后发（v2.8 无自动回复）", "| 常驻并行", CFG["workers"], "| 积压超过", CFG["burst_threshold"], "条开子 Agent，最多", CFG["max_workers"], "个 | 合并秒数", CFG["merge_seconds"], "| 模型", CFG["codex_model"] or "默认")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "watch":
        if sys.argv[2:] not in ([], ["--once"], ["--auto"]):
            raise SystemExit("用法：python agent.py watch [--once]")
        return watch(once="--once" in sys.argv[2:], auto="--auto" in sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "setup-notify":
        opt = dict(zip(sys.argv[2::2], sys.argv[3::2]))                   # --group 群名/cid  --webhook 地址  --secret SEC…
        setup_notify(group=opt.get("--group", ""), webhook=opt.get("--webhook", ""), secret=opt.get("--secret", "")); return
    if len(sys.argv) >= 2 and sys.argv[1] == "clear":
        n, k = clear_all(); print(f"已清空：{n} 件没处理完的事、{k} 份草稿，都没有发出"); return
    if len(sys.argv) >= 2 and sys.argv[1] == "audit":
        rows = [json.loads(l) for l in open(AUDIT, encoding="utf-8")] if os.path.exists(AUDIT) else []
        for r in rows[-int(sys.argv[2]) if len(sys.argv) > 2 else -20:]:
            print(r["发出时间"], r["群"], "←", r["原消息"]["谁"], "｜发出：", r["发出内容"][:60], "｜确认：", r["确认人"], "｜问过 AI", len(r["确认前问过 AI"]), "次")
        print("共", len(rows), "条，文件", AUDIT); return
    if len(sys.argv) >= 2 and sys.argv[1] == "purge":
        print("已清理原始记录", purge_now(), "条 / 个（记忆和草稿没动）"); return
    if len(sys.argv) >= 2 and sys.argv[1] == "stickers":
        print("表情包已下载", build_stickers(), "张 →", STICKERS); return
    if len(sys.argv) >= 2 and sys.argv[1] in ("review", "check", "status"):
        return {"review": review, "check": check, "status": status}[sys.argv[1]]()
    if len(sys.argv) == 3 and sys.argv[1] == "send":
        d = json.load(open(os.path.join(HOME, "drafts", sys.argv[2]), encoding="utf-8"))
        reply(d["event"], d["draft"]); audit(d.get("todo", ""), d["event"], d["draft"], "命令行 send 确认", reason=d.get("reason", "")); os.remove(os.path.join(HOME, "drafts", sys.argv[2])); print("已发送"); return
    if not in_window():
        log("窗口外，不启动"); return
    open_report_window()
    if CFG.get("notify_group"):
        threading.Thread(target=listen, args=(["--kind", "group", "--chat-id", CFG["notify_group"]], "提醒群"), daemon=True).start()
    for cid, name in {**CFG["groups"], **CFG["readonly_groups"]}.items():
        threading.Thread(target=listen, args=(["--kind", "group", "--chat-id", cid], name), daemon=True).start()
    if CFG.get("listen_dm"):
        threading.Thread(target=listen, args=(["--kind", "all-direct"], "私聊"), daemon=True).start()
    workers = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, int(CFG["workers"])))]
    for w in workers:
        w.start()
    threading.Thread(target=batcher, daemon=True).start()
    threading.Thread(target=supervisor, daemon=True).start()
    log("启动", VERSION, "（无自动回复，草稿确认）")
    status_event("已上岗", status_snapshot(), announce=True)
    try:                                                                   # v3.0 本机操作台：页面上直接处理，和提醒群指令同步
        import console
        if console.start(globals()):
            if CFG.get("open_on_start", True) and not console.lan():   # 上岗 / 部署 / 升级后自动在浏览器打开操作台，不用复制链接（11-19）
                console.popup()
            notify("🖥 打开操作台", f"[点这里打开操作台]({console.url()})\n" + ("内网其他电脑也能打开（链接带密钥，别外传）" if console.lan() else "只能在本机打开；有新的要处理会弹桌面通知") + "，处理后提醒群和页面同步。")
    except Exception as ex:
        log("操作台没开起来", repr(ex)[:200])
    threading.Thread(target=morning_report, daemon=True).start()
    threading.Thread(target=dws_version_check, daemon=True).start()
    threading.Thread(target=reminder_loop, daemon=True).start()
    threading.Thread(target=backfill_loop, daemon=True).start()
    threading.Thread(target=self_update_check, daemon=True).start()
    threading.Thread(target=cleanup_old, daemon=True).start()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    upgrade_ask()
    while in_window():
        time.sleep(30)
    daily_summary()
    status_event("已停止", "值守窗口结束；" + status_snapshot(), announce=True)
    log("到点退出")


if __name__ == "__main__":
    main()
