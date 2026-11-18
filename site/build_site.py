"""把文档做成内网网页：生成到 ~/qa-agent-site（不放桌面：launchd 后台读不了桌面目录），由 launchd 起 http.server 8090 常驻、开机登录自启。
页面：首页列出文档（在线看 / 下载）+ 版本和更新记录；文档在浏览器里用本地 marked.js 渲染（不依赖外网）。
用法：python3 -I site/build_site.py   （build_docs.py 生成文档后会自动调用）"""
import html, json, os, re, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
OUT = os.path.expanduser(os.environ.get("SITE_DIR", "~/group-assistant-site"))   # 网页输出目录（macOS 不要放桌面 / 文稿）
DOCS = [("分享-可直接部署并运行AI监控钉钉群并自动处理.md", "部署文档（新同事从这里开始）", "拖进 Codex 发「部署」；已装过的发「升级到 最新版」"),
        ("CHANGELOG.md", "更新记录", "每个版本改了什么"),
        ("roles/角色职责库.json", "角色职责库", "没有协作库时选角色用；可以自己增删改"),
        ("agent.py", "agent.py 源码", "助手主程序"),
        ("bootstrap_memory.py", "bootstrap_memory.py 源码", "首次建记忆")]
os.makedirs(os.path.join(OUT, "files"), exist_ok=True); os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
shutil.copy(os.path.join(HERE, "assets", "marked.min.js"), os.path.join(OUT, "assets"))
ver = re.search(r'VERSION = "([^"]+)"', open(os.path.join(REPO, "agent.py"), encoding="utf-8").read()).group(1)
rows = []
for i, (name, title, note) in enumerate(DOCS):
    src = os.path.join(REPO, "docs", name) if name.endswith(".md") and name != "CHANGELOG.md" else os.path.join(REPO, name)
    name = os.path.basename(name)
    dst = f"doc{i}" + os.path.splitext(name)[1]
    shutil.copy(src, os.path.join(OUT, "files", dst))
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
for k, v in {"{{VER}}": html.escape(ver), "{{VER_SHORT}}": html.escape(ver.split()[0]), "{{DOC0}}": html.escape(DOCS[0][0]),
             "{{CHANGELOG}}": cl, "{{DOWNLOADS}}": "".join(cards)}.items():
    page = page.replace(k, v)
open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(page)
open(os.path.join(OUT, "view.html"), "w", encoding="utf-8").write(f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>群消息助手 · 文档</title><script>try{{var t=localStorage.getItem('qa-theme');if(t&&t!=='auto')document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<link rel="stylesheet" href="assets/guide.css"><style>#c{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:28px 32px;margin-top:20px;overflow-x:auto}}#c pre{{background:var(--surface-soft);padding:14px;border-radius:8px;overflow-x:auto;font-size:13px}}#c table{{border-collapse:collapse;display:block;overflow-x:auto}}#c td,#c th{{border:1px solid var(--border);padding:6px 10px}}#c h1,#c h2,#c h3{{margin:1.2em 0 .5em}}#c p{{margin:.6em 0}}</style>
<script src="assets/marked.min.js"></script></head><body>
<header class="site-header"><div class="header-inner"><a class="brand" href="./"><span class="logo">群</span>群消息助手</a><nav class="header-nav"><a href="./">← 返回指南</a></nav><a class="button ghost" id="dl" download>下载原文件</a></div></header>
<main class="page"><div id="c">加载中…</div></main>
<script>const q=new URLSearchParams(location.search),f=q.get('f')||'',n=q.get('n')||f;
if(!/^doc\\d+\\.(md|py|json)$/.test(f)){{document.getElementById('c').textContent='文件不存在';}}else{{
document.getElementById('dl').href='files/'+f;document.getElementById('dl').download=n;document.title=n;
fetch('files/'+f).then(r=>r.text()).then(t=>{{const c=document.getElementById('c');
if(f.endsWith('.json')){{let d;try{{d=JSON.parse(t)}}catch(e){{}}if(d&&d['角色']){{const esc=x=>String(x).replace(/[&<>]/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}})[m]);const li=a=>'<ul>'+(a||[]).map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';c.innerHTML='<h1>角色职责库</h1><p>'+esc(d['说明']||'')+'</p><h2>通用规则</h2>'+li(d['通用规则'])+d['角色'].map(r=>'<h2>'+esc(r['名称'])+'</h2><p><b>关注</b></p>'+li(r['关注'])+'<p><b>有依据时可以直接回答</b></p>'+li(r['可以直接回答（有依据时）'])+'<p><b>一律交给本人</b></p>'+li(r['一律交给本人'])+'<p><b>推荐监控的群</b>：'+esc((r['推荐监控的群']||[]).join('、'))+'</p>').join('');}}else{{const p=document.createElement('pre');p.textContent=t;c.replaceChildren(p);}}}}else if(!f.endsWith('.md')){{const p=document.createElement('pre');p.textContent=t;c.replaceChildren(p);}}
else{{c.innerHTML=marked.parse(t.replace(/</g,'&lt;'));}}}});}}</script></body></html>""")
json.dump({"version": ver}, open(os.path.join(OUT, "version.json"), "w"))
print("网页已生成", OUT, ver)
