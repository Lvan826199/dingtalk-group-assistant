"""把文档做成内网网页（只提供最新版本下载，旧版升级说明不放，用户 11-18 定）：生成到 ~/qa-agent-site（不放桌面：launchd 后台读不了桌面目录），由 launchd 起 http.server 8090 常驻、开机登录自启。
页面：首页列出文档（在线看 / 下载）+ 版本和更新记录；文档在浏览器里用本地 marked.js 渲染（不依赖外网）。
用法：python3 -I site/build_site.py   （build_docs.py 生成文档后会自动调用）"""
import html, json, os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
OUT = os.path.expanduser(os.environ.get("SITE_DIR", "~/qa-agent-site"))
PREVIEW = os.environ.get("PREVIEW") == "1"
UPDATE_BASE_URL = os.environ.get("UPDATE_BASE_URL", "https://lvan826199.github.io/dingtalk-group-assistant/").rstrip("/")
DOCS = [("分享-可直接部署并运行AI监控钉钉群并自动处理.md", "部署文档（新同事从这里开始）", "下载部署文档，拖给 AI 发「开始」；安装包可选"),
        ("CHANGELOG.md", "更新记录", "每个版本改了什么"),
        ("roles/角色职责库.json", "角色职责库", "没有协作库时选角色用；可以自己增删改"),
        ("agent.py", "agent.py 源码", "助手主程序"),
        ("bootstrap_memory.py", "bootstrap_memory.py 源码", "首次建记忆")]
shutil.rmtree(os.path.join(OUT, "files"), ignore_errors=True)   # 只留最新版本的文件，旧的下载链接一起清掉
os.makedirs(os.path.join(OUT, "files"), exist_ok=True); os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
shutil.copy(os.path.join(HERE, "assets", "marked.min.js"), os.path.join(OUT, "assets"))
for _img in ("console.jpg", "console-panel.jpg"):   # 3.0 操作台截图（演示数据，人名都是虚构的）
    shutil.copy(os.path.join(HERE, "assets", _img), os.path.join(OUT, "assets"))
ver = re.search(r'VERSION = "([^"]+)"', open(os.path.join(REPO, "agent.py"), encoding="utf-8").read()).group(1)
rows = []
for i, (name, title, note) in enumerate(DOCS):
    if name.endswith(".md") and name != "CHANGELOG.md":
        src = os.environ.get("DOC_SOURCE") or os.path.join(REPO, "docs", name)
    else:
        src = os.path.join(REPO, name)
    name = os.path.basename(name)
    dst = f"doc{i}" + os.path.splitext(name)[1]
    target = os.path.join(OUT, "files", dst)
    if PREVIEW and name == "agent.py":
        data = open(src, encoding="utf-8").read().replace("https://lvan826199.github.io/dingtalk-group-assistant/", UPDATE_BASE_URL)
        open(target, "w", encoding="utf-8").write(data)
    else:
        shutil.copy(src, target)
    kb = os.path.getsize(src) // 1024 + 1
    rows.append(f'<li><div><a class="t" href="view.html?f={dst}&n={html.escape(name)}">{html.escape(title)}</a><span class="n">{html.escape(note)}</span></div>'
                f'<a class="dl" href="files/{dst}" download="{html.escape(name)}">下载 · {kb} KB</a></li>')
shutil.copy(os.path.join(HERE, "guide.css"), os.path.join(OUT, "assets"))
cl = open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8").read().replace("</", "<\\/")
cards = []
for i, (name, title, note) in enumerate(DOCS):
    dst = f"doc{i}" + os.path.splitext(name)[1]
    kb = os.path.getsize(os.path.join(OUT, "files", dst)) // 1024 + 1
    cards.append(f'<div class="dl"><b>{html.escape(title)}</b><span>{html.escape(note)} · {kb} KB</span><div class="row">'
                 f'<a href="view.html?f={dst}&n={html.escape(name)}">在线看</a><a href="files/{dst}" download="{html.escape(name)}">下载</a></div></div>')
page = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
if PREVIEW:
    banner = '<div style="background:#b42318;color:#fff;text-align:center;font-weight:800;padding:12px 16px;letter-spacing:.04em">预览版，未发布 · 此页面和安装包只供验收，正式用户仍使用 8090 的 v3.0</div>'
    page = page.replace("<body>", "<body>" + banner, 1)
for k, v in {"{{VER}}": html.escape(ver), "{{VER_SHORT}}": html.escape(ver.split()[0]), "{{DOC0}}": html.escape(DOCS[0][0]),
             "{{PACKAGE_WINDOWS}}": "files/群消息助手-" + ver.split()[0] + "-windows.zip",
             "{{PACKAGE_MACOS}}": "files/群消息助手-" + ver.split()[0] + "-macos.zip",
             "{{PACKAGE_LINUX}}": "files/群消息助手-" + ver.split()[0] + "-linux.tar.gz",
             "{{CHANGELOG}}": cl, "{{DOWNLOADS}}": "".join(cards)}.items():
    page = page.replace(k, v)
