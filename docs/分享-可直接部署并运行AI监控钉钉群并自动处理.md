# 可直接部署并运行：AI 监控钉钉群并自动处理（全角色版）

> **使用者只需要做一件事：** 把这个文件拖进你自己的 AI 编程助手（Codex、Claude Code、DSH、WorkBuddy、Trae、Qoder 都行，你平时用哪个就用哪个），发一个字「开始」。之后它每一步都会给你编号选项，你回数字就行。
>
> 作者：梦无矶　版本：v2.7 2026-11-18（全部角色可用、角色职责库、协作库可选、支持 Windows / macOS / Linux；回复更短分行、别人之间的对话不插话、内置表情包、按群开关自动回复；待回复列表 / 暂存草稿 / 一键清空；后台静默、并行 + 子 Agent、少确认、读工作目录对话记录、每日汇报到自己私聊）　适用：Windows / macOS / Linux + 任一 AI 编程助手（Codex / Claude Code / DSH / WorkBuddy / Trae / Qoder 等）+ 钉钉 CLI（`dws`）
>
> **已经装过的同事升级到 v2.7**：把本文件拖进你的 AI 助手，发「升级到 v2.7」。它只替换 `C:\qa-agent\agent.py` 和 `bootstrap_memory.py`（用第三节 3.2、3.3 的代码），`C:\qa-agent\角色职责库.json` 没有就按 3.5 写入、已有就不覆盖，**不改** `config.json`、`memory\`、`drafts\`、`工作手册.md`。**升级不能覆盖你已有的规则**：AI 助手先把新规则（v2.7 按角色补齐的工作手册段落；v2.6 回复 1～3 行分行、别人之间的对话不插话、群聊默认只提醒、表情默认关）和你的 `工作手册.md`、`memory\偏好与禁区.md`、`config.json` 逐条对比，有冲突的一条条问你选，你没选的保持原样。然后运行 `python C:\qa-agent\agent.py stickers`（下载表情包索引）和 `python C:\qa-agent\bootstrap_memory.py`（重建记忆草稿：旧版读错了发送者姓名，会把人认错），确认草稿后重启助手，运行 `python C:\qa-agent\agent.py check` 看到「版本 v2.7」就好了。助手启动后如果你原来有自动回复的群，会在提醒群问你「保持现状 / 全部只提醒」，没回之前照旧。

---

## 平台约定（Windows / macOS / Linux 通用，部署的 AI 先按本机系统换算）

下文的路径和命令**以 Windows 写法为例**。部署的 AI 第 0 步先判断本机系统，之后所有路径、命令都按这张表换算再执行。**用 `python` 还是 `python3`、装在哪个目录，都由 AI 自己按本机情况定，不问使用者**（很多同事不懂这些）：

| 项 | Windows | macOS | Linux |
|---|---|---|---|
| 安装目录（下文的 `C:\qa-agent`） | `C:\qa-agent` | `~/qa-agent`（**不要放桌面 / 文稿 / 下载**：系统隐私保护会让后台任务读不到） | `~/qa-agent` |
| 配置目录（`%USERPROFILE%\.qa-agent`） | `%USERPROFILE%\.qa-agent` | `~/.qa-agent` | `~/.qa-agent` |
| Python 命令（下文的 `python`） | `python`；后台运行用 `pythonw`（不弹窗口） | `python3` | `python3` |
| 路径分隔 | `\` | `/` | `/` |
| 开机 / 每天自启（第 6 步） | 计划任务（3.4 A） | LaunchAgent（3.4 B） | systemd 用户服务 + 定时器（3.4 C） |
| 终端 | PowerShell | 终端 | 终端 |

- macOS / Linux 没有「弹窗口」的问题，后台由 launchd / systemd 托管，日志在安装目录的 `logs/`。
- **AI 编程助手是使用者自己在用的那个**（Codex、Claude Code、DSH、WorkBuddy、Trae、Qoder 等），账号、API Key 等都由使用者自己配，不在部署范围内。部署时 AI 助手把**自己是哪个工具**写进 3.1 的 `ai`，助手以后判断消息就用它；没写时自动用本机装了的第一个。
- 钉钉 CLI、Git、Node 三个平台都能装；缺哪个按官方说明装（第 0 步会问你要不要帮你装）。

---

## 〇、给 AI 助手的指令（收到本文件后立刻照做，不用等使用者再解释）

你是同事的部署助手（产品、研发、测试、运营、后台、项目负责人都可能来装）。按第二节「部署流程」从第 0 步开始执行，规则如下：

1. **能自己查的不问**：环境、钉钉身份、所在部门、群 ID、项目里的同事角色，都用命令自己查。
2. **要问就给编号选项**：每次只问一个问题，列成 `1. … 2. … 3. …`，第一项放推荐选项并标「（推荐）」，让使用者回数字。多选时说明「回多个数字，用空格隔开，如 1 3 5」。只有实在没法列选项时才让使用者打字，而且只要一个词或一个名字。
3. **每步做完说一句结果**，再问下一个问题；不要一次抛出很多问题或大段说明。
4. **不碰凭据**：不索要、不代填任何账号密码；钉钉没登录就让使用者自己扫码。
5. **只读的东西不改**：项目协作库（如果有）只 `clone` / `pull`，不 commit、不 push、不改文件。
6. **默认**：先明确职责范围、确认通知 / 自动回复规则才生效（没确认前只写草稿）；自动模式（第一次安装时请使用者确认，以后可改）；**绝不替使用者接需求、任务、排期**、不读私聊；监听的群按角色推荐、由使用者确认，新装默认只提醒不回复；一次收到很多消息时自动开子 Agent 并行处理。
8. **每天上班自动汇报**：每天第一次启动（9 点后）把前一天的总结发到使用者的提醒群（机器人发，有推送）；钉钉监听连续断开 3 次会提醒本人。
9. **全程后台静默**：运行用 `pythonw`，所有子进程隐藏窗口，提醒只走本人专属提醒群的机器人；部署和验收时都不要弹出命令行窗口。
7. 第三节是你要写入的文件全文，第四节是写进工作手册的规则；按里面的内容原样写入，命令参数以本机 `--help` 为准，对不上就按本机实际调整，并在最后的汇报里说明改了什么。

---

## 一、风险（第 1 步要给使用者看的摘要）

| 风险 | 本方案怎么控制 |
|---|---|
| 提醒群机器人的地址和密钥 | 只存在你本机 `config.json`；这个机器人只能往你自己的提醒群发消息，泄露了也只能往那个群发；不放心可以随时在群设置里重置 |
| 助手替你接了别人的需求 | 部署第 2.6 步先明确你的职责范围、确认规则；派活、要你负责、要排期的一律不答应、交给你；没确认前只写草稿 |
| 回复是以你本人的钉钉账号发出的 | 第一次安装让你选：自动模式（默认，能回的直接回、拿不准交给你）或草稿模式（全部等你确认）；随时可以切换 |
| AI 可能理解错、说错 | 只处理你选中的群和你的工作范围；拿不准就交给你，不猜 |
| 群消息会发给外部 AI 模型服务 | 只监听你选中的群，私聊默认不读；请确认团队允许这样用 |
| 误操作 | AI 在只读模式里只出主意，真正发消息的是脚本，而且只能发到你允许回复的群 |
| 刷屏、自问自答 | 不处理自己和机器人的消息；每 10 分钟最多自动回 3 条 |
| 电脑关机或睡眠、钉钉登录过期会漏消息 | 开机自动拉起；钉钉监听连续断开 3 次弹通知提醒你重新登录；每天上班的汇报里写出前一天的异常次数 |

---

## 二、部署流程（AI 助手执行，使用者回数字）

### 第 0 步　环境检查（AI 助手自己做，不问人）

先判断本机系统（Windows / macOS / Linux），按「平台约定」换算后续命令。依次检查（`dws` 再跑一次 `dws upgrade --check`，有新版本就问使用者要不要 `dws upgrade -y`，旧版本可能和钉钉服务端对不上、消息发不出去）：`python --version`（macOS / Linux 用 `python3 --version`，3.10+）、`node --version`、`git --version`、`dws auth status`；再确认**正在执行部署的这个 AI 工具（就是你自己）有命令行、能在后台跑一次就退出**，并把自己是哪个工具写进 config.json 的 `ai`（Codex `codex exec`、Claude Code `claude -p`、DSH `dsh --profile headless`、WorkBuddy `codebuddy -p`、Qoder `qodercli -p`；Trae 等其他工具按它的 `--help` 找非交互参数，写进 3.1 的 `ai_cmd`）。AI 工具本身的安装、账号、API Key 都是使用者自己的事，不检查、不过问。

- 全部正常、`dws auth status` 显示 `"authenticated": true` → 直接进第 1 步。
- 缺什么就问：
  ```
  缺少 <xxx>，怎么处理？
  1. 我来帮你装（推荐）
  2. 我自己装，装好回 1 继续
  ```
- 钉钉没登录：
  ```
  钉钉 CLI 还没登录，需要你自己扫码：
  1. 我已在终端运行 dws auth login 并扫码完成（推荐）
  2. 先跳过，稍后再说
  ```

### 第 1 步　风险确认

把第一节表格念给使用者，然后问：

```
上面这些风险你能接受吗？
1. 能接受，后面全部按推荐一次装好，不再逐项问我（推荐）
2. 能接受，但后面每一步我想自己选
3. 先不部署
```

选 1：第 2–6 步取推荐项、不再逐项提问，只问这几种情况：**必须本人操作**（钉钉扫码、GitHub 权限、建提醒群机器人）、**认不出身份**、**第 2 步角色职责的二次确认**、**第 2.6 步职责范围和回复规则**（第一次安装必须本人确认）；最后一次性汇报装了什么。选 3 就结束。

### 第 2 步　认出你是谁、确定你的角色职责（协作库可选）

**2.1 有没有项目协作库**（问）：
```
你所在的项目有协作库（记录需求单、角色和负责人的 Git 仓库）吗？
1. 有（回仓库地址）
2. 没有 / 不清楚，先不用
```
- 选 1：自动 `git clone <地址> C:\qa-agent\project-coordination`（文件夹名固定叫 project-coordination，别的项目的协作库也放这里；已存在就 `git pull --ff-only`）。拉不下来（没权限、没登录 GitHub）时问：`1. 我去登录 / 申请权限，好了回 1 重试（推荐） 2. 先不用协作库`。
- 选 2 或拉不下来：跳过，后面全部用**角色职责库**（`C:\qa-agent\角色职责库.json`，第三节 3.5 原样写入）。

**2.2 认出你是谁**（自动）：`dws contact user get-self --format json` 取姓名和部门。有协作库时，再在协作库的人员登记（如 `registry\identities.json`）里按姓名找你的 `person_id` 和 `roles`，角色中文名按协作库的角色登记（如 `registry\roles.yaml`）念。

**2.3 确定角色职责**（分两种情况）：

**A. 协作库里有你的角色和职责** → 读出来展示，你决定：
```
从协作库读到：<姓名>，部门 <部门>，角色 <角色中文名>
这个角色的职责（协作库 + 角色职责库对应条目）：
- 关注：……
- 有依据时可以直接回答：……
- 一律交给你：……
1. 就按这个（推荐）
2. 我要改 / 补充（回一句话）
3. 角色不对，从角色职责库重新选
```

**B. 没有协作库，或协作库里没有你的角色 / 职责** → 从角色职责库选：
```
请选你的角色（可多选，回多个数字，用空格隔开）：
<按角色职责库「角色」列表编号，一行一个「编号. 名称：关注的前两项」>
<最后一项> 都不是（回一句话说你负责什么，我按你的话新建一条）
```
选好后逐个展示该角色的「关注 / 可以直接回答 / 一律交给本人」（库里写得不全的，AI 助手先按协作库和你说过的话自行补一版，标「AI 补充」），让你**修改、补充**：
```
<角色名>：
- 关注：……
- 有依据时可以直接回答：……
- 一律交给你：……
1. 就这样（推荐）
2. 我要改（回一句话，如「可以直接回答里加：线上告警归谁」）
3. 去掉这个角色
```

**2.4 二次确认**（两种情况都要）：把最终的角色和职责完整念一遍：
```
最终确认：你的角色是 <…>，助手按下面的职责判断消息归不归你：
<每个角色一段：关注 / 可以直接回答 / 一律交给你>
确认后写进你的工作手册，以后改也可以对 Codex 说。
1. 确认写入
2. 还要改
```
- 选 1 才写：每个角色一段写进 `工作手册.md` 的「按角色」一节（注明来源：协作库 / 角色职责库 / 本人补充，和日期）；`config.json` 的 `roles` 写角色 id。
- 本人在 2.3 里改过、或新建的角色，同时问一句：`要不要把这次的改动也存进你的角色职责库，下次选角色时直接用？ 1. 存（推荐） 2. 不存`。
- 有协作库、但协作库登记的角色和本人选的不一致时，以本人选的为准，并在最后的汇报里提一句「协作库登记的是 X，建议找项目负责人更新」。

**2.5 负责哪个项目**（问）：`1. <协作库对应的项目名>（推荐） 2. 其他（回一个项目名）`；没有协作库时直接问项目名。

### 第 2.6 步　明确你的职责范围，并确认什么时候通知你、什么时候自动回复（必做，选「全部按推荐」也要做）

助手只替你处理职责范围内的事，**绝不替你接别人的需求、任务、排期**。这一步做完并经你确认，自动回复才会生效；没确认前只写草稿。

**1）从协作库读（AI 助手自动；第 2 步没用协作库就跳过这一小步，只用第 2 步确认的角色职责 + 你在 2）里补充的事项）**，在 `C:\qa-agent\project-coordination\` 里：
- `registry\identities.json`：你的 `person_id`、角色；
- `features\*\feature.yaml`、`team-requests\**\request.yaml`：找出 Lane 负责人 / 确认人 / QA / 验收 / 负责人里写了你的单（按 `person_id` 或姓名搜），记单号、标题、状态；
- `node tools\todo-report.mjs --ref WORKTREE --person <你的姓名>`：你名下还没完成的待办；
- 这些单里常和你打交道的研发 / 产品（单里的 Lane 负责人、确认人）。

整理成这样念给你：

```
从协作库读到你的职责范围：
- 角色：服务端（示例；按你的实际角色念）
- 负责的需求单：REQ-001 订阅规则迁移（服务端）、REQ-002 评论改版（服务端）……
- 常对接的人：同事 A（服务端）、同事 B（后台）……
- 名下待办：3 条（P1 2 / P2 1）
```

**2）你补充（回数字）**

```
有没有要补充或去掉的？
1. 没有，就这些（推荐）
2. 我要补充（回一句话，如「还负责 064 的二创测试」）
3. 我要去掉（回要去掉的单号）
```

**3）你确认职责范围**

```
<最终的职责范围清单>
1. 确认（推荐）
2. 还要改
```

确认后写进 `memory\职责范围.md`（每条带「来源：协作库 / 本人补充」和日期），以后助手每次判断都会带上它。

**4）确认通知和自动回复的规则**

```
助手以后这样处理和你有关的消息：

