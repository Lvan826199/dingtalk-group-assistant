"""安装包升级共用逻辑；仅固定程序可替换，个人资料不属于程序包。"""
import argparse
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

PROGRAMS = ('agent.py', 'console.py', 'bootstrap_memory.py', 'package_runtime.py')
TEMPLATES = {'工作手册模板.md': '工作手册.md', 'roles/角色职责库.json': '角色职责库.json'}
ALLOWED = set(PROGRAMS) | set(TEMPLATES) | {'install.py','install.sh','install.ps1','install.cmd','package.json'}


def coordination_root(home, config):
    """通用默认目录；旧安装只有一个协作库时继续使用，不搬动或改写个人配置。"""
    if config.get('coordination_path'):
        return os.path.expanduser(config['coordination_path'])
    root = Path(home)
    default = root / 'project-coordination'
    if default.is_dir():
        return str(default)
    existing = [p for p in root.iterdir() if p.is_dir() and (p / 'registry/identities.json').is_file()]
    return str(existing[0]) if len(existing) == 1 else str(default)


def platform_name():
    return 'windows' if sys.platform == 'win32' else 'macos' if sys.platform == 'darwin' else 'linux'


def atomic_write(path, data, mode=0o644):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd, temp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(data)
        os.chmod(temp,mode);os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


@contextlib.contextmanager
def install_lock(root):
    path=Path(root)/'.install.lock';path.parent.mkdir(parents=True,exist_ok=True)
    f=path.open('a+b');f.seek(0);f.write(b'0');f.flush();f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        f.close();raise ValueError('另一个安装或升级正在进行，请稍后再试。') from None
    try: yield
    finally: f.close()


def validate_source(source):
    source=Path(source)
    meta=json.loads((source/'package.json').read_text(encoding='utf-8'))
    if set(meta.get('programs',[]))!=set(PROGRAMS) or not re.fullmatch(r'v\d+(?:\.\d+)+',meta.get('version','')):
        raise ValueError('安装包程序清单或版本不正确。')
    for name in PROGRAMS:
        compile((source/name).read_text(encoding='utf-8'),name,'exec')
    json.loads((source/'roles/角色职责库.json').read_text(encoding='utf-8'))
    (source/'工作手册模板.md').read_text(encoding='utf-8')
    return meta


def apply_programs(source, target):
    """替换失败时回滚已替换程序；首次模板使用独占创建，不覆盖个人资料。"""
    source=Path(source);target=Path(target);meta=validate_source(source);target.mkdir(parents=True,exist_ok=True)
    old={name:(target/name).read_bytes() if (target/name).exists() else None for name in PROGRAMS}
    changed=[]
    try:
        for name in PROGRAMS:
            atomic_write(target/name,(source/name).read_bytes());changed.append(name)
        atomic_write(target/'工作手册模板.md',(source/'工作手册模板.md').read_bytes())
        for name,dest in TEMPLATES.items():
            try:
                with (target/dest).open('xb') as f: f.write((source/name).read_bytes())
            except FileExistsError: pass
    except Exception:
        for name in reversed(changed):
            if old[name] is None: (target/name).unlink(missing_ok=True)
            else: atomic_write(target/name,old[name])
        raise
    return meta['version']


def read_manifest(url, context=None):
    parts=urllib.parse.urlsplit(url)
    if parts.scheme not in ('http','https') or parts.username or parts.password:
        raise ValueError('升级地址必须是 HTTP(S) 清单地址。')
    # 老配置保留原值；兼容原来的 version.json 和公开版源码检查地址。
    if parts.path.endswith('/version.json'):
        url=urllib.parse.urlunsplit(parts._replace(path=parts.path[:-12]+'files/latest.json'))
    elif parts.netloc=='raw.githubusercontent.com' and parts.path.endswith('/agent.py'):
        url='https://lvan826199.github.io/dingtalk-group-assistant/files/latest.json'
    with urllib.request.urlopen(url,timeout=30,context=context) as r:
        raw=r.read(65537)
    if len(raw)>65536: raise ValueError('升级清单过大。')
    data=json.loads(raw)
    if not re.fullmatch(r'v\d+(?:\.\d+)+',data.get('version','')): raise ValueError('升级清单版本无效。')
    name=data.get(platform_name(),'')
    if not name or '/' in name or '\\' in name or name in ('.','..'):
        raise ValueError('升级清单缺少本系统安装包。')
    digest=data.get('sha256',{}).get(name,'')
    if not re.fullmatch('[0-9a-fA-F]{64}',digest): raise ValueError('升级清单缺少有效 SHA-256。')
    return data, urllib.parse.urljoin(url,urllib.parse.quote(name))