import hashlib   # 静态文件按内容取短哈希当 ?v=，内容一变浏览器就重新取（11-19：版本号不变时用户看到的是旧缓存）
def _h(name):
    return hashlib.md5(open(os.path.join(OUT, "assets", name), "rb").read()).hexdigest()[:8]
for _n in ("guide.css", "console.jpg", "console-panel.jpg"):
    page = re.sub(r"assets/" + re.escape(_n) + r"\?v=[^\"']*", f"assets/{_n}?v={_h(_n)}", page)
open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(page)
open(os.path.join(OUT, "view.html"), "w", encoding="utf-8").write(f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>群消息助手 · 文档</title><script>try{{var t=localStorage.getItem('qa-theme');if(t&&t!=='auto')document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<link rel="stylesheet" href="assets/guide.css?v={_h('guide.css')}"><style>#c{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:28px 32px;margin-top:20px;overflow-x:auto}}#c pre{{background:var(--surface-soft);padding:14px;border-radius:8px;overflow-x:auto;font-size:13px}}#c table{{border-collapse:collapse;display:block;overflow-x:auto}}#c td,#c th{{border:1px solid var(--border);padding:6px 10px}}#c h1,#c h2,#c h3{{margin:1.2em 0 .5em}}#c p{{margin:.6em 0}}</style>
<script src="assets/marked.min.js"></script></head><body>
<header class="site-header"><div class="header-inner"><a class="brand" href="./"><span class="logo">群</span>群消息助手</a><nav class="header-nav"><a href="./">← 返回指南</a></nav><span id="mdtools" style="display:none;gap:10px;align-items:center;font-size:13.5px"><button class="link-button" id="cp">⧉ 复制页面</button><a id="raw"></a></span><a class="button ghost" id="dl" download>下载原文件</a></div></header>
<div class="toast" id="toast">已复制</div>
<main class="page"><div id="c">加载中…</div></main>
<script>const q=new URLSearchParams(location.search),f=q.get('f')||'',n=q.get('n')||f;
if(!/^doc\\d+\\.(md|py|json)$/.test(f)){{document.getElementById('c').textContent='文件不存在';}}else{{
document.getElementById('dl').href='files/'+f;document.getElementById('dl').download=n;document.title=n;
fetch('files/'+f).then(r=>r.text()).then(t=>{{const c=document.getElementById('c');
if(f.endsWith('.md')){{const raw=q.get('raw')==='1',tl=document.getElementById('mdtools'),ra=document.getElementById('raw');tl.style.display='inline-flex';
ra.textContent=raw?'以网页格式查看':'以 Markdown 格式查看';const u=new URLSearchParams(location.search);raw?u.delete('raw'):u.set('raw','1');ra.href='view.html?'+u.toString();
document.getElementById('cp').onclick=()=>{{const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();let ok=false;try{{ok=document.execCommand('copy')}}catch(e){{}}a.remove();
if(!ok&&navigator.clipboard){{navigator.clipboard.writeText(t)}}const to=document.getElementById('toast');to.textContent='已复制全文（'+Math.round(t.length/1024)+' KB），粘贴给你的 AI 助手就行';to.classList.add('on');setTimeout(()=>to.classList.remove('on'),1800)}};
if(raw){{const p=document.createElement('pre');p.style.whiteSpace='pre-wrap';p.textContent=t;c.replaceChildren(p);return}}}}
if(f.endsWith('.json')){{let d;try{{d=JSON.parse(t)}}catch(e){{}}if(d&&d['角色']){{const esc=x=>String(x).replace(/[&<>]/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}})[m]);const li=a=>'<ul>'+(a||[]).map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';c.innerHTML='<h1>角色职责库</h1><p>'+esc(d['说明']||'')+'</p><h2>通用规则</h2>'+li(d['通用规则'])+d['角色'].map(r=>'<h2>'+esc(r['名称'])+'</h2><p><b>关注</b></p>'+li(r['关注'])+'<p><b>有依据时可以直接回答</b></p>'+li(r['可以直接回答（有依据时）'])+'<p><b>一律交给本人</b></p>'+li(r['一律交给本人'])+'<p><b>推荐监控的群</b>：'+esc((r['推荐监控的群']||[]).join('、'))+'</p>').join('');}}else{{const p=document.createElement('pre');p.textContent=t;c.replaceChildren(p);}}}}else if(!f.endsWith('.md')){{const p=document.createElement('pre');p.textContent=t;c.replaceChildren(p);}}
else{{c.innerHTML=marked.parse(t.replace(/</g,'&lt;'));}}}});}}</script></body></html>""")
json.dump({"version": ver}, open(os.path.join(OUT, "version.json"), "w"))
print("网页已生成", OUT, ver)

subprocess.run([sys.executable, "-I", os.path.join(REPO, "tools", "build_package.py"), "--output", os.path.join(OUT, "files"),
                "--doc-source", os.environ.get("DOC_SOURCE", ""), "--update-base-url", UPDATE_BASE_URL], check=True)
