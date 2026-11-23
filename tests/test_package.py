"""安装包及升级验证：隔离个人目录，不使用真实账号和服务。"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


packages=load('package_builder_tests',ROOT/'tools/build_package.py')
runtime=load('package_runtime_tests',ROOT/'package_runtime.py')


@pytest.fixture
def built(tmp_path):
    out=tmp_path/'dist';manifest=packages.build(out)
    return out,manifest


def test_all_packages_have_programs_templates_and_installers(built,tmp_path):
    out,m=built
    assert json.loads((out/'latest.json').read_text(encoding="utf-8"))==m
    for platform in ('windows','macos','linux'):
        archive=out/m[platform]
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==m['sha256'][archive.name]
        extracted=tmp_path/platform
        assert runtime.extract_verified(archive,m['sha256'][archive.name],extracted)['version']==m['version']
        assert all((extracted/n).is_file() for n in runtime.PROGRAMS)
        if platform=='windows':
            assert (extracted/'install.cmd').is_file() and (extracted/'install.ps1').is_file()
        else: assert (extracted/'install.sh').is_file()
        assert '## 通用' in (extracted/'工作手册模板.md').read_text(encoding='utf-8')
        assert '## 按角色' not in (extracted/'工作手册模板.md').read_text(encoding='utf-8')
        assert not (extracted/'config.json').exists()


def test_upgrade_preserves_all_personal_files(built,tmp_path):
    out,m=built;src=tmp_path/'src';root=tmp_path/'install'
    runtime.extract_verified(out/m['windows'],m['sha256'][m['windows']],src)
    saved={}
    for name in ('config.json','memory/角色.md','drafts/one.json','工作手册.md','角色职责库.json','audit/发出留痕.jsonl','logs/状态.log'):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);saved[name]=('个人资料：'+name).encode();p.write_bytes(saved[name])
    (root/'agent.py').write_text('OLD', encoding="utf-8")
    runtime.apply_programs(src,root)
    assert (root/'agent.py').read_bytes()==(ROOT/'agent.py').read_bytes()
    for name,data in saved.items(): assert (root/name).read_bytes()==data
    assert not (root/'install.sh').exists()  # 不用安装器覆盖日常运行文件


def test_first_install_creates_templates_once(built,tmp_path):
    out,m=built;src=tmp_path/'source';root=tmp_path/'app'
    runtime.extract_verified(out/m['windows'],m['sha256'][m['windows']],src)
    runtime.apply_programs(src,root)
    assert (root/'工作手册.md').read_bytes()==(src/'工作手册模板.md').read_bytes()
    (root/'工作手册.md').write_text('本人修改',encoding='utf-8')
    runtime.apply_programs(src,root)
    assert (root/'工作手册.md').read_text(encoding='utf-8')=='本人修改'


def test_bad_sha_rejects_before_extracting(built,tmp_path):
    out,m=built;dest=tmp_path/'unpack'
    with pytest.raises(ValueError,match='SHA-256'):
        runtime.extract_verified(out/m['windows'],'0'*64,dest)
    assert not dest.exists()


def test_archive_cannot_write_outside_program_list(tmp_path):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('../config.json','overwrite')
    with pytest.raises(ValueError,match='清单'):
        runtime.extract_verified(p,hashlib.sha256(p.read_bytes()).hexdigest(),tmp_path/'out')
    assert not (tmp_path/'config.json').exists()


def test_program_replace_failure_rolls_back(built,tmp_path,monkeypatch):
    out,m=built;src=tmp_path/'source';root=tmp_path/'app';root.mkdir()
    runtime.extract_verified(out/m['windows'],m['sha256'][m['windows']],src)
    for n in runtime.PROGRAMS:(root/n).write_text('OLD:'+n, encoding="utf-8")
    real=runtime.atomic_write
    def fail(path,data,*args):
        if Path(path).name=='console.py' and data!=(b'OLD:console.py'):raise OSError('disk full')
        real(path,data,*args)
    monkeypatch.setattr(runtime,'atomic_write',fail)
    with pytest.raises(OSError):runtime.apply_programs(src,root)
    for n in runtime.PROGRAMS:assert (root/n).read_text(encoding="utf-8")=='OLD:'+n


def test_rebuild_only_keeps_latest_package(built,tmp_path):
    out,m=built
    old=out/'群消息助手-v0.1-windows.zip';old.write_bytes(b'old')
    (out/'doc0.md').write_text('guide', encoding="utf-8")
    packages.build(out)
    assert not old.exists() and (out/'doc0.md').read_text(encoding="utf-8")=='guide'


def test_manifest_resolves_legacy_url_without_editing_config(monkeypatch):
    name='assistant.zip';data={'version':'v9.0','windows':name,'macos':name,'linux':name,'sha256':{name:'a'*64}}
    urls=[]
    class Response(io.BytesIO):pass
    monkeypatch.setattr(runtime.urllib.request,'urlopen',lambda u,**kw:urls.append(u) or Response(json.dumps(data).encode()))
    m,url=runtime.read_manifest('http://10.0.0.1:8090/version.json')
    assert urls==['http://10.0.0.1:8090/files/latest.json']
    assert url=='http://10.0.0.1:8090/files/assistant.zip'
    assert m==data


def test_upgrade_is_only_triggered_by_owner_in_notify_group(make_agent,monkeypatch):
    a,_,_=make_agent({'groups':{'cidG':'测试群'}})
    called=[];monkeypatch.setattr(a,'perform_update',lambda:called.append(True))
    import threading
    class Immediate:
        def __init__(self,target,**kw):self.target=target
        def start(self):self.target()
    monkeypatch.setattr(a.threading,'Thread',Immediate)
    a.relevant({'sender':'别人','conversation_id':'cidN','content':'升级','message_id':'other'})
    a.relevant({'sender':'本人','conversation_id':'cidG','content':'升级','message_id':'ownelsewhere'})
    assert not called
    a.relevant({'sender':'本人','conversation_id':'cidN','content':'升级','message_id':'own'})
    assert called==[True]


def test_failed_update_keeps_current_program(make_agent,monkeypatch):
    a,notes,_=make_agent()
    before=Path(a.HOME,'agent.py').read_bytes()
    import package_runtime
    monkeypatch.setattr(package_runtime,'read_manifest',lambda *x:({'version':'v99.0'},'http://10.0.0.1/package.zip'))
    monkeypatch.setattr(package_runtime,'download_stage',lambda *x:(_ for _ in ()).throw(ValueError('SHA-256')))
    a.perform_update()
    assert not a.UPDATE_EXIT.is_set() and Path(a.HOME,'agent.py').read_bytes()==before
    assert any('升级未完成' in title for title,_ in notes)


def test_update_receipt_not_deleted_until_notified(make_agent):
    a,notes,_=make_agent();p=Path(a.HOME,'.update-receipt.json')
    p.write_text(json.dumps({'version':a.VERSION.split()[0]}), encoding="utf-8")
    a.notify=lambda *x:False;a.update_receipt();assert p.exists()
    a.notify=lambda *x:notes.append(x) or True;a.update_receipt()
    assert not p.exists() and notes[-1][0]=='已升级到 '+a.VERSION.split()[0]


def test_installer_rejects_missing_dependencies_without_writing(built,tmp_path,monkeypatch):
    out,m=built;src=tmp_path/'source'
    runtime.extract_verified(out/m['windows'],m['sha256'][m['windows']],src)
    installer=load('installer_test',src/'install.py')
    monkeypatch.setattr(installer.shutil,'which',lambda name:None)
    with pytest.raises(ValueError,match='缺少'):installer.preflight()


def test_install_lock_prevents_two_writers(tmp_path):
    with runtime.install_lock(tmp_path):
        with pytest.raises(ValueError,match='另一个'):
            with runtime.install_lock(tmp_path):pass


def test_upgrade_waits_for_finished_worker_and_preserves_unstarted_batch(make_agent):
    a,_,_=make_agent();batch=[{'sender':'同事','conversation_id':'cidG','message_id':'batch1','content':'@本人 看看'}]
    running=[True]
    a.in_window=lambda:running[0]
    def handle(b):
        assert a.BUSY['n']==1
        running[0]=False
        return 'done'
    a.handle=handle;a.READY.put(batch);a.worker()
    assert a.BUSY['n']==0 and a.ACTIVE['n']==0
    a.UPDATE_EXIT.set();a.READY.put(batch);running[0]=True;a.worker()
    assert a.READY.get_nowait()==batch


@pytest.mark.skipif(os.name=='nt',reason='Windows进程查询由本人实测')
def test_installer_refuses_running_legacy_agent_without_pid(built,tmp_path,monkeypatch):
    from types import SimpleNamespace
    out,m=built;src=tmp_path/'source';app=tmp_path/'app';app.mkdir();(app/'agent.py').write_text('old', encoding="utf-8")
    runtime.extract_verified(out/m['windows'],m['sha256'][m['windows']],src)
    installer=load('installer_running_test',src/'install.py')
    monkeypatch.setattr(installer,'command',lambda args,**kw:SimpleNamespace(returncode=0,stdout='321\n' if args[0]=='pgrep' else ''))
    monkeypatch.setattr(installer.runtime,'alive',lambda pid:True)
    monkeypatch.setattr(installer.time,'sleep',lambda _:None)
    with pytest.raises(ValueError,match='仍在运行'):installer.stop(app)
    assert (app/'agent.py').read_text(encoding="utf-8")=='old'


def test_coordination_path_is_generic_and_preserves_existing(tmp_path):
    coordination_root = runtime.coordination_root
    assert coordination_root(tmp_path, {}) == str(tmp_path / 'project-coordination')
    assert coordination_root(tmp_path, {'coordination_path': str(tmp_path / 'chosen')}) == str(tmp_path / 'chosen')
    legacy = tmp_path / 'legacy-project' / 'registry'
    legacy.mkdir(parents=True)
    (legacy / 'identities.json').write_text('{}', encoding="utf-8")
    assert coordination_root(tmp_path, {}) == str(legacy.parent)
    another = tmp_path / 'another' / 'registry'
    another.mkdir(parents=True)
    (another / 'identities.json').write_text('{}', encoding="utf-8")
    assert coordination_root(tmp_path, {}) == str(tmp_path / 'project-coordination')
