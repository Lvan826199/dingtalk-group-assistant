#!/bin/bash
# 会话里的「部署 + 定时回归 + Jira」监视（交给 Monitor，每次 ≤29 分钟、到 21:00 自停），每行输出是一条事件。
#   - 测试服换版只报不跑（用户 11-13：开发提交不触发回归）
#   - 到 10:00 / 15:00 / 18:30 启动 scheduled_round.sh（后台），每轮每天只触发一次（标记文件），错过整点在 29 分钟内补
#   - 10–21 点每次续期顺带 jira_watch.py --once
# launchd 不行：macOS 隐私保护不让后台任务读桌面目录（11-13 试过 Operation not permitted）。
set -u
QA="$(cd "$(dirname "$0")/../.." && pwd)"; AT="$QA/scripts/at"; DIR="$QA/runs/scheduled"; mkdir -p "$DIR"
# 早上补发前一天每日总结已停（11-24 本人：和 21:00 收尾汇报重复）
h=$(date +%H); [ "$h" -ge 10 ] && [ "$h" -lt 21 ] && python3 -I "$AT/jira_watch.py" --once 2>&1 | grep -v "^$" | sed 's/^/[jira] /' | cut -c1-600
cur() { curl -s -m 10 https://api-test.example.com/actuator/info | python3 -I -c 'import json,sys;print(json.load(sys.stdin)["git"]["commit"]["id"][:7])' 2>/dev/null; }
base=$(cur); end=$(( $(date +%s) + 29*60 )); stop=$(date -j -f "%H%M%S" 210000 +%s)
while [ "$(date +%s)" -lt "$end" ] && [ "$(date +%s)" -lt "$stop" ]; do
  c=$(cur); if [ -n "$c" ] && [ -n "$base" ] && [ "$c" != "$base" ]; then echo "测试服换版（只记录，不触发回归）: $base -> $c $(date +%H:%M)"; base=$c; fi
  hm=$(date +%H%M); slot=""
  [ "$hm" -ge 1000 ] && [ "$hm" -lt 1030 ] && slot=1000
  [ "$hm" -ge 1500 ] && [ "$hm" -lt 1530 ] && slot=1500
  [ "$hm" -ge 1830 ] && [ "$hm" -lt 1900 ] && slot=1830
  if [ -n "$slot" ] && [ ! -f "$DIR/$(date +%F)-$slot.started" ]; then
    touch "$DIR/$(date +%F)-$slot.started"
    echo "定时回归 $slot 启动 $(date +%H:%M)（日志 runs/scheduled/$(date +%F)-$slot.log）"
    nohup bash "$AT/scheduled_round.sh" "$slot" </dev/null >/dev/null 2>&1 &
  fi
  for f in "$DIR"/$(date +%F)-*.log; do
    [ -f "$f" ] || continue; st=$(grep -o "STATUS=[A-Z_]*" "$f" | tail -1)
    if [ -n "$st" ] && [ ! -f "$f.reported" ]; then touch "$f.reported"; echo "定时回归结果 $(basename "$f" .log): $st"; fi
  done
  sleep 60
done
