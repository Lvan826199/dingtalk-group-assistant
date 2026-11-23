#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo '未找到 Python 3.10+，请本人安装后重新运行。'; exit 1
fi
exec python3 -I install.py "$@"
