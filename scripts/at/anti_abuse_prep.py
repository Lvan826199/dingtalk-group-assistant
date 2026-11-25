"""OPS-019 防刷用例的前置：平台脚本沙箱发不了成批请求，由本机先把一次性游客号刷到指定状态，套件里 P1-防刷 用例再断言、最后冻结清理。
每个环境 3 个一次性游客号（sid at-tmp-aa<n>-<env>-<时间戳>，用该环境的 pf / appVersion / appBuild）：
  aa1  1 分钟内看 51 部不同的剧（seriesId 1..51，不存在的剧也计数）→ 第 51 次起 429/10429，封 24 小时
  aa2  当天看详情 200 次、一集没播（不触发），套件里第 201 次 → 429/10429，封 1 小时
  aa4  对 env 的 series 按顺序做广告解锁（cate=1）直到 14006（单剧当天次数 = 后台单剧次数×2，11-16 测试服 1000007 是第 7 次），
       记下撞限的那集；套件里同一集再解锁 → 14006，换一部剧的第一集广告解锁 → 0（按剧计数）
  aa3  看 1 次详情取第一集 → episode/play 一次 → 再看 199 次（共 200 次），套件里第 201 次 → 0（有播放不封）
阈值见 backend-server AntiAbuseService（ae9b4b0，合同维护人 11-16 10:32 测试群说明）；天按 UTC 算（北京 8 点换天），
但测试服广告解锁计数按 UTC 15 分钟一档清零（aa4 见下）。
run_suite.sh 跑套件 72 时每个环境开跑前调一次。用法：python3 -I anti_abuse_prep.py <env_id>
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from client import Client  # noqa: E402
import series_check as sc  # noqa: E402  复用它的平台 req / env_vars
from admin import Admin  # noqa: E402

CREATED = []


def require_enabled():
    """只读检查开关；不能为凑通过而自行开启。"""
    admin = Admin()
    if not admin.login().get("logged_in"):
        raise SystemExit("防刷前置阻塞：无法核实测试服开关，未创建游客号")
    data = admin._send("/business/globalconfig/list", {"page": 1, "limit": 50}, form=True)
    if data.get("code") != 0:
        raise SystemExit("防刷前置阻塞：无权读取测试服开关，未创建游客号")
    found = []
    for row in (data.get("page") or {}).get("list", []):
        base = row.get("base") or {}
        # 后台 base 是空的兼容视图；实际配置存于 baseInfo，值字段为 val。
        if row.get("baseInfo"):
            raw = row["baseInfo"]
            base = json.loads(raw) if isinstance(raw, str) else raw
        for conf in base.get("confs", []):
            if conf.get("key") == "antiAbuseSwitch":
                value = conf["val"] if "val" in conf else conf.get("value", "")
                found.append(str(value).strip())
    if not found:
        raise SystemExit("防刷前置阻塞：未查到antiAbuseSwitch，无法核实测试服开关，未创建游客号")
    if found != ["1"]:
        raise SystemExit("防刷前置阻塞：antiAbuseSwitch未开启；本轮防刷场景未验证，不能计为通过")



def set_vars(env, cur, values):
    for name, value in values.items():
        if name in cur:
            sc.req("DELETE", f"/environments/{env}/variables/{cur[name]['id']}")
        sc.req("POST", f"/environments/{env}/variables", {"name": name, "value": str(value), "type": "text",
                                                           "description": "anti_abuse_prep.py 每轮开跑前写入（一次性游客号，套件里冻结清理）"})


def guest(env, v, n):
    c = Client(f"at-tmp-aa{n}-{env}-{int(time.time() * 1000)}", v["pf"]["value"], v["appVersion"]["value"], int(v["appBuild"]["value"]))
    if c.login().get("code") != 0:
        raise SystemExit(f"env {env} aa{n} 游客登录失败")
    CREATED.append(c)
    return c


def details(c, ids):
    """并发 10 路：单次约 0.45 秒，串行 51 次会跨分钟（11-16 实测），分钟计数就凑不满。"""
    with ThreadPoolExecutor(10) as ex:
        return list(ex.map(lambda i: c.call("/api/series/detail", {"seriesId": i}, raw=True), ids))


from fixtures import F  # noqa: E402
OTHER_SERIES = F("aa_other_series")   # 换剧验证「按剧计数」用，取第一部不是 env series 的（fixtures.json）


def paid_eps(c, series):
    d = (c.call("/api/series/detail", {"seriesId": series}).get("data") or {}).get("seriesData") or {}
    eds = [e for s in d.get("seds") or [] for e in s.get("eds") or []]
    ids = [e["episodeId"] for e in eds]
    return eds[ids.index(d["lockEpisode"]):] if d.get("lockEpisode") in ids else []


def ad_unlock(c, series, ep):
    return c.call("/api/episode/unlock", {"seriesId": series, "cate": 1, "episodes": json.dumps([{"episodeId": ep["episodeId"], "sno": ep["sno"]}])})


def main():
    require_enabled()
    env = sys.argv[1]
    v = {x["name"]: x for x in sc.env_vars(env)}
    series = int(v["series"]["value"])
    out = {}

    c1 = guest(env, v, 1)
    while time.time() % 60 > 40:   # 分钟后段就等到下一分钟再刷，51 次落在同一分钟
        time.sleep(1)
    r = details(c1, range(1, 52))
    codes = [(st, b.get("code")) for st, b in r]
    print(f"env {env} aa1 {c1.uid} 51 部不同剧：前 50 次 {sorted(set(codes[:50]))}，第 51 次 {codes[50]}", flush=True)

    if codes[50] != (429, 10429):
        raise SystemExit(f"env {env} 防刷前置阻塞：51次详情未触发429/10429，先核运行实例开关与配置")

    c2 = guest(env, v, 2)
    r = details(c2, [series] * 200)
    print(f"env {env} aa2 {c2.uid} 无播放看详情 200 次：{sorted(set((st, b.get('code')) for st, b in r))}", flush=True)

    c3 = guest(env, v, 3)
    st, d = c3.call("/api/series/detail", {"seriesId": series}, raw=True)   # 第 1 次详情，顺便取第一集
    eds = [e for s in ((d.get("data") or {}).get("seriesData") or {}).get("seds") or [] for e in s.get("eds") or []]
    if not eds:
        raise SystemExit(f"env {env} aa3 剧 {series} 详情没有分集：{st} {d.get('code')}")
    p = c3.call("/api/episode/play", {"seriesId": series, "episodeId": eds[0]["episodeId"], "sno": eds[0].get("sno", 1)})
    r = [(st, d)] + details(c3, [series] * 199)
    print(f"env {env} aa3 {c3.uid} play {p.get('code')} 后看详情 200 次：{sorted(set((st, b.get('code')) for st, b in r))}", flush=True)

    # 测试服广告解锁的「当天」是 UTC 每 15 分钟一档（研发A 11-16 23:36 确认，正式服按自然日），跨档计数清零。
    # 撞上限到套件跑到 A06 一般 1 分钟、慢时 3 分钟，档内剩不到 6 分钟就等下一档开头再刷
    left = 900 - time.time() % 900
    if left < 360:
        print(f"env {env} aa4 本档只剩 {int(left)} 秒，等到下一档再刷", flush=True)
        time.sleep(left + 5)
    c4 = guest(env, v, 4)
    hit, ok = None, 0
    for ep in paid_eps(c4, series):
        code = ad_unlock(c4, series, ep).get("code")
        if code != 0:
            hit = ep if code == 14006 else None
            print(f"env {env} aa4 {c4.uid} 剧 {series} 广告解锁成功 {ok} 次后第 {ok + 1} 次 → {code}", flush=True)
            break
        ok += 1
    if hit is None:
        print(f"env {env} aa4 剧 {series} 没撞到 14006（成功 {ok} 次，付费集不够或上限变了），P1-防刷 A06 会失败", flush=True)
        raise SystemExit(f"env {env} 防刷前置阻塞：未造到广告限额，不写入无效集号")
    other = next(x for x in OTHER_SERIES if x != series)
    candidates = paid_eps(c4, other)
    if not candidates:
        raise SystemExit(f"env {env} 防刷前置阻塞：控制剧无有效付费集")
    first = candidates[0]
    out.update({"aa_ep4": hit["episodeId"], "aa_sno4": hit["sno"], "aa_series4b": other, "aa_ep4b": first["episodeId"], "aa_sno4b": first["sno"]})

    for n, c in ((1, c1), (2, c2), (3, c3), (4, c4)):
        out.update({f"aa_sid{n}": c.common["sid"], f"aa_uid{n}": c.uid, f"aa_token{n}": c.token})
    set_vars(env, v, out)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        for client in CREATED:
            try:
                cleaned = client.call("/api/v1/member/frozen", {"target": client.uid, "cate": 1, "reason": "at-anti-abuse-prep-failed-cleanup"})
                print(f"前置失败清理一次性账号 {client.uid}：code={cleaned.get('code')}", flush=True)
            except Exception as ex:
                print(f"前置失败清理未完成 {client.uid}：{type(ex).__name__}", flush=True)
        raise
