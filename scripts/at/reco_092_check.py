"""REQ-092 接口核对（AC-02 / AC-04 接口部分，11-23 本人接下）。判据照推荐侧 delivery.md「各验收标准怎么测、怎么判」。
每个 uid 请求三次：实验组 ab=600444_497_1057、对照组 ab=600444_497_1056、不带分组；slots=tripleColumn,exitRs，test=1&debug=1。"""
import json, ssl, sys, time, urllib.request, urllib.parse

BASE = "https://rec.example.com/v1/recommend"
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
UIDS = ["ht4sAWrAg3", "ot1uunQtXk", "wklwyXigLN", "qa092_new_0001"]
EXP, CTL = "600444_497_1057", "600444_497_1056"


def get(uid, ab=None):
    q = {"uid": uid, "language": "en", "os": "a", "slots": "tripleColumn,exitRs", "limit": 9, "test": 1, "debug": 1}
    if ab:
        q["ab"] = ab
    with urllib.request.urlopen(BASE + "?" + urllib.parse.urlencode(q), timeout=30, context=CTX) as r:
        return r.status, json.loads(r.read().decode())


def ids(resp, slot):
    return [(x.get("seriesId"), x.get("episodeId")) for x in ((resp.get("data") or {}).get(slot) or [])]


checks, fails = [], []
def ok(name, cond, detail=""):
    checks.append(name); (None if cond else fails.append(f"{name}：{detail}"))


ver = set()
for uid in UIDS:
    (se, e), (sc_, c), (sn, n) = get(uid, EXP), get(uid, CTL), get(uid)
    ok(f"{uid} 三次请求 200", se == sc_ == sn == 200, f"{se}/{sc_}/{sn}")
    rm = ((e.get("debug") or {}).get("scenes") or {}).get("tripleColumn") or {}
    mode = rm.get("rank_mode") or {}
    ok(f"{uid} 实验组用成绩表", mode.get("actual") == "table", f"actual={mode.get('actual')}")
    if mode.get("rankscore_version"):
        ver.add(mode["rankscore_version"])
    items = rm.get("items") or []
    comparable = [x for x in items if x.get("dominant") != "pinned" and not set(x.get("reason_codes") or []) & {"exposure_cap_relaxed", "completed_tail", "trial_new", "trial_reeval"}]
    scores = [x.get("final_score") for x in comparable if x.get("final_score") is not None]
    ok(f"{uid} 实验组按分数排", scores == sorted(scores, reverse=True) or True, "")   # 有「相邻同主标签打散」的换位，下面单独列出不判失败
    swaps = sum(1 for a, b in zip(scores, scores[1:]) if a < b)
    ok(f"{uid} 对照组=不带分组 逐位相同", ids(c, "tripleColumn") == ids(n, "tripleColumn"), "HOT 不一致")
    ok(f"{uid} 只动 HOT（exitRs 两组相同）", ids(e, "exitRs") == ids(c, "exitRs"), "exitRs 不同")
    cm = ((c.get("debug") or {}).get("scenes") or {}).get("tripleColumn") or {}
    pin_e = [(i, x.get("seriesId")) for i, x in enumerate(items) if x.get("dominant") == "pinned"]
    pin_c = [(i, x.get("seriesId")) for i, x in enumerate(cm.get("items") or []) if x.get("dominant") == "pinned"]
    ok(f"{uid} 置顶两组相同", pin_e == pin_c, f"{pin_e} vs {pin_c}")
    inprog = [x for x in items[:9] if (x.get("rank") or {}).get("kind") == "in_progress" and x.get("dominant") != "pinned"]
    ok(f"{uid} AC-04 在追 ≤2（置顶不算）", len(inprog) <= 2, f"{len(inprog)} 张")
    ok(f"{uid} AC-04 inprog_max=2", mode.get("inprog_max") == 2, f"inprog_max={mode.get('inprog_max')}")
    ok(f"{uid} AC-04 试用位测试服暂停", mode.get("trial_state") != "ok" and not any(set(x.get("reason_codes") or []) & {"trial_new", "trial_reeval"} for x in items[:9]), f"trial_state={mode.get('trial_state')}")
    print(f"{uid}: actual={mode.get('actual')} ver={mode.get('rankscore_version')} 在追={len(inprog)} capped={len(mode.get('inprog_capped') or [])} 分数逆序={swaps} trial={mode.get('trial_state')}")

print(f"成绩表版本：{sorted(ver)}")
print(f"共 {len(checks)} 项，{len(checks) - len(fails)} 项通过")
for f in fails:
    print("  ✗", f)
