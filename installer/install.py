"""三平台安装入口（由 install.sh / install.ps1 调用，不需管理员权限）。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import time
import shutil
import subprocess
import sys

SOURCE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('package_runtime',SOURCE/'package_runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


def command(args, required=True):
    result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if required and result.returncode:
        raise ValueError('系统自启命令执行失败，请在当前用户的终端检查：'+args[0]+'。未申请管理员权限。')
    return result


def preflight():
    if sys.version_info<(3,10): raise ValueError('需要 Python 3.10 或更新版本，请本人安装后重试。')
    extra=[Path.home()/'.local/bin',Path.home()/'.npm-global/bin',Path.home()/'AppData/Roaming/npm',Path('/opt/homebrew/bin'),Path('/usr/local/bin')]
    os.environ['PATH']=os.environ.get('PATH','')+os.pathsep+os.pathsep.join(map(str,extra))
    missing=[name for name in ('dws','git','node') if not shutil.which(name)]
    if not any(shutil.which(name) for name in ('codex','claude','dsh','codebuddy','qodercli')):
        missing.append('AI 命令行（codex / claude / dsh / codebuddy / qodercli 任一个）')
    if missing: raise ValueError('缺少：'+'、'.join(missing)+'。请本人安装后重试；安装包不自动安装依赖。')
    status=command([shutil.which('dws'),'auth','status','--format','json'],required=False)
    try: authenticated=json.loads(status.stdout).get('authenticated') is True
    except ValueError: authenticated=False
    if not authenticated: raise ValueError('钉钉尚未登录，请本人在终端执行 dws auth login，扫码完成后重试。')
    print('环境检查通过：Python、钉钉登录、AI 命令行、Git 和 Node 已就绪。')


def stop(root):
    # 3.0 及更早版本还没有 agent.pid，按安装目录核对真实进程，避免覆盖手动启动的旧版。
    pids = []
    if (root/'agent.py').exists():
        if os.name == 'nt':
            env = {**os.environ, 'QA_INSTALL_AGENT_PATH': str(root/'agent.py').lower()}
            script = "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($env:QA_INSTALL_AGENT_PATH) } | Select-Object -ExpandProperty ProcessId"
            result = subprocess.run(['powershell.exe','-NoProfile','-Command',script],env=env,capture_output=True,text=True)
            if result.returncode: raise ValueError('无法核对旧助手进程，请先停止旧助手后重试。')
        else:
            result = command(['pgrep','-f',re.escape(str(root/'agent.py'))+r'([[:space:]]|$)'],required=False)
            if result.returncode not in (0,1): raise ValueError('无法核对旧助手进程，请先停止旧助手后重试。')
        pids = [int(x) for x in result.stdout.split() if x.isdigit() and int(x) != os.getpid()]
    if os.name == 'nt':
        # Windows 结束计划任务未必触发 Python 的退出钩子，先结束整棵旧进程树。
        for pid in pids: command(['taskkill','/PID',str(pid),'/T','/F'],required=False)
        command(['schtasks','/End','/TN','QA-群消息助手'],required=False)
    elif sys.platform=='darwin':
        command(['launchctl','bootout',f'gui/{os.getuid()}/com.group-assistant.agent'],required=False)
    else:
        command(['systemctl','--user','stop','group-assistant.service'],required=False)
    pidfile=root/'logs/agent.pid'
    if pidfile.exists():
        try: pids.append(int(pidfile.read_text()))
        except ValueError: raise ValueError('后台进程记录损坏，请先确认旧助手已经停止。')
    for _ in range(20):
        if not any(runtime.alive(pid) for pid in set(pids)): return
        time.sleep(.25)
    raise ValueError('旧助手仍在运行，请先停止它，再重新运行安装脚本。')


def services(root):
    app=str(root/'agent.py');python=str(Path(sys.executable).resolve())
    if sys.platform=='darwin':
        path=Path.home()/'Library/LaunchAgents/com.group-assistant.agent.plist'
        data={'Label':'com.group-assistant.agent','ProgramArguments':[python,app], 'WorkingDirectory':str(root),
              'EnvironmentVariables':{'PATH':os.environ['PATH']},'StartCalendarInterval':{'Hour':9,'Minute':0},'RunAtLoad':True,
              'StandardErrorPath':str(root/'logs/launchd.err')}
        runtime.atomic_write(path,plistlib.dumps(data))
    elif sys.platform.startswith('linux'):
        path=Path.home()/'.config/systemd/user'
        def quote(s): return '"'+str(s).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
        runtime.atomic_write(path/'group-assistant.service',('[Unit]\nDescription=群消息助手\n[Service]\nType=simple\nWorkingDirectory='+str(root).replace('%','%%')+'\nExecStart='+quote(python)+' '+quote(app)+'\nEnvironment='+quote('PATH='+os.environ['PATH'])+'\nEnvironment=TZ=Asia/Shanghai\n[Install]\nWantedBy=default.target\n').encode())
        runtime.atomic_write(path/'group-assistant.timer',b'[Unit]\nDescription=Group assistant daily start\n[Timer]\nOnCalendar=*-*-* 09:00:00 Asia/Shanghai\nPersistent=true\n[Install]\nWantedBy=timers.target\n')
    else:
        # Windows 计划任务由 PowerShell 入口生成，使用当前用户的交互会话。
        script=SOURCE/'install.ps1'
        command(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-RegisterOnly','-Target',str(root),'-Python',python])


def start():
    if sys.platform=='darwin':
        command(['launchctl','bootstrap',f'gui/{os.getuid()}',str(Path.home()/'Library/LaunchAgents/com.group-assistant.agent.plist')])
    elif sys.platform.startswith('linux'):
        variables=[key for key in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY') if os.environ.get(key)]
        if variables: command(['systemctl','--user','import-environment',*variables],required=False)
        command(['systemctl','--user','daemon-reload'])
        command(['systemctl','--user','enable','--now','group-assistant.service','group-assistant.timer'])
    else: command(['schtasks','/Run','/TN','QA-群消息助手'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target');parser.add_argument('--no-autostart',action='store_true',help='仅供隔离验收，不注册或操作自启')
    args=parser.parse_args()
    root=Path(args.target or ('C:/qa-agent' if os.name=='nt' else Path.home()/'qa-agent')).expanduser().resolve()
    if any(part.lower() in ('desktop','documents','downloads','桌面','文稿','下载') for part in root.parts):
        raise ValueError('安装目录不能位于桌面、文稿或下载目录，请使用默认安装目录。')
    preflight();runtime.validate_source(SOURCE)
    with runtime.install_lock(root):
        if not args.no_autostart: stop(root)
        version=runtime.apply_programs(SOURCE,root)
        for folder in ('memory','drafts','audit','logs'): (root/folder).mkdir(exist_ok=True)
        config=Path.home()/'.qa-agent/config.json';config.parent.mkdir(parents=True,exist_ok=True)
        try:
            fd=os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump({'my_name':'','groups':{},'readonly_groups':{},'scope_confirmed':False},f,ensure_ascii=False,indent=2)
        except FileExistsError: pass
        if not args.no_autostart: services(root)
    print('程序安装完成：'+version+'。已有配置、记忆、草稿、工作手册、角色库、日志和留痕均保留。')
    print('正在运行自检；首次安装的姓名、职责、群和机器人需交给 AI 配置后才会通过。')
    # 不回显外部命令/配置正文，只显示自检自身的中文摘要。
    result=command([sys.executable,str(root/'agent.py'),'check'],required=False)
    for line in result.stdout.splitlines():
        if line.startswith(('版本','✅','❌','⚠️','回复方式','表情')): print(line)
    if result.returncode: raise ValueError('自检执行失败，请让 AI 助手检查安装目录中的 agent.py check。')
    if not args.no_autostart: start()
    print('下一步：把部署文档拖给 AI 助手，发送「配置」，确认身份、角色职责、群和提醒机器人。')
    if args.no_autostart: print('隔离验收模式：没有注册或启动自启服务。')
    else: print('自启已设置，后台已启动；操作台将在本机浏览器打开。')


if __name__=='__main__':
    try: main()
    except Exception as ex:
        print('安装未完成：'+(str(ex) if isinstance(ex,ValueError) else '文件或系统操作失败，请检查目录权限及当前用户的自启服务。'))
        sys.exit(1)
