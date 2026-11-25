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
# 调试群里回本人一律走机器人（11-24 本人：机器人已告诉我处理结果，不要再用我的身份在调试群发一遍）
if [ "$1" = "${QA_NOTIFY_GROUP}" ]; then
  python3 -I "$(dirname "$0")/notify_user.py" "回复你" "$3" >/dev/null && echo "已改由机器人发到调试群: True"; exit $?
fi
TEXT=$(printf '%s' "$3" | python3 -I -c "import sys,re;print(re.sub(r'\n+', '\n\n', sys.stdin.read().strip()))")
# dws v1.0.68 起正文参数是 --content（11-18 升级）；发失败用机器人通知用户（send_failed.py）
# 先记一笔「值守发出」，助手据此不把它当本人消息回「已收到」（11-24）
python3 -I -c "import json,os,sys,time;open(os.path.expanduser('~/qa-agent/logs/duty_outbox.jsonl'),'a',encoding='utf-8').write(json.dumps({'ts':time.time(),'cid':sys.argv[1],'text':sys.argv[2],'reply_to':sys.argv[3]},ensure_ascii=False)+'\\n')" "$1" "$TEXT" "$2" 2>/dev/null   # reply_to：助手据此认出这条已被值守回复（3.4.2）
OUT=$(dws chat +messages-reply --conversation-id "$1" --message-id "$2" --content "$TEXT" --uuid "reply-$(date +%s%N)" --yes --format json 2>&1)
if echo "$OUT" | grep -qE '"success": true|"ok": true'; then echo "引用回复: True"
  [ -z "${NO_ANNOUNCE:-}" ] && python3 -I "$(dirname "$0")/announce_sent.py" "$1" "$TEXT" "" "$2" >/dev/null 2>&1 &
else
  ERR=$(echo "$OUT" | grep -oE '"message": "[^"]*' | head -1 | cut -c13-)
  python3 -I "$(dirname "$0")/send_failed.py" "引用回复 $1" "$TEXT" "${ERR:-$OUT}"; echo "引用回复: False"
fi
