"""把本目录的 agent.py / bootstrap_memory.py 嵌进最新部署文档，并做语法检查、同步共享盘。
版本号取 agent.py 里的 VERSION，同时写进部署文档的版本行。用法：python3 -I build_docs.py"""
import json, os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); QA = os.path.join(HERE, "docs")
DOCS = {"分享-可直接部署并运行AI监控钉钉群并自动处理.md": {"agent.py": "### 3.2 agent.py", "bootstrap_memory.py": "### 3.3 bootstrap_memory.py", "roles/角色职责库.json": "### 3.5 角色职责库.json", "console.py": "### 3.6 console.py"}}   # 只维护内网一份部署文档（11-19 用户：不再单独出一位同事的升级说明）
SHARE = os.environ.get("DOCS_SHARE_DIR", "")   # 可选：生成后同步到共享盘的目录
src = {n: open(os.path.join(HERE, n), encoding="utf-8").read() for n in ("agent.py", "bootstrap_memory.py", "roles/角色职责库.json", "console.py")}
for n, code in src.items():
    json.loads(code) if n.endswith(".json") else compile(code, n, "exec")
ver = re.search(r'VERSION = "([^"]+)"', src["agent.py"]).group(1)
for doc, heads in DOCS.items():
    p = os.path.join(QA, doc); s = open(p, encoding="utf-8").read()
    for n, h in heads.items():
        fence = "```json\n" if n.endswith(".json") else "```python\n"
        a = s.index(h); b = s.index(fence, a) + len(fence); c = s.index("```", b)
        s = s[:b] + src[n] + s[c:]
    s = re.sub(r"(版本：|当前版本：)v[0-9][^\s　（]*", r"\g<1>" + ver.split()[0], s, count=1)
    for i, bk in enumerate(re.findall(r"```python\n(.*?)```", s, re.S)):
        compile(bk, f"{doc}#{i}", "exec")
    open(p, "w", encoding="utf-8").write(s)
    if os.path.isdir(SHARE) and doc.startswith("分享-"):                 # 共享盘只放最新的部署文档（用户 11-18：内网只提供最新版本）
        shutil.copy(p, SHARE)
    pass   # 仓库里的文档副本（11-18 起放 GitHub 私有仓库）
    print("已生成", doc, "版本", ver)
subprocess.run([sys.executable, "-I", os.path.join(HERE, "site", "build_site.py")])   # 同步内网网页
