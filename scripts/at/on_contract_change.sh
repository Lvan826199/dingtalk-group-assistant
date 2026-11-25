#!/bin/bash
# 合同（backend-server api/openapi/app-v1.yaml）有新提交后的整条链，一条命令跑完：
#   1 双端重新探测（p0_probe，AT_TAG=-c<合同rev>）
#   2 生成文档修正清单 + 接口台账（p0_report）
#   3 按新合同刷新平台单接口用例和 Schema 断言，挂到套件 72（platform_p0，P0_LIST=新清单）
#   4 双端跑全量回归套件 72（run_suite，先补币）
# 用法：on_contract_change.sh            （输出最后几行是回归结果；修正清单路径见 "清单:" 行）
set -u
cd "$(dirname "$0")"
SERVER="${APP_SERVER_REPO:-$HOME/qa-workflow/mirrors/backend-server}"
git -C "$SERVER" fetch -q origin dev
REV=$(git -C "$SERVER" rev-parse --short origin/dev)
BUILD=$(curl -s -m 10 https://api-test.example.com/actuator/info | python3 -I -c "import json,sys;print(json.load(sys.stdin)['git']['commit']['id'])")
D=$(date +%F)
echo "合同 $REV  测试服 $BUILD  $D"
AT_TAG="-c$REV" python3 -I p0_probe.py 2>&1 | grep -E "版本|结果|Error|Traceback"
AT_TAG="-c$REV" AT_SID=at-sid-02 AT_PF=i AT_APPVERSION=1.0.9 AT_APPBUILD=1000901 python3 -I p0_probe.py 2>&1 | grep -E "版本|结果|Error|Traceback"
A="../../runs/p0/$D-a-$BUILD-c$REV.json"; I="../../runs/p0/$D-i-$BUILD-c$REV.json"
[ -f "$A" ] && [ -f "$I" ] || { echo "探测输出缺失：$A / $I"; exit 1; }
python3 -I p0_report.py "$A" "$I" | tail -2
L="../../runs/p0/文档修正清单-$BUILD-合同$REV.md"
echo "清单: $L"
grep -E "^### |^- \[" "$L" | grep -v 待重测 | head -30
P0_LIST="$L" python3 -I platform_p0.py "$A" 2>&1 | tail -1
bash run_suite.sh
