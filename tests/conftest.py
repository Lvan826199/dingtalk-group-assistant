"""测试夹具：在临时目录里放一份 agent.py + 配置，按需加载成一个全新的模块；钉钉 / AI 命令全部替身，不碰真实账号。"""
import importlib.util, json, os, shutil, sys, uuid
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class R:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


@pytest.fixture
def make_agent(tmp_path, monkeypatch):
    """make_agent(cfg) -> (agent 模块, 提醒列表, 命令调用列表)。run / notify 都换成替身；需要真跑命令的测试自己再 monkeypatch。"""
    def _make(cfg=None, fake_run=True):
        home = tmp_path / "home"; app = tmp_path / "app"
        (home / ".qa-agent").mkdir(parents=True, exist_ok=True); app.mkdir(exist_ok=True)
        shutil.copy(os.path.join(ROOT, "agent.py"), app / "agent.py")
        if os.path.exists(os.path.join(ROOT, "console.py")):
            shutil.copy(os.path.join(ROOT, "console.py"), app / "console.py")
        (app / "工作手册.md").write_text("# 手册\n", encoding="utf-8")
        base = {"my_name": "本人", "groups": {}, "readonly_groups": {}, "notify_group": "cidN", "scope_confirmed": True}
        (home / ".qa-agent" / "config.json").write_text(json.dumps({**base, **(cfg or {})}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("HOME", str(home)); monkeypatch.setenv("USERPROFILE", str(home))
        name = "agent_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(name, app / "agent.py")
        a = importlib.util.module_from_spec(spec); sys.modules[name] = a; spec.loader.exec_module(a)
        notes, calls = [], []
        a.notify = lambda t, x: notes.append((t, x)) or True
        if fake_run:
            a.run = lambda args, **k: calls.append(args) or R(0, '{"success": true}')
        return a, notes, calls
    return _make