【自动回复，并在提醒群告诉你回了什么】
- 职责范围内、记忆或协作库里有明确依据的事实问题（如「067 测到哪了」「这个单谁在测」）
- 别人回了你之前问的事 → 回「收到，谢谢」
- 拿不准的先回「收到，我确认一下再回复」

【不回复，在提醒群通知你处理】
- 派活、找你接新需求、让你负责、问你能不能做、问什么时候完成 —— 一律不替你答应
- 要你拍板、排期、承诺上线或测试时间
- 涉及线上、数据、权限、费用
- 不在你职责范围内的事
- 没有依据、看不懂的

【不处理】
- 和你无关、没 @ 你、不含你关注的关键词的消息

回复模式：
1. 自动模式：按上面的规则，能回的直接回（推荐）
2. 草稿模式：能回的也先写草稿，在提醒群等你说「可以发送」
3. 规则还要改（回要改的地方）
```

选 1 或 2 后，把 `mode` 写进 `config.json`，并设 `"scope_confirmed": true`；规则原文写进 `工作手册.md` 的「通知与自动回复规则」一节。选 3 就按使用者的话改规则，再问一次。

### 第 3 步　确认要监控的群（按角色推荐，回数字确认）

1. 自动：按第 2 步确认的角色，取角色职责库里的「推荐监控的群」（如「项目协作群」「测试群」）。部署时问一句「你们的<项目协作群>叫什么？回群名」。都用 `dws chat +chat-search --query "<群名>" --format json` 查 `openConversationId`；搜不到说明你不在群里，告诉你「你还不在 <群名>，请先找群主拉你进群」，只用搜到的继续。
2. 问：
   ```
   助手推荐监控这些群：<群名 + 用途，一行一个>
   新装的助手在群里默认只提醒你、不回复；哪个群要自动回复，装好后在提醒群发「群名 自动回复」再二次确认。
   1. 就这些（推荐）
   2. 还要再加别的群
   3. 去掉其中一个（回群名）
   ```
3. 选 2 时，再问一次「回群名，一个就行」，查到后问 `1. 以后可能要自动回复 2. 只看，永远不回复`，可以重复加。
4. 自动：选「以后可能要自动回复」的写进 `config.json` 的 `groups`，只看的写进 `readonly_groups`；`auto_reply_groups` 保持空（全部只提醒）。各群用途写进 `memory\角色.md` 的「各群用途」。

### 第 3.5 步　建你自己的提醒群机器人（必做，约 2 分钟）

所有提醒（需要你处理、草稿待确认、已处理、每日汇报、监听异常）都由这个机器人发到一个只有你自己的群里：钉钉有推送，消息有历史记录可翻。

AI 助手先说明步骤：

1. 钉钉电脑端：发起群聊，随便拉一位同事建群，建好后把他移出群，只留你自己；群名建议「<你的名字> 的助手提醒」。
2. 群设置 → 机器人 → 添加机器人 → 自定义（通过 Webhook 接入）→ 安全设置勾选「加签」，复制下面那串 `SEC…` 开头的密钥。
3. 点完成后复制 Webhook 地址（`https://oapi.dingtalk.com/robot/send?access_token=…`）。

然后问：

```
1. 建好了，我把 Webhook 地址和 SEC 密钥发给你（推荐）
2. 我现在不方便，稍后再说（提醒会先记在 C:\qa-agent\待处理.md，补好后才有推送）
```

选 1：使用者把地址和密钥发过来后，AI 助手只写进 `%USERPROFILE%\.qa-agent\config.json` 的 `webhook` / `secret`，**不写进其他任何文件、不回显完整密钥**；再问一句「提醒群叫什么名字？」，用 `dws chat +chat-search --query "<群名>"` 查到它的 `openConversationId` 写进 `notify_group`（助手会监听这个群里本人的回复来处理草稿）；然后发一条「🧪 助手自检」，问使用者 `1. 收到了 2. 没收到`。没收到就让使用者核对地址、是否勾了「加签」。

### 第 4 步　建记忆（读历史会话）

```
要不要读这些群的历史消息，帮你整理「什么事找谁」「以前的问题怎么处理的」？（这个工作目录下的 Codex 对话记录默认都会读）
1. 读最近 30 天（推荐）
2. 读最近 7 天
3. 不读，从今天开始积累
```

选 1 或 2 时运行 `python C:\qa-agent\bootstrap_memory.py <天数>`。脚本会：
- 用协作库 `identities.json` 预填同事和角色（谁是 server / android / ios / 产品 / 运维 / QA）；
- 用 `features\*\feature.yaml` 里的负责人预填「需求单 → 负责人」；
- 读群历史，再读**你打开 AI 助手的这个工作目录下的全部 Codex 对话记录**（认 Codex 和 Claude Code 的会话记录；DSH、WorkBuddy 等其他工具的先跳过）（默认就读，路径记在 `config.json` 的 `workspace`），提炼负责人、问题处理、你说过的规矩，写成草稿。

然后问：

```
记忆草稿已生成：负责人 <N> 条、问题处理 <N> 条、你的规矩 <N> 条。
1. 我大致看一眼摘要就行，没问题就启用（推荐）
2. 我要逐条看
3. 先不启用，草稿留着
```

选 1 时把每份草稿的前 10 条念给使用者，再确认一次 `1. 启用 2. 不启用`。启用 = 把 `*.draft.md` 改名为正式文件。

### 第 5 步　关注的关键词和同事（选择题）

自动生成建议：你的姓名、你负责项目的单号前缀（从协作库 `registry\ids\` 读）、你常被 @ 的话题；同事从协作库里和你同项目的研发、产品中选。然后问：

```
助手会关注这些关键词：<列表>
和这些同事的消息：<列表>
1. 就这样（推荐）
2. 我想加几个（回要加的词或人名，空格隔开）
3. 我想去掉几个（回编号）
```

### 第 6 步　开机 / 每天自启

```
要不要设置每天自动启动（9:00 和开机登录时拉起，21:00 自动退出）？
1. 要（推荐）
2. 暂不，我手动运行 python C:\qa-agent\agent.py（macOS / Linux：python3 ~/qa-agent/agent.py）
```

选 1 时按本机系统用第三节 3.4 对应的做法：Windows 计划任务（A）、macOS LaunchAgent（B）、Linux systemd 用户服务（C）。

### 第 7 步　验收并汇报（AI 助手自己做）

逐项检查并把结果用 ✅ / ❌ 列给使用者：

1. 能收到选中群的消息（让使用者在某个群里 @ 自己或发一个关键词，看 `logs\<日期>.log` 出现「决定」）
2. 无关消息不进 `inbox.jsonl`，自己发的消息不触发
3. 提醒群收到「📝 #编号 草稿待确认」，`python C:\qa-agent\agent.py review` 能列出草稿、回编号发出
4. 运行期间**没有任何命令行窗口弹出**（`python C:\qa-agent\agent.py check` 全部 ✅）
5. 需要人处理的事在提醒群收到机器人消息「🔔 #编号 需要你处理」
6. `memory\职责范围.md` 存在、`config.json` 里 `scope_confirmed` 为 true；让同事在群里 @ 你「这个需求你来测一下吧」，助手**不答应**，提醒群收到「🔔 需要你处理」
7. 计划任务存在、用的是 pythonw、到 21:00 进程自己退出（选了自启时）
8. 日志里没有任何 token
9. 提醒群收到「🧪 助手自检」和「☀️ 每日汇报」（第一次部署当天汇报内容是「还没有前一天的总结」）

最后告诉使用者：「部署完成。日常对我说下面这些话就行」，并把第五节「日常用法」贴给他。

---

## 三、AI 助手要写入的文件

目录结构：

```
C:\qa-agent\
  agent.py                 监听 + 过滤 + 决策 + 执行 + 记忆
  bootstrap_memory.py      首次建记忆
  工作手册.md               第四节内容
  project-coordination\      项目协作库（只读）
  memory\                  角色 / 负责人 / 问题处理 / 偏好与禁区 / 每日总结
  logs\  drafts\  history\
  inbox.jsonl  待处理.md
%USERPROFILE%\.qa-agent\config.json   个人配置（不放进 C:\qa-agent，不外传）
```

### 3.1 config.json（第 2–6 步自动填）

```json
{
  "my_name": "",
  "person_id": "",
  "roles": [],
  "project": "",
  "groups": {},
  "readonly_groups": {},
  "keywords": [],
  "people": [],
  "listen_dm": false,
  "workspace": "部署时 Codex 自动填：使用者打开 Codex 的目录",
  "mode": "auto",
  "max_auto_replies_per_10min": 3,
  "daily_codex_limit": 300,
  "workers": 2,
  "merge_seconds": 20,
  "burst_threshold": 3,
  "max_workers": 4,
  "ai": "",
  "ai_model": "",
  "ack_on_escalate": true, "notify_group": "<提醒群 openConversationId，Codex 自动查>",
  "webhook": "",
  "secret": "",
  "window": ["09:00", "21:00"],
  "auto_reply_groups": [],
  "emoji": false
}
```

`mode`：auto（默认）= 能回的直接回，拿不准的交给你；draft = 全部写草稿，你确认才发。第一次安装时问你选哪个，以后对 AI 助手说「切到草稿模式 / 自动模式」随时改。`workers` 是常驻几个处理通道；一次收到很多消息、待处理超过 `burst_threshold` 批时，会临时开子 Agent（多开 AI 处理通道，最多 `max_workers` 个，处理完自动退出）；`merge_seconds` 是同一会话多少秒内连发合并成一次判断，`ai`（v2.7）：判断用哪个 AI，`codex` / `claude` / `dsh` / `codebuddy`（WorkBuddy）/ `qoder`，不填就自动用本机装了的第一个；Trae 等其他工具填 `ai_cmd`（命令数组，用 `{prompt}` 占位或配 `"ai_prompt": "stdin"` 从标准输入传）。`ai_model` 可填一个更快的模型名（旧配置的 `codex_model` 仍然有效）。`webhook` / `secret` **必填**：本人专属提醒群里自定义机器人的地址和加签密钥（第 3.5 步建），所有提醒、草稿、每日汇报都由它发。`auto_reply_groups`（v2.6）：哪些群允许自动回复，**新部署一律留空 = 所有群只提醒不回复**；以后本人在提醒群发「群名 自动回复」+「确认开启 群名」二次确认才加进来。`emoji`（v2.6）：表情默认关，本人在提醒群发「表情 开」才开；部署最后跑一次 `python agent.py stickers` 下载内置表情包索引。

### 3.2 agent.py（v2：后台静默、并行 + 子 Agent、合并、两种模式）

```python
"""群消息助手 v2（Windows / macOS / Linux，后台静默；v2.7 起不限 QA，按协作库角色适配全部角色）：dws 长连接监听 → 过滤 → AI 只读决策（Codex / Claude Code / WorkBuddy / Qoder / Trae 等，使用者自己装的那个）→ 脚本执行 → 记忆追加。
v2（2026-11-13）：全程不弹窗口（pythonw + 子进程隐藏 + 系统通知）；两路并行处理、同会话 20 秒内连发合并一次判断；
积压时自动开子 Agent（临时多开 Codex 处理通道，最多 max_workers 个，空了自动退出）；
每天上班把前一天总结发到本人自己的钉钉私聊；钉钉监听连续断开会提醒本人；
v2.7（梦无矶 11-18）：不限 QA——部署时按协作库 registry\roles.yaml 认全部角色（产品、Android、iOS、H5、网页版、服务端、剧中台、推荐、测试、运营、后台 UI、项目负责人），工作手册每个角色一段规则；名字改为「群消息助手」。
v2.6（梦无矶 11-18）：回复更短、分行（每条 1～3 行，几件事一行一件；发出前把换行统一变成空行，钉钉单个换行会连成一坨）；
  别人之间的对话不插话：消息 @ 的是别人、没 @ 本人，代码层直接不回，也不打扰本人。
  表情（一位同事提议，梦无矶 11-18 测过同意）：开关默认关，提醒群发「表情 开 / 关」切换。开了以后可以给消息点原生表情（白名单），也可以发内置表情包：
  ChineseBQB 开源表情包里 21 个可爱动物 / 卡通 / 程序员包，只留文件名有含义、去掉粗口暧昧的（约 890 张），走 jsDelivr 国内能看；钉钉只显示第一帧。
  按群开关自动回复（梦无矶 11-18 定）：新部署群聊默认只提醒、不回复；从旧版升上来不改原设置，启动时在提醒群问本人「保持现状 / 全部只提醒」；提醒群发「<群名> 自动回复」再回「确认开启 <群名>」二次确认后才开；
  「<群名> 只提醒」立即关；「群列表」看状态。写回 config.json，不用重启。表情也默认关，本人自己发「表情 开」才开。
  每人不用配置：python agent.py stickers 下载索引到 memory\表情包.json（部署时 Codex 跑）；提醒群「表情包」看张数，「删表情包 名字」拉黑。
v2.5.1：不确定是不是归本人的事，群里一个字都不回，只在提醒群问本人「是否归你」；「收到，我确认一下再回复」只在明确 @ 本人、且确定归本人时才回。
v2.5（一位同事试用后提议）：提醒群「待回复」看全部没处理完的事（含暂存草稿）；「清空」一键清掉待回复；「#编号 暂存：…」只存草稿不发，之后「#编号 可以发送」再发。
v2.4：部署先明确职责范围（协作库读取 → 本人补充 → 本人确认）并确认通知 / 自动回复规则；没确认前只写草稿；派活、要负责、要排期、要承诺、超出职责范围的一律交给本人，绝不替本人接。
v2.3：自动回复后在提醒群发「💬 已自动回复」；草稿发到提醒群，监听本人在提醒群里的回复：「#编号 可以发送」发出、「#编号 不发」作废、「#编号 改成：…」按改后的发出。
v2.2：提醒只走本人专属群的机器人（Webhook + 加签，必配）：交给本人的事、草稿待确认、处理完成、监听异常、每天上班汇报都发进这个群，有推送、有历史；
交给本人时先引用回复对方「收到，我确认一下再回复」；本人在该会话亲自回复 / review 发出或删除草稿后，机器人群里补一条「已处理」；status 命令看当天处理情况。
只带相关记忆进提示词；两种模式：auto（默认，能回的直接回、拿不准交给本人）/ draft（全部写草稿等确认）；review 命令批量确认草稿。
用法：pythonw agent.py            后台运行（Windows 计划任务这样启动；macOS / Linux 用 python3，由 launchd / systemd 托管）
      python agent.py review     列出草稿，回编号批量发送 / 删除
      python agent.py send <草稿> 发送一条草稿
      python agent.py check      自检（环境、登录、配置）
      python agent.py status     今天处理了多少、还有几件没处理
      python agent.py clear      清空待回复（没处理完的事和草稿全部清掉，不发出）
      python agent.py stickers   下载 / 更新内置表情包索引（v2.6）
配置 ~/.qa-agent/config.json（Windows 是 %USERPROFILE%\\.qa-agent\\config.json）；记忆在安装目录的 memory/（Windows C:\\qa-agent\\memory\\，macOS / Linux ~/qa-agent/memory/）。"""
import atexit, base64, datetime as dt, glob, signal, hashlib, hmac, json, os, queue, re, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request

