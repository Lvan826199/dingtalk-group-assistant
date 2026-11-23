"""轮询我提的 Jira 单（jira-drafts/*.json 里有 key 的），状态 / 指派 / 新评论有变化就打印一行。状态存 runs/jira_state.json。

用法：python3 -I jira_watch.py --once     只在北京时间 10:00–21:00 内查一次（用户 11-10 定 10–18，11-17 延到 21：每半小时一次，其他时间不看），
      窗口外直接退出、不请求。随群监听每 30 分钟续期时顺带调用一次即可，不再单独用 Monitor 轮询。
      python3 -I jira_watch.py --force    忽略时间窗口查一次。
"""
import glob
import fcntl
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jira  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "../../runs/jira_state.json")
ALERT_STATE = os.path.join(HERE, "../../runs/jira_watch_alert.json")
NOTIFY = os.path.join(HERE, "../notify_user.py")
WINDOW = (10, 21)  # 北京时间，含 10 点、不含 21 点（11-17 用户定延到 21 点，和群监听一致；原 18 点）


def keys():
    out = []
    for f in sorted(glob.glob(os.path.join(HERE, "../../jira-drafts/*.json"))):
        k = json.load(open(f, encoding="utf-8")).get("key")
        if k:
            out.append(k)
    extra = os.path.join(HERE, "../../runs/jira_watch_keys.json")
    if os.path.exists(extra):
        out.extend(json.load(open(extra, encoding="utf-8")))
    return list(dict.fromkeys(out))


def snapshot(k):
    i = jira.call("GET", f"/rest/api/2/issue/{k}?fields=status,assignee,comment,resolution,updated")["fields"]
    comments = [{"id": c["id"], "by": c["author"]["displayName"], "at": c["created"][:16], "text": c["body"]}
                for c in (i.get("comment") or {}).get("comments", [])]
    return {"status": i["status"]["name"], "assignee": (i.get("assignee") or {}).get("displayName"),
            "resolution": (i.get("resolution") or {}).get("name"), "comments": comments}


def check(state):
    failures = []
    for k in keys():
        try:
            now = snapshot(k)
        except SystemExit as e:  # 网络或鉴权问题：打印一次，下轮再试
            detail = f"{k} 查询失败: {str(e)[:120]}"
            print(f"[jira] {detail}", flush=True)
            failures.append(detail)
            continue
        except Exception as e:
            detail = f"{k} 查询异常: {repr(e)[:160]}"
            print(f"[jira] {detail}", flush=True)
            failures.append(detail)
            continue
        old = state.get(k)
        if old is None:
            state[k] = now
            continue
        for f in ("status", "assignee", "resolution"):
            if old.get(f) != now.get(f):
                print(f"[jira] {k} {f}: {old.get(f)} → {now.get(f)}", flush=True)
        seen = {c["id"] for c in old["comments"]}
        for c in now["comments"]:
            if c["id"] not in seen:
                print(f"[jira] {k} 新评论 {c['by']} {c['at']}: {c['text'][:300].replace(chr(10), ' ')}", flush=True)
        state[k] = now
    tmp = STATE + ".new"
    json.dump(state, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    return failures


def alert_failures(failures):
    """Jira 连接/解析异常不只写 watch.log：首次和每第 3 次用调试群机器人 @ 用户。"""
    try:
        meta = json.load(open(ALERT_STATE, encoding="utf-8")) if os.path.exists(ALERT_STATE) else {}
    except (OSError, ValueError):
        meta = {}
    if failures:
        count = int(meta.get("consecutive_failures") or 0) + 1
        meta.update({"consecutive_failures": count, "last_error": failures[-1], "last_time": time.strftime("%Y-%m-%d %H:%M:%S")})
        if count == 1 or count % 3 == 0:
            title = "⚠️ Jira 后台监视异常"
            text = (f"群：Jira 后台监视（调试通知群机器人）\n任务：Jira 状态 / 新评论监视\n时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"连续失败：{count} 次\n最近成功：{meta.get('last_success', '请查 watch.log')}\n错误：{failures[-1]}\n已保留上次成功状态，下一轮继续重试；收到恢复通知前不要把“未发现新评论”当成已确认。")
            try:
                sent = subprocess.run([sys.executable, "-I", NOTIFY, title, text], capture_output=True, text=True, timeout=20)
                if sent.returncode:
                    print("[jira] 异常告警发送未成功，保留错误等待下轮重试", flush=True)
                    meta["consecutive_failures"] = count - 1
            except Exception as e:
                print(f"[jira] 异常告警发送失败: {repr(e)[:120]}", flush=True)
    else:
        if meta.get("consecutive_failures"):
            meta.update({"recovered_at": time.strftime("%Y-%m-%d %H:%M:%S"), "consecutive_failures": 0})
            subprocess.run([sys.executable, "-I", NOTIFY, "✅ Jira 后台监视已恢复", f"任务：Jira 状态 / 新评论监视\n时间：{meta['recovered_at']}\n本轮已成功补查跟踪中的 Jira 单，后续按每半小时继续检查。"], capture_output=True, text=True, timeout=20)
        meta["last_success"] = time.strftime("%Y-%m-%d %H:%M:%S")
    json.dump(meta, open(ALERT_STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def in_window():
    h = time.localtime().tm_hour  # 本机就是 Asia/Shanghai
    return WINDOW[0] <= h < WINDOW[1]


def main():
    lock = open(STATE + ".lock", "a")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[jira] 另一轮正在查询，本轮不重复查询", flush=True)
        return
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    if "--force" not in sys.argv and not in_window():
        return
    failures = check(state)
    alert_failures(failures)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:          # Jira 偶尔连不上：打印并通过机器人告警，下轮续期再查
        detail = f"Jira 连不上，本轮跳过：{e!r}"[:240]
        print(detail, flush=True)
        alert_failures([detail])
