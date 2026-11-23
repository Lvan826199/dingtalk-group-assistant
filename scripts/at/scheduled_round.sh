#!/bin/bash
# 定时回归（用户 2026-11-13 定）：每天北京时间 10:00 必跑；15:00、18:30 只有测试服版本或合同有变化才跑。
# 不再「每次部署就跑」。优先级：群里要求回归 > 接口缺陷修复复测 > 定时轮（前两种由会话里的我手动跑 run_suite.sh / on_contract_change.sh）。
# 由 launchd（com.user.app-regression）调用：scheduled_round.sh 1000|1500|1830 [--force]
#   - 合同自上轮后有变化 → on_contract_change.sh（整条链）；否则 run_suite.sh
#   - 全绿才由 post_round.py 发短剧测试群最终结果；有失败先不发群，写 NEEDS_TRIAGE，先排除平台 / 用例 / 数据问题，同时调试群机器人提醒用户
#   - 版本 3 分钟内还在变就等（最多 30 分钟），中途换版的结果不报
# 状态 runs/scheduled/state.json：上次定时/手动回归跑过的测试服 commit 和合同 rev；日志 runs/scheduled/<日期>-<轮>.log
set -u
export DWS_DISABLE_KEYCHAIN=1
AT="$(cd "$(dirname "$0")" && pwd)"; QA="$(cd "$AT/../.." && pwd)"; SERVER="$QA/../backend-server"
SLOT="${1:-manual}"; FORCE="${2:-}"
DIR="$QA/runs/scheduled"; mkdir -p "$DIR"
LOG="$DIR/$(date +%F)-$SLOT.log"; STATE="$DIR/state.json"
exec >>"$LOG" 2>&1
echo "== $(date '+%F %T') 定时回归 $SLOT"
cur() { curl -s -m 10 https://api-test.example.com/actuator/info | python3 -I -c 'import json,sys;print(json.load(sys.stdin)["git"]["commit"]["id"][:7])' 2>/dev/null; }
git -C "$SERVER" fetch -q origin dev 2>/dev/null
REV=$(git -C "$SERVER" log -1 --format=%h origin/dev -- api/openapi/ 2>/dev/null)
# 等版本稳定 3 分钟（最多 30 分钟）
last=""; stable=0
for i in $(seq 1 60); do c=$(cur); [ -z "$c" ] && echo "$(date +%T) 取不到测试服版本，30 秒后重试"; if [ -n "$c" ] && [ "$c" = "$last" ]; then stable=$((stable+1)); else stable=0; last=$c; fi; [ $stable -ge 6 ] && break; sleep 30; done
BUILD=$last
[ -z "$BUILD" ] && { echo "测试服 actuator 取不到版本，放弃本轮"; echo "STATUS=ERROR" ; exit 1; }
read -r PREV_BUILD PREV_REV < <(python3 -I -c "import json;d=json.load(open('$STATE'));print(d.get('build',''),d.get('rev',''))" 2>/dev/null || echo " ")
echo "测试服 ${BUILD}（上轮 ${PREV_BUILD:-无}）  合同 ${REV}（上轮 ${PREV_REV:-无}）"
if [ "$SLOT" != "1000" ] && [ "$FORCE" != "--force" ] && [ "$BUILD" = "$PREV_BUILD" ] && [ "$REV" = "$PREV_REV" ]; then
  echo "没有新的提交，跳过"; echo "STATUS=SKIP"; exit 0
fi
OUT="$DIR/$(date +%F)-$SLOT.out"
# 推荐侧（11-18 加，11-19 起）：只随 10:00 轮跑，和套件 72 并行、互不影响，结果单独发测试群
[ "$SLOT" = "1000" ] && { bash "$AT/reco_round.sh" >>"$DIR/$(date +%F)-reco.log" 2>&1 & }
[ "$SLOT" = "1000" ] && export AA_WINDOW=1   # 10:00 轮自己开关防刷窗口（11-23 用户同意），跑完必关
if [ -n "$PREV_REV" ] && [ "$REV" != "$PREV_REV" ]; then
  echo "合同有变化 → on_contract_change"; bash "$AT/on_contract_change.sh" >"$OUT" 2>&1
else
  bash "$AT/run_suite.sh" >"$OUT" 2>&1
fi
grep -v "failed to get\|failed to store" "$OUT" | tail -15
END=$(cur)
if [ "$END" != "$BUILD" ]; then echo "跑的过程中测试服换版 $BUILD → ${END}，本轮作废"; echo "STATUS=VOID"; exit 0; fi
python3 -I -c "import json;json.dump({'build':'$BUILD','rev':'$REV','time':'$(date '+%F %T')','slot':'$SLOT'},open('$STATE','w'))"
if ! python3 -I "$AT/post_round.py" "$OUT" --check; then
  echo "有失败或没有结果 → 不发群，待复测"
  echo "STATUS=NEEDS_TRIAGE"
  python3 -I "$QA/scripts/notify_user.py" "定时回归 $SLOT 有失败待排查" "测试服 ${BUILD}，合同 ${REV}。结果暂不发测试群，先排除平台/用例/数据问题后复测。日志 runs/scheduled/$(date +%F)-$SLOT.log" || true
  exit 0
fi
python3 -I "$AT/post_round.py" "$OUT" | tail -3
echo "STATUS=POSTED"
