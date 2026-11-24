#!/bin/bash
# 群里发消息（可 @ 人）。钉钉 markdown 单个换行不换行（用户 11-18 截图指出连成一坨）：正文里的换行统一变成空行。
# 用法：send.sh <群 cid> "<正文，可含 <@id>>" [id1,id2,...]      多个 @ 用逗号分隔（空格分隔会发送失败）
# 编辑已发消息：send.sh --edit <群 cid> <msgId> "<正文>" [ids]
set -u
if [ "${HANDOFF_CONSUMER:-}" = "duty" ]; then
  echo "拒绝后台直接发送：请用 scripts/handoff/stage_reply.py 更新待确认草稿，由本人确认后统一发送。" >&2
  exit 4
fi
EDIT=""; [ "$1" = "--edit" ] && { EDIT="$3"; shift; set -- "$1" "${@:3}"; }
# 调试群里回本人一律走机器人（11-24 本人：机器人已告诉我处理结果，不要再用我的身份在调试群发一遍）
if [ "$1" = "${QA_NOTIFY_GROUP}" ]; then
  python3 -I "$(dirname "$0")/notify_user.py" "回复你" "$2" >/dev/null && echo "已改由机器人发到调试群: True"; exit $?
fi
TEXT=$(printf '%s' "$2" | python3 -I -c "import sys,re;print(re.sub(r'\n+', '\n\n', sys.stdin.read().strip()))")
AT=(); [ -n "${3:-}" ] && AT=(--at-open-dingtalk-ids "$3")
# dws v1.0.68 起正文参数是 --content、会话是 --conversation-id（11-18 升级）；发失败用机器人通知用户（send_failed.py）
if [ -n "$EDIT" ]; then
  OUT=$(dws chat message edit --conversation-id "$1" --message-id "$EDIT" --text "$TEXT" ${AT[@]+"${AT[@]}"} 2>&1)
else
  # 新入口要求正文同时包含 <@openDingTalkId> 占位符；只传 at flag 会返回成功但消息不产生真实 @。
  if [ -n "${3:-}" ]; then
    MENTIONS=$(printf '%s' "$3" | python3 -c 'import sys; print(" ".join("<@" + x.strip() + ">" for x in sys.stdin.read().split(",") if x.strip()))')
    TEXT="$MENTIONS"$'\n\n'"$TEXT"
  fi
  # 先记一笔「值守发出」，助手据此不把它当本人消息回「已收到」（11-24）
  python3 -I -c "import json,os,sys,time;open(os.path.expanduser('~/qa-agent/logs/duty_outbox.jsonl'),'a',encoding='utf-8').write(json.dumps({'ts':time.time(),'cid':sys.argv[1],'text':sys.argv[2]},ensure_ascii=False)+'\\n')" "$1" "$TEXT" 2>/dev/null
  OUT=$(dws chat +messages-send --identity user --group "$1" --text "$TEXT" ${AT[@]+"${AT[@]}"} --uuid "qa-send-$(date +%s%N)" --wait-delivery --yes --format json 2>&1)
fi
if echo "$OUT" | grep -qE '"success": true|"ok": true|"deliveryStatus": "delivered"'; then echo '"success": true'
  [ -z "$EDIT" ] && [ -z "${NO_ANNOUNCE:-}" ] && python3 -I "$(dirname "$0")/announce_sent.py" "$1" "$TEXT" >/dev/null 2>&1 &
else
  ERR=$(echo "$OUT" | grep -oE '"message": "[^"]*' | head -1 | cut -c13-)
  python3 -I "$(dirname "$0")/send_failed.py" "群 $1" "$TEXT" "${ERR:-$OUT}"; echo '"success": false'
fi
