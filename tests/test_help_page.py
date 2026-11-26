"""使用帮助页（11-25）：指南站生成 help.html 并互相链接；操作台顶栏「❓ 帮助」指向 HELP_URL，打包时跟着站点地址改。"""
import importlib.util, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_site_builds_help_page_with_defaults_from_agent(tmp_path):
    out = tmp_path / "site"
    env = {**os.environ, "SITE_DIR": str(out)}
    subprocess.run([sys.executable, "-I", str(ROOT / "site" / "build_site.py")], env=env, check=True, capture_output=True)
    page = (out / "help.html").read_text(encoding="utf-8")
    assert not re.search(r"\{\{[A-Z_0-9]+\}\}", page)                         # 占位符全部替换
    agent = (ROOT / "agent.py").read_text(encoding="utf-8")
    mins = int(re.search(r'"remind_after_minutes": (\d+)', agent).group(1))
    assert (f"{mins // 60} 小时" if mins % 60 == 0 else f"{mins} 分钟") in page   # 超时时长取程序默认值
    for section in ('id="what"', 'id="console"', 'id="terms"', 'id="commands"', 'id="cards"', 'id="faq"'):
        assert section in page
    assert (out / "assets" / "help.css").exists() and re.search(r"assets/help\.css\?v=[0-9a-f]{8}", page)
    assert 'href="help.html"' in (out / "index.html").read_text(encoding="utf-8")
    assert 'href="help.html"' in (out / "view.html").read_text(encoding="utf-8")


def test_help_commands_are_real_commands():
    """帮助页列出的提醒群指令必须是程序真的认的写法（防止文档和代码对不上）。"""
    page = (ROOT / "site" / "help.html").read_text(encoding="utf-8")
    shown = set(re.findall(r'<code class="cp">([^<]+)</code>', page))
    assert {"#编号 可以发送", "#编号 不发", "#编号 改成：新内容", "#编号 暂存：内容", "#编号 问：依据是什么？",
            "#编号 不归我", "#编号 已处理", "全部发送", "待回复", "清空", "提醒间隔 3小时", "群列表", "升级"} <= shown
    agent = (ROOT / "agent.py").read_text(encoding="utf-8")
    for token in ("可以(?:发送|发)?", "不发|删除|作废|算了", "改成", "暂存", "(?:问|请问|问一下)", "不归我", "手动已处理|已处理|处理了|处理完了",
                  "全部(可以)?发(送)?", "(一键)?清空(待回复)?", "提醒间隔", "群列表", '"升级"', "清理记录", "弹出"):
        assert token in agent or token in (ROOT / "console.py").read_text(encoding="utf-8"), token


def test_console_help_button_uses_help_url_and_follows_site_address(tmp_path):
    spec = importlib.util.spec_from_file_location("console_help", ROOT / "console.py")
    console = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(console)
    assert console.HELP_URL == "https://lvan826199.github.io/dingtalk-group-assistant//help.html"
    assert f'href="{console.HELP_URL}"' in console.PAGE and "__HELP_URL__" not in console.PAGE
    spec = importlib.util.spec_from_file_location("pkg_help", ROOT / "tools" / "build_package.py")
    pkg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pkg)
    _, files = pkg.contents(update_base_url="http://10.0.0.5:9000")
    assert b'HELP_URL = "http://10.0.0.5:9000/help.html"' in files["console.py"]   # 其他部署的打包会换成它们的站点地址
