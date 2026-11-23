"""在等别人回复的事项：超过 24 小时没结果就催（用户 2026-11-11 定）。

清单 runs/pending.json：[{"id","who","what","asked","where","note"}]，asked 为 "YYYY-MM-DD HH:MM"（北京时间）。
用法：pending_check.py            列出所有待回复，超 24h 的标 ⚠ 该催
      pending_check.py add "<who>" "<what>" "<where>"     新增（asked=现在）
      pending_check.py done <id> ["结论"]                 关掉（写进 note，移到 closed）
      pending_check.py bump <id>                          催过一次，asked 重置为现在
"""
import json
import os
import sys
import time

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../runs/pending.json")
LIMIT_H = 24


def load():
    return json.load(open(P, encoding="utf-8")) if os.path.exists(P) else {"open": [], "closed": []}


def save(d):
    json.dump(d, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def hours(asked):
    return (time.time() - time.mktime(time.strptime(asked, "%Y-%m-%d %H:%M"))) / 3600


def main():
    d = load()
    a = sys.argv[1:]
    if a and a[0] == "add":
        nid = max([x["id"] for x in d["open"] + d["closed"]] + [0]) + 1
        d["open"].append({"id": nid, "who": a[1], "what": a[2], "where": a[3] if len(a) > 3 else "", "asked": time.strftime("%Y-%m-%d %H:%M"), "note": ""})
        save(d)
        return print("加入", nid)
    if a and a[0] in ("done", "bump"):
        for x in d["open"]:
            if x["id"] == int(a[1]):
                if a[0] == "done":
                    x["note"] = a[2] if len(a) > 2 else ""
                    x["closed"] = time.strftime("%Y-%m-%d %H:%M")
                    d["open"].remove(x)
                    d["closed"].append(x)
                else:
                    x["note"] = (x.get("note") or "") + f" 催于 {time.strftime('%m-%d %H:%M')};"
                    x["asked"] = time.strftime("%Y-%m-%d %H:%M")
                save(d)
                return print(a[0], a[1])
        return print("没有这个 id")
    over = 0
    for x in d["open"]:
        h = hours(x["asked"])
        flag = "⚠ 该催" if h >= LIMIT_H else "  "
        over += h >= LIMIT_H
        print(f"{flag} #{x['id']} {x['who']}｜{x['what']}｜问于 {x['asked']}（{h:.0f}h）｜{x['where']}{(' ' + x['note']) if x.get('note') else ''}")
    print(f"待回复 {len(d['open'])}，超 24h {over}")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
