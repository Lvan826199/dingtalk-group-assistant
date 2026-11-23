"""监听设置的保存、真实群选择、时段边界和动态订阅；不使用真实配置或账号。"""
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import urllib.error
import urllib.request

import pytest
from conftest import R


@pytest.mark.parametrize('window,now,expected', [
    (['09:00','21:00'],'08:59',False), (['09:00','21:00'],'09:00',True),
    (['09:00','21:00'],'20:59',True), (['09:00','21:00'],'21:00',False),
    (['21:00','08:00'],'20:59',False), (['21:00','08:00'],'21:00',True),
    (['21:00','08:00'],'00:00',True), (['21:00','08:00'],'07:59',True),
    (['21:00','08:00'],'08:00',False),
])
def test_daily_and_overnight_boundaries(make_agent,window,now,expected):
    a,_,_=make_agent()
    assert a.window_contains(window,now) is expected
    assert a.window_contains(window,now,all_day=True)


@pytest.mark.parametrize('body', [
    {'window':['9:00','21:00']}, {'window':['25:00','21:00']},
    {'window':['09:00','09:00']}, {'window':'09:00'}, {'all_day':'true'},
    {'window':['09:00',None]}, {'group':[]},
    {'group':{'cid':'cidG','rule':'x'*2001}}, {'group':{'cid':'cidG','paused':'false'}},
])
def test_invalid_settings_are_atomic(make_agent,body):
    a,_,_=make_agent({'groups':{'cidG':'已知群'}})
    before=Path(a.CFG_PATH).read_bytes()
    with pytest.raises(ValueError): a.save_monitor_settings(body)
    assert Path(a.CFG_PATH).read_bytes()==before
    assert a.CFG['groups']=={'cidG':'已知群'}


def test_save_preserves_personal_settings_and_default_rules(make_agent):
    a,_,_=make_agent({'roles':['qa'],'custom_personal':{'keep':True},'groups':{'cidG':'已有群'}})
    draft=Path(a.HOME,'drafts','keep.json');draft.write_text('{"draft":"保留草稿"}')
    a.save_monitor_settings({'group':{'cid':'cidNew','name':'伪造名','rule':''}}, {'cid':'cidNew','name':'真实群'})
    s=a.save_monitor_settings({'window':['08:30','23:40'],'all_day':False,'roles':['attacker']})
    cfg=json.loads(Path(a.CFG_PATH).read_text())
    assert cfg['groups']=={'cidG':'已有群','cidNew':'真实群'}
    assert cfg['roles']==['qa'] and cfg['custom_personal']=={'keep':True}
    assert s['window']==['08:30','23:40'] and cfg['group_rules']['cidNew']==''
    assert draft.read_text()=='{"draft":"保留草稿"}'
    assert not any(k in s for k in ('webhook','secret','custom_personal'))
    a.save_monitor_settings({'group':{'cid':'cidNew','rule':'  关注发布  ','readonly':True,'paused':True}})
    assert 'cidNew' not in a.CFG['groups'] and a.CFG['readonly_groups']['cidNew']=='真实群'
    a.save_monitor_settings({'group':{'cid':'cidNew','paused':False}})
    assert a.CFG['group_rules']['cidNew']=='关注发布' and not a.CFG['paused_groups']
    assert a.CFG['readonly_groups']['cidNew']=='真实群'


def test_unknown_group_and_notify_group_rejected(make_agent):
    a,_,_=make_agent()
    with pytest.raises(ValueError,match='搜索'):a.save_monitor_settings({'group':{'cid':'cidForged','name':'假群'}})
    with pytest.raises(ValueError,match='提醒群'):a.save_monitor_settings({'group':{'cid':'cidN'}},{'cid':'cidN','name':'通知群'})


def test_atomic_save_failure_keeps_memory_and_disk(make_agent,monkeypatch):
    a,_,_=make_agent()
    before=Path(a.CFG_PATH).read_bytes()
    import package_runtime
    def fail(*args,**kwargs):raise OSError('disk full')
    monkeypatch.setattr(package_runtime,'atomic_write',fail)
    with pytest.raises(OSError):a.save_monitor_settings({'window':['10:00','22:00']})
    assert a.CFG['window']==['09:00','21:00'] and Path(a.CFG_PATH).read_bytes()==before


def test_group_scope_reaches_real_decision_and_default_keeps_filter(make_agent):
    a,_,calls=make_agent({'groups':{'cidG':'项目群'}})
    e={'sender':'同事','conversation_id':'cidG','message_id':'scope1','content':'新版已经部署'}
    assert not a.relevant(e)
    a.save_monitor_settings({'group':{'cid':'cidG','rule':'关注部署公告'}})
    assert a.relevant(e)
    prompts=[]
    a.ai_exec=lambda prompt,**kwargs:prompts.append(prompt) or '{"action":"ignore","reason":"仅记录"}'
    a.decide([e])
    assert '关注部署公告' in prompts[0] and '不授予发送' in prompts[0]
    a.save_monitor_settings({'group':{'cid':'cidG','paused':True}})
    assert not a.relevant(e)
    assert not calls