VERSION = "v2.7 2026-11-18"
HOME = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(os.path.expanduser("~"), ".qa-agent", "config.json")
DEFAULTS = {"my_name": "", "person_id": "", "roles": [], "project": "", "groups": {}, "readonly_groups": {}, "keywords": [], "people": [],
            "listen_dm": False, "mode": "auto", "max_auto_replies_per_10min": 3, "daily_codex_limit": 300, "workers": 2, "merge_seconds": 20,
            "burst_threshold": 3, "max_workers": 4, "ack_on_escalate": True, "notify_group": "", "scope_confirmed": False,
            "codex_model": "", "webhook": "", "secret": "", "window": ["09:00", "21:00"],
            "emoji": False, "emoji_names": ["赞", "OK", "收到", "谢谢", "辛苦了", "加油", "鼓掌"]}
CFG = {**DEFAULTS, **json.load(open(CFG_PATH, encoding="utf-8"))}
COORD = os.path.join(HOME, "project-coordination")
MEMDIR = os.path.join(HOME, "memory")
for d in ("logs", "drafts", "memory"):
    os.makedirs(os.path.join(HOME, d), exist_ok=True)

# ---- Windows 下所有子进程都不弹窗口
NOWIN = {}
if os.name == "nt":
    si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
    NOWIN = {"creationflags": 0x08000000, "startupinfo": si}          # CREATE_NO_WINDOW


def which(name):
    return shutil.which(name) or shutil.which(name + ".cmd") or shutil.which(name + ".exe") or name


DWS, GIT, NODE = which("dws"), which("git"), which("node")

# ---- 判断用的 AI（v2.7：不限 Codex）。使用者自己选、自己装；config 里 "ai" 指定，不指定就用本机装了的第一个。
# 都用只读 / 计划模式跑一次就退出；prompt 长的走 stdin（Windows 命令行长度有限）。参数以本机 --help 为准，对不上用 ai_cmd 自定义。
AI_PRESETS = {
    "codex": {"name": "Codex", "bin": "codex", "args": ["exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", "{out}"], "prompt": "arg", "model": ["-m"]},
    "claude": {"name": "Claude Code", "bin": "claude", "args": ["-p", "--permission-mode", "plan", "--output-format", "text"], "prompt": "stdin", "model": ["--model"]},
    "codebuddy": {"name": "WorkBuddy / CodeBuddy", "bin": "codebuddy", "args": ["-p", "--output-format", "text"], "prompt": "stdin", "model": ["--model"]},
    "qoder": {"name": "Qoder", "bin": "qodercli", "args": ["-p", "-o", "text"], "prompt": "stdin", "model": ["--model"]},
    # DSH（DeepSeek Harness）：官方 headless 模式「答一个任务就退出」，任务从 stdin 读（参数 -）；没有只读开关，提示词只要它输出 JSON，执行都由脚本做
    "dsh": {"name": "DSH", "bin": "dsh", "args": ["--profile", "headless", "-"], "prompt": "stdin", "model": []},
}


def ai_engine():
    """返回 (显示名, 参数模板, prompt 传法)。ai_cmd 自定义优先（如 Trae：部署时按 traecli --help 填），其次 ai 指定的，最后自动找本机装了的。"""
    if CFG.get("ai_cmd"):
        return CFG.get("ai", "自定义"), list(CFG["ai_cmd"]), CFG.get("ai_prompt", "stdin")
    names = [CFG["ai"]] if CFG.get("ai") in AI_PRESETS else list(AI_PRESETS)
    for k in names:
        pr = AI_PRESETS[k]
        exe = which(pr["bin"])
        if shutil.which(exe) or os.path.exists(exe):
            model = CFG.get("ai_model") or CFG.get("codex_model")
            return pr["name"], [exe] + pr["args"] + ((pr["model"] + [model]) if model and pr["model"] else []), pr["prompt"]
    return "（没找到）", [], "stdin"


def ai_exec(prompt, timeout=300):
    """跑一次 AI，返回它的最后输出文本；找不到 / 失败返回空串。"""
    name, args, how = ai_engine()
    if not args:
        log("没找到可用的 AI 命令行（codex / claude / codebuddy / qodercli / dsh）"); return ""
    out = os.path.join(HOME, "logs", f"ai-{threading.get_ident()}-{time.time_ns()}.txt")
    args = [out if a == "{out}" else a for a in args]
    if how == "arg":
        args = [prompt if a == "{prompt}" else a for a in args] if "{prompt}" in args else args + [prompt]
    r = run(args, cwd=HOME, timeout=timeout, **({"input": prompt} if how == "stdin" else {"stdin": subprocess.DEVNULL}))
    text = open(out, encoding="utf-8").read() if os.path.exists(out) else (r.stdout or "")
    if os.path.exists(out):
        os.remove(out)                                                     # 以前固定文件名：这次失败会读到上次的结果
    if r.returncode != 0 and not text.strip():
        log(name, "执行失败", (r.stderr or "")[:200])
    return text
import ssl
SSLCTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem") if os.path.exists("/etc/ssl/cert.pem") and os.name != "nt" else ssl.create_default_context()


def run(args, **kw):
    """找不到命令（没装 dws / codex 等）时不崩，返回 127，由调用方当失败处理（v2.7，Linux 实测发现自检直接崩）。"""
    try:
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **NOWIN, **kw)
    except FileNotFoundError as ex:
        return subprocess.CompletedProcess(args, 127, "", f"找不到命令：{args[0]}（{ex}）")
    except subprocess.TimeoutExpired:                                      # 超时（如 AI 命令卡住）不崩，按失败处理
        return subprocess.CompletedProcess(args, 124, "", f"超时：{args[0]}")


CHILDREN = []   # 监听子进程：助手被停掉（计划任务结束 / launchctl bootout / systemctl stop / Ctrl+C）时一起结束，不留孤儿进程（v2.7）


def popen(args, **kw):
    p = subprocess.Popen(args, text=True, encoding="utf-8", errors="replace", **NOWIN, **({} if os.name == "nt" else {"start_new_session": True}), **kw)
    CHILDREN.append(p)
    return p


def _stop_children(*_):
    """dws 是 node 包装 + 真正的程序两层，只结束外层会留下里层：Windows 用 taskkill /T 连子进程一起结束，macOS / Linux 结束整个进程组。"""
    for p in CHILDREN:
        if p.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, **NOWIN)
                else:
                    os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                pass
    if _:
        sys.exit(0)


atexit.register(_stop_children)
for _sig in ("SIGTERM", "SIGHUP", "SIGINT"):
    if hasattr(signal, _sig):
        try:
            signal.signal(getattr(signal, _sig), _stop_children)
        except (ValueError, OSError):
            pass


HANDBOOK = open(os.path.join(HOME, "工作手册.md"), encoding="utf-8").read()
Q = queue.Queue()
SEEN, SENT, LOCK = set(), [], threading.Lock()
LOG = open(os.path.join(HOME, "logs", dt.date.today().isoformat() + ".log"), "a", encoding="utf-8")
STATE = {"calls": 0, "todo_t": 0, "todo": ""}
FAILS = {}
OUT = {}            # 助手自己发出的文字 → 发出时间；监听再收到时不当作本人亲自回复


def log(*a):
    line = dt.datetime.now().strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    with LOCK:
        LOG.write(line + "\n"); LOG.flush()
    if sys.stdout and sys.stdout.isatty():
        print(line, flush=True)


def in_window():
    s, e = CFG["window"]; now = dt.datetime.now().strftime("%H:%M")
    return s <= now < e