def extract_verified(archive, digest, output):
    """校验在解压前完成；拒绝路径穿越、链接、非预期文件及解压炸弹。"""
    archive=Path(archive);output=Path(output)
    if hashlib.sha256(archive.read_bytes()).hexdigest().lower()!=digest.lower():
        raise ValueError('SHA-256 校验不一致，拒绝升级，旧版未改动。')
    members=[]
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for i in z.infolist():
                if i.is_dir(): continue
                if stat.S_ISLNK(i.external_attr>>16): raise ValueError('安装包包含链接。')
                members.append((i.filename,i.file_size,lambda i=i:z.read(i)))
            _extract_members(members,output)
    else:
        with tarfile.open(archive,'r:gz') as z:
            for i in z.getmembers():
                if i.isdir(): continue
                if not i.isfile(): raise ValueError('安装包包含非普通文件。')
                members.append((i.name,i.size,lambda i=i:z.extractfile(i).read()))
            _extract_members(members,output)
    return validate_source(output)


def _extract_members(members, output):
    names=[n for n,_,_ in members]
    if len(names)!=len(set(names)) or any(n not in ALLOWED for n in names) or sum(s for _,s,_ in members)>20000000:
        raise ValueError('安装包文件清单不正确。')
    output.mkdir(parents=True,exist_ok=True)
    for name,_,read in members:
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(read())


def download_stage(manifest, url, target, context=None):
    root=Path(target)/'logs';root.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.upgrade-',dir=root))
    try:
        archive=stage/'download'
        with urllib.request.urlopen(url,timeout=60,context=context) as r, archive.open('wb') as f:
            size=0
            while True:
                block=r.read(65536)
                if not block: break
                size+=len(block)
                if size>20000000: raise ValueError('安装包过大。')
                f.write(block)
        meta=extract_verified(archive,manifest['sha256'][manifest[platform_name()]],stage/'files')
        if meta['version']!=manifest['version']: raise ValueError('安装包版本与清单不一致。')
        archive.unlink();return stage
    except Exception:
        shutil.rmtree(stage);raise


def alive(pid):
    if os.name=='nt':
        k=ctypes.windll.kernel32;k.OpenProcess.restype=ctypes.c_void_p
        handle=k.OpenProcess(0x100000,False,pid)
        if not handle: return False
        try: return k.WaitForSingleObject(ctypes.c_void_p(handle),0)==258
        finally: k.CloseHandle(ctypes.c_void_p(handle))
    try: os.kill(pid,0);return True
    except ProcessLookupError: return False


def restart(target, python):
    root=Path(target)
    if sys.platform=='darwin' and (Path.home()/'Library/LaunchAgents/com.group-assistant.agent.plist').exists():
        args=['launchctl','kickstart',f'gui/{os.getuid()}/com.group-assistant.agent']
    elif sys.platform.startswith('linux') and (Path.home()/'.config/systemd/user/group-assistant.service').exists():
        args=['systemctl','--user','restart','group-assistant.service']
    elif os.name=='nt':
        query=subprocess.run(['schtasks','/Query','/TN','QA-群消息助手'],capture_output=True)
        args=['schtasks','/Run','/TN','QA-群消息助手'] if query.returncode==0 else None
    else: args=None
    if args:
        p=subprocess.run(args,capture_output=True)
        if p.returncode: raise ValueError('重新启动后台失败，请运行安装脚本恢复自启。')
    else:
        options={'creationflags':0x08000000} if os.name=='nt' else {'start_new_session':True}
        with (root/'logs/后台.log').open('ab') as log:
            subprocess.Popen([python,str(root/'agent.py')],cwd=root,stdout=log,stderr=log,**options)


def finish_upgrade(stage, target, parent, python):
    stage=Path(stage);target=Path(target)
    for _ in range(900):
        if not alive(parent): break
        time.sleep(1)
    else: raise ValueError('旧后台未结束，未替换程序，请稍后重试。')
    with install_lock(target):
        version=apply_programs(stage/'files',target)
        atomic_write(target/'.update-receipt.json',json.dumps({'version':version},ensure_ascii=False).encode())
    restart(target,python)
    shutil.rmtree(stage)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--finish',required=True);p.add_argument('--target',required=True);p.add_argument('--parent',type=int,required=True);p.add_argument('--python',required=True)
    args=p.parse_args()
    try: finish_upgrade(args.finish,args.target,args.parent,args.python)
    except Exception as ex:
        # 不回显 URL / 配置 / 子进程输出，避免泄露个人资料。
        atomic_write(Path(args.target)/'.update-error.json',json.dumps({'message':str(ex) if isinstance(ex,ValueError) else '程序替换或重新启动失败，请重新运行安装脚本。'},ensure_ascii=False).encode())
        try: restart(args.target,args.python)
        except Exception: pass
        raise SystemExit(1)
