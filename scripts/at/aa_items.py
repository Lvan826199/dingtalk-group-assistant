"""开关关着时临时停用套件 72 的防刷用例 A01～A11，跑完恢复（11-23 本人同意：这 11 条开关关时必失败，每条空等约 51 秒）。
用法：aa_items.py off | restore    off 前先把原始列表备份到 runs/aa_items_backup.json，restore 按备份原样写回。"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import series_check as sc

BK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "runs", "aa_items_backup.json")
items = sc.req("GET", "/api-suites/72")["data"]["items"]
body = lambda xs: {"items": [{"case_id": i["case_id"], "sort_order": i["sort_order"], "enabled": i["enabled"]} for i in xs]}
if sys.argv[1] == "off":
    if not os.path.exists(BK):
        json.dump(items, open(BK, "w"), ensure_ascii=False)
    n = 0
    for i in items:
        if re.match(r"A(0\d|1[01]) ", str(i.get("case_name") or "")) and i["enabled"]:
            i["enabled"] = False; n += 1
    sc.req("PUT", "/api-suites/72/items", body(items))
    print("防刷用例已临时停用", n, "条")
else:
    if not os.path.exists(BK):
        print("没有备份，不动"); sys.exit(0)
    sc.req("PUT", "/api-suites/72/items", body(json.load(open(BK))))
    os.remove(BK); print("防刷用例已恢复")
