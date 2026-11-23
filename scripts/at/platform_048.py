"""REQ-048「播放地址按权限下发」用例（合同维护人 11-12 15:07 定口径，按 dev PlaybackAccessService）：挂到套件 72 末尾，三个环境都跑，断言按环境 appBuild 分支：
  appBuild ≥ 1010100（环境 165，at-sid-03）：新分支 —— 有权限的集带签名地址，没权限的集 videos 为空；已解锁集的下一集也带地址（设计如此）；未上线集只在上线前 40 分钟内出现；
  不带 appBuild / 非法值：按新分支裁剪（TRIM_UNVERIFIED），三个环境都断言（研发A 15:19 确认不读会话版本）；
  appBuild < 1010100（环境 163/164）：老分支 —— 已上线集都带地址（11-11 紧急修复后未上线集不下发地址）。
每轮在环境 165 用金币解锁一集（100 币），topup.py 会补。用法：python3 -I platform_048.py [--dry-run]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from platform_batch1 import body, items, req, step, unlock_eps  # noqa: E402

PID = 903
K = "P1-048 播放地址按权限（分支按 appBuild）"
NEW = 1010100
WINDOW_MS = 40 * 60 * 1000


def code_assert(code):
    return [{"type": "status_code", "expected": 200, "mode": "hard"},
            {"type": "json_path", "path": "$.code", "expected": code, "mode": "soft"}]


CLASSIFY = r'''
build = int(self.get_env_value('appBuild') or 0)
sid_series = int(self.get_env_value('series'))
d = (response.json().get('data') or {}).get('seriesData') or {}
eds = [e for s in (d.get('seds') or []) for e in (s.get('eds') or [])]
assert eds, '剧详情没有分集'
hist = self.get_env_value('k_hist') or []   # 提取出来就是 list（平台脚本禁止 import，不做字符串兜底）
done = set([i.get('episodeId') for i in hist if i.get('seriesId') == sid_series])
now = global_function.timestamp_ms()
online = [e for e in eds if (e.get('onlineIn') or 0) <= now]
future = [e for e in eds if (e.get('onlineIn') or 0) > now]
free = [e for e in online if not e.get('coin')]
paid = [e for e in online if e.get('coin')]
unlocked = [e for e in paid if e['episodeId'] in done]
locked = [e for e in paid if e['episodeId'] not in done]
assert all([e.get('videos') for e in free]), '免费集应带地址：%s' % [e['episodeId'] for e in free if not e.get('videos')]
assert all([e.get('videos') for e in unlocked]), '已解锁集应带地址：%s' % [e['episodeId'] for e in unlocked if not e.get('videos')]
if build >= __NEW__:
    with_url = [e for e in locked if e.get('videos')]
    assert len(with_url) <= 1, '新分支锁定集 videos 应为空（只允许已解锁/免费集的下一集例外）：%s' % [e['episodeId'] for e in with_url]
    far = [e for e in future if e['onlineIn'] - now > __WIN__]
    assert not far, '新分支上线前 40 分钟外的集不应出现：%s' % [e['episodeId'] for e in far]
    assert all([e.get('videos') for e in future]), '新分支 40 分钟内的未上线集应带地址：%s' % [e['episodeId'] for e in future if not e.get('videos')]
    pick = [e for e in locked if not e.get('videos')]
else:
    assert all([e.get('videos') for e in paid]), '老分支已上线付费集都应带地址：%s' % [e['episodeId'] for e in paid if not e.get('videos')]
    assert all([not e.get('videos') for e in future]), '老分支未上线集不应带地址（11-11 紧急修复）：%s' % [e['episodeId'] for e in future if e.get('videos')]
    pick = locked[1:] or locked   # 第 1 个锁定集是「已解锁/免费集的下一集」，裁剪时也带地址，核裁剪要用第 2 个
assert locked, '这个账号在本剧没有未解锁的付费集了，换剧（数据问题，不是缺陷）'
assert pick, '锁定集只剩 1 个，核不了裁剪（数据问题，不是缺陷）'
# k_locked_ep：裁剪后 videos 应为空的锁定集（K02/K04 用）；k_unlock_ep：第 1 个锁定集（解锁必须按顺序，否则 14005；K05–K07 用）
self.set_env_value('k_locked_ep', pick[0]['episodeId'])
self.set_env_value('k_unlock_ep', locked[0]['episodeId'])
self.set_env_value('k_unlock_sno', locked[0]['sno'])
self.set_env_value('k_unlock_coin', locked[0].get('coin') or 0)
self.set_env_value('k_free_ep', free[0]['episodeId'] if free else locked[0]['episodeId'])
nxt = [e for e in eds if e['episodeId'] == locked[0]['episodeId'] + 1]
self.set_env_value('k_next_ep', nxt[0]['episodeId'] if nxt else 0)
'''.replace('__NEW__', str(NEW)).replace('__WIN__', str(WINDOW_MS))

DETAIL_LOCKED = r'''
build = int(self.get_env_value('appBuild') or 0)
d = response.json().get('data') or {}
e = d.get('episodeData') or d.get('ed') or d
has = bool(e.get('videos'))
if build >= __NEW__:
    assert not has, '新分支锁定集 episode/detail 的 videos 应为空'
else:
    assert has, '老分支已上线付费集 episode/detail 应带地址'
'''.replace('__NEW__', str(NEW))

TRIM_NO_BUILD = r'''
build = int(self.get_env_value('appBuild') or 0)
d = (response.json().get('data') or {}).get('seriesData') or {}
eds = [e for s in (d.get('seds') or []) for e in (s.get('eds') or [])]
locked_ep = int(self.get_env_value('k_locked_ep'))
me = [e for e in eds if e['episodeId'] == locked_ep]
assert me, '找不到本轮选的锁定集'
assert not me[0].get('videos'), '不带 / 非法 appBuild 应按新分支裁剪（TRIM_UNVERIFIED）：锁定集 videos 应为空'  # 三个环境都断言（合同维护人/研发A 11-12 15:19）
'''.replace('__NEW__', str(NEW))

AFTER_UNLOCK = r'''
build = int(self.get_env_value('appBuild') or 0)
d = (response.json().get('data') or {}).get('seriesData') or {}
eds = {e['episodeId']: e for s in (d.get('seds') or []) for e in (s.get('eds') or [])}
ep = int(self.get_env_value('k_unlock_ep')); nxt = int(self.get_env_value('k_next_ep') or 0)
assert eds.get(ep, {}).get('videos'), '刚解锁的集应带地址'
if build >= __NEW__ and nxt and nxt in eds:
    assert eds[nxt].get('videos'), '新分支：已解锁集的下一集也应带地址（设计如此）'
'''.replace('__NEW__', str(NEW))

FORYOU = r'''
build = int(self.get_env_value('appBuild') or 0)
d = response.json().get('data') or {}
lst = d.get('datas') or d.get('list') or (d if isinstance(d, list) else [])
assert lst, 'foryou 为空'
if build >= __NEW__:
    bad = [x for x in lst if not ((x.get('ed') or {}).get('videos'))]
    assert not bad, '新分支 For You 只应返回可播的集：%d 条没有地址' % len(bad)
'''.replace('__NEW__', str(NEW))

CASES = [
    (K, "K00 准备：解锁历史 → k_hist", "high", "normal", "按本账号已解锁集区分有无权限。", [],
     step("unlock history", "/api/user/episode/unlock/history", body(ps=500), extract=[("k_hist", "$.data.data")])),
    (K, "K01 series/detail 按分支核 videos：免费 / 已解锁带地址，新分支锁定集为空、40 分钟外未上线集不出现", "urgent", "normal",
     "合同维护人 11-12：≥1010100 新分支；已解锁集的下一集也带地址不算缺陷；未上线集 40 分钟窗口；老分支已上线集都带地址、未上线集不带。", [],
     step("series detail", "/api/series/detail", body(seriesId="{{series}}"), teardown=CLASSIFY)),
    (K, "K02 episode/detail 锁定集：新分支 videos 空 / 老分支带地址", "urgent", "normal", "", [],
     step("episode detail locked", "/api/episode/detail", body(seriesId="{{series}}", episodeId="{{k_locked_ep}}"), teardown=DETAIL_LOCKED)),
    (K, "K03 episode/detail 免费集带地址（两分支）", "high", "normal", "", [],
     step("episode detail free", "/api/episode/detail", body(seriesId="{{series}}", episodeId="{{k_free_ep}}"),
          teardown="d = response.json().get('data') or {}\ne = d.get('episodeData') or d.get('ed') or d\nassert e.get('videos'), '免费集应带地址'")),
    (K, "K04 series/detail 不带 appBuild → 新会话按新分支裁剪（TRIM_UNVERIFIED）", "high", "boundary",
     "合同维护人/研发A 11-12 15:19：参数只从请求取，取不到走 TRIM_UNVERIFIED，三个环境都裁剪（我 15:1x 说老会话不裁剪是看错，已撤回）。", [],
     step("series detail no build", "/api/series/detail", body(drop=("appBuild",), seriesId="{{series}}"), teardown=TRIM_NO_BUILD)),
    (K, "K04b series/detail appBuild=0 → 裁剪", "medium", "boundary", "缺省值 0 走 TRIM_UNVERIFIED（研发A 15:19）。", [],
     step("series detail build 0", "/api/series/detail", body(seriesId="{{series}}", appBuild=0), teardown=TRIM_NO_BUILD)),
    (K, "K04c series/detail pf 未知 → 裁剪", "medium", "boundary", "合同维护人：平台不认识也按新分支裁剪（11-12 实测 pf=x 锁定集 videos 空）。", [],
     step("series detail pf x", "/api/series/detail", body(seriesId="{{series}}", pf="x"), teardown=TRIM_NO_BUILD)),
    (K, "K04d series/detail appBuild 非数字 → 10101 appBuild invalid", "low", "exception", "参数校验先于分流（11-12 实测）。", [],
     step("series detail bad build", "/api/series/detail", body(seriesId="{{series}}", appBuild="at-bad"), asserts=code_assert(10101))),
    (K, "K05 金币解锁第 1 个锁定集 → 0", "urgent", "normal", "必须按顺序解锁（跳集 14005）。每轮解锁一集（100 币），topup 会补；解锁后该集和下一集都应带地址。", [],
     step("unlock", "/api/episode/unlock", body(seriesId="{{series}}", cate=2, episodes=unlock_eps("k_unlock_ep", "k_unlock_sno", "k_unlock_coin")))),
    (K, "K06 解锁后 series/detail：该集带地址，新分支下一集也带地址", "urgent", "normal", "合同维护人：多给 1 集是设计如此。", [],
     step("series detail after unlock", "/api/series/detail", body(seriesId="{{series}}"), teardown=AFTER_UNLOCK)),
    (K, "K07 episode/detail 刚解锁的集带地址", "high", "normal", "", [],
     step("episode detail unlocked", "/api/episode/detail", body(seriesId="{{series}}", episodeId="{{k_unlock_ep}}"),
          teardown="d = response.json().get('data') or {}\ne = d.get('episodeData') or d.get('ed') or d\nassert e.get('videos'), '已解锁集应带地址'")),
    (K, "K08 drama/foryou 新分支只返可播集（fillPlayableOnly，不多给锁定集）", "high", "normal", "研发A 15:19：多给 1 集只在详情 / 单集 / 推荐 / 解锁返回；For You 只返免费、已解锁、VIP 的可播集。老分支不断言地址。", [],
     step("foryou", "/api/drama/foryou", body(pn=1, ps=10), teardown=FORYOU)),
]


def main():
    print("048 用例", len(CASES))
    if "--dry-run" in sys.argv:
        for c in CASES:
            print(" ", c[1])
        return
    flows = {f["name"]: f for f in items(f"/projects/{PID}/business-flows")}
    f = flows.get(K) or req("POST", f"/projects/{PID}/business-flows", {"name": K, "description": "OPS-018 / REQ-048 播放地址按权限（三环境，断言按 appBuild 分支）"})
    existing = {c["name"]: c for c in items(f"/projects/{PID}/api-test-cases?business_flow_id={f['id']}")}
    order = []
    for flow_name, name, prio, ctype, desc, pre, request in CASES:
        meta = {"name": name, "business_flow_id": f["id"], "description": desc, "priority": prio, "case_type": ctype, "tags": ["OPS-018", "REQ-048", "P1"]}
        c = existing.get(name)
        if c:
            req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}", meta)
        else:
            c = req("POST", f"/projects/{PID}/api-test-cases", meta)
        req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}/case-data",
            {"case_data": {"name": name, "skip": False, "description": desc, "request": request, "preconditions": pre, "retry": 0}})
        order.append(c["id"])
    stale = [c for n, c in existing.items() if n not in {x[1] for x in CASES}]
    for c in stale:
        req("DELETE", f"/projects/{PID}/api-test-cases/{c['id']}")
    suites = {s.get("code"): s for s in items(f"/projects/{PID}/api-suites")}
    reg = req("GET", f"/projects/{PID}/api-suites/{suites['regression']['id']}")
    stale_ids = {c["id"] for c in stale}
    cur = [it["case_id"] for it in sorted(reg["items"], key=lambda x: x["sort_order"]) if it["case_id"] not in stale_ids]
    full = [cid for cid in cur if cid not in order] + order
    req("PUT", f"/projects/{PID}/api-suites/{reg['id']}/items", {"items": [{"case_id": cid, "sort_order": i, "enabled": True} for i, cid in enumerate(full)]})
    print("套件", reg["id"], "regression 挂", len(full), "条（048", len(order), "）")


if __name__ == "__main__":
    main()
