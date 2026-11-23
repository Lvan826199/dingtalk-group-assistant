#!/bin/bash
# 引用回复（用户 11-11 要求：回别人的具体消息时要像 合同维护人 一样引用原消息）。
# 用法：reply.sh <openConversationId> <openMessageId> "<纯文本>"
# 群 cid：协调群 ${QA_COORD_GROUP}  测试群 ${QA_TEST_GROUP}；消息 id 在监听输出的 msg= 里。
# 只支持纯文本，不支持 markdown / @；需要 @ 多人或发文件仍用 dws chat message send。
set -u
if [ "${HANDOFF_CONSUMER:-}" = "duty" ]; then
  echo "拒绝后台直接发送：请用 scripts/handoff/stage_reply.py 更新待确认草稿，由本人确认后统一发送。" >&2
  exit 4
fi
# 钉钉只有空行才换行（见 SOP 10.5）：把正文里的单个换行统一变成空行，引用回复才不会连成一坨（用户 11-11 指出）
TEXT=$(printf '%s' "$3" | python3 -I -c "import sys,re;print(re.sub(r'\n+', '\n\n', sys.stdin.read().strip()))")
# dws v1.0.68 起正文参数是 --content（11-18 升级）；发失败用机器人通知用户（send_failed.py）
OUT=$(dws chat +messages-reply --conversation-id "$1" --message-id "$2" --content "$TEXT" --uuid "reply-$(date +%s%N)" --yes --format json 2>&1)
if echo "$OUT" | grep -qE '"success": true|"ok": true'; then echo "引用回复: True"
  [ -z "${NO_ANNOUNCE:-}" ] && python3 -I "$(dirname "$0")/announce_sent.py" "$1" "$TEXT" "" "$2" >/dev/null 2>&1 &
else
  ERR=$(echo "$OUT" | grep -oE '"message": "[^"]*' | head -1 | cut -c13-)
  python3 -I "$(dirname "$0")/send_failed.py" "引用回复 $1" "$TEXT" "${ERR:-$OUT}"; echo "引用回复: False"
fi