def minutes_left():
    e = dt.datetime.combine(dt.date.today(), dt.time.fromisoformat(CFG["window"][1]))
    return max(0, int((e - dt.datetime.now()).total_seconds() // 60))


def notify(title, text):
    """提醒本人：只走本人专属群的机器人（有推送、有历史）。机器人没配或发送失败时记进 待处理.md 和日志，第二天的汇报里会写出来。"""
    ok = False
    if CFG.get("webhook") and CFG.get("secret"):
        ts = str(int(time.time() * 1000)); sec = CFG["secret"]
        sign = base64.b64encode(hmac.new(sec.encode(), f"{ts}\n{sec}".encode(), hashlib.sha256).digest()).decode()
        url = f"{CFG['webhook']}&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"
        body = {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n" + text.replace("\n", "\n\n")}}
        for _ in (1, 2):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=15, context=SSLCTX) as r:
                    ok = json.loads(r.read().decode()).get("errcode") == 0
                if ok:
                    break
            except Exception as ex:
                log("机器人发送失败", repr(ex))
            time.sleep(3)
    if not ok:
        log("提醒没发出去（机器人未配置或发送失败）", title)
        with LOCK, open(os.path.join(HOME, "待处理.md"), "a", encoding="utf-8") as f:
            f.write(f"\n## {dt.datetime.now():%m-%d %H:%M} {title}（机器人没发出去）\n{text}\n")
    return ok


OPEN_PATH = os.path.join(HOME, "logs", "open.json")      # 还没处理完的事：{编号: {...}}


def _open_load():
    try:
        return json.load(open(OPEN_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _open_save(d):
    with LOCK:
        json.dump(d, open(OPEN_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def open_add(e, kind, why):
    """交给本人 / 草稿待确认 → 记一个编号（本地 open.json），机器人消息里带上，处理完再发一条「已处理」。"""
    no = "#" + re.sub(r"[^A-Za-z0-9]", "", e.get("message_id", ""))[-5:]
    d = _open_load(); d[no] = {"cid": e.get("conversation_id"), "kind": kind, "who": e.get("sender"),
                               "what": str(e.get("content") or "")[:60], "why": why[:60], "at": f"{dt.datetime.now():%m-%d %H:%M}", "event": e}
    _open_save(d)
    return no


def open_close(no, why):
    d = _open_load()
    x = d.pop(no, None)
    if x:
        _open_save(d); log("已处理", no, why)
        notify(f"✅ {no} 已处理", f"{x['who']}：{x['what']}\n{why}")


def close_by_conversation(cid):
    """本人在这个会话里亲自回复了 → 这个会话里交给本人的事都算处理了。"""
    for no, x in list(_open_load().items()):
        if x.get("cid") == cid and x.get("kind") == "escalate":
            open_close(no, "你已在该会话回复")


# ---- 表情（v2.6）：原生表情回应 + 内置表情包（ChineseBQB）
STICKERS = os.path.join(MEMDIR, "表情包.json")     # {名字: 图片地址}
BQB_TREE = "https://api.github.com/repos/zhaoolee/ChineseBQB/git/trees/master?recursive=1"
BQB_CDN = "https://cdn.jsdelivr.net/gh/zhaoolee/ChineseBQB@master/"
BQB_PACKS = ("001", "007", "008", "009", "010", "011", "023", "024", "026", "031", "034", "035", "049", "052", "054", "055", "056", "057", "060", "108", "109")
BQB_BAD = ("TM|tm|装B|装逼|B|屁|死|滚|婊|崽种|傻|操|尼玛|妈|日你|骚|丑|蠢|智障|脑残|打你|踹|杀|血|枪|刀|弄死|去你|老子|爸爸|爷|撕|色|胸|亲我|亲亲|嫁|"
           "老婆|老公|约|睡你|舔|恶心|呕|吐|绿|穷|胖|秃|蛇精|污|鸡儿|蛋疼|凉凉|凉了|心机|闭嘴|管我|凭什么|上吊|来玩|马子|找抽|别爱我|配不上|小可爱|"
           "撩|宝贝|爱我|魅力|甜蜜|网线|打我|生气|闹|钱|排位|卵|肾|么么哒|兄弟你这")


def build_stickers():
    """下载 ChineseBQB 目录，按推荐包 + 过滤规则生成 memory\表情包.json；已拉黑的（「删表情包」）不再加回来。"""
    with urllib.request.urlopen(urllib.request.Request(BQB_TREE, headers={"User-Agent": "qa-agent"}), timeout=60, context=SSLCTX) as r:
        tree = json.loads(r.read().decode())["tree"]
    black = set(json.load(open(STICKERS + ".blacklist", encoding="utf-8"))) if os.path.exists(STICKERS + ".blacklist") else set()
    lib = {}
    for x in tree:
        p = x["path"]
        if x["type"] != "blob" or "/" not in p or p[:3] not in BQB_PACKS or x.get("size", 0) > 1_500_000 or not p.lower().endswith((".gif", ".jpg", ".jpeg", ".png", ".webp")):
            continue
        name = os.path.splitext(p.split("/")[-1])[0].split("-", 1)[-1]
        if re.search(r"[一-鿿]{2,}", name) and not re.search(BQB_BAD, name) and name not in black and name not in lib:
            lib[name] = BQB_CDN + urllib.parse.quote(p)
    json.dump(lib, open(STICKERS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return len(lib)


def stickers():
    return json.load(open(STICKERS, encoding="utf-8")) if os.path.exists(STICKERS) else {}


def save_cfg(key, value):
    """提醒群里切开关时写回 config.json（只改这一项）。"""
    CFG[key] = value
    with LOCK:
        c = json.load(open(CFG_PATH, encoding="utf-8")); c[key] = value
        json.dump(c, open(CFG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


PENDING_ON = {}   # 等二次确认开自动回复的群：cid → 时间


def can_reply(cid):
    """v2.6（梦无矶 11-18 定）：新部署群聊默认只提醒不回复，本人在提醒群二次确认过的群（auto_reply_groups）才自动回复。
    升级不能覆盖本人已有的规则：老配置没有 auto_reply_groups 时照旧（groups 里的都能回），并在提醒群问本人要不要改（upgrade_ask）。"""
    if "auto_reply_groups" not in CFG:
        return cid in CFG["groups"]
    return cid in CFG["groups"] and cid in (CFG.get("auto_reply_groups") or [])


def upgrade_ask():
    """从旧版升上来：新默认（群聊只提醒）和本人现在的设置（这些群自动回复）冲突，问本人定，没回之前保持原样。"""
    if "auto_reply_groups" in CFG or not CFG["groups"]:
        return
    notify("⚙️ v2.6 有一处默认和你现在的设置不一样，需要你定",
           "新版默认：群聊只提醒、不在群里回复，开自动回复要二次确认。\n你现在这些群是自动回复：" + "、".join(CFG["groups"].values()) +
           "\n回「保持现状」：这些群继续自动回复；回「全部只提醒」：都改成只提醒。没回之前照旧，不改你的设置。")


def group_command(text):
    """按群开关自动回复：「群列表」看状态；「<群名> 只提醒」立即关；「<群名> 自动回复」要再回「确认开启 <群名>」（10 分钟内）才开。写回 config.json。"""
    allg = {**CFG["groups"], **CFG["readonly_groups"]}
    if text in ("保持现状", "全部只提醒") and "auto_reply_groups" not in CFG:
        save_cfg("auto_reply_groups", list(CFG["groups"]) if text == "保持现状" else [])
        notify("👥 已按你说的设置", "保持原来的自动回复群" if text == "保持现状" else "所有群改成只提醒；要开哪个群发「群名 自动回复」"); return True
    if text in ("群列表", "监听群", "看群"):
        rows = [f"{n}：{'自动回复' if can_reply(c) else '只提醒'}" for c, n in allg.items()]
        notify("👥 监听的群", "\n".join(rows) + "\n改：发「群名 只提醒」或「群名 自动回复」（开自动回复要二次确认）"); return True
    m = re.fullmatch(r"(确认开启)\s*(.+)", text) or re.fullmatch(r"(.+?)\s*(只提醒|只看|不回复|自动回复|可以回复)", text)
    if not m:
        return False
    confirm = m.group(1) == "确认开启"
    name = (m.group(2) if confirm else m.group(1)).strip()
    hit = [c for c, n in allg.items() if name == n] or [c for c, n in allg.items() if name in n]
    if len(hit) != 1:
        notify("❓ 没认出是哪个群", f"「{name}」匹配到 {len(hit)} 个。发「群列表」看准确群名。"); return True
    cid = hit[0]; gname = allg[cid]
    on = list(CFG["auto_reply_groups"]) if "auto_reply_groups" in CFG else list(CFG["groups"])   # 旧配置：当前能回的就是 groups
    if not confirm and m.group(2) in ("只提醒", "只看", "不回复"):
        save_cfg("auto_reply_groups", [c for c in on if c != cid]); PENDING_ON.pop(cid, None)
        notify("👥 已切换", f"{gname}：只提醒，不在群里回复任何话"); return True
    if not confirm:
        PENDING_ON[cid] = time.time()
        notify("⚠️ 请二次确认", f"要在「{gname}」开启自动回复吗？开了以后，确定归你、有明确依据的消息助手会直接在群里回。\n确认请在 10 分钟内回「确认开启 {gname}」。"); return True
    if time.time() - PENDING_ON.pop(cid, 0) > 600:
        notify("❓ 没有待确认的开启", f"先发「{gname} 自动回复」，再在 10 分钟内回「确认开启 {gname}」。"); return True
    if cid in CFG["readonly_groups"]:
        g, ro = dict(CFG["groups"]), dict(CFG["readonly_groups"]); g[cid] = ro.pop(cid)
        save_cfg("groups", g); save_cfg("readonly_groups", ro)
    save_cfg("auto_reply_groups", on + [cid])
    notify("👥 已开启自动回复", f"{gname}：仍按职责范围和硬规则，拿不准的照样交给你。随时发「{gname} 只提醒」关掉。"); return True


def sticker_command(text):
    """提醒群表情指令，认了就返回 True。"""
    m = re.fullmatch(r"表情\s*(开|关|打开|关闭|on|off)", text, re.I)
    if m:
        on = m.group(1).lower() in ("开", "打开", "on")
        save_cfg("emoji", on)
        notify("😀 表情已" + ("打开" if on else "关闭"), f"表情回应（{'、'.join(CFG['emoji_names'])}）和表情包{'会在轻松的场合用' if on else '都不再发'}。表情包 {len(stickers())} 张" + ("" if stickers() else "，还没下载：在电脑上运行 python agent.py stickers") + "。")
        return True
    if text in ("表情包", "表情包库", "看表情包"):
        lib = stickers()
        notify(f"🖼 表情包 {len(lib)} 张", "随便看几个：" + "、".join(list(lib)[::max(1, len(lib) // 20)][:20]) + "\n不喜欢哪张就发「删表情包 名字」。"); return True
    m = re.fullmatch(r"删(除)?表情包?\s*(\S+)", text)
    if m:
        lib = stickers(); gone = lib.pop(m.group(2), None)
        bl = STICKERS + ".blacklist"
        black = json.load(open(bl, encoding="utf-8")) if os.path.exists(bl) else []
        with LOCK:
            json.dump(lib, open(STICKERS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            json.dump(sorted(set(black + [m.group(2)])), open(bl, "w", encoding="utf-8"), ensure_ascii=False)
        notify("🗑 表情包", f"「{m.group(2)}」" + ("已删除，以后不会再用" if gone else "不在库里（已记黑名单）")); return True
    return False


def react(e, emoji):
    """给原消息点表情回应：只用白名单里的（钉钉不校验名字，乱写也能点上）。"""
    if emoji not in CFG["emoji_names"]:
        return False
    r = run([DWS, "chat", "message", "add-emoji", "--conversation-id", e["conversation_id"], "--msg-id", e["message_id"], "--emoji", emoji, "--format", "json"], timeout=60)
    return r.returncode == 0 and '"success": false' not in (r.stdout or "")


def send_sticker(e, name):
    """内置表情包：Markdown 图片（钉钉只显示第一帧，一位同事 11-18 实验）。"""
    url = stickers().get(name)
    if not url:
        return False
    r = run([DWS, "chat", "message", "send", "--group", e["conversation_id"], "--title", name, "--text", f"![{name}]({url})", "--format", "json"], timeout=60)
    return r.returncode == 0 and '"success": false' not in (r.stdout or "")


def ack(e):
    """交给本人时先让对方知道已经看到：只在可回复的群、且对方明确 @ 了本人时回（v2.5.1：没 @ 本人的消息也回执会刷屏，11-17 一位同事那边连回 项目助手 给别人的消息）。"""
    if CFG.get("ack_on_escalate") and can_reply(e.get("conversation_id")) and "@" + CFG["my_name"] in str(e.get("content") or ""):
        try:
            reply(e, "收到，我确认一下再回复。", keep_draft=False)
        except Exception as ex:
            log("确认回执失败", repr(ex))


def related_memory(text):
    """只带和这条消息相关的记忆：角色.md 全带（短）；其余按消息里的词命中行，最多 3000 字。"""
    parts = []
    scope = os.path.join(MEMDIR, "职责范围.md")
    if os.path.exists(scope):
        parts.append("## 我的职责范围（本人已确认）\n" + open(scope, encoding="utf-8").read()[:2500])
    p = os.path.join(MEMDIR, "角色.md")
    if os.path.exists(p):
        parts.append("## 角色\n" + open(p, encoding="utf-8").read()[:1500])
    words = {w for w in re.findall(r"[A-Za-z][A-Za-z0-9_\-/.]{2,}|[\u4e00-\u9fff]{2,4}", text)}
    hits = []
    for name in ("负责人.md", "问题处理.md", "偏好与禁区.md"):
        p = os.path.join(MEMDIR, name)
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.startswith(("|", "-")) and any(w in line for w in words):
                    hits.append(f"[{name[:-3]}] {line.strip()}")
    pref = os.path.join(MEMDIR, "偏好与禁区.md")
    if os.path.exists(pref):                                              # 规矩永远带上（通常不长）
        parts.append("## 偏好与禁区\n" + open(pref, encoding="utf-8").read()[:1500])
    if hits:
        parts.append("## 相关记忆\n" + "\n".join(hits)[:3000])
    return "\n\n".join(parts)


def todo_text():
    """协作库里本人的待办，每小时刷新一次；只在消息像是问待办 / 进度时才带进提示词。"""
    if time.time() - STATE["todo_t"] > 3600 and os.path.isdir(COORD):
        run([GIT, "-C", COORD, "pull", "--ff-only", "-q"], timeout=120)
        r = run([NODE, "tools/todo-report.mjs", "--ref", "WORKTREE", "--person", CFG["my_name"]], cwd=COORD, timeout=120)
        STATE.update(todo_t=time.time(), todo=(r.stdout or "")[-3000:])
    return STATE["todo"]


def draft_by_no(no):
    for f in glob.glob(os.path.join(HOME, "drafts", "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if d.get("todo") == no:
            return f, d
    return None, None


def stash(no, text):
    """「#编号 暂存：内容」：只存草稿不发。已有草稿就改内容；交给本人的事（没有草稿）就新建一份草稿挂在这个编号上。"""
    f, d = draft_by_no(no)
    if f:
        d["draft"] = text; json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        x = _open_load().get(no)
        if not x or not x.get("event"):
            notify(f"❓ 没找到 {no}", "可能已经处理过；在提醒群发「待回复」看还有哪些。"); return
        name = save_draft(x["event"], text)
        p = os.path.join(HOME, "drafts", name); dd = json.load(open(p, encoding="utf-8")); dd["todo"] = no
        json.dump(dd, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    notify(f"📌 {no} 草稿已暂存（没发）", f"{text[:200]}\n要发时回「{no} 可以发送」；再改回「{no} 暂存：新内容」。")


def clear_all():
    """清空待回复：没处理完的事和草稿全部清掉，什么都不发。"""
    n = len(_open_load()); fs = glob.glob(os.path.join(HOME, "drafts", "*.json"))
    for f in fs:
        os.remove(f)
    _open_save({}); log("清空待回复", n, "件", len(fs), "份草稿")
    return n, len(fs)


def command(e):
    """本人在提醒群里回草稿：「#编号 可以发送 / 发送 / 发」「#编号 不发 / 删除 / 作废」「#编号 改成：新内容」「#编号 暂存：内容」「#编号 不归我」「全部发送」「清空」。"""
    text = str(e.get("content") or "").strip()
    if re.fullmatch(r"(一键)?清空(待回复)?", text):
        n, k = clear_all(); notify("🧹 待回复已清空", f"清掉 {n} 件没处理完的事、{k} 份草稿，都没有发出。"); return
    m = re.match(r"(#[A-Za-z0-9]{3,8})\s*不归我", text)
    if m:
        f, _ = draft_by_no(m.group(1))
        if f:
            os.remove(f)
        open_close(m.group(1), "你说不归你，群里不回"); return
    m = re.match(r"(#[A-Za-z0-9]{3,8})\s*暂存[：:]\s*(.+)", text, re.S)
    if m:
        stash(m.group(1), m.group(2).strip()); return
    if re.search(r"全部(可以)?发(送)?", text):
        nos = [json.load(open(f, encoding="utf-8")).get("todo") for f in glob.glob(os.path.join(HOME, "drafts", "*.json"))]
    else:
        nos = ["#" + x for x in re.findall(r"#([A-Za-z0-9]{3,8})", text)]
    if not nos:
        return
    for no in nos:
        f, d = draft_by_no(no)
        if not f:
            notify(f"❓ 没找到草稿 {no}", "可能已经发过或删了；看还有哪些：在提醒群发「草稿」两个字。"); continue
        m = re.search(r"改成[：:]\s*(.+)", text, re.S)
        if m:
            d["draft"] = m.group(1).strip()
        if re.search(r"不发|删除|作废|算了", text):
            os.remove(f); open_close(no, "你说不发，草稿已作废")
        elif m or re.search(r"可以|发送|发出|发吧|^发", text):
            try:
                reply(d["event"], d["draft"], keep_draft=False); os.remove(f); open_close(no, "已按你确认发出：" + d["draft"][:100])
            except SendFailed:
                pass                                                       # 已用机器人通知过；草稿还在，恢复后再回「可以发送」
            except Exception as ex:
                notify(f"⚠️ {no} 发送失败", repr(ex)[:200])


def list_drafts_to_group():
    """「待回复」/「草稿」：列出全部没处理完的事，有草稿（含暂存）的带上草稿内容。"""
    drafts = {d.get("todo"): d["draft"] for d in (json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(HOME, "drafts", "*.json")))}
    rows = [f"{no} {x['at']} {x['who']}：{x['what'][:40]}" + (f" → 草稿：{drafts[no][:60]}" if no in drafts else "（还没草稿）")
            for no, x in _open_load().items()]
    notify(f"📋 待回复 {len(rows)} 件", "\n".join(rows) + "\n回「#编号 暂存：内容」存草稿不发，「#编号 可以发送」发出，「清空」全部清掉" if rows else "没有")


def relevant(e):
    sender = str(e.get("sender") or "")
    if CFG.get("notify_group") and e.get("conversation_id") == CFG["notify_group"]:
        if sender == CFG["my_name"] and e.get("message_id") not in SEEN:
            SEEN.add(e.get("message_id"))
            try:
                if sticker_command(str(e.get("content") or "").strip()) or group_command(str(e.get("content") or "").strip()):
                    return False
                list_drafts_to_group() if str(e.get("content") or "").strip() in ("草稿", "看草稿", "待回复", "待回复详细") else command(e)
            except Exception as ex:
                log("提醒群指令处理失败", repr(ex))
        return False                                                       # 提醒群里的消息不交给 AI
    if sender == CFG["my_name"] and e.get("conversation_id"):
        if BQB_CDN in str(e.get("content") or ""):
            return False                                                   # 助手发的表情包（以本人身份发），不算本人亲自回复
        mine = re.sub(r"\s+", "", str(e.get("content") or ""))
        if not any(mine and (mine in k or k in mine) for k, t in OUT.items() if time.time() - t < 900):
            close_by_conversation(e.get("conversation_id"))                # 本人亲自回了（不是助手发的），待办自动完成
        return False
    if not sender or "机器人" in sender:
        return False
    if e.get("message_id") in SEEN:
        return False
    text = str(e.get("content") or "") + json.dumps(e.get("quoted_message") or "", ensure_ascii=False)
    return any(k in text for k in CFG["keywords"] + [CFG["my_name"]]) or sender in CFG["people"]


def listen(args, tag):
    while in_window():
        dur = min(29, minutes_left())
        if dur < 1:
            break
        try:
            p = popen([DWS, "event", "+listen-im", *args, "--duration", f"{dur}m"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except FileNotFoundError:
            log(tag, "找不到钉钉 CLI（dws），10 分钟后再试")
            if FAILS.get(tag) != -1:
                FAILS[tag] = -1
                notify("钉钉 CLI 没装好", f"{tag}：找不到 dws 命令，监听没有启动。请让你的 AI 助手按部署文档第 0 步装好 dws，再自己扫码登录钉钉。")
            time.sleep(600); continue
        t0, got, err = time.time(), 0, ""
        for line in p.stdout:
            try:
                e = json.loads(line)
                got += 1
            except ValueError:
                if "cooldown" in line:
                    log(tag, "订阅冷却，60 秒后重连"); time.sleep(60)
                elif line.strip():
                    err = line.strip()[:200]
                continue
            if isinstance(e, dict) and "error" in e:
                err = json.dumps(e["error"], ensure_ascii=False)[:200]; continue
            if relevant(e):
                SEEN.add(e.get("message_id")); Q.put(e)
        p.wait()
        if time.time() - t0 < 60 and not got:                             # 不到 1 分钟就断、一条都没收到 = 异常（登录过期、网络等）
            FAILS[tag] = FAILS.get(tag, 0) + 1
            log("监听异常", tag, FAILS[tag], "次", err)
            if FAILS[tag] == 3:
                notify("钉钉监听连不上", f"{tag} 连续 3 次断开：{err or '无输出'}。如果是登录过期，请在终端运行 dws auth login 扫码。")
            time.sleep(min(300, 30 * FAILS[tag]))
        else:
            FAILS[tag] = 0
            log(tag, "本轮监听结束，续期"); time.sleep(5)


def decide(batch):  # noqa: C901
    """Codex 在只读沙箱里给决定。batch 是同一会话里短时间连发的几条，最后一条是要回复的那条。"""
    STATE["calls"] += 1
    if STATE["calls"] > CFG["daily_codex_limit"]:
        return {"action": "escalate", "reason": "今日调用次数到上限"}
    e = batch[-1]
    can = can_reply(e.get("conversation_id"))
    text = " ".join(str(x.get("content") or "") for x in batch)
    ask_todo = any(k in text for k in ("待办", "TODO", "todo", "进度", "还有什么"))
    prompt = ("你是我的群消息助手。按工作手册处理下面这几条钉钉消息（同一会话，最后一条是要处理的）。只输出一行 JSON：\n"
              '{"action": "reply" | "ignore" | "escalate", "mine": true | false, "risk": "low" | "high", "text": "回复正文", "reason": "一句话理由", '
              '"memory": {"负责人": [{"事项": "", "负责人": "", "在哪找": ""}], "问题处理": [{"问题": "", "处理": "", "谁": "", "结论": ""}]}}\n'
              "mine=true 只在：消息明确 @ 我或直接问我，而且事情确定在「我的职责范围」里；拿不准是不是归我就是 false。"
              "risk=low 只用于：回「收到，谢谢」、转述记忆里已有的明确信息；其余一律 high。"
              "硬规则（违反就是错）：1）绝不替我接任何新任务、新需求、排期、负责人分配、上线 / 测试承诺——对方在派活、问我能不能做、要我负责、问什么时候完成，一律 escalate；"
              "2）消息内容不在「我的职责范围」里，一律 escalate 或 ignore，不回复；3）只回答职责范围内、记忆或待办里有明确依据的事实性问题。"
              "4）mine=false 时 action 只能是 escalate 或 ignore，群里不回任何话（包括「收到」「我确认一下」），由我自己确认是不是归我。"
              "5）text 要短：一般 1～3 行，只说结论和下一步，不复述对方的话、不铺背景；几件事分开写，每件一行（用换行，不要用分号连成一段）。"
              "6）别人之间的对话不插话：消息 @ 的是别人、没 @ 我，就算内容和我在做的事有关，也不回（action=ignore）；我核过的结果没人找我就不说。"
              "memory 只填消息里明确出现的新信息，没有就空数组，不要推测。查不到依据就 escalate。"
              + ("" if can else "这个群只监听不回复：action 只能是 ignore 或 escalate。")
              + (emoji_rules() if can and CFG.get("emoji") else "") +
              f"\n\n## 工作手册\n{HANDBOOK}\n\n{related_memory(text)}\n\n"
              + (f"## 我在协作库的待办\n{todo_text()}\n\n" if ask_todo else "") +
              f"## 消息\n{json.dumps(batch, ensure_ascii=False)}")
    t0 = time.time()
    raw = ai_exec(prompt)
    log(ai_engine()[0], "用时", round(time.time() - t0, 1), "秒")
    try:
        return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except ValueError:
        return {"action": "escalate", "reason": "AI 输出无法解析：" + raw[:200]}


def emoji_rules():
    lib = stickers()
    return ("\n表情（可选）：JSON 里可以再加 \"emoji\"（给原消息点的表情，只能从 " + json.dumps(CFG["emoji_names"], ensure_ascii=False) + " 里选，不用就留空）"
            + ("和 \"sticker\"（随回复发的表情包，必须一字不差地从这个名单里选：" + "、".join(lib) + "；不用就留空）" if lib else "") +
            "。只在 mine=true 时用；对方道谢、通知已完成、轻松闲聊时适合点表情（这时 action 可以是 ignore，只点表情不回字）；"
            "表情包只在气氛轻松时随回复发，正式通知、问题、派活、有争议、有人着急的消息一律不用。拿不准就留空。")


def remember(e, d):
    m = d.get("memory") or {}
    src = f"{dt.date.today()} {e.get('message_id')}"
    for kind, cols in (("负责人", ["事项", "负责人", "在哪找"]), ("问题处理", ["问题", "处理", "谁", "结论"])):
        rows = [r for r in (m.get(kind) or []) if all(str(r.get(c, "")).strip() for c in cols[:2])]
        if not rows:
            continue
        p = os.path.join(MEMDIR, kind + ".md")
        with LOCK:
            old = open(p, encoding="utf-8").read() if os.path.exists(p) else f"# {kind}\n"
            with open(p, "a", encoding="utf-8") as f:
                for r in rows:
                    if f"| {r.get(cols[0])} | {r.get(cols[1])} |" in old:
                        continue
                    f.write("| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + f" | {src} |\n")
        log("记忆追加", kind, len(rows), "条")


def tidy(text):
    """钉钉里单个换行不换行，整段会连成一坨（11-18 梦无矶截图指出）：每行之间统一空一行；AI 偶尔把换行写成字面 \\n，也一并还原。"""
    text = str(text or "").replace("\\n", "\n")
    return "\n\n".join(x.strip() for x in text.splitlines() if x.strip())


class SendFailed(RuntimeError):
    """钉钉 CLI 以本人身份发消息失败（已经用机器人通知过本人）。"""


SEND_FAIL = {"t": 0, "n": 0}


def send_failed(e, text, err):
    """dws 出故障 / 版本不兼容 / 服务端报错时消息发不出去：用提醒群机器人同步通知本人，30 分钟内只提醒一次（v2.7，11-18 全公司 dws 发消息报「请求参数不能为空」）。"""
    SEND_FAIL["n"] += 1
    log("钉钉消息没发出去", e.get("conversation_id"), err[:200])
    if time.time() - SEND_FAIL["t"] < 1800:
        return
    SEND_FAIL["t"] = time.time()
    group = {**CFG["groups"], **CFG["readonly_groups"]}.get(e.get("conversation_id"), e.get("conversation_id"))
    notify("⚠️ 钉钉消息没发出去", f"群：{group}\n原消息：{e.get('sender')}：{str(e.get('content'))[:100]}\n要发的内容：{text[:500]}\n错误：{err[:200]}\n"
           "可能是钉钉 CLI（dws）故障或版本太旧：在电脑上运行 dws doctor 检查，dws upgrade -y 升级；如果同事也都发不出去，就是钉钉那边的问题，等恢复。"
           "要紧的先手动发；内容已存成草稿，恢复后在这里回「#编号 可以发送」重发。30 分钟内再失败不重复提醒。")


def reply(e, text, keep_draft=True):
    text = tidy(text)
    OUT[re.sub(r"\s+", "", text)] = time.time()
    r = run([DWS, "chat", "+messages-reply", "--conversation-id", e["conversation_id"], "--message-id", e["message_id"],
             "--text", text, "--uuid", f"qa-agent-{time.time_ns()}", "--yes", "--format", "json"], timeout=60)
    out = r.stdout or ""
    if r.returncode != 0 or not re.search(r'"(success|ok)":\s*true', out):
        err = re.search(r'"message":\s*"([^"]*)', out + (r.stderr or ""))
        err = err.group(1) if err else (out or r.stderr or "")[:200]
        if keep_draft:                                                   # 发不出去的回复存成草稿，恢复后一句话重发
            name = save_draft(e, text); no = open_add(e, "draft", "发送失败待重发：" + text[:20])
            dd = json.load(open(os.path.join(HOME, "drafts", name), encoding="utf-8")); dd["todo"] = no
            json.dump(dd, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        send_failed(e, text, err)
        raise SendFailed("回复失败：" + err)


def save_draft(e, text):
    name = dt.datetime.now().strftime("%m%d-%H%M%S-") + re.sub(r"[^A-Za-z0-9]", "", e["message_id"])[:12] + ".json"
    json.dump({"event": e, "draft": text}, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return name


def handle(batch):
    e = batch[-1]
    d = decide(batch)
    remember(e, d)
    log("决定", e.get("sender"), d.get("action"), d.get("risk"), d.get("reason"), d.get("emoji") or "", d.get("sticker") or "")
    ats = re.findall(r"@([^\s@]+)", str(e.get("content") or ""))
    if ats and CFG["my_name"] not in ats and "所有人" not in ats:              # @ 的是别人：不插话（v2.6，11-18 梦无矶回了 项目助手 @ 另一位同事 的消息）
        log("别人之间的对话，不回", e.get("sender"), ats[:3]); return
    fun = CFG.get("emoji") and d.get("mine") is True and can_reply(e.get("conversation_id")) and CFG["mode"] != "draft" and CFG.get("scope_confirmed")
    if d.get("action") == "ignore":
        if fun and d.get("emoji") and react(e, d["emoji"]):
            log("已点表情", d["emoji"], e.get("message_id"))
        return
    brief = f"{e.get('sender')}：{str(e.get('content'))[:200]}"
    if d.get("mine") is not True and d.get("action") == "reply":
        d["action"] = "escalate"                                           # 不确定归我就不替我回（v2.5.1）
    if d.get("action") != "reply" or not can_reply(e.get("conversation_id")):
        no = open_add(e, "escalate", d.get("reason") or "")
        if d.get("mine") is True:
            notify(f"🔔 {no} 需要你处理", f"{brief}\n原因：{d.get('reason')}\n你在原会话回复后，这里会自动补一条「已处理」。")
            ack(e)
        else:
            notify(f"❓ {no} 是不是归你？", f"{brief}\n原因：{d.get('reason')}\n群里我没回任何话。归你就在原会话自己回；不归你在这里回「{no} 不归我」。")
        return
    with LOCK:
        SENT[:] = [t for t in SENT if t > time.time() - 600]
        over = len(SENT) >= CFG["max_auto_replies_per_10min"]
    auto = CFG["mode"] != "draft" and CFG.get("scope_confirmed")           # auto 直接回；draft 或职责范围 / 规则还没确认时全部出草稿
    if not auto or over:
        name = save_draft(e, d.get("text", ""))
        no = open_add(e, "draft", "草稿：" + d.get("text", "")[:20])
        dd = json.load(open(os.path.join(HOME, "drafts", name), encoding="utf-8")); dd["todo"] = no
        json.dump(dd, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        notify(f"📝 {no} 草稿待确认", f"{brief}\n草稿：{d.get('text', '')[:200]}\n在这里回：「{no} 可以发送」/「{no} 不发」/「{no} 改成：新内容」")
        return
    reply(e, d.get("text", ""))
    with LOCK:
        SENT.append(time.time())
    log("已自动回复", e.get("message_id"))
    extra = ""
    if fun and d.get("emoji") and react(e, d["emoji"]):
        extra += f"\n点了表情：{d['emoji']}"
    if fun and d.get("sticker") and send_sticker(e, d["sticker"]):
        extra += f"\n发了表情包：{d['sticker']}"
    notify("💬 已自动回复", f"{brief}\n回复：{d.get('text', '')[:300]}{extra}")


ACTIVE = {"n": 0}
READY = queue.Queue()          # 攒好的批次（同一会话 merge_seconds 秒内的消息）


def batcher():
    """分拣：按会话攒批，第一条进来后等 merge_seconds 秒，把这段时间同一会话的消息合成一批放进 READY。"""
    pending = {}               # conversation_id -> [首条时间, [消息…]]
    while in_window():
        try:
            e = Q.get(timeout=1)
            pending.setdefault(e.get("conversation_id"), [time.time(), []])[1].append(e)
        except queue.Empty:
            pass
        now = time.time()
        for cid in [c for c, (t, _) in pending.items() if now - t >= CFG["merge_seconds"]]:
            READY.put(pending.pop(cid)[1])


def worker(temp=False):
    """处理通道：从 READY 取一批，一次判断。temp=True 是积压时临时开的子 Agent，没活了就退出。"""
    with LOCK:
        ACTIVE["n"] += 1
    try:
        while in_window():
            try:
                batch = READY.get(timeout=5 if temp else 30)
            except queue.Empty:
                if temp:
                    return
                continue
            with LOCK, open(os.path.join(HOME, "inbox.jsonl"), "a", encoding="utf-8") as f:
                for x in batch:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
            try:
                handle(batch)
            except SendFailed:
                pass                                                       # 发不出去已用机器人通知本人，回复存成了草稿
            except Exception as ex:
                e = batch[-1]
                log("处理失败", repr(ex)); notify("助手处理失败", f"{e.get('sender')}：{str(e.get('content'))[:120]}\n{ex!r}"[:300])
    finally:
        with LOCK:
            ACTIVE["n"] -= 1


def supervisor():
    """一次收到太多任务时开子 Agent：待处理批次超过 burst_threshold，就临时加处理通道，最多 max_workers 个。"""
    while in_window():
        backlog = READY.qsize()
        with LOCK:
            n = ACTIVE["n"]
        if backlog > CFG["burst_threshold"] and n < CFG["max_workers"]:
            add = max(1, min(CFG["max_workers"] - n, backlog // max(1, CFG["burst_threshold"])))
            for _ in range(add):
                threading.Thread(target=worker, args=(True,), daemon=True).start()
            log("积压", backlog, "批，开子 Agent", add, "个，当前共", n + add, "个")
        time.sleep(5)


def daily_summary():
    """21:00 退出前写当天总结（结构化），第二天上班由 morning_report() 发到本人私聊。"""
    today = dt.date.today().isoformat()
    p = os.path.join(HOME, "logs", today + ".log")
    lines = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []
    cnt = lambda k: sum(1 for l in lines if k in l)
    acts = [l.split("决定 ", 1)[1] for l in lines if "决定 " in l]
    body = [f"- 处理相关消息 {len(acts)} 批：自动回复 {cnt('已自动回复')}，写草稿 {sum(1 for a in acts if ' reply ' in a) - cnt('已自动回复')}，"
            f"交给我 {sum(1 for a in acts if ' escalate ' in a)}，忽略 {sum(1 for a in acts if ' ignore ' in a)}",
            f"- 新记的负责人 / 问题处理：{cnt('记忆追加')} 次",
            f"- 异常：处理失败 {cnt('处理失败')} 次，监听异常 {cnt('监听异常')} 次",
            f"- 还没确认的草稿：{len(glob.glob(os.path.join(HOME, 'drafts', '*.json')))} 条"]
    body += ["- 交给我的事："] + [f"  - {a[:120]}" for a in acts if " escalate " in a][-10:]
    with open(os.path.join(MEMDIR, "每日总结.md"), "a", encoding="utf-8") as f:
        f.write(f"\n## {today}\n" + "\n".join(body) + "\n")


def morning_report():
    """每天第一次启动（≥ 09:00）：把前一天的每日总结发到本人的提醒群（机器人发，有推送、有历史）。"""
    mark = os.path.join(HOME, "logs", f"morning-{dt.date.today()}.sent")
    if os.path.exists(mark):
        return
    open(mark, "w").close()
    p = os.path.join(MEMDIR, "每日总结.md")
    text = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    secs = [(m.group(1), m.start()) for m in re.finditer(r"^## (\d{4}-\d{2}-\d{2})", text, re.M)]
    prev = [x for x in secs if x[0] < dt.date.today().isoformat()]
    if prev:
        day, start = max(prev)
        nxt = [st for d, st in secs if st > start]
        body = text[start: min(nxt) if nxt else len(text)].split("\n", 1)[1].strip()
    else:
        day, body = "无", "（还没有前一天的总结）"
    msg = f"【群消息助手每日汇报｜{dt.date.today():%m-%d}】\n前一天（{day}）：\n{body}\n今天：09:00–21:00 监听，模式 {CFG['mode']}。"
    op = _open_load()
    if op:
        msg += f"\n还没处理完 {len(op)} 件：" + "；".join(f"{no} {x['who']}：{x['what'][:20]}" for no, x in list(op.items())[:10])
    if notify(f"☀️ 每日汇报 {dt.date.today():%m-%d}", msg):
        log("每日汇报已发到提醒群")


def review():
    files = sorted(glob.glob(os.path.join(HOME, "drafts", "*.json")))
    if not files:
        print("没有待确认的草稿。"); return
    items = [json.load(open(f, encoding="utf-8")) | {"_f": f} for f in files]
    for i, d in enumerate(items, 1):
        e = d["event"]
        print(f"\n[{i}] {e.get('sender')}：{str(e.get('content'))[:120]}\n    草稿：{d['draft']}")
    ans = input("\n回编号发送（如 1 3）；a = 全部发送；d + 编号删除（如 d2）；直接回车退出：").strip().lower()
    if not ans:
        return
    if ans.startswith("d"):
        for n in ans[1:].split():
            d = items[int(n) - 1]
            os.remove(d["_f"]); open_close(d.get("todo", ""), "草稿已删除"); print("已删除", n)
        return
    picks = range(1, len(items) + 1) if ans == "a" else [int(n) for n in ans.split()]
    for n in picks:
        d = items[n - 1]
        reply(d["event"], d["draft"]); os.remove(d["_f"]); open_close(d.get("todo", ""), "草稿已发送"); print("已发送", n)


def status():
    today = dt.date.today().isoformat()
    p = os.path.join(HOME, "logs", today + ".log")
    lines = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []
    acts = [l for l in lines if "决定 " in l]
    print(f"今天（{today}）：处理 {len(acts)} 批，自动回复 {sum('已自动回复' in l for l in lines)} 条，"
          f"交给你 {sum(' escalate ' in l for l in acts)} 件，忽略 {sum(' ignore ' in l for l in acts)} 批，失败 {sum('处理失败' in l for l in lines)} 次")
    op = _open_load()
    print(f"还没处理完：{len(op)} 件（提醒群里也有）")
    for no, x in op.items():
        print(f"  {no} {x['at']} {x['who']}：{x['what']}｜{x['why']}")
    print("最近 5 条记录：")
    for l in acts[-5:]:
        print(" ", l[:150])


def dws_version_check():
    """每天第一次启动时查一次钉钉 CLI 有没有新版本，有就在提醒群说一声（v2.7：11-18 钉钉发消息故障，旧版 CLI 和服务端对不上时症状一样，早知道早升级）。"""
    mark = os.path.join(HOME, "logs", f"dws-version-{dt.date.today()}.checked")
    if os.path.exists(mark):
        return
    open(mark, "w").close()
    up = run([DWS, "upgrade", "--check"], timeout=90)
    out = (up.stdout or "") + (up.stderr or "")
    if re.search(r"新版本可用|→", out) and "已是最新" not in out:
        line = next((x.strip() for x in out.splitlines() if "→" in x), "")
        notify("⬆️ 钉钉 CLI 有新版本", f"{line}\n消息发不出去、监听异常时先升级：在电脑上运行 dws upgrade -y，然后重启助手。没问题可以先不升。")
    log("钉钉 CLI 版本检查", "有新版本" if "→" in out else "已是最新或查不到")


def check():
    print("版本", VERSION)
    ai_name, ai_args, _ = ai_engine()
    pong = ai_exec("只回复两个字：正常", timeout=120) if ai_args else ""
    print(("✅ " if pong.strip() else "❌ ") + f"判断用的 AI：{ai_name}" + ("" if pong.strip() else "（命令行调用失败：确认你平时用的这个 AI 工具在终端里能用；用的是别的工具就在 config.json 改 ai）"))
    for name, args in (("dws 登录", [DWS, "auth", "status"]), ("git", [GIT, "--version"]), ("node", [NODE, "--version"])):
        r = run(args, timeout=60)
        ok = r.returncode == 0 and ('"authenticated": true' in r.stdout if name == "dws 登录" else True)
        print(("✅ " if ok else "❌ ") + name)
    up = run([DWS, "upgrade", "--check"], timeout=60)
    if re.search(r"新版本可用|→", (up.stdout or "") + (up.stderr or "")) and "已是最新" not in (up.stdout or ""):   # 「已是最新版本」里也有「新版本」三个字
        print("⚠️ 钉钉 CLI 有新版本：消息发不出去时先 dws upgrade -y 升级（" + ((up.stdout or "").strip().splitlines() or [""])[-1][:60] + "）")
    print(("✅ " if notify("助手自检", f"{VERSION} 自检消息，看到这条说明提醒群机器人正常。") else "❌ ") + "提醒群机器人（发了一条自检消息）")
    print(("✅ " if CFG["groups"] or CFG["readonly_groups"] else "❌ ") + f"监听群 {len(CFG['groups'])} 个可回复、{len(CFG['readonly_groups'])} 个只看")
    print(("✅ " if CFG.get("scope_confirmed") and os.path.exists(os.path.join(MEMDIR, "职责范围.md")) else "❌ ") + "职责范围和回复规则已确认（没确认前只写草稿）")
    print("表情", "开" if CFG.get("emoji") else "关", "| 表情包", len(stickers()), "张" + ("" if stickers() else "（未下载：python agent.py stickers）"))
    print("模式", CFG["mode"], "| 常驻并行", CFG["workers"], "| 积压超过", CFG["burst_threshold"], "条开子 Agent，最多", CFG["max_workers"], "个 | 合并秒数", CFG["merge_seconds"], "| 模型", CFG["codex_model"] or "默认")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "clear":
        n, k = clear_all(); print(f"已清空：{n} 件没处理完的事、{k} 份草稿，都没有发出"); return
    if len(sys.argv) >= 2 and sys.argv[1] == "stickers":
        print("表情包已下载", build_stickers(), "张 →", STICKERS); return
    if len(sys.argv) >= 2 and sys.argv[1] in ("review", "check", "status"):
        return {"review": review, "check": check, "status": status}[sys.argv[1]]()
    if len(sys.argv) == 3 and sys.argv[1] == "send":
        d = json.load(open(os.path.join(HOME, "drafts", sys.argv[2]), encoding="utf-8"))
        reply(d["event"], d["draft"]); os.remove(os.path.join(HOME, "drafts", sys.argv[2])); print("已发送"); return
    if not in_window():
        log("窗口外，不启动"); return
    if CFG.get("notify_group"):
        threading.Thread(target=listen, args=(["--kind", "group", "--chat-id", CFG["notify_group"]], "提醒群"), daemon=True).start()
    for cid, name in {**CFG["groups"], **CFG["readonly_groups"]}.items():
        threading.Thread(target=listen, args=(["--kind", "group", "--chat-id", cid], name), daemon=True).start()
    if CFG.get("listen_dm"):
        threading.Thread(target=listen, args=(["--kind", "all-direct"], "私聊"), daemon=True).start()
    workers = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, int(CFG["workers"])))]
    for w in workers:
        w.start()
    threading.Thread(target=batcher, daemon=True).start()
    threading.Thread(target=supervisor, daemon=True).start()
    log("启动", VERSION, "模式", CFG["mode"])
    threading.Thread(target=morning_report, daemon=True).start()
    threading.Thread(target=dws_version_check, daemon=True).start()
    upgrade_ask()
    while in_window():
        time.sleep(30)
    daily_summary()
    log("到点退出")


if __name__ == "__main__":
    main()
```

**AI 助手写完后核对**：先跑 `dws event +listen-im --kind group --chat-id <一个选中的群> --duration 1m`，看一条真实消息的字段名（`sender`、`content`、`message_id`、`conversation_id`、`quoted_message`），对不上就改 `relevant()` / `reply()`；再跑一次 `python agent.py check`，「判断用的 AI」一项要是 ✅（它会真的问 AI 一句）。AI 命令行参数和本机 `--help` 对不上时，在 config.json 用 `ai_cmd` 写本机能用的命令，不改代码。

### 3.3 bootstrap_memory.py

```python
"""首次建记忆：协作库预填同事 / 需求负责人 + 选中群最近 N 天历史 + 工作目录下的全部 Codex 会话记录，交给 codex exec（只读）提炼成 memory\\*.draft.md，等本人确认。
用法：python bootstrap_memory.py [天数，默认 30]"""
import datetime as dt, glob, json, os, re, shutil, subprocess, sys

HOME = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(os.path.expanduser("~"), ".qa-agent", "config.json"), encoding="utf-8"))
DWS = shutil.which("dws") or shutil.which("dws.cmd")
# 判断用的 AI：与 agent.py 的 AI_PRESETS 一致（v2.7 不限 Codex）；config 的 ai / ai_cmd / ai_prompt / ai_model 同样生效
AI_PRESETS = {"codex": (["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", "{out}"], "arg"),
              "claude": (["claude", "-p", "--permission-mode", "plan", "--output-format", "text"], "stdin"),
              "codebuddy": (["codebuddy", "-p", "--output-format", "text"], "stdin"),
              "qoder": (["qodercli", "-p", "-o", "text"], "stdin"),
              "dsh": (["dsh", "--profile", "headless", "-"], "stdin")}
COORD = os.path.join(HOME, "project-coordination")
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
EXP = os.path.join(HOME, "history"); MEM = os.path.join(HOME, "memory")
for d in (EXP, MEM, os.path.join(HOME, "logs")):
    os.makedirs(d, exist_ok=True)
start = (dt.datetime.now() - dt.timedelta(days=DAYS)).strftime("%Y-%m-%dT00:00:00+08:00")
today = dt.date.today().isoformat()
NOWIN = {}
if os.name == "nt":                                                     # 子进程不弹窗口
    si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
    NOWIN = {"creationflags": 0x08000000, "startupinfo": si}
ROLE_CN = {"project_lead": "项目负责人", "server": "服务端", "android": "Android", "ios": "iOS", "h5": "H5", "web": "网页版", "backoffice": "后台 UI",
           "product": "产品", "qa": "测试", "ops": "运营", "recommendation": "推荐 / 内容分发", "vidstore": "剧中台服务端"}   # 与协作库角色登记对齐（v2.7）

# 1) 协作库预填：同事角色 + 需求单负责人（只读）
seed = []
idf = os.path.join(COORD, "registry", "identities.json")
if os.path.exists(idf):
    ids = json.load(open(idf, encoding="utf-8"))
    for p in (ids.get("people") or []) if isinstance(ids, dict) else ids:   # identities.json 顶层是 {"people": [...]}；以前直接遍历拿到的是键名，预填一直是空的（v2.7 修）
        if isinstance(p, dict) and p.get("status") == "active" and p.get("roles"):
            seed.append({"事项": "、".join(ROLE_CN.get(r, r) for r in p["roles"]) + " 相关", "负责人": p["display_name"], "在哪找": "协作群 / 测试群", "依据": "协作库 identities.json"})
for f in glob.glob(os.path.join(COORD, "features", "*", "feature.yaml")):
    text = open(f, encoding="utf-8", errors="ignore").read()
    title = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", text, re.M)
    owner = re.search(r"^\s*(?:owner|dri|assignee|developer):\s*['\"]?([^\s'\"#]+)", text, re.M)
    if title and owner:
        seed.append({"事项": f"{os.path.basename(os.path.dirname(f))} {title.group(1)[:40]}", "负责人": owner.group(1), "在哪找": "协作群", "依据": "协作库 feature.yaml"})


def codex(prompt):
    """跑一次判断用的 AI（名字沿用 codex，实际按 config 选 / 自动找本机装了的）。"""
    out = os.path.join(HOME, "logs", "bootstrap_last.txt")
    if os.path.exists(out):
        os.remove(out)
    if CFG.get("ai_cmd"):
        args, how = list(CFG["ai_cmd"]), CFG.get("ai_prompt", "stdin")
    else:
        names = [CFG["ai"]] if CFG.get("ai") in AI_PRESETS else list(AI_PRESETS)
        found = [k for k in names if shutil.which(AI_PRESETS[k][0][0]) or shutil.which(AI_PRESETS[k][0][0] + ".cmd")]
        if not found:
            print("没找到可用的 AI 命令行（codex / claude / codebuddy / qodercli / dsh），请在 config.json 填 ai_cmd"); return ""
        args, how = AI_PRESETS[found[0]]
        args = [shutil.which(args[0]) or shutil.which(args[0] + ".cmd")] + args[1:]
    args = [out if a == "{out}" else a for a in args]
    if how == "arg":
        args = [prompt if a == "{prompt}" else a for a in args] if "{prompt}" in args else args + [prompt]
    try:
        r = subprocess.run(args, cwd=HOME, capture_output=True, text=True, encoding="utf-8", timeout=900, **NOWIN, **({"input": prompt} if how == "stdin" else {"stdin": subprocess.DEVNULL}))
    except subprocess.TimeoutExpired:
        print("AI 15 分钟没返回（命令卡住），这一块跳过"); return ""
    return open(out, encoding="utf-8").read() if os.path.exists(out) else (r.stdout or "")


# 2) 导出选中群的历史（只读，参数以 `dws chat +chat-messages --help` 为准）
msgs = []
for cid, name in {**CFG["groups"], **CFG.get("readonly_groups", {})}.items():
    f = os.path.join(EXP, re.sub(r'[\\/:*?"<>|]', "_", name) + ".json")
    with open(f, "w", encoding="utf-8") as out:
        subprocess.run([DWS, "chat", "+chat-messages", "--group", cid, "--start", start, "--order", "asc", "--page-all",
                        "--page-limit", "200", "--max-items", "5000", "--format", "json"], stdout=out, timeout=900, **NOWIN)
    try:
        data = json.load(open(f, encoding="utf-8"))
    except ValueError:
        print("导出失败：", name); continue
    for m in data.get("messages") or []:     # dws 的姓名字段是 sender；以前读 senderName 拿不到、退成 senderId 乱码，模型按内容猜人，把 项目助手 认成一位同事（11-18 一位同事反馈）
        msgs.append({"群": name, "id": m.get("messageId"), "时间": m.get("createTime") or m.get("createAt"),
                     "人": m.get("sender") or m.get("senderName") or m.get("senderNick") or "（未知）", "内容": str(m.get("text") or m.get("content") or "")[:800]})
# 2b) 工作目录下的全部 Codex 会话记录（默认读；config.json 的 workspace = 部署时使用者打开 Codex 的目录）
WS = os.path.normcase(os.path.abspath(CFG.get("workspace") or os.getcwd()))
skip = ("# AGENTS.md instructions", "<environment_context", "<user_instructions", "<skills_instructions")
ncodex = 0
for f in glob.glob(os.path.join(os.path.expanduser("~"), ".codex", "sessions", "**", "*.jsonl"), recursive=True):   # 归档的 .jsonl.zst 不读
    cwd, rows = None, []
    for line in open(f, encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        pl = d.get("payload") or {}
        if d.get("type") == "session_meta":
            cwd = os.path.normcase(os.path.abspath(pl.get("cwd") or ""))
        elif d.get("type") == "response_item" and pl.get("type") == "message" and pl.get("role") in ("user", "assistant"):
            text = "\n".join(x.get("text", "") for x in pl.get("content") or [] if isinstance(x, dict))
            if text.strip() and not text.lstrip().startswith(skip):
                rows.append({"群": "Codex 会话", "id": os.path.basename(f)[:40], "时间": d.get("timestamp"),
                             "人": "我" if pl["role"] == "user" else "Codex", "内容": text[:800]})
    if cwd and (cwd == WS or cwd.startswith(WS + os.sep)):
        msgs += rows; ncodex += len(rows)
# 2c) 工作目录下的 Claude Code 会话记录（v2.7：用 Claude Code 的同事也有对话可读；~/.claude/projects/*/*.jsonl）
#     只取本人打的字（content 是字符串、不是工具结果 / 系统注入）和 Claude 的正文（text 段，不要思考和工具调用）
nclaude = 0
for f in glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", "*.jsonl")):
    rows, inws = [], False
    for line in open(f, encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") not in ("user", "assistant") or d.get("isSidechain"):
            continue
        cwd = os.path.normcase(os.path.abspath(d.get("cwd") or ""))
        if d.get("cwd") and (cwd == WS or cwd.startswith(WS + os.sep)):
            inws = True
        m = d.get("message") or {}
        c = m.get("content")
        if d["type"] == "user":
            text = c if isinstance(c, str) else ""
            if d.get("isMeta") or d.get("isCompactSummary") or text.lstrip().startswith(("<", "[", "This session is being continued", "Your claude.ai")):
                text = ""                                             # 系统注入、上下文压缩摘要、额度提示、图片占位，不是本人打的字
        else:
            text = "\n".join(x.get("text", "") for x in (c or []) if isinstance(x, dict) and x.get("type") == "text")
        if text.strip():
            rows.append({"群": "Claude Code 会话", "id": os.path.basename(f)[:40], "时间": d.get("timestamp"),
                         "人": "我" if d["type"] == "user" else "Claude", "内容": text[:800]})
    if inws:
        msgs += rows; nclaude += len(rows)
print("协作库预填", len(seed), "条；导出群消息", len(msgs) - ncodex - nclaude, "条；工作目录", WS, "下的 Codex 会话记录", ncodex, "条、Claude Code 会话记录", nclaude, "条")

# 3) 分块提炼（每块 300 条）
facts = {"负责人": list(seed), "问题处理": [], "偏好与禁区": [], "角色线索": []}
for i in range(0, len(msgs), 300):
    raw = codex(f"""下面是我（{CFG['my_name']}，角色 {CFG.get('roles')}）在工作群里的历史消息（「人」= 发送者姓名，以它为准，不要按内容或语气猜是谁说的；「（未知）」就当不知道是谁），以及我和 AI 助手的对话记录（「群」= Codex 会话 / Claude Code 会话）（JSON）。只根据消息内容提炼，不要推测、不要编造。
只输出一个 JSON 对象，键固定为：
"负责人": [{{"事项": "模块/服务/环境/单据类型", "负责人": "姓名", "在哪找": "群名", "依据": "日期 消息id"}}],
"问题处理": [{{"问题": "...", "处理": "怎么解决的", "谁": "姓名", "结论": "...", "依据": "日期 消息id"}}],
"偏好与禁区": [{{"规矩": "我本人说过的要求或做法", "依据": "日期 消息id"}}],
"角色线索": ["我负责什么、常被问什么（每条一句，带依据）"]
消息：
{json.dumps(msgs[i:i + 300], ensure_ascii=False)}""")
    try:
        part = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        for k in facts:
            facts[k] += part.get(k) or []
    except ValueError:
        print("第", i // 300 + 1, "块解析失败，跳过")


def table(rows, cols):
    seen, lines = set(), ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        key = tuple(str(r.get(c, "")) for c in cols[:2])
        if key in seen:
            continue
        seen.add(key); lines.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + " |")
    return "\n".join(lines)


# 4) 写草稿，等本人在部署第 4 步确认后改名为正式文件
open(os.path.join(MEM, "负责人.draft.md"), "w", encoding="utf-8").write(f"# 负责人（{today}：协作库 + 近 {DAYS} 天群历史）\n\n" + table(facts["负责人"], ["事项", "负责人", "在哪找", "依据"]) + "\n")
open(os.path.join(MEM, "问题处理.draft.md"), "w", encoding="utf-8").write(f"# 问题处理（{today}）\n\n" + table(facts["问题处理"], ["问题", "处理", "谁", "结论", "依据"]) + "\n")
open(os.path.join(MEM, "偏好与禁区.draft.md"), "w", encoding="utf-8").write(f"# 偏好与禁区（{today}）\n\n" + "\n".join(f"- {r.get('规矩')}（{r.get('依据')}）" for r in facts["偏好与禁区"]) + "\n")
open(os.path.join(MEM, "角色.draft.md"), "w", encoding="utf-8").write(
    f"# 角色（{today}）\n\n- 我是：{CFG['my_name']}，角色 {CFG.get('roles')}，负责 {CFG.get('project')}。\n\n## 各群用途\n（部署第 3 步写入）\n\n## 线索\n"
    + "\n".join(f"- {x}" for x in facts["角色线索"]) + "\n")
print("草稿已写入 memory\\*.draft.md")
```

### 3.4 开机 / 每天自启（第 6 步选 1 时执行，按本机系统选一种）

三种做法效果一样：每天 09:00 和登录时拉起，21:00 助手自己退出；同一时间只跑一个。都用使用者本人账号，这样能用到他的 `dws` 登录态。工作时间内关掉电脑睡眠，否则监听会断。

**A. Windows：计划任务**（PowerShell，只在用户登录时运行）

```powershell
$act  = New-ScheduledTaskAction -Execute "pythonw.exe" -Argument "C:\qa-agent\agent.py" -WorkingDirectory "C:\qa-agent"   # pythonw：没有黑色命令行窗口
$trg1 = New-ScheduledTaskTrigger -Daily -At 09:00
$trg2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set  = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 13) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "QA-群消息助手" -Action $act -Trigger $trg1,$trg2 -Settings $set -Description "钉钉群监听 + Codex 决策，09:00-21:00"
```

暂停：`Disable-ScheduledTask -TaskName "QA-群消息助手"`；恢复：`Enable-ScheduledTask …`；卸载：`Unregister-ScheduledTask -TaskName "QA-群消息助手" -Confirm:$false`，再删 `C:\qa-agent` 和 `%USERPROFILE%\.qa-agent`。（任务名保留旧名，老用户不用重建。）

**B. macOS：LaunchAgent**（登录后生效，不需要管理员）。先取 python3 的绝对路径：`python3 -c "import sys;print(sys.executable)"`，替换下面的 `<PYTHON3>`；`<HOME>` 换成 `echo $HOME` 的结果。写入 `~/Library/LaunchAgents/com.group-assistant.agent.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.group-assistant.agent</string>
  <key>ProgramArguments</key><array><string><PYTHON3></string><string><HOME>/qa-agent/agent.py</string></array>
  <key>WorkingDirectory</key><string><HOME>/qa-agent</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:<HOME>/.npm-global/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string><HOME>/qa-agent/logs/launchd.err</string>
</dict></plist>
```

```bash
plutil -lint ~/Library/LaunchAgents/com.group-assistant.agent.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.group-assistant.agent.plist
```

- `PATH` 里要包含 `dws`、你的 AI 命令行（codex / claude / dsh / codebuddy / qodercli …）、`git`、`node` 所在目录（`which …` 查，按实际补进去），launchd 不读 shell 的 PATH。
- 暂停：`launchctl bootout gui/$(id -u)/com.group-assistant.agent`；恢复：再 `bootstrap` 一次；卸载：暂停后删 plist、`~/qa-agent`、`~/.qa-agent`。
- 后台跑时 `dws` 报钥匙串错误（`-25308`）：在 `EnvironmentVariables` 里加 `DWS_DISABLE_KEYCHAIN` = `1`，并用同样的环境变量重新 `dws auth login` 一次。

**C. Linux：systemd 用户服务 + 定时器**（不需要 root）。写两个文件：

`~/.config/systemd/user/group-assistant.service`

```ini
[Unit]
Description=群消息助手（09:00-21:00 监听钉钉群）

[Service]
Type=simple
WorkingDirectory=%h/qa-agent
ExecStart=/usr/bin/env python3 %h/qa-agent/agent.py
Environment=PATH=%h/.local/bin:%h/.npm-global/bin:/usr/local/bin:/usr/bin:/bin
Environment=TZ=Asia/Shanghai

[Install]
WantedBy=default.target
```

`~/.config/systemd/user/group-assistant.timer`

```ini
[Unit]
Description=每天 09:00 拉起群消息助手

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now group-assistant.service group-assistant.timer   # service：登录时拉起；timer：每天 09:00
loginctl enable-linger $USER    # 可选：不登录桌面也运行（需要管理员同意时再做）
```

- `PATH` 同样要包含 `dws`、你的 AI 命令行、`git`、`node` 所在目录（`which …` 查）。
- `TZ=Asia/Shanghai`：服务器常用 UTC 时区，不设的话助手按 UTC 算 09:00–21:00，会在北京时间下午五点才开始。定时器的 `OnCalendar` 也按系统时区算：系统是 UTC 时改成 `*-*-* 01:00:00`（= 北京 09:00），或者 `sudo timedatectl set-timezone Asia/Shanghai`（需要管理员）。
- 暂停：`systemctl --user disable --now group-assistant.timer group-assistant.service`；日志：`journalctl --user -u group-assistant`。

---

### 3.5 角色职责库.json（写入 `C:\qa-agent\角色职责库.json`）

没有协作库、或协作库没有对应角色时，第 2 步从这里选角色。使用者可以随时对 AI 助手说「角色职责库加一个角色 / 删掉某个角色 / 改某条」，AI 助手改这份文件。**AI 助手也可以自行补充**：部署或日常对话中发现库里没有的角色、或某个角色缺了明显的职责（协作库里有登记、或使用者在对话里说过），直接追加进库，条目里写「来源：AI 补充，日期，依据一句话」，补完告诉使用者一声；只要不是本人正在用的角色，不用逐条确认。**改的是本人在用的角色时，先把改动念给本人二次确认，再同步进工作手册「按角色」一节**。升级时不覆盖本人改过的这份（新版本有新角色时只问要不要加进来）。

```json
{
 "说明": "角色职责库（v2.7 起）：部署时没有协作库、或协作库里没有对应角色时，从这里选角色。每个角色写「关注什么 / 有依据时可以直接回答什么 / 一律交给本人什么」。使用者可以自己新增、删除、修改条目（对 AI 助手说即可）；使用者自己的 AI 助手也可以自行补充（库里没有的角色、从协作库或日常对话里看到的职责），补充的条目标「来源：AI 补充 + 日期」。改动只影响自己电脑上的这份；选进自己职责范围、写进工作手册前要本人二次确认。初版依据一个移动 App 项目的角色分工整理，按你们团队的实际情况增删改。",
 "通用规则": [
  "任何角色收到「能不能做 / 什么时候好 / 你来负责 / 排期 / 承诺」都交给本人",
  "只回答有依据的事实（协作库、记忆、群里已发的通知），回答注明依据；没依据就交给本人",
  "别人之间的对话（@ 的是别人）不插话"
 ],
 "角色": [
  {
   "id": "product",
   "名称": "产品",
   "关注": [
    "需求单、需求说明（Spec）、确认版",
    "验收结论",
    "多语言文案"
   ],
   "可以直接回答（有依据时）": [
    "需求是怎么定的、文案用哪一版：按确认版或已发的决定回答并给出处"
   ],
   "一律交给本人": [
    "需求变更",
    "优先级",
    "拍板类问题"
   ],
   "推荐监控的群": [
    "项目协作群"
   ]
  },
  {
   "id": "android",
   "名称": "Android",
   "关注": [
    "安卓包、打包通知",
    "崩溃 / 缺陷单",
    "接口联调"
   ],
   "可以直接回答（有依据时）": [
    "最新包是哪个、带没带某个改动：按打包通知和合入记录回答"
   ],
   "一律交给本人": [
    "修复时间",
    "是否带进某个版本"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "ios",
   "名称": "iOS",
   "关注": [
    "iOS 包、提审",
    "TestFlight / 蒲公英",
    "缺陷单"
   ],
   "可以直接回答（有依据时）": [
    "最新包、提审状态：按打包通知和提审记录回答"
   ],
   "一律交给本人": [
    "提审、加急",
    "拒审应对"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "h5",
   "名称": "H5",
   "关注": [
    "H5 页面、活动页",
    "发布记录"
   ],
   "可以直接回答（有依据时）": [
    "页面地址、上线了没：按发布记录回答"
   ],
   "一律交给本人": [
    "改页面",
    "上线时间"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "web",
   "名称": "网页版（PC＋H5）",
   "关注": [
    "网页版需求",
    "发布",
    "接口对接"
   ],
   "可以直接回答（有依据时）": [
    "网页版在哪看、发没发：按发布记录回答"
   ],
   "一律交给本人": [
    "需求",
    "排期"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "server",
   "名称": "服务端",
   "关注": [
    "测试服 / 正式服发布",
    "接口合同",
    "线上告警",
    "缺陷单"
   ],
   "可以直接回答（有依据时）": [
    "测试服是哪个版本、某接口怎么调：按发布通知和接口合同回答"
   ],
   "一律交给本人": [
    "改接口",
    "上线",
    "数据修复",
    "任何线上操作"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "vidstore",
   "名称": "剧中台服务端",
   "关注": [
    "剧中台服务发布",
    "内容 / 剧集数据",
    "和业务服务端的对接"
   ],
   "可以直接回答（有依据时）": [
    "剧数据从哪来、接口状态：按合同和发布记录回答"
   ],
   "一律交给本人": [
    "数据修改",
    "数据导入"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "recommendation",
   "名称": "推荐 / 内容分发",
   "关注": [
    "推荐接口",
    "版位配置",
    "成绩表、实验分组"
   ],
   "可以直接回答（有依据时）": [
    "某版位怎么排、实验组用的哪版：按调用说明和配置版本回答"
   ],
   "一律交给本人": [
    "改配置",
    "发布规则",
    "实验开关"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "qa_func",
   "名称": "测试：功能测试",
   "关注": [
    "提测通知、包号",
    "验收标准",
    "缺陷争议"
   ],
   "可以直接回答（有依据时）": [
    "能测了吗：查最近的提测 / 发布消息回答"
   ],
   "一律交给本人": [
    "缺陷是否成立的争议",
    "准出结论"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "qa_api",
   "名称": "测试：接口自动化",
   "关注": [
    "测试服发布",
    "接口合同变动",
    "回归请求"
   ],
   "可以直接回答（有依据时）": [
    "回归结果、用例覆盖：按最近一轮回归记录回答"
   ],
   "一律交给本人": [
    "要不要跑回归、什么时候跑",
    "接口失败的结论（先排除用例问题）"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "qa_perf",
   "名称": "测试：性能测试",
   "关注": [
    "压测窗口",
    "环境占用"
   ],
   "可以直接回答（有依据时）": [
    "压测结果：按已发报告回答"
   ],
   "一律交给本人": [
    "任何涉及正式环境的压测请求"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "qa_lead",
   "名称": "测试负责人",
   "关注": [
    "排期、风险、阻塞",
    "准出"
   ],
   "可以直接回答（有依据时）": [
    "当前测试进度：只汇总已有状态"
   ],
   "一律交给本人": [
    "承诺时间、资源",
    "准出结论"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  },
  {
   "id": "ops",
   "名称": "运营",
   "关注": [
    "运营配置、名单",
    "榜单文案与顺序",
    "活动时间"
   ],
   "可以直接回答（有依据时）": [
    "现在配置的是什么、名单里有没有某某：按已发的配置记录回答"
   ],
   "一律交给本人": [
    "改配置",
    "加删名单"
   ],
   "推荐监控的群": [
    "项目协作群"
   ]
  },
  {
   "id": "backoffice",
   "名称": "后台 UI",
   "关注": [
    "运营 / 配置后台的需求",
    "后台发布"
   ],
   "可以直接回答（有依据时）": [
    "后台哪里改、发没发：按发布记录回答"
   ],
   "一律交给本人": [
    "改功能",
    "权限"
   ],
   "推荐监控的群": [
    "项目协作群"
   ]
  },
  {
   "id": "project_lead",
   "名称": "项目负责人 / 跨团队负责人",
   "关注": [
    "整体进度、阻塞",
    "跨团队依赖",
    "发版决策"
   ],
   "可以直接回答（有依据时）": [
    "进度和待办：按协作库待办报告或已发状态汇总"
   ],
   "一律交给本人": [
    "任何指派、拍板、承诺"
   ],
   "推荐监控的群": [
    "项目协作群",
    "测试群"
   ]
  }
 ]
}```

## 四、工作手册（写入 `C:\qa-agent\工作手册.md`，第 2 步按角色选好段落）

```markdown
# 工作手册（助手照此处理群消息）

## 通用
- 只处理：@我、引用我的消息、我关注的关键词和同事的消息。其他话题 ignore。
- 回复用引用回复，简短客气；不编造数据；不确定就说「我确认一下再回复」。
- **绝不替我接**：别人派活、找我接新需求、让我负责、问我能不能做、问什么时候完成——一律交给我（escalate），不要答应、不要估时间。
- 不在「我的职责范围」（memory\职责范围.md）里的事：交给我或忽略，不回复。
- 一律交给我（escalate）：要我做决定、排期、承诺时间的；涉及线上、数据、权限、费用的；看不懂或没依据的。
- 有人问「XX 找谁 / 归谁管」：查记忆「负责人」，有就答并注明依据日期；没有就 escalate，不猜。
- 有人报以前出现过的问题：查记忆「问题处理」，告诉对方当时的处理和负责人，并 @ 当时的负责人确认；拿不准就 escalate。
- 有人问「我的待办 / 进度 / 看 TODO」：按「我在协作库的待办」回答，原样分 P0 / P1 / P2，不替别人认领。
- 别人回复了我之前问的事：引用回复「收到，谢谢」+ 一句结论。
- 有人纠正了我的回复：致谢并更正，交给我（escalate）让我把规矩补进偏好与禁区。
- 只监听不回复的群：只 ignore 或 escalate。
- project-coordination 协作库只读：我不替本人提交、推送或改协作库。

## 按角色（第 2 步二次确认后写入，只写本人选定的角色）
通用：任何角色收到「能不能做 / 什么时候好 / 你来负责 / 排期」都交给我；只回答有依据的事实（协作库、记忆、群里已发过的通知），回答注明依据；没依据就交给我。
<每个选定的角色一段，格式：
- 角色名（来源：协作库 / 角色职责库 / 本人补充，日期）：关注 ……；有依据时可以直接回答 ……；一律交给我 ……>
```

---

## 五、日常用法（对 AI 助手说这些就行）

| 你说 | 它做 |
|---|---|
| 草稿要不要发 | 在提醒群里直接回：「#编号 可以发送」/「#编号 不发」/「#编号 改成：新内容」/「全部发送」；发「草稿」两个字列出待确认的。也可以运行 `python C:\qa-agent\agent.py review` |
| 看还有哪些没回 / 先写个草稿晚点发 / 全清掉 | 在提醒群发「待回复」列出全部没处理完的事（带草稿）；「#编号 暂存：内容」只存草稿不发，之后「#编号 可以发送」；「清空」全部清掉、不发（v2.5，一位同事提议） |
| 表情（v2.6，默认关） | 提醒群发「表情 开 / 关」；「表情包」看张数，「删表情包 名字」拉黑；只在轻松场合、确定找你时用 |
| 哪些群能自动回复（v2.6） | 提醒群发「群列表」看；「群名 自动回复」后再回「确认开启 群名」才开；「群名 只提醒」立即关 |
| 提醒群问「❓ #编号 是不是归你？」 | 归你就在原会话自己回；不归你在提醒群回「#编号 不归我」，群里不会有任何回复（v2.5.1） |
| 看一下今天的待处理 | 读 `待处理.md`，列给你 |
| 助手正常吗 | 运行 `python C:\qa-agent\agent.py check` |
| 今天处理得怎么样 / 还有什么没处理 | 运行 `python C:\qa-agent\agent.py status`；交给你的事和待确认草稿都在提醒群里，处理完会补一条「✅ 已处理」 |
| 昨天干了什么 | 每天上班自动发到你和自己的钉钉私聊；也可以直接看 `memory\每日总结.md` |
| 提醒群收到「⚠️ 钉钉消息没发出去」 | 先在电脑上运行 `dws doctor`；提示有新版本就 `dws upgrade -y`；同事也都发不出去就是钉钉那边的问题，等恢复。没发出去的回复已存成草稿，恢复后在提醒群回「#编号 可以发送」重发；要紧的先手动发 |
| 角色职责库加一个角色 / 删掉某个角色 / 改某条 | AI 助手改 `C:\qa-agent\角色职责库.json`；改的是你在用的角色时先念给你二次确认，再同步进工作手册 |
| 角色职责库里缺了某个角色 | 不用管，AI 助手发现了会自行补充（标「AI 补充」），补完告诉你；补的是你在用的角色时先念给你确认 |
| 我换角色了 / 多负责一个角色 | AI 助手按第 2 步重走一遍角色职责（展示 → 你修改补充 → 二次确认） |
| 「XX 这事以后归 YY 管」，记一下 | 追加进 `memory\负责人.md` |
| 以后这类问题不要自己回 | 追加进 `memory\偏好与禁区.md` 和工作手册 |
| 多监控一个群 / 少监控一个群 | 你说群名，它查到后问你能不能回复，更新配置 |
| 暂停助手 / 恢复助手 | Windows 停用 / 启用计划任务；macOS `launchctl bootout / bootstrap`；Linux `systemctl --user disable / enable --now`（见 3.4） |
| 切到草稿模式 / 自动模式 | 改 `mode`，下次启动生效（也可以让它立即重启助手） |
| 看 TODO | 在协作库跑待办报告，按 P0 / P1 / P2 给你 |

**换电脑**（也可以换系统，比如 Windows 换 Mac）：把安装目录整个拷走（记忆都在 `memory` 里）；`config.json` 不要拷，到新电脑让 AI 助手重新走一遍第 0–2 步。

> Windows 版已有同事在用；macOS 在维护人电脑上实测（自检、常驻、停止）；Linux 在内网 Ubuntu 24.04 实测（自检、systemd 启停、定时器、停止无残留；钉钉登录部分用替身，未接真实群）。判断用的 AI：Claude Code 在 macOS 实测过；Codex、DSH、WorkBuddy、Qoder 按官方文档接入（DSH 用模拟命令验过参数和传法），未在真机实测；Trae 用自定义命令。遇到问题把 AI 助手的报错截图发给梦无矶。

---
