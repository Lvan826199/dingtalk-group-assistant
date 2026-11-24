<!-- Author: 梦无矶 -->
# 接口自动化 + 测试平台：工作流程与脚本

本分支（`workflow/api-automation`）只放「服务端接口自动化」怎么和本平台（AiTestProject）配合跑的流程说明和脚本，不含平台代码。平台代码在 `master`。

凭据一律不进仓库：平台令牌、后台账号、Jira 账号、钉钉机器人密钥都在使用者本机 `~/.config/` 下；钉钉群和人员 ID 用环境变量或本机配置文件（见文末）。

## 一、整体链路

```
触发 ──► 探测 ──► 合同核对 ──► 回归（6 个环境）──► 发结果
```

1. **触发**：`scripts/at/watch.sh` 常驻，盯三件事：
   - 测试服换版（只记录，不单独触发回归）；
   - 定时回归：10:00 必跑；15:00、18:30 有新提交或合同变化才跑（`scheduled_round.sh`）；
   - Jira 新评论（`jira_watch.py`）。
   另外，群里有人要求、研发说合同改了，手动跑 `on_contract_change.sh`。
2. **探测**（`p0_probe.py`、`env_tokens.py`、`series_check.py`）：取测试服当前版本；各环境登录、把 uid / token 写进平台环境变量；检查测试用剧的「付费集 + 跳集」数据够不够，不够自动换剧。
3. **合同核对**（`platform_p0.py`）：从服务端仓库 `origin/dev` 取 `api/openapi/app-v1.yaml`，84 个接口在安卓、iOS 各真实调一遍，逐字段比对，对不上的写进「文档修正清单」；同时把最新用例同步挂到平台套件 72。
4. **回归**（`run_suite.sh`）：按环境逐个调用平台 `POST /api-suites/72/execute`，轮询 `/api-executions/{id}`，读日志统计。
5. **发结果**（`post_round.py`）：发测试群，@ QA 负责人和合同维护人；有新失败再 @ 本轮提交的研发。

## 二、`run_suite.sh` 的保护

| 保护 | 做法 |
|---|---|
| 同一时间只跑一轮 | 目录锁 `/tmp/qa-run_suite.lock`，已有一轮在跑就退出（`RUN_BUSY`），不排队撞车 |
| 测试服中途换版 | 每个环境开跑前、跑完各取一次测试服版本，变了就标「作废，需重跑」，不算失败 |
| 偶发失败 | 首跑有失败立即再跑一次，重跑通过的列为「偶发」，不算失败 |
| 防刷用例 | A01～A11 在平台上设了执行条件 `antiAbuseSwitch == 1` 和「不重试」（`aa_platform.py setup`）；每轮开跑前把测试服开关值同步进环境变量（`aa_platform.py sync`），开关关着时平台记「跳过」；10:00 那轮自己打开开关（`anti_abuse_switch.py`）照常跑、跑完关回 |
| 前置不足 | 账号 / 换剧准备失败直接 `PRECONDITION_BLOCKED` 退出，不计通过 |

## 三、失败怎么处理

1. **先排除自己这边**：用例写错、测试数据不对、前提不满足、测试服正在发版。能自己修的先修再重跑。
2. **代码对、合同错**：找合同维护人改合同。只改合同文件、不动代码、和接口自动化相关的，可以直接推 dev，推完在群里说一声。
3. **代码错**：直接提 Jira 缺陷（`jira.py`），附请求、返回、日志；群里贴单号、@ 对应研发、知会 QA 负责人。
4. **修复上测试服后复测**，结果回 Jira 和群里。

## 四、脚本清单

| 脚本 | 作用 |
|---|---|
| `at/watch.sh` | 常驻监视：测试服换版、定时回归、Jira |
| `at/scheduled_round.sh` | 定时轮（10:00 / 15:00 / 18:30） |
| `at/on_contract_change.sh` | 合同变化：探测 → 合同核对 → 回归 |
| `at/run_suite.sh` | 在平台执行套件并统计（见第二节） |
| `at/platform_p0.py` / `platform_p1.py` / … | 合同核对、生成并挂载平台用例 |
| `at/p0_probe.py` / `p0_report.py` / `schema_diff.py` | 真实调用与逐字段比对、出清单 |
| `at/env_tokens.py` / `series_check.py` / `topup.py` | 前置：登录写变量、换剧、补币 |
| `at/anti_abuse_prep.py` / `anti_abuse_switch.py` / `aa_platform.py` | 防刷前置、开关、平台执行条件与变量同步（`aa_items.py` 为旧的临时停用办法，已不用） |
| `at/post_round.py` | 回归结果发群 |
| `at/jira.py` / `jira_watch.py` | 提缺陷、看评论 |
| `send.sh` / `reply.sh` | 钉钉发消息 / 引用回复（成功后 `announce_sent.py` 通知本人并记操作台） |
| `notify_user.py` / `send_failed.py` | 调试群机器人通知本人、发送失败告警 |
| `guard.py` | 正式发布前核对本人在调试群的批准消息 |

## 五、本机配置（不进仓库）

| 位置 | 内容 |
|---|---|
| `~/.config/aitest/token` | 平台令牌 |
| `~/.config/app-admin/account.json` | 后台账号（防刷开关读写） |
| `~/.config/jira/account.json` | Jira 账号 |
| `~/.config/qa-workflow/people.json` | `{"姓名": "钉钉 openDingtalkId"}`，发群 @ 用 |
| `~/.config/qa-workflow/reco_at_ids.json` | 推荐侧回归要 @ 的人（JSON 数组） |
| 环境变量 `QA_TEST_GROUP` / `QA_COORD_GROUP` / `QA_NOTIFY_GROUP` | 测试群 / 协调群 / 调试通知群的会话 ID |

脚本里写死的平台地址、项目号（903）、套件号（72）和环境号（163～169）按自己的平台改。
