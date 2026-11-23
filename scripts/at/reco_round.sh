#!/bin/bash
# 推荐侧接口回归（OPS-018 推荐侧，11-18 起；11-19 起随 10:00 定时轮跑）：平台套件 77 recommendation × 环境 167 reco-test。
# 全绿才发短剧测试群最终结果（@QA负责人 @合同维护人）；有失败先不发群，调试群机器人提醒用户排查。
# 用法：reco_round.sh [--no-post]
set -u
T=$(cat ~/.config/aitest/token); B=http://aitest.example.internal:8000/api/v1/projects/903
QA="$(cd "$(dirname "$0")/../.." && pwd)"; RECO=https://rec.example.com
for w in $(seq 1 20); do
  R=$(curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{"environment_id":167}' "$B/api-suites/77/execute")
  echo "$R" | grep -q '"code":409' || break; sleep 30
done
EID=$(echo "$R" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['data']['execution_id'])" 2>/dev/null) || { echo "reco 触发失败: ${R:0:200}"; exit 1; }
for i in $(seq 1 180); do
  s=$(curl -s -H "Authorization: Bearer $T" "$B/api-executions/$EID" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['data']['status'])")
  [ "$s" != running ] && [ "$s" != pending ] && break; sleep 5
done
RES=$(curl -s -H "Authorization: Bearer $T" "$B/api-executions/$EID/logs" | python3 -I -c "
import json,sys;L=json.load(sys.stdin)['data']['logs'];f=[l for l in L if 'passed' not in l['message'][-8:]]
print('suite 77 env 167 exec ${EID} $s', len(L)-len(f), '/', len(L))
[print('   ', l['message'][7:300]) for l in f]")
echo "$RES"
# 取证：版位配置版本、092 实验组这一刻用没用成绩表
INFO=$(curl -s -m 20 "$RECO/v1/slots?test=1" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['data'].get('configVersion',''))" 2>/dev/null)
MODE=$(curl -s -m 20 "$RECO/v1/recommend?uid=ht4sAWrAg3&language=en&os=a&slots=tripleColumn&limit=9&test=1&debug=1&ab=600444_497_1057" | python3 -I -c "
import json,sys;d=json.load(sys.stdin);rm=((d.get('debug') or {}).get('scenes',{}).get('tripleColumn') or {}).get('rank_mode') or {}
print('按成绩表排（%s）' % rm.get('rankscore_version') if rm.get('actual')=='table' else '未用成绩表，按退回原规则断言')" 2>/dev/null)
echo "configVersion ${INFO}；092 实验组：${MODE}"
[ "${1:-}" = "--no-post" ] && exit 0
if ! echo "$RES" | head -1 | grep -q " passed "; then
  python3 -I "$QA/scripts/notify_user.py" "推荐侧回归有失败待排查" "exec ${EID}：$(echo "$RES" | head -4)" || true
  echo "STATUS=NEEDS_TRIAGE"; exit 0
fi
N=$(echo "$RES" | head -1 | awk '{print $8"/"$10}')
PAYLOAD="$QA/runs/scheduled/$(date +%F)-reco-outbound.json"
python3 -I - "$PAYLOAD" "$EID" "$N" "$INFO" "$MODE" <<'PYREPORT'
import datetime,json,sys
from pathlib import Path
path,eid,count,info,mode=sys.argv[1:]
now=datetime.datetime.now()
payload={"key":f"scheduled:{now:%Y-%m-%d}:reco:{eid}",
 "event":{"type":"scheduled_regression_result","conversation_id":"${QA_TEST_GROUP}","message_id":"","sender":"定时回归","create_time":f"{now:%Y-%m-%d %H:%M:%S}","content":f"套件77 环境167 exec {eid} {count}通过"},
 "text":f"【OPS-018｜推荐侧接口回归】\n结果：{count}通过（exec {eid}，仅推荐测试服）\n配置：configVersion {info}\n092实验组：{mode}",
 "at_ids":$(cat ~/.config/qa-workflow/reco_at_ids.json 2>/dev/null || echo []),
 "authorization":"本人2026-11-20职责内事实回复自主处理授权；日常推荐侧10:00回归播报",
 "reason":f"本轮套件77、环境167、exec {eid}结果{count}通过；配置版本及实验组模式取自本轮日志。"}
Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2))
PYREPORT
if python3 -I "$QA/scripts/handoff/assistant_send.py" "$PAYLOAD"; then
  echo "STATUS=SENT_PENDING_READBACK"
else
  echo "STATUS=SEND_FAILED"; exit 1
fi