def test_listener_changes_do_not_duplicate_or_restart_other_tasks(make_agent,monkeypatch):
    a,_,_=make_agent({'groups':{'cidG':'同名群','cidH':'同名群'}})
    a.in_window=lambda:True
    started=[];stopped=[]
    class FakeThread:
        def __init__(self,**kw):self.args=kw['args'];self.alive=False
        def start(self):self.alive=True;started.append(self.args)
        def is_alive(self):return self.alive
    monkeypatch.setattr(a.threading,'Thread',FakeThread)
    a.stop_listener_process=lambda p:stopped.append(p)
    a.sync_listeners();a.sync_listeners()
    assert len(started)==3 and len(a.LISTENER_SPECS)==3  # 提醒群 + 两个同名群
    gtag=next(t for t,(args,_) in a.LISTENER_SPECS.items() if 'cidG' in args)
    process=object();a.LISTENER_PROCESSES[gtag]=process
    a.save_monitor_settings({'group':{'cid':'cidG','paused':True}})
    a.sync_listeners()
    assert stopped==[process] and len(started)==3
    assert len(a.LISTENER_SPECS)==2 and len(a.CFG['groups'])==2
    a.LISTENER_THREADS[gtag].alive=False;a.LISTENER_PROCESSES.pop(gtag)
    a.sync_listeners()
    a.save_monitor_settings({'group':{'cid':'cidG','paused':False}})
    a.sync_listeners()
    assert len(started)==4
    a.in_window=lambda:False;a.sync_listeners()
    assert not a.LISTENER_SPECS
    assert not a.UPDATE_EXIT.is_set()


def test_outside_window_service_stays_available_for_user_edits(make_agent,monkeypatch):
    a,_,_=make_agent({'console':False})
    a.in_window=lambda:False
    actions=[]
    class FakeThread:
        def __init__(self,**kwargs):pass
        def start(self):pass
        def join(self,timeout=None):pass
    monkeypatch.setattr(a.threading,'Thread',FakeThread)
    monkeypatch.setattr(sys,'argv',['agent.py'])
    monkeypatch.setattr(a.UPDATE_EXIT,'wait',lambda timeout:actions.append('waiting') or True)
    a.open_report_window=lambda:None
    a.main()
    assert actions==['waiting'] and a.SERVICE_RUNNING
    assert not a.LISTENER_SPECS


def boot_console(make_agent):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    a,_,_=make_agent({'groups':{'cidG':'已有群'},'console_port':port})
    sys.path.insert(0,a.HOME)
    console=importlib.import_module('console');importlib.reload(console)
    server=console.start(vars(a))
    return a,console,server


def request(console,path,body=None,key=True):
    url=console.url().split('?')[0].rstrip('/')+path+('&' if '?' in path else '?')+('k='+console.TOKEN if key else '')
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    try:
        response=urllib.request.urlopen(req,timeout=5)
        return response.status,json.loads(response.read())
    except urllib.error.HTTPError as ex:
        raw=ex.read().decode()
        try:body=json.loads(raw)
        except ValueError:body={'msg':raw}
        return ex.code,body


def test_console_search_selection_and_settings_api(make_agent):
    a,c,srv=boot_console(make_agent)
    try:
        assert request(c,'/api/monitor',key=False)[0]==403
        assert request(c,'/api/monitor',{'window':['00:00','23:59']},key=False)[0]==403
        assert request(c,'/api/monitor')[1]['groups'][0]['name']=='已有群'
        a.run=lambda *args,**kwargs:R(0,json.dumps({'chats':[
            {'openConversationId':'cidOne','title':'同名群','memberCount':2},
            {'openConversationId':'cidTwo','title':'同名群','memberCount':3}],
            'complete':False,'hasMore':True,'failures':[]}))
        result=request(c,'/api/monitor/search?q=group')[1]
        assert len(result['matches'])==2 and result['complete'] is False and result['msg']
        # 同名不自动选中；只有明确选择一个真实ID才保存。
        assert len(a.CFG['groups'])==1
        code,body=request(c,'/api/monitor',{'group':{'cid':'cidTwo','name':'假名','rule':'只关注发版'}})
        assert code==200 and body['ok'] and a.CFG['groups']['cidTwo']=='同名群'
        assert 'cidOne' not in a.CFG['groups']
        assert request(c,'/api/monitor',{'group':{'cid':'cidBad','name':'假群'}})[0]==400
        c.GROUP_CANDIDATES['cidOne']['at']=0
        assert request(c,'/api/monitor',{'group':{'cid':'cidOne'}})[0]==400
    finally:srv.shutdown();srv.server_close()


def test_failed_search_is_not_empty_success(make_agent):
    a,c,srv=boot_console(make_agent)
    try:
        a.run=lambda *args,**kwargs:R(1,'not json')
        code,body=request(c,'/api/monitor/search?q=group')
        assert code==400 and body['msg'] and not c.GROUP_CANDIDATES
    finally:srv.shutdown();srv.server_close()
