"""生成群消息助手部署文档。

默认模式更新正式文档、共享盘和指南站；--docs-only 仅更新仓库文档，
--preview 仅生成隔离预览站。均以仓库中的公共部署文档为底稿。
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); QA = os.path.join(HERE, "docs")
DOCS = {"分享-可直接部署并运行AI监控钉钉群并自动处理.md": {"agent.py": "### 3.2 agent.py", "bootstrap_memory.py": "### 3.3 bootstrap_memory.py", "roles/角色职责库.json": "### 3.5 角色职责库.json", "console.py": "### 3.6 console.py", "package_runtime.py": "### 3.7 package_runtime.py"}}   # 只维护内网一份部署文档（11-19 用户：不再单独出一位同事的升级说明）
SHARE = os.path.expanduser(os.environ.get("DOCS_SHARE_DIR", ""))
PROGRAM_NAMES = ("agent.py", "bootstrap_memory.py", "roles/角色职责库.json", "console.py", "package_runtime.py")


def source_files(preview=False):
    src = {n: open(os.path.join(HERE, n), encoding="utf-8").read() for n in PROGRAM_NAMES}
    if preview:
        # 包内默认升级地址必须指向预览服务；正式源码仍保持 8090。
        src = {n: code.replace("https://lvan826199.github.io/dingtalk-group-assistant/", "http://127.0.0.1:8091") for n, code in src.items()}
    for n, code in src.items():
        json.loads(code) if n.endswith(".json") else compile(code, n, "exec")
    return src


def render_doc(template, target, src, version, heads=None):
    heads = heads or DOCS["分享-可直接部署并运行AI监控钉钉群并自动处理.md"]
    s = open(template, encoding="utf-8").read()
    s = re.sub(r"(?m)^}```[ \t]*$", "}\n```", s)  # 修复旧版 JSON 末尾缺换行的围栏
    for n, h in heads.items():
        fence = "```json\n" if n.endswith(".json") else "```python\n"
        a = s.index(h); b = s.index(fence, a) + len(fence)
        c = re.search(r"^```\s*$", s[b:], re.M).start() + b
        s = s[:b] + src[n].rstrip() + "\n" + s[c:]
    s = re.sub(r"(版本：|当前版本：)v[0-9][^\s　（]*", r"\g<1>" + version.split()[0], s, count=1)
    s = s.replace(
        "> **先下载安装包**：打开指南页，按本机系统下载、解压；Windows 双击 `install.cmd`，macOS / Linux 在解压目录运行 `sh install.sh`。装好后把本文件拖给自己的 AI 助手，发「配置」。",
        "> **直接开始**：把本文件拖给自己的 AI 助手，发「开始」。AI 会按步骤完成配置；如果希望一键安装或方便升级，再从指南页下载对应系统的安装包。",
    )
    s = s.replace(
        "> **已经装过**：首次转到 3.1 先下载安装包并运行安装脚本，以后提醒群收到新版本通知，回「升级」即可。",
        "> **已经装过**：把本文件拖给 AI 助手发「开始」即可继续使用；想用安装包升级时再运行对应系统的安装脚本，之后提醒群回「升级」即可。",
    )
    s = s.replace("## 二、先安装，再配置（AI 助手执行配置，使用者回数字）", "## 二、先配置，安装包可选（AI 助手执行配置，使用者回数字）")
    s = s.replace(
        "① 打开 https://lvan826199.github.io/dingtalk-group-assistant/ ，下载对应系统的最新版安装包并解压。Windows 双击 `install.cmd`；macOS / Linux 在解压目录运行 `sh install.sh`。默认装到 `C:\\qa-agent` / `~/qa-agent`，不需要管理员权限。缺 Python 3.10+、钉钉 CLI、Git、Node 或可用 AI 命令时，按中文提示由本人补装；钉钉未登录时本人执行 `dws auth login`，脚本不代登录。\n\n② 将本文件拖给 AI 助手，发「配置」。AI 只做身份、角色职责、群、提醒机器人与记忆；不再重写几千行程序。安装结束会打开操作台；首次空配置的自检会显示待配置项，这是尚未验收完成，不是“全绿”。配置完成后重启服务并运行 `agent.py check`，逐项确认。",
        "① 将本文件拖给 AI 助手，发「开始」。AI 先按第 1 步检查环境，再确认身份、角色职责、群、提醒机器人与记忆；不需要先找安装目录。\n\n② 如果希望一键安装，再打开指南页下载对应系统的安装包并运行：Windows 双击 `install.cmd`；macOS / Linux 在解压目录运行 `sh install.sh`。默认装到 `C:\\qa-agent` / `~/qa-agent`，不需要管理员权限。安装完成后回到本文件继续配置并运行 `agent.py check`。",
    )
    s = re.sub(r"先确认安装包已经装好，再按第二节「配置流程」[^\n]*规则如下：", "先按第二节从第 1 步开始执行；需要一键安装时再使用安装包，不能运行安装包时使用第三节手动安装，规则如下：", s, count=1)
    for i, bk in enumerate(re.findall(r"^```python\n(.*?)^```\s*$", s, re.S | re.M)):
        compile(bk, f"{os.path.basename(target)}#{i}", "exec")
    open(target, "w", encoding="utf-8").write(s)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="只生成 ~/qa-agent-site-preview，不改正式文档和 8090")
    parser.add_argument("--docs-only", action="store_true", help="只更新仓库 docs，不部署站点、根目录文档或共享盘")
    parser.add_argument("--approved", default="", help="正式上线必填：梦无矶在调试群批准上线的那条消息 ID（scripts/guard.py 核对）")
    args = parser.parse_args()
    if args.preview and args.docs_only:
        parser.error("--preview 与 --docs-only 不能同时使用")
    guard = os.path.join(os.path.dirname(HERE), "scripts", "guard.py")
    if not args.preview and not args.docs_only and os.path.exists(guard):   # 正式更新内网 / 共享盘必须有本人批准（11-23）
        if not args.approved or subprocess.run([sys.executable, "-I", guard, "正式更新内网和共享盘", args.approved]).returncode:
            parser.error("正式上线要先在调试群拿到梦无矶批准，并用 --approved <消息ID> 运行；只想看效果用 --preview")
    src = source_files(preview=args.preview)
    ver = re.search(r'VERSION = "([^"]+)"', src["agent.py"]).group(1)
    if args.preview:
        out = os.path.expanduser("~/qa-agent-site-preview")
        template = os.path.join(HERE, "docs", "分享-可直接部署并运行AI监控钉钉群并自动处理.md")
        with tempfile.TemporaryDirectory(prefix="qa-agent-preview-") as td:
            doc = os.path.join(td, "分享-可直接部署并运行AI监控钉钉群并自动处理.md")
            render_doc(template, doc, src, ver)
            env = {**os.environ, "SITE_DIR": out, "PREVIEW": "1", "DOC_SOURCE": doc,
                   "UPDATE_BASE_URL": "http://127.0.0.1:8091"}
            subprocess.run([sys.executable, "-I", os.path.join(HERE, "site", "build_site.py")], env=env, check=True)
        print("预览已生成", out, ver, "（8091；正式 8090、共享盘和根目录文档未修改）")
        return

    for doc, heads in DOCS.items():
        template = os.path.join(HERE, "docs", doc)
        p = template if args.docs_only else os.path.join(QA, doc)
        render_doc(template, p, src, ver, heads)
        if args.docs_only:
            print("已更新仓库文档", doc, "版本", ver)
            continue
        if SHARE and os.path.isdir(SHARE) and doc.startswith("分享-"):
            shutil.copy(p, SHARE)
        os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
        if os.path.abspath(p) != os.path.abspath(template):
            shutil.copy(p, template)
        print("已生成", doc, "版本", ver)
    if not args.docs_only:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "site", "build_site.py")], check=True)


if __name__ == "__main__":
    main()
