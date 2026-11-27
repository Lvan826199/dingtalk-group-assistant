"""跑套件前的前置条件：两个固定账号余额不够就用后台补币（每轮金币解锁消耗 150）。

用法：python3 -I topup.py [最低余额=500] [补到=2000]
输出每个账号补币前后的余额；后台不可用时打印原因并以非 0 退出（run_suite.sh 会照常继续跑，由用例自己报 14002）。
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from admin import Admin  # noqa: E402
from client import Client  # noqa: E402

ACCOUNTS = [  # (sid, pf, appVersion, appBuild)
    ("at-sid-07", "i", "1.1.0", 1010002),   # iOS 1.1.0（11-27 加，环境 170）
    ("at-sid-06", "a", "1.1.1", 1010103),
    ("at-sid-05", "a", "1.1.1", 1010102),
    ("at-sid-01", "a", "1.1.0", 1010001),
    ("at-sid-02", "i", "1.0.9", 1000901),
    ("at-sid-03", "a", "1.1.1", 1010100),
    ("at-sid-04", "i", "1.1.1", 1010101),   # iOS 1.1.1（11-13 加）   # 第三环境（048 新分支，合同维护人 11-12 15:3x 定）
]


def balance(c):
    d = c.call("/api/user/rich").get("data") or {}
    return (d.get("coin") or 0) + (d.get("bonus") or 0)


def main(min_bal=500, top=2000):
    clients = {}
    for sid, pf, ver, build in ACCOUNTS:
        c = Client(sid, pf, ver, build)
        if c.login().get("code") != 0:
            print(f"{sid} 登录失败", flush=True)
            continue
        clients[sid] = c
    need = {sid: c for sid, c in clients.items() if balance(c) < min_bal}
    before = {sid: balance(c) for sid, c in clients.items()}
    if need:
        a = Admin()
        if not a.login().get("logged_in"):
            print("后台登录失败，无法补币", before, flush=True)
            return 1
        res = a.add_coin([c.uid for c in need.values()], top)
        if res.get("code") != 0:
            print("补币失败:", res, flush=True)
            return 1
    for sid, c in clients.items():
        print(f"{sid} 余额 {before[sid]} → {balance(c)}" + ("（已补）" if sid in need else ""), flush=True)
    return 0


if __name__ == "__main__":
    args = [int(x) for x in sys.argv[1:3]]
    raise SystemExit(main(*args))
