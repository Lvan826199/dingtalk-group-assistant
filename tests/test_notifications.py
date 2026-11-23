"""机器人和操作台双通道：真实 HTTP 桥接、离线补记、去重与业务状态隔离。"""
import json
from pathlib import Path
import urllib.error
import urllib.request

import pytest
from test_console import _boot, _get
from test_workflow import real_notify


def payload(key='notice-1', delivered=True):
    return {'notification_id': key, 'title': '测试群 · #11111 核查结果',
            'text': '已核实：仍缺测试数据。\n下一步：等待数据补齐。',
            'delivered': delivered, 'source': 'duty', 'time': '2026-11-23T11:00:00'}


def test_notification_bridge_visible_without_closing_business_task(make_agent):
    a, c, _, calls, n1, n2 = _boot(make_agent)
    before = a._open_load()
    assert c.mirror_notification(payload()) is True
    assert c.mirror_notification(payload()) is True
    state = json.loads(_get(c, '/api/state').read())
    assert len(state['notifications']) == 1
    row = state['notifications'][0]
    assert row['text'] == payload()['text'] and row['delivered'] is True
    assert row['related_nos'] == ['#11111']
    assert a._open_load() == before and len(state['send']) == len(state['judge']) == 1
    assert not calls
    page = _get(c, '/').read().decode()
    assert '机器人通知' in page and '机器人未送达' in page


def test_offline_outbox_imports_once_without_resending(make_agent):
    a, c, _, calls, *_ = _boot(make_agent)
    root = Path.home() / '.qa-agent'
    config = json.loads((root / 'config.json').read_text(encoding="utf-8"))
    config['console_port'] = 0
    (root / 'config.json').write_text(json.dumps(config), encoding="utf-8")
    # 缺少授权文件模拟操作台不可用，不尝试对外联网。
    (root / 'console_token').unlink()
    assert c.mirror_notification(payload(delivered=False)) is False
    assert len(list((root / 'notification-outbox').glob('*.json'))) == 1
    a.import_notification_outbox()
    a.import_notification_outbox()
    assert not list((root / 'notification-outbox').glob('*.json'))
    assert a.notification_snapshot()[0]['delivered'] is False
    assert len(a.notification_snapshot()) == 1 and not calls
    # 重启后重放相同 ID 仍然去重。
    a.NOTIFICATION_IDS = None
    assert a.record_notification(payload(delivered=False)) is False


def test_notification_api_rejects_missing_key_remote_and_invalid_body(make_agent, monkeypatch):
    a, c, *_ = _boot(make_agent)
    base = c.url().split('?')[0].rstrip('/') + '/api/notifications'
    def post(value, authenticated=True):
        req = urllib.request.Request(base, json.dumps(value).encode(),
                                     {'Content-Type': 'application/json', 'X-Key': c.TOKEN if authenticated else ''})
        return urllib.request.urlopen(req, timeout=5)
    with pytest.raises(urllib.error.HTTPError) as err:
        post(payload(), False)
    assert err.value.code == 403
    for invalid in ([], {}, {**payload(), 'delivered': 'true'}, {**payload(), 'event': []} | {'event': ['bad']}):
        with pytest.raises(urllib.error.HTTPError) as err:
            post(invalid)
        assert err.value.code == 400
    monkeypatch.setattr(c.H, '_local', lambda self: False)
    with pytest.raises(urllib.error.HTTPError) as err:
        post(payload())
    assert err.value.code == 403
    assert not a.notification_snapshot()


def test_failed_builtin_robot_send_is_visible(make_agent):
    a, _, _ = make_agent()
    real_notify(a)
    assert a.notify('测试通知', '机器人未配置，保留通知。') is False
    row = a.notification_snapshot()[0]
    assert row['delivered'] is False and row['title'] == '测试通知'
