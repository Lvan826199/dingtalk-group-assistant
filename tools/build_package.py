"""生成三平台安装包和 latest.json；只打包固定程序及首次安装模板。"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ('agent.py', 'console.py', 'bootstrap_memory.py', 'package_runtime.py')
INSTALLERS = ('install.py', 'install.sh', 'install.ps1', 'install.cmd')


def contents(root=ROOT, update_base_url="", doc_source=""):
    files = {name: (root / name).read_bytes() for name in PROGRAMS}
    files.update({name: (root / 'installer' / name).read_bytes() for name in INSTALLERS})
    files['roles/角色职责库.json'] = (root / 'roles/角色职责库.json').read_bytes()
    doc = Path(doc_source).read_text(encoding='utf-8') if doc_source else next((root / 'docs').glob('分享-*.md')).read_text(encoding='utf-8')
    section = doc.split('## 四、工作手册', 1)[1].split('```markdown\n', 1)[1].split('```', 1)[0]
    general = section.split('## 按角色', 1)[0].rstrip() + '\n'
    files['工作手册模板.md'] = general.encode('utf-8')
    version = re.search(r'VERSION = "([^"]+)"', files['agent.py'].decode()).group(1).split()[0]
    files['package.json'] = (json.dumps({'version': version, 'programs': list(PROGRAMS)}, ensure_ascii=False, indent=2)+'\n').encode()
    if update_base_url:
        old = b"https://lvan826199.github.io/dingtalk-group-assistant/"
        new = update_base_url.rstrip("/").encode()
        files = {name: data.replace(old, new) for name, data in files.items()}
    return version, files


def build(out, root=ROOT, update_base_url="", doc_source=""):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    version, files = contents(root, update_base_url=update_base_url, doc_source=doc_source)
    manifest = {'version': version, 'update_url': (update_base_url.rstrip('/') + '/files/latest.json') if update_base_url else 'https://lvan826199.github.io/dingtalk-group-assistant//files/latest.json', 'sha256': {}}
    for platform in ('windows', 'macos', 'linux'):
        suffix = 'tar.gz' if platform == 'linux' else 'zip'
        name = f'群消息助手-{version}-{platform}.{suffix}'
        target = out / name; temp = out / (name+'.new')
        selected = {k:v for k,v in files.items() if k not in (('install.sh',) if platform == 'windows' else ('install.ps1','install.cmd'))}
        if platform == 'linux':
            with tarfile.open(temp, 'w:gz') as archive:
                for k,v in sorted(selected.items()):
                    info=tarfile.TarInfo(k); info.size=len(v); info.mode=0o755 if k.endswith('.sh') else 0o644
                    archive.addfile(info, io.BytesIO(v))
        else:
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
                for k,v in sorted(selected.items()):
                    info=zipfile.ZipInfo(k); info.compress_type=zipfile.ZIP_DEFLATED
                    info.external_attr=(0o100755 if k.endswith('.sh') else 0o100644)<<16
                    archive.writestr(info, v)
        temp.replace(target)
        manifest[platform]=name
        manifest['sha256'][name]=hashlib.sha256(target.read_bytes()).hexdigest()
    temp=out/'latest.json.new'; temp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(out/'latest.json')
    for old in out.glob('群消息助手-v*'):
        if old.name not in manifest.values(): old.unlink()
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default=str(Path.home()/'qa-agent-site/files'));parser.add_argument('--doc-source',default='');parser.add_argument('--update-base-url',default='')
    args=parser.parse_args(); result=build(args.output, doc_source=args.doc_source, update_base_url=args.update_base_url)
    print('安装包已生成：'+result['version']+'（Windows / macOS / Linux），校验清单 latest.json 已更新。')
