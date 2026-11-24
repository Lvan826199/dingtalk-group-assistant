"""P1 用例录入测试平台 APP-API（只在测试服跑；条件是 合同维护人 2026-11-11 14:44 定的，见 README-交接.md「P1 条件」）。
可重复执行：按名称更新；追加到套件 72（regression）现有用例之后，不动前面的顺序。

覆盖：
  账号生命周期（一次性游客号 at-tmp-<时间戳>，跑完立即冻结清理；探测结论见沟通记录 11-11 15:0x）
  投币 /api/episode/insert/coin（专用号 + 环境变量 series 的免费集，每轮最多花 4 个币）
  Stripe 沙盒：goods → purchase（每天一个固定幂等键，不付款不建订阅）→ orderResult；portal / cancel / resume 无客户无订阅的码
  第三方登录 sign / unbind 只做反向
  钱包服务间 /api/open/wallet/trade（X-Internal-Key 在环境变量 internal_key；每轮净花 1 bonus/coin）
  防刷 OPS-019：详情限频（一次性游客号由 anti_abuse_prep.py 刷到位，用后冻结）
用法：python3 -I platform_p1.py [--dry-run]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from platform_batch1 import body, items, req, step  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PID = 903
ROUTES = json.load(open(os.path.join(HERE, "../../runs/p0/java_routes.json")))


def code_assert(code):
    return [{"type": "status_code", "expected": 200, "mode": "hard"},
            {"type": "json_path", "path": "$.code", "expected": code, "mode": "soft"}]


TMP = dict(sid="{{tmp_sid}}", uid="{{tmp_uid}}", token="{{tmp_token}}")       # 一次性游客号
TMP2 = dict(sid="{{tmp_sid}}", uid="{{tmp_uid2}}", token="{{tmp_token2}}")    # 冻结后 sid 收敛到的新游客
NEW_SID = "self.set_env_value('tmp_sid', 'at-tmp-' + str(global_function.timestamp_ms()))"
# 幂等键 = sid + 商品 sku + 天：同商品同天复用同一单；商品目录变了（11-11 067 切新商品源后旧 sku 下线，复用旧键返回 14104 product no longer available）就换新单
# 11-12 14:5x 又因测试服商品重录（067）让当天的键返回 14104，改成每轮一个新键：每轮建一个不付款的 OPEN 单（24h 过期），不建订阅
IDEM = "self.set_env_value('idem', 'at-' + str(self.get_env_value('sid')) + '-' + str(self.get_env_value('sp_sku')) + '-' + str(global_function.timestamp_ms()))"

L = "P1-账号生命周期"
C = "P1-投币"
S = "P1-Stripe 沙盒"
T = "P1-第三方登录"
CASES = [  # (flow, name, priority, case_type, desc, preconditions, request)
    # ---- 账号生命周期（S11）：新 sid 登录 → 登出 → 再登录 → 延时冻结 → 旧 token 被踢 → 新游客 → 立即冻结清理
    (L, "L01 新 sid 登录建游客号", "high", "normal", "每轮用新 sid（at-tmp-时间戳）登录，服务端建游客号；跑完由 L11 立即冻结清理。", [],
     step("login", "/api/user/login", body(auth=False, sid="{{tmp_sid}}"), extract=[("tmp_uid", "$.data.uid"), ("tmp_token", "$.data.token")], setup=NEW_SID)),
    (L, "L02 游客 user/info → 0", "high", "normal", "新游客号能正常访问。", [],
     step("user info", "/api/user/info", body(**TMP))),
    # ---- S1 新用户首开（用本轮一次性游客号）：init → conf → user/info → 新人奖励到账 → 首页 → 签到 → 奖励可消费
    (L, "S1a 新游客 init / conf → 0", "high", "normal", "首开配置接口对新号可用。", [step("init", "/api/init", body(**TMP))],
     step("conf", "/api/conf", body(**TMP))),
    (L, "S1b 新游客新人奖励到账：coin 0、bonus > 0", "high", "normal", "11-11 实测新游客 bonus 80（配置值），断言只看 bonus > 0。", [],
     step("rich", "/api/user/rich", body(**TMP), extract=[("tmp_bonus0", "$.data.bonus")],
          teardown="d = response.json().get('data') or {}\nassert float(d.get('coin') or 0) == 0 and float(d.get('bonus') or 0) > 0, '新游客应 coin 0、bonus > 0：%s' % d")),
    (L, "S1c 新游客首页可用：tabs 非空", "high", "normal", "", [],
     step("index", "/api/drama/index", body(**TMP), teardown="assert (response.json().get('data') or {}).get('tabs'), '首页 tabs 为空'")),
    (L, "S1d 新游客签到列表：today=1、checkedDays=0", "medium", "normal", "", [],
     step("ckin list", "/api/task/chin/list", body(**TMP),
          teardown="d = response.json().get('data') or {}\nassert d.get('today') == 1 and d.get('checkedDays') == 0, '新游客签到状态不对：%s' % d")),
    (L, "S1e 新游客签到领取 → 0", "high", "normal", "新号第一档必可领。", [],
     step("ckin reward", "/api/task/ckin/reward", body(**TMP))),
    (L, "S1f 签到后 bonus 增加", "high", "normal", "S5 场景链前半：奖励到账。", [],
     step("rich after ckin", "/api/user/rich", body(**TMP), extract=[("tmp_bonus1", "$.data.bonus")],
          teardown="assert float((response.json().get('data') or {}).get('bonus') or 0) > float(self.get_env_value('tmp_bonus0')), '签到后 bonus 没增加'")),
    (L, "S1g 奖励可消费：用 bonus 投币 1 → bonus 减 1", "high", "normal", "S5 场景链后半：bonus 先扣（新游客 bonus 不够解锁付费集，用投币验证可消费）。", [],
     step("insert coin", "/api/episode/insert/coin", body(seriesId="{{series}}", episodeId="{{free_ep}}", sno="{{free_sno}}", cate=1, coin=1, **TMP),
          teardown="d = response.json().get('data') or {}\nassert abs(float(self.get_env_value('tmp_bonus1')) - float(d.get('bonus') or 0) - 1) < 0.01, 'bonus 应减 1：%s → %s' % (self.get_env_value('tmp_bonus1'), d.get('bonus'))")),
    (L, "L03 logout → 0 且 data.uid 仍是本游客", "high", "normal", "logout 语义（读码 LoginApiService.logout）：按 sid 收敛到唯一游客 uid 并返回，游客登出返回自己。", [],
     step("logout", "/api/v1/member/logout", body(**TMP),
          teardown="assert (response.json().get('data') or {}).get('uid') == self.get_env_value('tmp_uid'), 'logout 返回的 uid 不是本游客'")),
    (L, "L04 游客登出后旧 token user/info → 0（游客登出是空操作）", "medium", "normal", "合同维护人 11-11 15:12 核：登出按 sid 收敛到游客号，游客自己登出选回同一 uid 并重设在线标记，旧 token 仍 0。绑定第三方的账号登出会切到游客号、旧 token 10400（appBuild ≥ 1000500），测试服无第三方 mock 不测。", [],
     step("user info old token", "/api/user/info", body(**TMP))),
    (L, "L05 再登录仍是同一 uid", "high", "normal", "游客号按 sid 复用。", [],
     step("login again", "/api/user/login", body(auth=False, sid="{{tmp_sid}}"), extract=[("tmp_token", "$.data.token")],
          teardown="assert (response.json().get('data') or {}).get('uid') == self.get_env_value('tmp_uid'), '再登录 uid 变了'")),
    (L, "L06 frozen target≠uid → 10101", "medium", "exception", "MemberFrozenBusinessService：target must equal uid。", [],
     step("frozen other", "/api/v1/member/frozen", body(target="someone-else", cate=1, **TMP), asserts=code_assert(10101))),
    (L, "L07 frozen cate 非法 → 10101", "medium", "exception", "cate 只能 1（立即）/ 2（延时）。", [],
     step("frozen bad cate", "/api/v1/member/frozen", body(target="{{tmp_uid}}", cate=9, **TMP), asserts=code_assert(10101))),
    (L, "L08 frozen 延时(cate=2) → 0，返回新游客 uid 和 delayAt", "high", "normal", "延时删除：落冻结记录，sid 收敛到新游客 uid。", [],
     step("frozen postpone", "/api/v1/member/frozen", body(target="{{tmp_uid}}", cate=2, reason="at-regression", **TMP), extract=[("tmp_uid2", "$.data.uid")],
          teardown="d = response.json().get('data') or {}\nassert d.get('uid') and d.get('uid') != self.get_env_value('tmp_uid'), '应返回新的游客 uid'\nassert d.get('delayAt'), '延时冻结应带 delayAt'")),
    (L, "L09 冻结后旧 token → 10400 MEMBER_OFFLINE", "high", "exception", "冻结把原 uid 踢下线。", [],
     step("old token", "/api/user/info", body(**TMP), asserts=code_assert(10400))),
    (L, "L10 再登录得到新游客 uid", "high", "normal", "同 sid 再登录，uid 等于 frozen 返回的新游客。", [],
     step("login new guest", "/api/user/login", body(auth=False, sid="{{tmp_sid}}"), extract=[("tmp_token2", "$.data.token")],
          teardown="assert (response.json().get('data') or {}).get('uid') == self.get_env_value('tmp_uid2'), '再登录 uid 不是 frozen 返回的新游客'")),
    # channel/init（研发B 11-11 15:04：测试服可调、渠道屏蔽缓存允许改）：用本轮的一次性游客号调，不碰固定号的渠道缓存
    (L, "L10a channel/init 未知渠道+剧 → 0（归 organic）", "medium", "normal", "读码 resolveChannelCache：渠道不在配置里按 organic 处理，首次写该 uid 的渠道缓存；用一次性游客号，不影响固定号。", [],
     step("channel init", "/api/channel/init", body(channelId=999999, seriesId="{{series}}", **TMP2))),
    (L, "L10b channel/init 缺 channelId → 0", "low", "boundary", "合同标必填，实际可选（11-11 探测，待进修正清单）。", [],
     step("channel init no channel", "/api/channel/init", body(seriesId="{{series}}", **TMP2))),
    (L, "L10c channel/init 缺 seriesId → 0", "low", "boundary", "合同标必填，实际可选（11-11 探测，待进修正清单）。", [],
     step("channel init no series", "/api/channel/init", body(channelId=999999, **TMP2))),
    (L, "L10d channel/init 不带 token → 10402", "low", "exception", "@VerifyToken。", [],
     step("channel init no token", "/api/channel/init", body(drop=("token",), channelId=999999, seriesId="{{series}}", **TMP2), asserts=code_assert(10402))),
    (L, "L11 立即冻结(cate=1) 清理新游客 → 0", "high", "normal", "清理本轮造的游客号（服务端会再收敛出一个空游客 uid，无数据）。", [],
     step("frozen immediately", "/api/v1/member/frozen", body(target="{{tmp_uid2}}", cate=1, reason="at-regression-cleanup", **TMP2))),
    (L, "L12 立即冻结后旧 token → 10400", "medium", "exception", "立即删除后原 token 失效。", [],
     step("old token 2", "/api/user/info", body(**TMP2), asserts=code_assert(10400))),
    (L, "L13 frozen 不带 token → 10402", "medium", "exception", "@VerifyToken。", [],
     step("no token", "/api/v1/member/frozen", body(drop=("token",), target="{{uid}}", cate=1), asserts=code_assert(10402))),
    # ---- 第三方登录只做反向（测试服没有第三方 mock）
    (T, "T01 sign 假 openToken → 10101 provider verification failed", "medium", "exception", "服务端去第三方平台校验真 token；测试服无 mock，只做反向。", [],
     step("sign bad", "/api/v1/member/sign", body(cate=1, openId="at-probe", openToken="at-bad-token", tracking="enabled", fullName=""), asserts=code_assert(10101))),  # sign 要带已登录的 uid/token（@VerifyToken），不带是 10402
    (T, "T01b sign 不带 token → 10402", "low", "exception", "@VerifyToken。", [],
     step("sign no token", "/api/v1/member/sign", body(drop=("token",), cate=1, openId="at-probe", openToken="at-bad-token", tracking="enabled", fullName=""), asserts=code_assert(10402))),
    (T, "T01c sign 1.1.2 Limited Login 缺 nonce → 10101", "medium", "exception",
     "TR-SERVER-2026-003（合同 5a9dfe1e）：App 1.1.2 起 Limited Login 必带 nonce，没过回 10101 provider verification failed。"
     "测试服没有真 FB 令牌，假令牌本身也回 10101，所以这条只守「缺 nonce 不报 500、码不变」，nonce 一致 / 重放要客户端真机验。", [],
     step("sign no nonce", "/api/v1/member/sign", body(appVersion="1.1.2", cate=1, openId="at-probe", openToken="at-bad-token", tracking="limited", fullName=""), asserts=code_assert(10101))),
    (T, "T02 unbind 未绑定 → 10101 provider not bound", "medium", "exception", "固定号没绑第三方。", [],
     step("unbind", "/api/v1/member/unbind", body(cate=1), asserts=code_assert(10101))),
    (T, "T03 unbind 不带 token → 10402", "low", "exception", "@VerifyToken。", [],
     step("unbind no token", "/api/v1/member/unbind", body(drop=("token",), cate=1), asserts=code_assert(10402))),
    # ---- 投币（专用号 + 环境变量 series 的免费集；free_ep / free_sno 来自 00 准备用例）
    (C, "C01 insert/coin coin=1 → 0 且余额减 1", "high", "normal", "读码：coin 1~3，先扣 bonus。前置记余额，投币后 coin+bonus 减 1。",
     [step("rich before", "/api/user/rich", body(), extract=[("ic_coin0", "$.data.coin"), ("ic_bonus0", "$.data.bonus")])],
     step("insert coin", "/api/episode/insert/coin", body(seriesId="{{series}}", episodeId="{{free_ep}}", sno="{{free_sno}}", cate=1, coin=1),
          teardown="d = response.json().get('data') or {}\nbefore = float(self.get_env_value('ic_coin0')) + float(self.get_env_value('ic_bonus0'))\nafter = float(d.get('coin') or 0) + float(d.get('bonus') or 0)\nassert abs(before - after - 1) < 0.01, '投 1 币应扣 1：%s → %s' % (before, after)")),
    (C, "C02 insert/coin coin=999999 截为 3 → 0 且只扣 3", "medium", "boundary", "读码：coin > 3 截到 3（合同待补上限）。",
     [step("rich before", "/api/user/rich", body(), extract=[("ic_coin0", "$.data.coin"), ("ic_bonus0", "$.data.bonus")])],
     step("insert coin big", "/api/episode/insert/coin", body(seriesId="{{series}}", episodeId="{{free_ep}}", sno="{{free_sno}}", cate=1, coin=999999),
          teardown="d = response.json().get('data') or {}\nbefore = float(self.get_env_value('ic_coin0')) + float(self.get_env_value('ic_bonus0'))\nafter = float(d.get('coin') or 0) + float(d.get('bonus') or 0)\nassert abs(before - after - 3) < 0.01, '超额投币应只扣 3：%s → %s' % (before, after)")),
    (C, "C06 insert/coin 不存在的剧 → 10404", "medium", "exception", "f5c3b189 fix(OPS-018)（研发B 11-11，按 合同维护人 的问题补的存在性校验）：剧 / 集不存在返回 10404 CODE_DATA_NOT_EXIST，不再扣币。", [],
     step("insert coin bad series", "/api/episode/insert/coin", body(seriesId=9999999, episodeId=1, sno=1, cate=1, coin=1), asserts=code_assert(10404))),
    (C, "C07 insert/coin 不存在的集 → 10404", "medium", "exception", "同上。前置记余额给 C09 比。",
     [step("rich before", "/api/user/rich", body(), extract=[("ic_coin0", "$.data.coin"), ("ic_bonus0", "$.data.bonus")])],
     step("insert coin bad episode", "/api/episode/insert/coin", body(seriesId="{{series}}", episodeId=9999999, sno=1, cate=1, coin=1), asserts=code_assert(10404))),
    (C, "C09 不存在的剧 / 集投币后余额不变", "medium", "normal", "研发A 11-11 16:27 口径：不存在返回 CODE_DATA_NOT_EXIST、不记录、不扣币。", [],
     step("rich after", "/api/user/rich", body(),
          teardown="d = response.json().get('data') or {}\nassert float(d.get('coin') or 0) == float(self.get_env_value('ic_coin0')) and float(d.get('bonus') or 0) == float(self.get_env_value('ic_bonus0')), '余额变了：%s/%s → %s/%s' % (self.get_env_value('ic_coin0'), self.get_env_value('ic_bonus0'), d.get('coin'), d.get('bonus'))")),
    (C, "C08 insert/coin 不带 episodeId → 0（剧支持记录，有意允许）", "low", "boundary", "合同维护人 11-11：2025-11-25 加剧支持记录时去掉 episodeId > 0 的判断，允许只对剧投币。会扣 1 币。", [],
     step("insert coin no episode", "/api/episode/insert/coin", body(seriesId="{{series}}", cate=1, coin=1))),
    (C, "C03 insert/coin 缺 seriesId → 10101", "medium", "exception", "seriesId <= 0 或 cate <= 0 → seriesId or episodeId INVALID。", [],
     step("drop seriesId", "/api/episode/insert/coin", body(episodeId="{{free_ep}}", sno="{{free_sno}}", cate=1, coin=1), asserts=code_assert(10101))),
    (C, "C04 insert/coin 缺 cate → 10101", "medium", "exception", "同上。", [],
     step("drop cate", "/api/episode/insert/coin", body(seriesId="{{series}}", episodeId="{{free_ep}}", sno="{{free_sno}}", coin=1), asserts=code_assert(10101))),
    (C, "C05 insert/coin 不带 token → 10402", "low", "exception", "@VerifyToken。", [],
     step("no token", "/api/episode/insert/coin", body(drop=("token",), seriesId="{{series}}", episodeId="{{free_ep}}", sno="{{free_sno}}", cate=1, coin=1), asserts=code_assert(10402))),
    # ---- Stripe 沙盒：不付款、不建订阅；幂等键按天固定，一天只造一单
    (S, "S00 准备：取 Stripe 商品", "high", "normal", "goods 第一条商品的 sku / basePlan / productId / priceKey 导出给下单用。", [],
     step("goods", "/api/v2/thirdPay/stripe/goods", body(countryCode="US", currencyCode="USD"),
          extract=[("sp_sku", "$.data.thirdPayDetailsList[0].platformSku"), ("sp_bp", "$.data.thirdPayDetailsList[0].platformBasePlanId"),
                   ("sp_pid", "$.data.thirdPayDetailsList[0].thirdPayProductData.thirdPayProductId"),
                   ("sp_key", "$.data.thirdPayDetailsList[0].thirdPayProductData.thirdPayPriceDataList[0].thirdPayPriceKey")])),
    (S, "S01 purchase（每轮新幂等键）→ 0 返回本地订单", "high", "normal", "创建本地订单 + Hosted Checkout，不付款（24h 过期）。幂等键每轮一个：同键在商品重录后会 14104（11-11、11-12 两次），按天复用不可靠。", [],
     step("purchase", "/api/v2/thirdPay/stripe/purchase",
          body(countryCode="US", currencyCode="USD", platformSku="{{sp_sku}}", platformBasePlanId="{{sp_bp}}", thirdPayProductId="{{sp_pid}}", thirdPayPriceKey="{{sp_key}}", idempotencyKey="{{idem}}"),
          extract=[("sp_order", "$.data.paymentOrderId")], setup=IDEM,
          teardown="d = response.json().get('data') or {}\nassert d.get('paymentOrderId') and d.get('status') in ('OPEN', 'PROCESSING'), '应返回 OPEN/PROCESSING 的本地订单：%s' % d.get('status')")),
    (S, "S02 orderResult 查到该单 → 0", "high", "normal", "按本地订单号查，data 是数组（11-11 实测，合同待核）。", [],
     step("order result", "/api/v2/thirdPay/stripe/orderResult", body(countryCode="US", currencyCode="USD", paymentOrderIds="{{sp_order}}"),
          teardown="d = response.json().get('data') or []\nassert isinstance(d, list) and d and d[0].get('paymentOrderId') == self.get_env_value('sp_order'), 'orderResult 没查到本单'\nassert d[0].get('status') and d[0].get('paymentState'), '缺 status / paymentState'")),
    (S, "S03 orderResult 缺 paymentOrderIds → 10101", "medium", "exception", "合同：空值返回 10101。", [],
     step("drop ids", "/api/v2/thirdPay/stripe/orderResult", body(countryCode="US", currencyCode="USD"), asserts=code_assert(10101))),
    (S, "S04 purchase 缺 platformSku → 10101", "medium", "exception", "必填。", [],
     step("drop sku", "/api/v2/thirdPay/stripe/purchase",
          body(countryCode="US", currencyCode="USD", platformBasePlanId="{{sp_bp}}", thirdPayPriceKey="{{sp_key}}", idempotencyKey="at-drop-sku"), asserts=code_assert(10101))),
    (S, "S05 portal（已有 Customer）→ 0 且返回 portalUrl", "medium", "normal", "S01 下单时 Stripe 已给固定号建了 Customer，之后 portal 都能开；没 Customer 的号是 14111（11-11 首单前实测）。", [],
     step("portal", "/api/v2/thirdPay/stripe/portal", body(countryCode="US", currencyCode="USD"),
          teardown="assert (response.json().get('data') or {}).get('portalUrl'), 'portal 应返回 portalUrl'")),
    (S, "S06 subscription/cancel 无订阅 → 14113", "medium", "exception", "固定号没有 Stripe 订阅。", [],
     step("cancel", "/api/v2/thirdPay/stripe/subscription/cancel", body(countryCode="US", currencyCode="USD"), asserts=code_assert(14113))),
    (S, "S07 subscription/resume 无订阅 → 14113", "medium", "exception", "同上。", [],
     step("resume", "/api/v2/thirdPay/stripe/subscription/resume", body(countryCode="US", currencyCode="USD"), asserts=code_assert(14113))),
]
# ---- 回调 / 推送 / 支付验单：只做反向（合同维护人 11-11：要真票据或会真发，正向不跑）
O = "P1-回调与推送反向"
CASES += [
    (O, "O01 af/push 空参无签名 → HTTP 401", "low", "exception", "AppsFlyer 回调有自己的鉴权，空请求 401；正向会真往 AF 发，不跑。", [],
     step("af push empty", "/api/af/push", {}, asserts=[{"type": "status_code", "expected": 401, "mode": "hard"}])),
    (O, "O08 apple/notify 空体 → 10101（BUG-779 修后）", "medium", "exception", "研发B 11-11 16:07 修复 eac3b6c7：验签失败（坏包）→ HTTP 200 + code 10101；处理失败 → HTTP 503 让苹果重试。修复上测试服前这条是 code 500。", [],
     step("apple notify empty", "/api/apple/notify", {}, asserts=code_assert(10101))),
    (O, "O09 apple/notify 假 signedPayload → 10101（BUG-779 修后）", "medium", "exception", "同上。", [],
     step("apple notify bad", "/api/apple/notify", {"signedPayload": "at-bad-payload"}, asserts=code_assert(10101))),
    (O, "O02 pay/verify 缺 payChannel → 10101 payChannel error", "medium", "exception", "验单要真票据，只做反向。", [],
     step("pay verify no channel", "/api/pay/verify", body(receipt="at-bad", productId="x", orderId="at-bad"), asserts=code_assert(10101))),
    (O, "O03 pay/verify 不带 token → 10402", "low", "exception", "@VerifyToken。", [],
     step("pay verify no token", "/api/pay/verify", body(drop=("token",), receipt="at-bad"), asserts=code_assert(10402))),
    (O, "O04 open/push/send 不带 X-Internal-Key → 10401", "high", "exception", "BUG-765 修复（e959c3f，11-13 上测试服）：三个 open 接口必带服务间密钥（配置 drama.open.internal-key，和 wallet 的不是同一把）。正向等研发A给 key 后补。", [],
     step("push send no key", "/api/open/push/send", {"items": [{"uid": "{{uid}}", "t": 1}]}, asserts=code_assert(10401))),
    (O, "O05 open/push/send 错误 key → 10401", "medium", "exception", "", [],
     dict(step("push send bad key", "/api/open/push/send", {"items": []}, asserts=code_assert(10401)), headers={"Content-Type": "application/json", "X-Internal-Key": "at-bad-key"})),
    (O, "O06 open/push/test 不带 key → 10401", "medium", "exception", "765 范围内的测试接口。", [],
     step("push test no key", "/api/open/push/test", {"uids": ["{{uid}}"]}, asserts=code_assert(10401))),
    (O, "O07 open/task/test 不带 key → 10401", "medium", "exception", "765 范围内的测试接口。", [],
     step("task test no key", "/api/open/task/test", {"id": 1}, asserts=code_assert(10401))),
    (O, "O10 open/push/send 带 key 只推专用号 → 0，itemCount=1、uidCount=1", "high", "normal", "研发A 11-13 给 open key（平台变量 open_key）。专用号没有真实设备 token，hitTokenCount=0、skipCount=1，不会真推给人。", [],
     dict(step("push send ok", "/api/open/push/send", {"notiId": 0, "items": [{"uid": "{{uid}}", "t": 0, "title": "at regression", "body": "OPS-018 自动化测试推送"}]},
               teardown="d = response.json().get('data') or {}\nassert d.get('itemCount') == 1 and d.get('uidCount') == 1, '计数不对：%s' % d\nassert d.get('acceptedCount', 0) + d.get('skipCount', 0) + d.get('failCount', 0) == 1, '受理 + 跳过 + 失败应等于 1：%s' % d"),
          headers={"Content-Type": "application/json", "X-Internal-Key": "{{open_key}}"})),
    (O, "O11 open/push/send 带 key 缺 items → 10101 items required", "medium", "exception", "", [],
     dict(step("push send no items", "/api/open/push/send", {}, asserts=code_assert(10101)), headers={"Content-Type": "application/json", "X-Internal-Key": "{{open_key}}"})),
    (O, "O12 open/push/send 带 key notiId=10 越界 → 10101", "low", "exception", "notiId 只能 0～9 或已有通知 ID。", [],
     dict(step("push send bad noti", "/api/open/push/send", {"notiId": 10, "items": [{"uid": "{{uid}}", "t": 0, "title": "x", "body": "x"}]}, asserts=code_assert(10101)), headers={"Content-Type": "application/json", "X-Internal-Key": "{{open_key}}"})),
    (O, "O13 open/push/send 带 key t=8 越界 → 10101", "low", "exception", "t 只能 0～7。", [],
     dict(step("push send bad t", "/api/open/push/send", {"items": [{"uid": "{{uid}}", "t": 8, "title": "x", "body": "x"}]}, asserts=code_assert(10101)), headers={"Content-Type": "application/json", "X-Internal-Key": "{{open_key}}"})),
    (O, "O14 open/push/test 带 key 缺 langs → 10101", "low", "exception", "测试接口不跑正向（会按 uids 真推）。", [],
     dict(step("push test no langs", "/api/open/push/test", {"uids": ["{{uid}}"]}, asserts=code_assert(10101)), headers={"Content-Type": "application/json", "X-Internal-Key": "{{open_key}}"})),
    (O, "O15 open/task/test 带 key 缺 id → 10101", "low", "exception", "", [],
     dict(step("task test no id", "/api/open/task/test", {}, asserts=code_assert(10101)), headers={"Content-Type": "application/json", "X-Internal-Key": "{{open_key}}"})),
    (O, "O16 open/task/test 带 key 不存在的 id → 10404 task layer not exist", "low", "exception", "正向要后台先配任务分层，不做。", [],
     dict(step("task test none", "/api/open/task/test", {"id": 999999}, asserts=code_assert(10404)), headers={"Content-Type": "application/json", "X-Internal-Key": "{{open_key}}"})),
]
for p, nm in (("/api/v2/thirdPay/stripe/purchase", "S08 purchase 不带 token → 10402"), ("/api/v2/thirdPay/stripe/orderResult", "S09 orderResult 不带 token → 10402"),
              ("/api/v2/thirdPay/stripe/portal", "S10 portal 不带 token → 10402"), ("/api/v2/thirdPay/stripe/subscription/cancel", "S11 cancel 不带 token → 10402")):
    if (ROUTES.get(p) or {}).get("login"):
        CASES.append((S, nm, "low", "exception", "@VerifyToken。", [], step("no token", p, body(drop=("token",), countryCode="US", currencyCode="USD", paymentOrderIds="x"), asserts=code_assert(10402))))

# ---- 钱包服务间接口 /api/open/wallet/trade（Go 调 Java；研发C 11-12 14:46 允许自动化用、研发A 14:48 私聊给了 X-Internal-Key，存环境变量 internal_key）
# 合同 5ec569b6「AI 二创扣退 Coin」；行为 11-12 15:0x 用专用号探过（沟通记录）。每轮净花 1 个 bonus/coin（REMIX_UNLOCK 不退款），REMIX_GENERATE 扣 1 再退 1。
W = "P1-钱包服务间 wallet/trade"
WT = "/api/open/wallet/trade"
WNO = ("self.set_env_value('wt_no', 'at-gen-' + str(global_function.timestamp_ms()))\n"
       "self.set_env_value('wt_no2', 'at-close-' + str(global_function.timestamp_ms()))\n"
       "self.set_env_value('wt_no3', 'at-big-' + str(global_function.timestamp_ms()))\n"
       "self.set_env_value('wt_no4', 'at-unlock-' + str(global_function.timestamp_ms()))")


def wt_step(name, b, key="{{internal_key}}", **kw):
    """wallet/trade 的请求：裸 JSON（不带客户端公共参数），头 X-Internal-Key；key=None 不带头。"""
    s = step(name, WT, b, **kw)
    if key is not None:
        s["headers"]["X-Internal-Key"] = key
    return s


def wt_state(state, extra=""):
    return "d = response.json().get('data') or {}\nassert d.get('state') == %r, 'state 应为 %s：%%s' %% d\n%s" % (state, state, extra)


GEN = dict(uid="{{uid}}", bizType="REMIX_GENERATE")
UNL = dict(uid="{{uid}}", bizType="REMIX_UNLOCK")
CASES += [
    (W, "W00 准备：记余额、生成本轮单号", "high", "normal", "wt_no（扣退）、wt_no2（退款先到）、wt_no3（余额不足）、wt_no4（解锁）各用一次性单号。", [],
     step("rich", "/api/user/rich", body(), extract=[("wt_coin0", "$.data.coin"), ("wt_bonus0", "$.data.bonus")], setup=WNO)),
    (W, "W01 不带 X-Internal-Key → 10401", "high", "exception", "合同：密钥缺失或不一致一律 10401。", [],
     wt_step("no key", dict(action="QUERY", bizOrderNo="{{wt_no}}", **GEN), key=None, asserts=code_assert(10401))),
    (W, "W02 错误 X-Internal-Key → 10401", "high", "exception", "", [],
     wt_step("bad key", dict(action="QUERY", bizOrderNo="{{wt_no}}", **GEN), key="at-bad-key", asserts=code_assert(10401))),
    (W, "W03 QUERY 无此单 → 0 state NOT_FOUND", "high", "normal", "QUERY 只读。", [],
     wt_step("query none", dict(action="QUERY", bizOrderNo="{{wt_no}}", **GEN), teardown=wt_state("NOT_FOUND"))),
    (W, "W04 CHARGE REMIX_GENERATE 1 → 0 CHARGED，paidCoin+giftCoin=1、不扣 Bonus", "high", "normal", "首次扣款：先充值币 pcf 再赠送币 fcf。", [],
     wt_step("charge gen", dict(action="CHARGE", bizOrderNo="{{wt_no}}", amount=1, **GEN), extract=[("wt_trade", "$.data.chargeTradeNo")],
             teardown=wt_state("CHARGED", "assert abs(float(d.get('paidCoin') or 0) + float(d.get('giftCoin') or 0) - 1) < 0.01 and not d.get('bonus'), '拆分不对：%s' % d\nassert d.get('chargeTradeNo'), '缺 chargeTradeNo'"))),
    (W, "W05 扣款后 coin 减 1、bonus 不变", "high", "normal", "", [],
     step("rich after charge", "/api/user/rich", body(),
          teardown="d = response.json().get('data') or {}\nassert abs(float(self.get_env_value('wt_coin0')) - float(d.get('coin') or 0) - 1) < 0.01, 'coin 应减 1：%s → %s' % (self.get_env_value('wt_coin0'), d.get('coin'))\nassert abs(float(self.get_env_value('wt_bonus0')) - float(d.get('bonus') or 0)) < 0.01, 'bonus 不应变：%s → %s' % (self.get_env_value('wt_bonus0'), d.get('bonus'))")),
    (W, "W06 CHARGE 同单同金额重复 → 0 CHARGED 返回原拆分", "high", "normal", "幂等：同一 uid+bizType+bizOrderNo 只扣一次。", [],
     wt_step("charge repeat", dict(action="CHARGE", bizOrderNo="{{wt_no}}", amount=1, **GEN),
             teardown=wt_state("CHARGED", "assert d.get('chargeTradeNo') == self.get_env_value('wt_trade'), '重复扣款应返回原台账：%s' % d"))),
    (W, "W07 重复扣款不再扣：coin 仍只减 1", "high", "normal", "", [],
     step("rich after repeat", "/api/user/rich", body(),
          teardown="d = response.json().get('data') or {}\nassert abs(float(self.get_env_value('wt_coin0')) - float(d.get('coin') or 0) - 1) < 0.01, '重复扣款多扣了：%s → %s' % (self.get_env_value('wt_coin0'), d.get('coin'))")),
    (W, "W08 CHARGE 同单换金额 → 14201 amount conflict", "medium", "exception", "", [],
     wt_step("charge conflict", dict(action="CHARGE", bizOrderNo="{{wt_no}}", amount=2, **GEN), asserts=code_assert(14201))),
    (W, "W09 QUERY 已扣的单 → 0 CHARGED", "medium", "normal", "", [],
     wt_step("query charged", dict(action="QUERY", bizOrderNo="{{wt_no}}", **GEN), teardown=wt_state("CHARGED"))),
    (W, "W10 REFUND → 0 REFUNDED，amount=1、有 refundTradeNo", "high", "normal", "按原拆分全额退回原币桶。", [],
     wt_step("refund", dict(action="REFUND", bizOrderNo="{{wt_no}}", reason="GENERATION_FAILED", **GEN),
             teardown=wt_state("REFUNDED", "assert d.get('refundTradeNo') and abs(float(d.get('amount') or 0) - 1) < 0.01, '退款台账不对：%s' % d"))),
    (W, "W11 退款后余额恢复：coin、bonus 都回到起点", "high", "normal", "", [],
     step("rich after refund", "/api/user/rich", body(),
          teardown="d = response.json().get('data') or {}\nassert abs(float(self.get_env_value('wt_coin0')) - float(d.get('coin') or 0)) < 0.01 and abs(float(self.get_env_value('wt_bonus0')) - float(d.get('bonus') or 0)) < 0.01, '退款后余额没恢复：%s/%s → %s/%s' % (self.get_env_value('wt_coin0'), self.get_env_value('wt_bonus0'), d.get('coin'), d.get('bonus'))")),
    (W, "W12 REFUND 重复 → 0 REFUNDED 原台账", "medium", "normal", "只退一次。", [],
     wt_step("refund repeat", dict(action="REFUND", bizOrderNo="{{wt_no}}", reason="GENERATION_FAILED", **GEN), teardown=wt_state("REFUNDED"))),
    (W, "W13 CHARGE 已退款的单 → 14202 trade closed", "medium", "exception", "", [],
     wt_step("charge refunded", dict(action="CHARGE", bizOrderNo="{{wt_no}}", amount=1, **GEN), asserts=code_assert(14202))),
    (W, "W14 REFUND 没扣过的单（退款先到）→ 0 CLOSED", "medium", "normal", "记 CLOSED，不动余额、不写流水。", [],
     wt_step("refund first", dict(action="REFUND", bizOrderNo="{{wt_no2}}", reason="GENERATION_FAILED", **GEN), teardown=wt_state("CLOSED"))),
    (W, "W15 CHARGE 已关单 → 14202", "medium", "exception", "", [],
     wt_step("charge closed", dict(action="CHARGE", bizOrderNo="{{wt_no2}}", amount=1, **GEN), asserts=code_assert(14202))),
    (W, "W16 CHARGE 100000 余额不足 → 14002", "high", "exception", "专用号余额远小于 100000。不建台账、不扣 Bonus。", [],
     wt_step("charge too much", dict(action="CHARGE", bizOrderNo="{{wt_no3}}", amount=100000, **GEN), asserts=code_assert(14002))),
    (W, "W17 余额不足不建台账：QUERY → NOT_FOUND", "medium", "normal", "", [],
     wt_step("query big", dict(action="QUERY", bizOrderNo="{{wt_no3}}", **GEN), teardown=wt_state("NOT_FOUND"))),
    (W, "W18 CHARGE REMIX_UNLOCK 1 → 0 CHARGED，bonus+paidCoin+giftCoin=1、回显 uid/bizType/bizOrderNo", "high", "normal", "Side-story 解锁：先扣 Bonus。不退款，每轮净花 1。", [],
     wt_step("charge unlock", dict(action="CHARGE", bizOrderNo="{{wt_no4}}", amount=1, **UNL),
             teardown=wt_state("CHARGED", "assert abs(float(d.get('bonus') or 0) + float(d.get('paidCoin') or 0) + float(d.get('giftCoin') or 0) - 1) < 0.01, '拆分不等于 amount：%s' % d\nassert d.get('uid') == self.get_env_value('uid') and d.get('bizType') == 'REMIX_UNLOCK' and d.get('bizOrderNo') == self.get_env_value('wt_no4'), 'REMIX_UNLOCK 应回显 uid/bizType/bizOrderNo：%s' % d"))),
    (W, "W19 解锁扣款先扣 Bonus：总余额减 1，bonus>0 时扣的是 bonus", "high", "normal", "", [],
     step("rich after unlock", "/api/user/rich", body(),
          teardown="d = response.json().get('data') or {}\nc0, b0 = float(self.get_env_value('wt_coin0')), float(self.get_env_value('wt_bonus0'))\nc1, b1 = float(d.get('coin') or 0), float(d.get('bonus') or 0)\nassert abs((c0 + b0) - (c1 + b1) - 1) < 0.01, '总余额应减 1：%s+%s → %s+%s' % (c0, b0, c1, b1)\nif b0 >= 1:\n    assert abs(b0 - b1 - 1) < 0.01 and abs(c0 - c1) < 0.01, '有 bonus 时应先扣 bonus：%s/%s → %s/%s' % (c0, b0, c1, b1)")),
    (W, "W19b 解锁历史：新版本（≥1010100）有 Side-story 解锁记录（标题 Special unlock），老版本没有（BUG-795）；lang=en_US", "high", "normal",
     "研发A 11-13 修复 e881c9b：/api/user/episode/unlock/history 带上 Side-story 解锁（cate 2003），标题固定英文「Side-story unlock」、不随语言变；11-17 同事定改「special unlock」，研发A d0102058（合同同提交）20:20 上测试服，已核 165/166 全部是 special unlock、seriesId / episodeId 为 0；11-18 同事定首字母大写，a971c85 改 Special unlock（已核 165/166）；只对客户端 build ≥ 1010100 返回。W18 刚做过一次解锁。", [],
     step("unlock history", "/api/user/episode/unlock/history", body(ps=50),
          teardown="items = (response.json().get('data') or {}).get('data') or []\nss = [x for x in items if x.get('cate') == 2003]\nif int(self.get_env_value('appBuild')) >= 1010100:\n    assert ss, '新版本应能看到 Side-story 解锁记录'\n    assert all([x.get('title') == 'Special unlock' and x.get('seriesId') == 0 and x.get('episodeId') == 0 for x in ss]), 'Side-story 记录标题 / seriesId / episodeId 不对：%s' % ss[:2]\nelse:\n    assert not ss, '老版本不应返回 Side-story 解锁记录：%d 条' % len(ss)")),
    (W, "W19c 解锁历史按语言：lang=ja_JP 时 Side-story 标题是日文译文、不是英文（ba0de46）", "medium", "normal",
     "研发A 11-17 21:05 ba0de461：标题按 App 语言显示，译文取多语言表服务端页第 19 行；表里没有的语言仍是英文。不写死译文（表会改），只断言非空、统一、不是英文。", [],
     step("unlock history ja", "/api/user/episode/unlock/history", body(ps=50, lang="ja_JP"),
          teardown="items = (response.json().get('data') or {}).get('data') or []\nss = [x for x in items if x.get('cate') == 2003]\nif int(self.get_env_value('appBuild')) >= 1010100:\n    ts = {x.get('title') for x in ss}\n    assert ss and len(ts) == 1, '日语下 Side-story 标题应存在且统一：%s' % ts\n    t = ts.pop()\n    assert t and t.lower() != 'special unlock', '日语下应返回译文：%r' % t\nelse:\n    assert not ss, '老版本不应返回 Side-story 解锁记录：%d 条' % len(ss)")),
    (W, "W19d 解锁历史按语言：表里没有的语言（zh_CN）回退英文 Special unlock（ba0de46 / a971c85）", "low", "normal",
     "同 W19c：简体中文不在多语言表里，回退英文。", [],
     step("unlock history zh", "/api/user/episode/unlock/history", body(ps=50, lang="zh_CN"),
          teardown="items = (response.json().get('data') or {}).get('data') or []\nss = [x for x in items if x.get('cate') == 2003]\nif int(self.get_env_value('appBuild')) >= 1010100:\n    assert ss and all([x.get('title') == 'Special unlock' for x in ss]), 'zh_CN 应回退 Special unlock：%s' % {x.get('title') for x in ss}\nelse:\n    assert not ss, '老版本不应返回 Side-story 解锁记录：%d 条' % len(ss)")),
    (W, "W20 REFUND REMIX_UNLOCK → 10101 action INVALID", "medium", "exception", "解锁后不退款。", [],
     wt_step("refund unlock", dict(action="REFUND", bizOrderNo="{{wt_no4}}", reason="GENERATION_FAILED", **UNL), asserts=code_assert(10101))),
    (W, "W21 action 非法 → 10101", "low", "exception", "", [],
     wt_step("bad action", dict(action="PAY", bizOrderNo="{{wt_no}}", **GEN), asserts=code_assert(10101))),
    (W, "W22 bizOrderNo 含非法字符 → 10101", "low", "exception", "只允许 [A-Za-z0-9_.:-]{1,64}。", [],
     wt_step("bad order no", dict(action="QUERY", bizOrderNo="at bad!", **GEN), asserts=code_assert(10101))),
    (W, "W23 CHARGE amount=0 → 10101", "low", "exception", "amount 1～100000。", [],
     wt_step("amount 0", dict(action="CHARGE", bizOrderNo="at-zero", amount=0, **GEN), asserts=code_assert(10101))),
    (W, "W24 CHARGE 缺 amount → 10101", "low", "exception", "", [],
     wt_step("no amount", dict(action="CHARGE", bizOrderNo="at-noamount", **GEN), asserts=code_assert(10101))),
    (W, "W25 REFUND 缺 reason → 10101", "low", "exception", "reason ^[A-Z0-9_]{1,32}$ 必填。", [],
     wt_step("no reason", dict(action="REFUND", bizOrderNo="at-noreason", **GEN), asserts=code_assert(10101))),
    (W, "W26 缺 uid → 10101", "low", "exception", "", [],
     wt_step("no uid", dict(action="QUERY", bizOrderNo="{{wt_no}}", bizType="REMIX_GENERATE"), asserts=code_assert(10101))),
    (W, "W27 bizType 非法 → 10101", "low", "exception", "只有 REMIX_GENERATE / REMIX_UNLOCK。", [],
     wt_step("bad biztype", dict(action="QUERY", bizOrderNo="{{wt_no}}", uid="{{uid}}", bizType="X"), asserts=code_assert(10101))),
]


# ---- 防刷（OPS-019，ae9b4b0；合同维护人 11-16 10:32 测试群要求补用例）
# 平台脚本沙箱发不了成批请求：run_suite.sh 每个环境开跑前由 anti_abuse_prep.py 造 3 个一次性游客号并刷到位，这里断言后立即冻结清理。
A = "P1-防刷"
AA = [dict(sid="{{aa_sid%d}}" % n, uid="{{aa_uid%d}}" % n, token="{{aa_token%d}}" % n) for n in (1, 2, 3, 4)]
LIMITED = [{"type": "status_code", "expected": 429, "mode": "hard"},
           {"type": "json_path", "path": "$.code", "expected": 10429, "mode": "soft"},
           {"type": "json_path", "path": "$.message", "expected": "TOO_MANY_REQUESTS", "mode": "soft"}]
CASES += [
    (A, "A01 1 分钟内看超过 50 部不同的剧 → 封：详情 HTTP 429 / 10429", "high", "exception",
     "前置 aa1 已在同一分钟看了 51 部不同的剧（第 51 次起 429）。封 24 小时，封后任何剧（含真实剧）的详情都打不开。", [],
     step("detail blocked minute", "/api/series/detail", body(seriesId="{{series}}", **AA[0]), asserts=LIMITED)),
    (A, "A02 被封只拦详情：user/info → 0", "medium", "normal", "限频只挂在 /api/series/detail。", [],
     step("user info while blocked", "/api/user/info", body(**AA[0]))),
    (A, "A03 当天看详情超过 200 次且一集没播 → 第 201 次 429 / 10429", "high", "exception",
     "前置 aa2 已无播放看了 200 次（都 0）。天按 UTC 换（北京 8 点），封 1 小时。", [],
     step("detail blocked daily", "/api/series/detail", body(seriesId="{{series}}", **AA[1]), asserts=LIMITED)),
    (A, "A04 有过播放：看详情第 201 次仍 → 0", "high", "normal",
     "前置 aa3 先 episode/play 一次再看了 200 次；当天有播放不按「200 次无播放」封。", [],
     step("detail with play", "/api/series/detail", body(seriesId="{{series}}", **AA[2]))),
    (A, "A05 正常账号刷详情不受影响：固定号 series/detail → 0", "high", "normal", "本轮固定号详情调用远低于阈值。", [],
     step("detail normal", "/api/series/detail", body(seriesId="{{series}}"))),
    (A, "A06 广告解锁超过单剧当天上限 → 14006 CODE_AD_UNLOCK_LIMIT", "high", "exception",
     "前置 aa4 对本剧按顺序广告解锁到撞限（上限 = 后台单剧次数×2，11-16 测试服 1000007 第 7 次撞限），这里对撞限那集再解锁一次。现在的包不认识 14006（两端表现由 QA 手测）。", [],
     step("ad unlock limit", "/api/episode/unlock", body(seriesId="{{series}}", cate=1, episodes='[{"episodeId":{{aa_ep4}},"sno":{{aa_sno4}}}]', **AA[3]),
          asserts=code_assert(14006))),
    (A, "A07 广告解锁按剧计数：换一部剧的第一集 → 0", "high", "normal", "单剧撞限不影响别的剧（全局上限只记日志不拦）。", [],
     step("ad unlock other series", "/api/episode/unlock", body(seriesId="{{aa_series4b}}", cate=1, episodes='[{"episodeId":{{aa_ep4b}},"sno":{{aa_sno4b}}}]', **AA[3]))),
] + [
    (A, f"A{7 + n:02d} 清理：立即冻结一次性游客号 aa{n} → 0", "medium", "normal", "被封只拦详情，冻结接口照常可用。", [],
     step(f"frozen aa{n}", "/api/v1/member/frozen", body(target="{{aa_uid%d}}" % n, cate=1, reason="at-anti-abuse-cleanup", **AA[n - 1])))
    for n in (1, 2, 3, 4)
]


def main():
    print("P1 用例", len(CASES))
    if "--dry-run" in sys.argv:
        for c in CASES:
            print(" ", c[0], "|", c[1])
        return
    flows = {f["name"]: f for f in items(f"/projects/{PID}/business-flows")}
    existing, order = {}, []
    for flow_name in sorted({c[0] for c in CASES}):
        f = flows.get(flow_name) or req("POST", f"/projects/{PID}/business-flows", {"name": flow_name, "description": "OPS-018 P1（只在测试服）"})
        flows[flow_name] = f
        existing.update({(flow_name, c["name"]): c for c in items(f"/projects/{PID}/api-test-cases?business_flow_id={f['id']}")})
    for flow_name, name, prio, ctype, desc, pre, request in CASES:
        meta = {"name": name, "business_flow_id": flows[flow_name]["id"], "description": desc, "priority": prio, "case_type": ctype, "tags": ["OPS-018", "P1"]}
        c = existing.get((flow_name, name))
        if c:
            req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}", meta)
        else:
            c = req("POST", f"/projects/{PID}/api-test-cases", meta)
        req("PUT", f"/projects/{PID}/api-test-cases/{c['id']}/case-data",
            {"case_data": {"name": name, "skip": False, "description": desc, "request": request, "preconditions": pre, "retry": 0}})
        order.append(c["id"])
    # 改过名的旧用例：P1 这几个流程里不在 CASES 的都删掉（平台和套件），避免过期用例留在套件里
    wanted = {(c[0], c[1]) for c in CASES}
    stale = [c for key, c in existing.items() if key not in wanted]
    for c in stale:
        req("DELETE", f"/projects/{PID}/api-test-cases/{c['id']}")
    if stale:
        print("删过期 P1 用例", [c["name"] for c in stale])
    suites = {s.get("code"): s for s in items(f"/projects/{PID}/api-suites")}
    reg = req("GET", f"/projects/{PID}/api-suites/{suites['regression']['id']}")
    stale_ids = {c["id"] for c in stale}
    cur = [it["case_id"] for it in sorted(reg["items"], key=lambda x: x["sort_order"]) if it["case_id"] not in stale_ids]
    full = [cid for cid in cur if cid not in order] + order   # P1 固定排在最后
    req("PUT", f"/projects/{PID}/api-suites/{reg['id']}/items", {"items": [{"case_id": cid, "sort_order": i, "enabled": True} for i, cid in enumerate(full)]})
    print("套件", reg["id"], "regression 挂", len(full), "条（P1", len(order), "）")


if __name__ == "__main__":
    main()
