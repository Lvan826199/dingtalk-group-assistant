#!/bin/bash
# 在测试平台 APP-API（项目 903）上执行套件并等结果。用法：run_suite.sh [suite_id...]，不传默认 72（regression 全量回归，209 条）。环境 163 (android 1010001) / 164 (ios 1000901) / 165 (android 1010100，048 新分支，11-12 加)。
# 旧套件 70 batch1 / 71 p0-single 已停用（11-11 用户要求合成一个），只留历史。
# ENVS="164" 可只跑一端。每个 (套件, 环境) 打印一行 "suite S env E exec ID status pass/total" 和失败用例明细。
set -u
# 同一时间只跑一轮（11-23：14:47 和 15:00 两轮撞车、后一轮一直排队）。锁是目录，进程退出自动删；锁的主人已不在就接管。
LOCK=/tmp/qa-run_suite.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  if kill -0 "$(cat "$LOCK/pid" 2>/dev/null)" 2>/dev/null; then
    echo "RUN_BUSY：已有一轮在跑（pid $(cat "$LOCK/pid")），本轮不启动"; exit 3
  fi
  rm -rf "$LOCK"; mkdir "$LOCK"
fi
echo $$ > "$LOCK/pid"
CLEANUP='rm -rf "$LOCK"'
trap 'eval "$CLEANUP"' EXIT
T=$(cat ~/.config/aitest/token)
build() { curl -s -m 10 https://api-test.example.com/actuator/info | python3 -I -c "import json,sys;c=json.load(sys.stdin).get('git',{}).get('commit',{});i=c.get('id');print((i.get('abbrev') if isinstance(i,dict) else str(i or ''))[:7])" 2>/dev/null; }
B=http://aitest.example.internal:8000/api/v1/projects/903
# 前置条件：账号余额不够先补币（金币解锁每轮扣 150），补不上也继续跑，由用例报 14002
python3 -I "$(dirname "$0")/topup.py" || echo "[run_suite] 补币失败，继续执行"
# 前置条件 1.5：各环境登录、把 uid / token 写进环境变量，用例可单独跑（用户 11-13 提议；再登录不会让旧 token 失效）
if ! python3 -I "$(dirname "$0")/env_tokens.py" ${ENVS:-163 164 165 166 168 169}; then
  echo "PRECONDITION_BLOCKED：账号或对照变量准备失败，本轮未执行，不计通过"
  exit 2
fi
# 前置条件 2：每端的 series 还有没有可用的"付费集+跳集"对，没有就自动换剧
if ! python3 -I "$(dirname "$0")/series_check.py"; then
  echo "PRECONDITION_BLOCKED：换剧检查失败，本轮未执行，不计通过"
  exit 2
fi
# 防刷窗口（11-23 用户同意）：AA_WINDOW=1 时本轮开跑前自己打开测试服 antiAbuseSwitch、跑完（含中途退出）一定关回去；
# 不开窗口时开关若是关的，只跳过防刷 A01～A11 用例，其余照常跑、照常计数。
AA_OPENED=0
if [ "${AA_WINDOW:-0}" = 1 ] && python3 -I "$(dirname "$0")/anti_abuse_switch.py" status | grep -q "=0"; then
  python3 -I "$(dirname "$0")/anti_abuse_switch.py" on && AA_OPENED=1
  CLEANUP="$CLEANUP"'; [ "$AA_OPENED" = 1 ] && python3 -I "$(dirname "$0")/anti_abuse_switch.py" off; python3 -I "$(dirname "$0")/aa_platform.py" sync'
fi
# 防刷用例由平台自己判断（11-23 平台 d41cfbf0）：A01～A11 已设执行条件 antiAbuseSwitch == 1 + 不重试，
# 开关关着时平台记「跳过」。这里只把开关当前值同步进各环境变量（aa_platform.py），不再临时停用用例。
python3 -I "$(dirname "$0")/aa_platform.py" sync || echo "[run_suite] 防刷开关同步失败，防刷用例可能按旧值跑或跳过"
for S in "${@:-72}"; do
  for env in ${ENVS:-163 164 165 166 168 169}; do
    # 前置条件 3（OPS-019 防刷，11-16 加）：套件 72 每个环境开跑前造一次性游客号刷到位，P1-防刷 用例断言后冻结清理；放在这里是因为「无播放 200 次」只封 1 小时
    if [ "$S" = 72 ]; then
      AA_SKIP=0
      if ! python3 -I "$(dirname "$0")/anti_abuse_prep.py" "$env"; then
        echo "suite $S env $env 防刷前置未满足（开关关或造号失败）：只跳过防刷 A01～A11 用例，其余照常跑"
        AA_SKIP=1
      fi
    fi
    # 3. 记版本：开跑前、跑完各取一次测试服版本，变了这个环境作废（11-23 一天中途换版 3 次）
    # 4. 偶发：首跑有失败就立即再跑一次，重跑通过的记「偶发」不算失败（11-23 K04）
    FIRST=""
    for attempt in 1 2; do
    B0=$(build)
      # 平台同一套件上一轮没结束会返回 409，等它结束（最多 20 分钟）再触发
      for w in $(seq 1 40); do
        R=$(curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d "{\"environment_id\":$env}" "$B/api-suites/$S/execute")
        echo "$R" | grep -q '"code":409' || break
        [ "$w" = 1 ] && echo "suite $S env $env 上一轮未结束，等待…"
        sleep 30
      done
      EID=$(echo "$R" | python3 -I -c "import json,sys;d=json.load(sys.stdin);print(d['data']['execution_id'])" 2>/dev/null) || { echo "suite $S env $env 触发失败: ${R:0:200}"; continue 2; }
      for i in $(seq 1 300); do   # 最多等 25 分钟（377 条一个环境约 12 分钟）
        s=$(curl -s -H "Authorization: Bearer $T" "$B/api-executions/$EID" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['data']['status'])")
        [ "$s" != running ] && [ "$s" != pending ] && break
        sleep 5
      done
      B1=$(build)
      OUT=$(curl -s -H "Authorization: Bearer $T" "$B/api-executions/$EID/logs" | python3 -I -c "
import json,sys;L=json.load(sys.stdin)['data']['logs'];sk=[l for l in L if 'skipped' in l['message'][-12:]];f=[l for l in L if 'passed' not in l['message'][-8:] and l not in sk]
import re
skip=[l for l in f if '${AA_SKIP:-0}'=='1' and re.match(r'A(0\\d|1[01]) ', l['message'][7:])]
f=[l for l in f if l not in skip]; n=len(L)-len(skip)
n-=len(sk); print('suite $S env $env exec $EID $s', n-len(f), '/', n, ('（跳过 %d 条，不计入）' % (len(skip)+len(sk))) if (skip or sk) else '')
[print('   ', l['message'][7:220]) for l in f]")

      if [ -n "$B0" ] && [ -n "$B1" ] && [ "$B0" != "$B1" ]; then
        echo "$OUT" | head -1 | sed "s/$/ （测试服中途换版 $B0→$B1，本环境作废，需重跑）/"; break
      fi
      NF=$(echo "$OUT" | tail -n +2 | grep -c .)
      if [ "$attempt" = 1 ] && [ "$NF" -gt 0 ]; then
        FIRST=$(echo "$OUT" | tail -n +2); echo "suite $S env $env 首跑 $NF 条失败（exec $EID），立即重跑一次看是否偶发"; continue
      fi
      echo "$OUT"
      if [ -n "$FIRST" ]; then
        FLAKY=$(echo "$FIRST" | while IFS= read -r l; do echo "$OUT" | grep -qF -- "$l" || echo "$l"; done)
        [ -n "$FLAKY" ] && echo "suite $S env $env 偶发（首跑失败、重跑通过，不计失败）：$(echo "$FLAKY" | sed 's/^ *//; s/:.*//' | paste -sd '；' -)"
      fi
      break
    done
  done
done
