"""测试服防刷总开关 antiAbuseSwitch：查看 / 打开 / 关闭（11-23 用户同意由我们自己在固定窗口开关，不再每次找研发A）。
只在测试服；后台 /business/globalconfig/save 会按请求参数重建「全部」配置项，漏传的项会被写成空——
所以先读出全部 14 项原值，只改这一项，原样写回，写完再读一遍逐项核对，别的项有任何变化立即用原值恢复并报错。
用法：python3 -I anti_abuse_switch.py status | on | off"""
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from admin import Admin  # noqa: E402

KEY = "antiAbuseSwitch"


def read(a):
    r = a._send("/business/globalconfig/info/1", {}, form=True)
    if r.get("code") != 0:
        raise SystemExit(f"读配置失败：{r.get('msg')}")
    return {x["key"]: ("" if x.get("val") is None else str(x["val"])) for row in r.get("kvs") or [] for x in row if x.get("key")}


def write(a, conf):
    r = a._send("/business/globalconfig/save", {"cate": 1, **conf}, form=True)
    if r.get("code") != 0:
        raise SystemExit(f"保存失败：{r.get('msg')}（可能没有保存权限）")


def main(cmd):
    a = Admin()
    if not a.login().get("logged_in"):
        raise SystemExit("后台登录失败")
    before = read(a)
    if KEY not in before:
        raise SystemExit("没找到 antiAbuseSwitch")
    if cmd == "status":
        print(f"{KEY}={before[KEY]}（1 开 / 0 关）"); return
    want = "1" if cmd == "on" else "0"
    if before[KEY] == want:
        print(f"{KEY} 已经是 {want}，不用改"); return
    write(a, {**before, KEY: want})
    after = read(a)
    changed = {k: (before[k], after.get(k)) for k in before if k != KEY and before[k] != after.get(k)}
    if changed or after.get(KEY) != want:
        write(a, before)
        raise SystemExit(f"写入后核对不一致，已用原值恢复：{changed or after.get(KEY)}")
    print(f"{KEY}: {before[KEY]} → {want}，其余 {len(before) - 1} 项核对未变")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("status", "on", "off"):
        raise SystemExit(__doc__)
    main(sys.argv[1])
