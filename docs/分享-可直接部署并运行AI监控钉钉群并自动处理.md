# 可直接部署并运行：AI 监控钉钉群并自动处理（全角色版）

> **使用者只需要做一件事：** 把这个文件拖进你自己的 AI 编程助手（Codex、Claude Code、DSH、WorkBuddy、Trae、Qoder 都行，你平时用哪个就用哪个），发一个字「开始」。之后它每一步都会给你编号选项，你回数字就行。
>
> 作者：梦无矶　版本：v3.0 2026-11-19（命令行实时汇报；决策权交给人；状态可见；全角色、任意 AI、Windows / macOS / Linux）　适用：Windows / macOS / Linux + 任一 AI 编程助手（Codex / Claude Code / DSH / WorkBuddy / Trae / Qoder 等）+ 钉钉 CLI（`dws`）
>
> **已经装过的同事升级到 v3.0**：把本文件拖进你的 AI 助手，发「升级到最新版」。先停止旧后台，替换 `C:\qa-agent\agent.py`、`bootstrap_memory.py`，**新增** `C:\qa-agent\console.py`（用第三节 3.2、3.3、3.6 的代码），`角色职责库.json` 没有就按 3.5 写入、已有就不覆盖，**保留** `config.json`、`memory\`、`drafts\`、`工作手册.md`。重新启动后台，运行 `python C:\qa-agent\agent.py check` 看到「版本 v3.0」；重启后浏览器会自动打开操作台。v3.0 起提醒群不再刷「收到消息 / 心跳」这类值守状态（出问题仍提醒），值守状态看操作台顶栏的绿点；原来的汇报窗口默认关闭。无需新增配置。

---

## 平台约定（Windows / macOS / Linux 通用，部署的 AI 先按本机系统换算）

下文的路径和命令**以 Windows 写法为例**。部署的 AI 第 0 步先判断本机系统，之后所有路径、命令都按这张表换算再执行。**用 `python` 还是 `python3`、装在哪个目录，都由 AI 自己按本机情况定，不问使用者**（很多同事不懂这些）：

| 项 | Windows | macOS | Linux |
|---|---|---|---|
| 安装目录（下文的 `C:\qa-agent`） | `C:\qa-agent` | `~/qa-agent`（**不要放桌面 / 文稿 / 下载**：系统隐私保护会让后台任务读不到） | `~/qa-agent` |
| 配置目录（`%USERPROFILE%\.qa-agent`） | `%USERPROFILE%\.qa-agent` | `~/.qa-agent` | `~/.qa-agent` |
| Python 命令（下文的 `python`） | 后台用 `pythonw`，汇报窗口自动用同目录的 `python.exe` | `python3` | `python3` |
| 路径分隔 | `\` | `/` | `/` |
| 开机 / 每天自启（第 6 步） | 计划任务（3.4 A） | LaunchAgent（3.4 B） | systemd 用户服务 + 定时器（3.4 C） |
| 终端 | PowerShell | 终端 | 终端 |

- 后台由计划任务 / launchd / systemd 托管，默认自动显示实时汇报：Windows 独立控制台、macOS「终端」、Linux 桌面终端。已有前台终端时直接在原窗口显示。无图形桌面的 Linux 无法弹窗，会在提醒群提示并继续写 `logs/status.jsonl`，不停止后台。
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
6. **默认**：先明确职责范围、确认通知规则；**助手不自动回复任何消息**（公司要求：决策权交给人）——能答的写成草稿，本人确认后才发，本人可以先问 AI 再决定；**绝不替使用者接需求、任务、排期**、不读私聊；监听的群按角色推荐、由使用者确认；一次收到很多消息时自动开子 Agent 并行处理。
8. **每天上班自动汇报**：每天第一次启动（9 点后）把前一天的总结发到使用者的提醒群（机器人发，有推送）；钉钉监听连续断开 3 次会提醒本人。
9. **默认显示实时汇报**：后台启动后自动打开只读汇报窗口，使用者不必输入命令。Windows 后台仍用 `pythonw`、查看器单独用 `python.exe` 新控制台；macOS 自动打开「终端」；Linux 桌面环境自动打开可用终端。已有前台终端直接在原窗口输出，不重复开窗。关闭查看器不停止独立后台。无图形桌面或启动失败必须明确提示，后台继续写日志；不要虚报开窗成功。显式配置 `report_window: false` 才关闭自动开窗，机器人通知偏好保持原样。
10. **状态必须可见**：启动、收到相关消息、开始处理、处理完成、监听异常、心跳和停止都写入 `logs/status.jsonl`；默认通过提醒群机器人同步，`status_notifications: false` 只关闭机器人状态消息，不删除日志。终端 `watch` 独立于此开关，显示消息上下文、判断摘要和真实结果；草稿待确认、待人决定、发送成功和失败必须区分，不把草稿说成已发送。
7. 第三节是你要写入的文件全文，第四节是写进工作手册的规则；按里面的内容原样写入，命令参数以本机 `--help` 为准，对不上就按本机实际调整，并在最后的汇报里说明改了什么。

---

## 一、风险（第 1 步要给使用者看的摘要）

| 风险 | 本方案怎么控制 |
|---|---|
| 提醒群机器人的地址和密钥 | 只存在你本机 `config.json`；这个机器人只能往你自己的提醒群发消息，泄露了也只能往那个群发；不放心可以随时在群设置里重置 |
| 助手替你接了别人的需求 | 部署第 2.6 步先明确你的职责范围、确认规则；派活、要你负责、要排期的一律不答应、交给你；没确认前只写草稿 |
| 回复是以你本人的钉钉账号发出的 | 不自动回复：所有回复都先写成草稿发到你的提醒群，你确认后才发；每条发出的消息都留痕（谁、何时确认、问过 AI 什么） |
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

### 第 2.6 步　明确你的职责范围，并确认什么时候通知你（必做，选「全部按推荐」也要做）

助手只替你看职责范围内的事，**绝不替你接别人的需求、任务、排期**，也**不会替你在群里说任何话**：能答的写成草稿，你确认后才发。

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

**4）确认通知规则**

```
助手以后这样处理和你有关的消息（所有消息都由你决定发不发）：

【写好草稿，发到提醒群等你确认】
- 职责范围内、记忆或协作库里有明确依据的问题，附上依据
- 别人回了你之前问的事 → 草稿「收到，谢谢」
- 你回「#编号 可以发送」才发；也可以「#编号 改成：…」「#编号 不发」，或先「#编号 问：依据是什么？」

【只提醒你，不写草稿】
- 派活、找你接新需求、让你负责、问你能不能做、问什么时候完成 —— 一律不替你答应
- 要你拍板、排期、承诺上线或测试时间
- 涉及线上、数据、权限、费用
- 不在你职责范围内的事、没有依据或看不懂的

【不处理】
- 和你无关、没 @ 你、不含你关注的关键词的消息、别人之间的对话

超过 2 小时还没处理的，会再提醒你一次（可以改：在提醒群发「提醒间隔 3小时」，或「提醒间隔 关」）。
1. 就按这个（推荐）
2. 规则还要改（回要改的地方）
```

选 1 后设 `"scope_confirmed": true`，规则原文写进 `工作手册.md` 的「通知规则」一节。选 2 就按使用者的话改规则，再问一次。

### 第 3 步　确认要监控的群（按角色推荐，回数字确认）

1. 自动：按第 2 步确认的角色，取角色职责库里的「推荐监控的群」（如「项目协作群」「测试群」）。部署时问一句「你们的<项目协作群>叫什么？回群名」。都用 `dws chat +chat-search --query "<群名>" --format json` 查 `openConversationId`；搜不到说明你不在群里，告诉你「你还不在 <群名>，请先找群主拉你进群」，只用搜到的继续。
2. 问：
   ```
   助手推荐监控这些群：<群名 + 用途，一行一个>
   助手不会在任何群里自动回复，所有消息都由你确认后才发。
   1. 就这些（推荐）
   2. 还要再加别的群
   3. 去掉其中一个（回群名）
   ```
3. 选 2 时，再问一次「回群名，一个就行」，查到后问 `1. 可以往这个群发（你确认过的草稿） 2. 只看，不往这个群发任何东西`，可以重复加。
4. 自动：可以发的写进 `config.json` 的 `groups`，只看的写进 `readonly_groups`。各群用途写进 `memory\角色.md` 的「各群用途」。

### 第 3.5 步　建提醒群和提醒机器人（必做，约 1 分钟，v3.0 起群由助手自动建）

所有提醒（需要你处理、草稿待确认、已处理、每日汇报、监听异常）都由一个机器人发到只有你自己的群里：钉钉有推送，消息有历史可翻。

AI 助手先问：

```
1. 我已经有自己的提醒群（和机器人），直接用（推荐，不新建）
2. 没有，帮我建一个
```

选 1：问群名，有机器人就请使用者把 Webhook 地址和 SEC 密钥发过来，运行 `python C:\qa-agent\agent.py setup-notify --group "<群名>" --webhook "<地址>" --secret "<SEC…>"`，助手绑定后发一条「🧪 助手自检」就完成；群里还没有机器人就只带 `--group`，按下面第 2～4 条加一个。

选 2：AI 助手运行 `python C:\qa-agent\agent.py setup-notify`（macOS / Linux：`python3 ~/qa-agent/agent.py setup-notify`），它会：

1. 用钉钉 CLI 自动建好群「群消息助手·<你的名字>」，只有你自己，并写进配置的 `notify_group`；
2. 在这个群里发一条加机器人的步骤。**钉钉不允许程序代建自定义机器人、也拿不到它的地址和密钥，这一步只能本人点**：群设置 → 机器人 → 添加机器人 → 自定义 → 安全设置勾「加签」，复制 `SEC…` 密钥 → 完成后复制 Webhook 地址；
3. 你把 **Webhook 地址** 和 **SEC 密钥** 直接发在这个群里，助手 15 分钟内读到后自动写进 `%USERPROFILE%\.qa-agent\config.json` 的 `webhook` / `secret`（不写进别的文件、不回显），再发一条「🧪 助手自检」；
4. 看到自检后，把群里带地址和密钥的两条消息撤回或删掉。

AI 助手只问一句：`1. 看到自检了  2. 没看到`。没看到就让使用者核对是否勾了「加签」、地址是否完整，再运行一次 `setup-notify`。

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

后台启动后会自动显示实时汇报窗口：Windows 独立控制台、macOS「终端」、Linux 桌面终端。使用者不需要运行 `watch`。窗口只读日志、不启动监听或消费事件，同一安装目录已有自动查看器时不重复打开；窗口可跨后台重启继续查看。关闭查看器不会停止独立后台，下次启动后台会重新打开。若使用者本来就在前台终端直接运行主程序，汇报显示在原窗口，关闭该主程序会停止它自己的工作。

### 第 7 步　验收并汇报（AI 助手自己做）

逐项检查并把结果用 ✅ / ❌ 列给使用者：

1. 能收到选中群的消息（让使用者在某个群里 @ 自己或发一个关键词，看 `logs\<日期>.log` 出现「决定」）
2. 无关消息不进 `inbox.jsonl`，自己发的消息不触发
3. 提醒群收到「📝 #编号 草稿待确认」，`python C:\qa-agent\agent.py review` 能列出草稿、回编号发出
4. 后台默认自动打开一份汇报窗口，无需用户运行命令；Windows 用独立 `python.exe` 控制台，不套隐藏子进程参数；macOS / Linux 桌面有对应窗口。已在前台终端运行时不另开窗口，其余业务子进程保持隐藏
5. 需要人处理的事在提醒群收到机器人消息「🔔 #编号 需要你处理」
6. `memory\职责范围.md` 存在、`config.json` 里 `scope_confirmed` 为 true；让同事在群里 @ 你「这个需求你来测一下吧」，助手**不答应**，提醒群收到「🔔 需要你处理」
7. 计划任务存在、用的是 pythonw、到 21:00 进程自己退出（选了自启时）
8. 日志里没有任何 token
9. 提醒群收到「🧪 助手自检」和「☀️ 每日汇报」（第一次部署当天汇报内容是「还没有前一天的总结」）
10. 自动打开的窗口显示最近状态，新消息出现收到、开始处理、具体结论，草稿与发送分开显示；关闭窗口不停止独立后台，重启后台不重复打开已有自动窗口。Linux 无图形桌面或终端启动失败时有明确提示，监听继续。确认只启动了一份后台，不以窗口打开或单次心跳作为全部处理成功的依据

最后告诉使用者：「部署完成。日常对我说下面这些话就行」，并把第五节「日常用法」贴给他。

---

## 三、AI 助手要写入的文件

目录结构：

```
C:\qa-agent\
  agent.py                 监听 + 过滤 + 决策 + 执行 + 记忆
  console.py               本机操作台（v3.0，网页上直接处理，第 3.6 节）
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
  "mode": "draft",
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
  "emoji": false,
  "keep_days": 30,
  "remind_after_minutes": 120,
  "ai_fallback": true
}
```

`mode`：v2.8 起固定为草稿确认（填什么都一样，不再有自动回复）。`remind_after_minutes`（v2.8）：没处理的事超过多少分钟再提醒一次，默认 120，0 = 不再提醒；提醒群发「提醒间隔 3小时 / 30分钟 / 关」随时改。`status_notifications`（v2.9）：是否把状态同步到提醒群，默认 `true`；设为 `false` 仍保留 `logs/status.jsonl`。`status_heartbeat_minutes`（v2.9）：心跳间隔，默认 15 分钟。`workers` 是常驻几个处理通道；一次收到很多消息、待处理超过 `burst_threshold` 批时，会临时开子 Agent（多开 AI 处理通道，最多 `max_workers` 个，处理完自动退出）；`merge_seconds` 是同一会话多少秒内连发合并成一次判断，`ai`（v2.7）：判断用哪个 AI，`codex` / `claude` / `dsh` / `codebuddy`（WorkBuddy）/ `qoder`，不填就自动用本机装了的第一个；Trae 等其他工具填 `ai_cmd`（命令数组，用 `{prompt}` 占位或配 `"ai_prompt": "stdin"` 从标准输入传）。`ai_model` 可填一个更快的模型名（旧配置的 `codex_model` 仍然有效）。`webhook` / `secret` **必填**：本人专属提醒群里自定义机器人的地址和加签密钥（第 3.5 步建），所有提醒、草稿、每日汇报和状态通知都由它发。`emoji`（v2.6）：表情默认关，本人在提醒群发「表情 开」才开；部署最后跑一次 `python agent.py stickers` 下载内置表情包索引。`keep_days`（v2.7）：收到的消息原文、群历史导出、旧日志只保留最近 N 天（默认 30，0 = 不清）；提炼好的记忆和草稿不受影响。`ai_fallback`（v2.7）：判断用的 AI 没结果时，自动换本机装了的其他 AI 再试（默认开）。`update_url` / `update_page`：助手每天查一次有没有新版本、在哪下载，一般不用改。

### 3.2 agent.py（v2：后台静默、并行 + 子 Agent、合并、两种模式）

```python
"""群消息助手 v2（Windows / macOS / Linux，默认实时汇报；v2.7 起不限 QA，按协作库角色适配全部角色）：dws 长连接监听 → 过滤 → AI 只读决策（Codex / Claude Code / WorkBuddy / Qoder / Trae 等，使用者自己装的那个）→ 脚本执行 → 记忆追加。
v2（2026-11-13）：全程不弹窗口（pythonw + 子进程隐藏 + 系统通知）；两路并行处理、同会话 20 秒内连发合并一次判断；
积压时自动开子 Agent（临时多开 Codex 处理通道，最多 max_workers 个，空了自动退出）；
每天上班把前一天总结发到本人自己的钉钉私聊；钉钉监听连续断开会提醒本人；
v2.8（内网版，项目负责人 11-18：决策权交给人）：取消自动回复——任何消息都先写成草稿，本人确认后才发；连「收到，我确认一下」回执和自动点表情也取消。
  超过 2 小时（remind_after_minutes，可改，提醒群「提醒间隔 3小时 / 关」）还没处理的事，合并再提醒一次。
  提醒群「#编号 问：…」可以先问清楚 AI（依据、背景、改写），再决定发不发；每条发出的消息都留痕（谁、何时确认、问过什么、依据），存 audit/发出留痕.jsonl，不随保留期清理。
v2.9（内网版，11-19）：状态可见——启动、收到相关消息、开始处理、处理完成、监听异常、独立心跳和停止都写入 logs/status.jsonl；状态通知默认发提醒群，心跳默认每 15 分钟一次。
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
用法：pythonw agent.py            后台运行并自动打开汇报窗口（Windows 计划任务；macOS / Linux 用 python3，由 launchd / systemd 托管）
      python agent.py review     列出草稿，回编号批量发送 / 删除
      python agent.py send <草稿> 发送一条草稿
      python agent.py check      自检（环境、登录、配置）
      python agent.py status     今天处理了多少、还有几件没处理
      python agent.py watch      打开只读实时汇报窗口，不重复启动监听
      python agent.py watch --once  查看最近 20 条状态后退出
      python agent.py clear      清空待回复（没处理完的事和草稿全部清掉，不发出）
      python agent.py stickers   下载 / 更新内置表情包索引（v2.6）
      python agent.py audit [N]  看最近 N 条发出留痕（谁、何时确认、问过 AI 什么）（v2.8）
      python agent.py purge      立刻清掉原始记录（消息原文、群历史导出、旧日志），记忆和草稿不动（v2.7）
配置 ~/.qa-agent/config.json（Windows 是 %USERPROFILE%\\.qa-agent\\config.json）；记忆在安装目录的 memory/（Windows C:\\qa-agent\\memory\\，macOS / Linux ~/qa-agent/memory/）。"""
import atexit, base64, datetime as dt, glob, signal, hashlib, hmac, json, os, queue, re, shlex, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request
from collections import deque

VERSION = "v3.0 2026-11-19"
HOME = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(os.path.expanduser("~"), ".qa-agent", "config.json")
DEFAULTS = {"my_name": "", "person_id": "", "roles": [], "project": "", "groups": {}, "readonly_groups": {}, "keywords": [], "people": [],
            "listen_dm": False, "mode": "auto", "max_auto_replies_per_10min": 3, "daily_codex_limit": 300, "workers": 2, "merge_seconds": 20,
            "burst_threshold": 3, "max_workers": 4, "ack_on_escalate": True, "notify_group": "", "scope_confirmed": False,
            "codex_model": "", "webhook": "", "secret": "", "window": ["09:00", "21:00"],
            "emoji": False, "emoji_names": ["赞", "OK", "收到", "谢谢", "辛苦了", "加油", "鼓掌"],
            "keep_days": 30, "remind_after_minutes": 120, "status_notifications": False, "status_heartbeat_minutes": 15, "report_window": False,
            "update_url": "https://raw.githubusercontent.com/Lvan826199/dingtalk-group-assistant/main/agent.py", "update_page": "https://github.com/Lvan826199/dingtalk-group-assistant"}
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

# ---- 开机自启（LaunchAgent / systemd / 计划任务）带的 PATH 很短，找不到装在用户目录下的 AI 命令和钉钉 CLI
# （macOS 上 claude / codex 默认在 ~/.local/bin，launchd 的 PATH 里没有，11-18 实测）。把常见安装目录补到 PATH 末尾，已有的不重复加。
def _extend_path():
    h = os.path.expanduser("~")
    if os.name == "nt":
        extra = [os.path.join(os.environ.get("APPDATA", ""), "npm"), os.path.join(h, ".local", "bin"), os.path.join(h, "AppData", "Local", "Programs", "Python", "Launcher")]
    else:
        extra = [os.path.join(h, ".local", "bin"), os.path.join(h, ".npm-global", "bin"), "/opt/homebrew/bin", "/usr/local/bin",
                 os.path.join(h, ".bun", "bin"), os.path.join(h, ".cargo", "bin"), os.path.join(h, "bin"), "/snap/bin"]
        extra += sorted(glob.glob(os.path.join(h, ".nvm", "versions", "node", "*", "bin")), reverse=True)[:1]   # nvm 装的 node / npm 全局命令
    cur = os.environ.get("PATH", "").split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join(cur + [d for d in extra if d and os.path.isdir(d) and d not in cur])


_extend_path()


# ---- 开机自启（LaunchAgent / systemd / 计划任务）带的 PATH 很短，找不到装在用户目录下的 AI 命令和钉钉 CLI
# （macOS 上 claude / codex 默认在 ~/.local/bin，launchd 的 PATH 里没有，11-18 实测）。把常见安装目录补到 PATH 末尾，已有的不重复加。
def _extend_path():
    h = os.path.expanduser("~")
    if os.name == "nt":
        extra = [os.path.join(os.environ.get("APPDATA", ""), "npm"), os.path.join(h, ".local", "bin"), os.path.join(h, "AppData", "Local", "Programs", "Python", "Launcher")]
    else:
        extra = [os.path.join(h, ".local", "bin"), os.path.join(h, ".npm-global", "bin"), "/opt/homebrew/bin", "/usr/local/bin",
                 os.path.join(h, ".bun", "bin"), os.path.join(h, ".cargo", "bin"), os.path.join(h, "bin"), "/snap/bin"]
        extra += sorted(glob.glob(os.path.join(h, ".nvm", "versions", "node", "*", "bin")), reverse=True)[:1]   # nvm 装的 node / npm 全局命令
    cur = os.environ.get("PATH", "").split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join(cur + [d for d in extra if d and os.path.isdir(d) and d not in cur])


_extend_path()


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


def ai_engine(only=None):
    """返回 (显示名, 参数模板, prompt 传法)。ai_cmd 自定义优先（如 Trae：部署时按 traecli --help 填），其次 ai 指定的，最后自动找本机装了的。
    only=预设名时只看这一个（备用 AI 用）。"""
    if CFG.get("ai_cmd") and not only:
        return CFG.get("ai", "自定义"), list(CFG["ai_cmd"]), CFG.get("ai_prompt", "stdin")
    names = [only] if only else ([CFG["ai"]] if CFG.get("ai") in AI_PRESETS else list(AI_PRESETS))
    for k in names:
        pr = AI_PRESETS[k]
        exe = which(pr["bin"])
        if shutil.which(exe) or os.path.exists(exe):
            model = CFG.get("ai_model") or CFG.get("codex_model")
            return pr["name"], [exe] + pr["args"] + ((pr["model"] + [model]) if model and pr["model"] else []), pr["prompt"]
    return "（没找到）", [], "stdin"


def ai_exec(prompt, timeout=300):
    """跑一次 AI，返回它的最后输出文本。主 AI 没结果（没装、报错、卡住）时，按顺序试本机装了的其他 AI（v2.7；config "ai_fallback": false 关掉）。都不行返回空串。"""
    name, args, how = ai_engine()
    text = _ai_once(name, args, how, prompt, timeout)
    if text.strip() or CFG.get("ai_fallback") is False:
        return text
    for k in AI_PRESETS:
        n2, a2, h2 = ai_engine(only=k)
        if not a2 or n2 == name:
            continue
        log(name, "没结果，改用备用", n2)
        text = _ai_once(n2, a2, h2, prompt, timeout)
        if text.strip():
            if not STATE.get("fallback_told"):
                STATE["fallback_told"] = True
                notify("🔁 判断用的 AI 换成了备用", f"{name} 没给出结果（没装好、报错或卡住），这次改用 {n2}。经常这样的话，检查一下 {name} 在终端里能不能用。今天不再重复提醒。")
            return text
    return text


def _ai_once(name, args, how, prompt, timeout):
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
STATUS_LOG = os.path.join(HOME, "logs", "status.jsonl")
LISTENERS = {}      # tag -> {started, alive}
LAST_EVENT = {"t": 0, "summary": ""}


def log(*a, console=True):
    line = dt.datetime.now().strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    with LOCK:
        LOG.write(line + "\n"); LOG.flush()
    if console and sys.stdout and sys.stdout.isatty():
        console_write(line)


def report_text(value, limit=800):
    """运行窗口只展示摘要；配置中的机器人凭据和常见密钥字段打码。"""
    text = str(value or "")
    for key in ("webhook", "secret"):
        if CFG.get(key):
            text = text.replace(str(CFG[key]), "[已隐藏]")
    text = re.sub(r"(?i)(\b(?:access_token|token|secret|password|x-internal-key)\b[\"']?\s*[:=]\s*[\"']?)[^\s,\"'}]+", r"\1[已隐藏]", text)
    text = re.sub(r"(?i)(\bauthorization\s*[:=]\s*)(?:Bearer\s+)?[^\s,]+", r"\1[已隐藏]", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x1f\x7f-\x9f]", " ", text)
    return " ".join(text.split())[:limit]


def console_write(text):
    if sys.stdout is None:
        return
    try:
        try:
            print(text, flush=True)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"
            print(text.encode(encoding, errors="backslashreplace").decode(encoding), flush=True)
    except (BrokenPipeError, OSError):
        pass


def format_report(rec):
    stamp = report_text(rec.get("time"), 30)
    stage = report_text(rec.get("stage"), 40)
    context = " / ".join(report_text(rec.get(k), 80) for k in ("group", "sender") if rec.get(k))
    ref = report_text(rec.get("message_id"), 100)
    title = f"[{stamp}] {stage}" + (f" · {context}" if context else "") + (f" · msg={ref}" if ref else "")
    lines = [title]
    if rec.get("preview"):
        lines.append("  原消息：" + report_text(rec["preview"], 180))
    if rec.get("detail"):
        lines.append("  " + report_text(rec["detail"]))
    return "\n".join(lines)


def status_event(stage, detail="", announce=False, event=None):
    """把值守状态落盘；announce=True 时同步发提醒群，避免助手静默卡住。"""
    rec = {"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "stage": stage,
           "detail": report_text(detail), "pid": os.getpid(), "version": VERSION}
    if event:
        cid = event.get("conversation_id")
        rec.update(group=report_text({**CFG["groups"], **CFG["readonly_groups"]}.get(cid, "提醒群" if cid == CFG.get("notify_group") else "私聊/其他会话"), 80),
                   sender=report_text(event.get("sender"), 80), message_id=report_text(event.get("message_id"), 100))
        if stage in ("收到消息", "开始处理"):
            rec["preview"] = report_text(event.get("content"), 180)
    with LOCK:
        with open(STATUS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log("状态", stage, rec["detail"], console=False)
    if sys.stdout and sys.stdout.isatty():
        console_write(format_report(rec))
    # v3.0：值守状态改在操作台顶栏看（绿点），提醒群默认不再刷「收到消息 / 心跳」；出问题的还照发
    if announce and (CFG.get("status_notifications") or stage in ("监听异常", "发送失败", "处理失败", "汇报窗口未打开")):
        notify(f"📡 {stage}", format_report(rec) if event else rec["detail"])


def report_records(path, follow=True, tail=20):
    """只读状态日志；保留半行，支持文件截断/替换，不碰监听或消费游标。"""
    offset, identity, initial = 0, None, True
    while True:
        records = deque(maxlen=tail) if initial else []
        try:
            with open(path, "rb") as f:
                st = os.fstat(f.fileno())
                current = (st.st_dev, st.st_ino)
                if current != identity or st.st_size < offset:
                    offset = 0
                identity = current
                f.seek(offset)
                while True:
                    line = f.readline()
                    if not line or not line.endswith(b"\n"):
                        break
                    offset = f.tell()
                    try:
                        rec = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(rec, dict):
                        records.append(rec)
        except FileNotFoundError:
            pass
        yield from records
        initial = False
        if not follow:
            return
        yield None


def report_window_lock():
    """一个安装目录只保留一份自动查看器；锁随进程退出释放，不触碰事件。"""
    f = open(os.path.join(HOME, "logs", "report-window.lock"), "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if os.fstat(f.fileno()).st_size == 0:
                f.write(b"0"); f.flush()
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        f.close()
        return None


def open_report_window():
    """默认随后台打开只读查看器。已有交互终端直接输出；查看器不属于监听子进程。"""
    if CFG.get("report_window") is False:
        status_event("汇报窗口", "已按本机设置关闭自动开窗，状态仍写入日志")
        return
    if sys.stdout and sys.stdout.isatty():
        status_event("汇报窗口", "实时汇报已在当前终端显示")
        return
    try:
        lock = report_window_lock()
        if lock is None:
            status_event("汇报窗口", "已有自动汇报窗口，继续使用，不重复打开")
            return
        lock.close()
        args = [sys.executable, "-u", os.path.abspath(__file__), "watch", "--auto"]
        if sys.platform == "win32":
            # pythonw 不附带控制台；查看器必须用同目录的 python.exe，且不能套 NOWIN。
            if os.path.basename(args[0]).lower() == "pythonw.exe":
                args[0] = os.path.join(os.path.dirname(args[0]), "python.exe")
            subprocess.Popen(args, cwd=HOME, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10))
        elif sys.platform == "darwin":
            script = os.path.join(HOME, "logs", "实时汇报.command")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nexec " + shlex.join(args) + "\n")
            os.chmod(script, 0o700)
            r = run(["/usr/bin/open", "-a", "Terminal", script], timeout=15)
            if r.returncode:
                raise OSError((r.stderr or r.stdout or "Terminal 启动失败")[:200])
        else:
            if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                raise OSError("没有图形桌面会话，无法开终端窗口；后台继续运行，状态写入 logs/status.jsonl")
            terminals = [("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"), ("xterm", "-e")]
            terminal = next(([exe, sep] for name, sep in terminals if (exe := shutil.which(name))), None)
            if not terminal:
                raise OSError("未找到终端程序；请安装桌面终端或在本机终端运行 agent.py watch")
            subprocess.Popen(terminal + args, cwd=HOME, start_new_session=True)
        status_event("汇报窗口", "已请求打开实时汇报窗口；窗口会自行显示最近记录和新状态")
    except (OSError, subprocess.SubprocessError) as ex:
        detail = report_text(ex)
        status_event("汇报窗口未打开", detail)
        notify("⚠️ 实时汇报窗口未打开", detail + "。后台继续运行；查看日志或在终端运行 agent.py watch。")


def watch(once=False, auto=False):
    lock = report_window_lock() if auto else None
    if auto and lock is None:
        console_write("已有自动汇报窗口，本窗口退出，不启动监听。")
        return
    console_write("群消息助手 · 实时汇报（只读查看，不启动第二套监听；Ctrl+C 只关闭查看窗口）")
    last, shown, pulse = None, 0, time.monotonic()
    try:
        for rec in report_records(STATUS_LOG, follow=not once):
            if rec is not None:
                console_write(format_report(rec)); last = rec; shown += 1; pulse = time.monotonic()
            else:
                if time.monotonic() - pulse >= 60:
                    console_write("等待新状态；最后记录：" + report_text((last or {}).get("time") or "暂无") + "。此窗口仅展示日志，进程存活和处理结果需结合状态核对。")
                    pulse = time.monotonic()
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if lock:
            lock.close()
    if not shown:
        console_write("尚无状态记录；请确认后台助手已启动，升级后已重启运行。")


def status_snapshot():
    alive = [name for name, x in LISTENERS.items() if x.get("alive")]
    opened = len(_open_load())
    last = LAST_EVENT.get("summary") or "无"
    return f"监听 {len(alive)}/{len(LISTENERS)}（{'、'.join(alive) or '无'}）；处理通道 {ACTIVE['n']}；队列 {Q.qsize() + READY.qsize()}；待处理 {opened}；最近事件 {last}"


def heartbeat_loop():
    """独立线程定期报告；Codex / 监听线程卡住时，外部 watchdog 仍可依靠 status.jsonl 判断最后心跳。"""
    while in_window():
        mins = max(1, int(CFG.get("status_heartbeat_minutes") or 15))
        time.sleep(mins * 60)
        if in_window():
            status_event("心跳", status_snapshot(), announce=bool(CFG.get("status_notifications")))


def in_window():
    s, e = CFG["window"]; now = dt.datetime.now().strftime("%H:%M")
    return s <= now < e


def minutes_left():
    e = dt.datetime.combine(dt.date.today(), dt.time.fromisoformat(CFG["window"][1]))
    return max(0, int((e - dt.datetime.now()).total_seconds() // 60))


def notify(title, text):
    """提醒本人：只走本人专属群的机器人（有推送、有历史）。机器人没配或发送失败时记进 待处理.md 和日志，第二天的汇报里会写出来。"""
    ok = False
    if CFG.get("quiet_new_items") and title[:1] in ("🔔", "❓", "📝"):
        log("新事项只进操作台，不发提醒群", title); return True          # 和别的值守并行时避免提醒群重复（11-19）
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


def _resolve_group(q):
    """群名或 openConversationId → openConversationId（群名要唯一命中）。"""
    if q.startswith("cid"):
        return q
    r = run([DWS, "chat", "+chat-search", "--query", q, "--format", "json"], timeout=60)
    ids = list(dict.fromkeys(re.findall(r'"openConversationId"\s*:\s*"([^"]+)"', r.stdout or "")))
    return ids[0] if len(ids) == 1 else None


def setup_notify(wait_minutes=15, group="", webhook="", secret=""):
    """v3.0：提醒群自动建好（dws 建群，只有本人），再引导本人在群里加自定义机器人。
    钉钉开放接口不支持创建自定义机器人、也拿不到它的地址和密钥，这一步只能本人在群设置里点（约 1 分钟）；
    本人把地址和加签密钥直接发在这个群里，助手读到后自己写进配置、发一条自检，不用手改任何文件。"""
    # 已有提醒群 / 机器人的直接绑定，不强制新建（11-19 梦无矶）：--group 群名或 cid；--webhook 地址 --secret SEC 密钥
    if group:
        cid = _resolve_group(group)
        if not cid:
            print(f"没找到唯一的群「{group}」，换个更完整的群名，或直接给 openConversationId"); return False
        save_cfg("notify_group", cid); print("已绑定提醒群", group)
    if webhook and secret:
        save_cfg("webhook", webhook); save_cfg("secret", secret)
    if CFG.get("notify_group") and CFG.get("webhook") and CFG.get("secret"):
        ok = notify("🧪 助手自检", "已绑定你现有的提醒群和机器人：以后草稿、提醒、日报都从这里发。")
        print("已用现有的群和机器人，自检", "成功" if ok else "失败（核对地址、密钥是否对应这个群的机器人）"); return ok
    cid = CFG.get("notify_group")
    if not cid:
        name = f"群消息助手·{CFG.get('my_name') or '提醒'}"
        r = run([DWS, "chat", "+chat-create", "--name", name, "--yes", "--format", "json"], timeout=90)
        m = re.search(r'"openConversationId"\s*:\s*"([^"]+)"', r.stdout or "")
        if not m:
            print("建群失败：", (r.stdout or r.stderr or "")[:300]); return False
        cid = m.group(1); save_cfg("notify_group", cid); print(f"已建好提醒群「{name}」（只有你一个人）")
    steps = ("这是你的群消息助手提醒群，只有你自己。还差一步（钉钉不允许程序代建机器人，要你点一下，约 1 分钟）：\n"
             "1. 电脑钉钉打开本群 → 右上角「群设置」→「机器人」→「添加机器人」→「自定义」\n"
             "2. 名字随便填（比如「助手」），安全设置勾「加签」，复制那串以 SEC 开头的密钥\n"
             "3. 点「完成」，复制 Webhook 地址\n"
             "4. 把 **Webhook 地址** 和 **SEC 密钥** 直接发在本群（一条或两条都行）\n"
             "助手读到后自动写进配置，再发一条「🧪 助手自检」，你在群里看到就好了。")
    run([DWS, "chat", "+messages-send", "--group", cid, "--markdown", steps, "--yes", "--format", "json"], timeout=60)
    print("已在提醒群发了加机器人的步骤；把 Webhook 地址和 SEC 密钥发进群里，我等你", wait_minutes, "分钟")
    since, hook, sec, end = dt.datetime.now() - dt.timedelta(minutes=1), CFG.get("webhook") or "", CFG.get("secret") or "", time.time() + wait_minutes * 60
    while time.time() < end and not (hook and sec):
        time.sleep(10)
        r = run([DWS, "chat", "message", "list", "--group", cid, "--time", f"{since:%Y-%m-%d %H:%M:%S}", "--direction", "newer", "--limit", "20", "--format", "json"], timeout=60)
        text = r.stdout or ""
        m = re.search(r"https://oapi\.dingtalk\.com/robot/send\?access_token=[0-9a-f]{20,}", text)
        hook = m.group(0) if m else hook
        m = re.search(r"\bSEC[0-9a-f]{40,}\b", text)
        sec = m.group(0) if m else sec
    if not (hook and sec):
        print("没等到地址和密钥；发进群后再运行一次：python agent.py setup-notify"); return False
    save_cfg("webhook", hook); save_cfg("secret", sec)
    ok = notify("🧪 助手自检", "提醒机器人配好了：以后草稿、提醒、日报都从这里发。\n建议把群里那两条带地址和密钥的消息撤回或删除。")
    print("机器人已配置，自检", "成功" if ok else "失败（核对是否勾了「加签」、地址是否完整）"); return ok


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
                               "what": str(e.get("content") or "")[:60], "why": why[:60], "at": f"{dt.datetime.now():%m-%d %H:%M}", "ts": time.time(), "event": e}
    _open_save(d)
    return no


def open_close(no, why):
    d = _open_load()
    x = d.pop(no, None)
    if x:
        _open_save(d); log("已处理", no, why)
        status_event("事项已关闭", f"{no}：{why}", event=x.get("event"))
        notify(f"✅ {no} 已处理", f"{x['who']}：{x['what']}\n{why}")


def close_by_conversation(cid):
    """本人在这个会话里亲自回复了 → 这个会话里交给本人的事都算处理了。"""
    for no, x in list(_open_load().items()):
        if x.get("cid") == cid:                                           # 本人（或代本人值守的程序）已在原会话回复：草稿也作废
            f, _ = draft_by_no(no)
            if f:
                os.remove(f)
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
    """这个群能不能往里发消息（只发本人确认过的草稿）。v2.8 起没有自动回复：groups 里的群可发草稿，readonly_groups 只看。"""
    return cid in CFG["groups"]


def upgrade_ask():
    """v2.8 升级提示：以前开过自动回复的，告诉本人现在一律改成草稿确认（公司要求：决策权交给人）。只提示一次。"""
    mark = os.path.join(HOME, "logs", "v2.8-notice")
    if os.path.exists(mark) or not CFG["groups"]:
        return
    open(mark, "w").close()
    notify("ℹ️ v2.8：不再自动回复", "从这一版起，助手不在群里自动回复任何消息：能答的写成草稿发到这里，你确认后才发；回执「收到，我确认一下」和自动点表情也取消了。\n"
           "拿不准可以先问：「#编号 问：依据是什么？」。每条发出的消息都会留痕。")


def group_command(text):
    """「群列表」看监听的群；「<群名> 只看」以后这个群的草稿也不发（只提醒）；「<群名> 可发草稿」恢复。v2.8 起没有自动回复。"""
    allg = {**CFG["groups"], **CFG["readonly_groups"]}
    if text in ("清理记录", "清理原始记录"):
        n = purge_now()
        notify("🧹 原始记录已清理", f"清掉 {n} 条 / 个（收到的消息原文、群历史导出、旧日志）。提炼好的记忆、草稿和发出留痕没动。平时会自动只保留最近 {CFG.get('keep_days') or '不限'} 天。"); return True
    m = re.fullmatch(r"提醒间隔\s*(关|关闭|0|\d+(?:\.\d+)?)\s*(小时|h|分钟|分|min)?", text, re.I)
    if m:
        v = m.group(1)
        mins = 0 if v in ("关", "关闭", "0") else int(float(v) * (60 if (m.group(2) or "小时").lower() in ("小时", "h") else 1))
        save_cfg("remind_after_minutes", mins)
        notify("⏰ 已设置", "超时不再重复提醒" if not mins else f"没处理的事超过 {mins // 60 if mins % 60 == 0 else mins} {'小时' if mins % 60 == 0 else '分钟'}会再提醒一次"); return True
    if text in ("群列表", "监听群", "看群"):
        rows = [f"{n}：{'可发草稿（你确认后发）' if can_reply(c) else '只看'}" for c, n in allg.items()]
        notify("👥 监听的群", "\n".join(rows) + "\n改：发「群名 只看」或「群名 可发草稿」。所有消息都要你确认才会发出。"); return True
    if re.search(r"自动回复|确认开启", text):
        notify("ℹ️ 不提供自动回复", "按公司要求，决策权交给人：助手只写草稿，你确认后才发。拿不准可以先问「#编号 问：……」。"); return True
    m = re.fullmatch(r"(.+?)\s*(只看|只提醒|不回复|可发草稿|可以发)", text)
    if not m:
        return False
    name, ro = m.group(1).strip(), m.group(2) in ("只看", "只提醒", "不回复")
    hit = [c for c, n in allg.items() if name == n] or [c for c, n in allg.items() if name in n]
    if len(hit) != 1:
        notify("❓ 没认出是哪个群", f"「{name}」匹配到 {len(hit)} 个。发「群列表」看准确群名。"); return True
    cid = hit[0]; gname = allg[cid]
    g, rog = dict(CFG["groups"]), dict(CFG["readonly_groups"])
    g.pop(cid, None); rog.pop(cid, None)
    (rog if ro else g)[cid] = gname
    save_cfg("groups", g); save_cfg("readonly_groups", rog)
    notify("👥 已切换", f"{gname}：" + ("只看，草稿也不往这个群发" if ro else "可发草稿，你确认后发")); return True


def sticker_command(text):
    """提醒群表情指令，认了就返回 True。"""
    m = re.fullmatch(r"表情\s*(开|关|打开|关闭|on|off)", text, re.I)
    if m:
        on = m.group(1).lower() in ("开", "打开", "on")
        save_cfg("emoji", on)
        notify("😀 表情包已" + ("打开" if on else "关闭"), f"表情包{'会在轻松的场合附在草稿里建议，你确认发送时才一起发' if on else '不再建议'}。表情包 {len(stickers())} 张" + ("" if stickers() else "，还没下载：在电脑上运行 python agent.py stickers") + "。")
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
    """v2.8 起取消：「收到，我确认一下再回复」也是没经本人确认就发出的话，不再发。保留函数名兼容旧调用。"""
    return


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


AUDIT = os.path.join(HOME, "audit", "发出留痕.jsonl")    # v2.8：每条发出的消息谁确认的、问过什么、依据；不随保留期清理


def audit(no, ev, text, confirm, sticker="", reason=""):
    os.makedirs(os.path.dirname(AUDIT), exist_ok=True)
    x = _open_load().get(no, {})
    rec = {"发出时间": f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}", "编号": no, "群": {**CFG["groups"], **CFG["readonly_groups"]}.get(ev.get("conversation_id"), ev.get("conversation_id")),
           "原消息": {"谁": ev.get("sender"), "内容": str(ev.get("content") or "")[:500], "消息ID": ev.get("message_id")},
           "发出内容": text, "表情包": sticker, "确认人": CFG["my_name"], "确认方式": confirm[:200],
           "AI 依据": reason or x.get("reason", ""), "确认前问过 AI": x.get("qa", [])}
    with LOCK, open(AUDIT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ask_ai(no, question):
    """「#编号 问：……」：带着原消息、草稿、依据、记忆去问 AI；AI 可以给答复，也可以按要求改草稿。只回提醒群，不往原会话发任何东西。"""
    x = _open_load().get(no)
    f, d = draft_by_no(no)
    if not x and not d:
        notify(f"❓ 没找到 {no}", "可能已经处理完了。发「待回复」看还有哪些。"); return
    ev = (d or {}).get("event") or x.get("event") or {}
    status_event("正在回答追问", f"{no}：{question}", event=ev)
    draft = (d or {}).get("draft", "")
    qa = (x or {}).get("qa", [])
    prompt = ("你是我的群消息助手。我在决定怎么处理下面这条群消息前，想先问清楚。只输出一行 JSON："
              '{"answer": "直接回答我的问题，1～5 行，有依据就写出处，没依据就说不知道", "new_draft": "只有我要求改写 / 起草回复时才填，否则留空"}\n'
              "不要替我做决定，不要承诺任何事；new_draft 也只是草稿，我确认后才会发。\n\n"
              f"## 工作手册\n{HANDBOOK}\n\n{related_memory(str(ev.get('content') or '') + question)}\n\n"
              f"## 原消息\n{json.dumps(ev, ensure_ascii=False)}\n\n## 现在的草稿\n{draft or '（还没有）'}\n\n## 之前的判断依据\n{(x or {}).get('reason') or (d or {}).get('reason') or ''}\n\n"
              f"## 之前问过的\n{json.dumps(qa, ensure_ascii=False)}\n\n## 我的问题\n{question}")
    raw = ai_exec(prompt)
    try:
        r = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except ValueError:
        r = {"answer": raw.strip()[:800] or "AI 没给出回答，稍后再问一次。", "new_draft": ""}
    ans, nd = str(r.get("answer") or "").strip(), str(r.get("new_draft") or "").strip()
    if x is not None:
        y = _open_load()
        if no in y:
            y[no].setdefault("qa", []).append({"问": question, "答": ans[:500], "改写": nd[:300], "时间": f"{dt.datetime.now():%H:%M}"}); _open_save(y)
    if nd:
        if f:
            d["draft"] = nd; json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        elif ev:
            name = save_draft(ev, nd, reason=(x or {}).get("reason", ""))
            dd = json.load(open(os.path.join(HOME, "drafts", name), encoding="utf-8")); dd["todo"] = no
            json.dump(dd, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    notify(f"💡 {no} AI 的回答", (ans or "（没有回答）") + (f"\n\n新草稿：{nd}\n要发就回「{no} 可以发送」，再改回「{no} 改成：…」，继续问回「{no} 问：…」。" if nd else f"\n\n还想问就继续「{no} 问：…」；决定好了回「{no} 可以发送」/「{no} 不发」，或自己在原会话回。"))
    status_event("追问已回答", f"{no}：{ans}" + ("；草稿已更新，待本人确认" if nd else ""), event=ev)


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
    m = re.match(r"(#[A-Za-z0-9]{3,8})\s*(?:问|请问|问一下)[：:]\s*(.+)", text, re.S)
    if m:
        ask_ai(m.group(1), m.group(2).strip()); return
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
                reply(d["event"], d["draft"], keep_draft=False)
                st = d.get("sticker") if CFG.get("emoji") else ""
                if st:
                    send_sticker(d["event"], st)
                audit(no, d["event"], d["draft"], text, sticker=st, reason=d.get("reason", ""))
                os.remove(f); open_close(no, "已按你确认发出：" + d["draft"][:100])
            except SendFailed:
                pass                                                       # 已用机器人通知过；草稿还在，恢复后再回「可以发送」
            except Exception as ex:
                notify(f"⚠️ {no} 发送失败", repr(ex)[:200])


def list_drafts_to_group():
    """「待回复」/「草稿」：列出全部没处理完的事，有草稿（含暂存）的带上草稿内容。"""
    drafts = {d.get("todo"): d["draft"] for d in (json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(HOME, "drafts", "*.json")))}
    rows = [f"{no} {x['at']} {x['who']}：{x['what'][:40]}" + (f" → 草稿：{drafts[no][:60]}" if no in drafts else "（还没草稿）")
            for no, x in _open_load().items()]
    link = ""
    try:
        import console                                                     # v3.0：附上操作台链接，点开在页面里处理
        if console.A:
            link = f"\n\n[打开操作台看全部、直接处理]({console.url()})"
    except Exception:
        pass
    notify(f"📋 待回复 {len(rows)} 件", "\n".join(rows) + "\n回「#编号 暂存：内容」存草稿不发，「#编号 可以发送」发出，「清空」全部清掉" + link if rows else "没有" + link)


def relevant(e):
    sender = str(e.get("sender") or "")
    if CFG.get("notify_group") and e.get("conversation_id") == CFG["notify_group"]:
        if sender == CFG["my_name"] and e.get("message_id") not in SEEN:
            SEEN.add(e.get("message_id"))
            status_event("收到消息", "收到本人在提醒群的指令", event=e)
            try:
                if sticker_command(str(e.get("content") or "").strip()) or group_command(str(e.get("content") or "").strip()):
                    return False
                list_drafts_to_group() if re.fullmatch(r"(看)?草稿|待回复(详细)?|.{0,6}(待办|待处理|要处理|没处理|没回)(的)?(事|消息)?(有哪些|有什么|吗|呢)?[？?]?|还有(什么|啥|哪些)(事|要处理的|没处理的)?[？?]?", str(e.get("content") or "").strip()) else command(e)
            except Exception as ex:
                log("提醒群指令处理失败", repr(ex))
                status_event("处理失败", f"提醒群指令：{ex!r}", event=e)
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
    return any(k in text for k in CFG["keywords"] + [CFG["my_name"], "@所有人", "@全体成员"]) or sender in CFG["people"]   # @所有人 也要看（11-19：「@所有人 安卓 1.1.1 已提审」被漏）


def backfill_loop():
    """兜底补读（11-19）：实时监听每 29 分钟续一次期，续期间隙、断线、订阅冷却时的消息会丢。
    每 backfill_minutes 分钟（默认 30）把各群从上次补读起的消息不过滤地拉一遍，没见过、又和我有关的照常交给 AI。"""
    since = dt.datetime.now() - dt.timedelta(minutes=30)
    while in_window():
        time.sleep(max(5, int(CFG.get("backfill_minutes") or 30)) * 60)
        now = dt.datetime.now()
        for cid, name in {**CFG["groups"], **CFG["readonly_groups"]}.items():
            r = run([DWS, "chat", "message", "list", "--group", cid, "--time", f"{since:%Y-%m-%d %H:%M:%S}", "--direction", "newer", "--limit", "50"], timeout=60)
            try:
                msgs = json.loads(r.stdout).get("messages") or []
            except (ValueError, AttributeError):
                log("补读失败", name, str(getattr(r, "stdout", ""))[:120]); continue
            for m in msgs:
                e = {"sender": m.get("sender"), "content": m.get("content") or m.get("text"), "conversation_id": m.get("openConversationId") or cid,
                     "message_id": m.get("openMessageId") or m.get("messageId"), "quoted_message": m.get("quotedMessage")}
                if e["message_id"] and relevant(e):
                    SEEN.add(e["message_id"]); Q.put(e)
                    log("补读到漏掉的消息", name, e["sender"], str(e["content"])[:60])
                    status_event("收到消息", "断线/续期间隙补读，已加入处理队列", event=e)
        since = now - dt.timedelta(minutes=2)   # 和上一轮留 2 分钟重叠，SEEN 去重


def listen(args, tag):
    LISTENERS[tag] = {"started": time.time(), "alive": True}
    status_event("监听已启动", tag, announce=True)
    try:
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
                    status_event("监听异常", f"{tag}：找不到 dws 命令", announce=True)
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
                    LAST_EVENT.update(t=time.time(), summary=f"{tag} / {e.get('sender')}：{str(e.get('content') or '')[:80]}")
                    status_event("收到消息", "已加入处理队列，等待合并同一会话的消息", announce=True, event=e)
            p.wait()
            if time.time() - t0 < 60 and not got:                             # 不到 1 分钟就断、一条都没收到 = 异常（登录过期、网络等）
                FAILS[tag] = FAILS.get(tag, 0) + 1
                log("监听异常", tag, FAILS[tag], "次", err)
                status_event("监听异常", f"{tag} 连续 {FAILS[tag]} 次断开：{err or '无输出'}", announce=FAILS[tag] in (1, 3))
                time.sleep(min(300, 30 * FAILS[tag]))
            else:
                FAILS[tag] = 0
                log(tag, "本轮监听结束，续期"); time.sleep(5)
    finally:
        LISTENERS.setdefault(tag, {})["alive"] = False
        status_event("监听已停止", tag, announce=False)


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
    """v2.8：不再自动点表情；表情包只作为草稿的附带建议，本人确认发送时才一起发。"""
    lib = stickers()
    if not lib:
        return ""
    return ("\n表情包（可选）：action=reply 时 JSON 里可以再加 \"sticker\"（随草稿建议的表情包，必须一字不差地从这个名单里选："
            + "、".join(lib) + "；不用就留空）。只在 mine=true、气氛轻松时建议；正式通知、问题、派活、有争议的一律留空。")


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


def send_failed(e, text, err, no=""):
    """dws 出故障 / 版本不兼容 / 服务端报错时消息发不出去：用提醒群机器人同步通知本人，30 分钟内只提醒一次（v2.7，11-18 全公司 dws 发消息报「请求参数不能为空」）。"""
    SEND_FAIL["n"] += 1
    log("钉钉消息没发出去", e.get("conversation_id"), err[:200])
    if time.time() - SEND_FAIL["t"] < 1800:
        return
    SEND_FAIL["t"] = time.time()
    group = {**CFG["groups"], **CFG["readonly_groups"]}.get(e.get("conversation_id"), e.get("conversation_id"))
    notify("⚠️ 钉钉消息没发出去" + (f"（{no}）" if no else ""), f"群：{group}\n原消息：{e.get('sender')}：{str(e.get('content'))[:100]}\n要发的内容：{text[:500]}\n错误：{err[:200]}\n"
           "可能是钉钉 CLI（dws）故障或版本太旧：在电脑上运行 dws doctor 检查，dws upgrade -y 升级；如果同事也都发不出去，就是钉钉那边的问题，等恢复。"
           + (f"要紧的先手动发；内容已存成草稿，恢复后在这里回「{no} 可以发送」重发。" if no else "要紧的先手动发。") + "30 分钟内再失败不重复提醒（发「待回复」能看到全部没发出去的）。")


def reply(e, text, keep_draft=True):
    text = tidy(text)
    OUT[re.sub(r"\s+", "", text)] = time.time()
    r = run([DWS, "chat", "+messages-reply", "--conversation-id", e["conversation_id"], "--message-id", e["message_id"],
             "--text", text, "--uuid", f"qa-agent-{time.time_ns()}", "--yes", "--format", "json"], timeout=60)
    out = r.stdout or ""
    if r.returncode != 0 or not re.search(r'"(success|ok)":\s*true', out):
        err = re.search(r'"message":\s*"([^"]*)', out + (r.stderr or ""))
        err = err.group(1) if err else (out or r.stderr or "")[:200]
        no = ""
        if keep_draft:                                                   # 发不出去的回复存成草稿，恢复后一句话重发
            name = save_draft(e, text); no = open_add(e, "draft", "发送失败待重发：" + text[:20])
            dd = json.load(open(os.path.join(HOME, "drafts", name), encoding="utf-8")); dd["todo"] = no
            json.dump(dd, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        send_failed(e, text, err, no)
        status_event("发送失败", f"{no}：{err}；草稿保留，尚未发出", event=e)
        raise SendFailed("回复失败：" + err)
    status_event("已发送", "钉钉返回发送成功：" + text, event=e)


def save_draft(e, text, sticker="", reason=""):
    name = dt.datetime.now().strftime("%m%d-%H%M%S-") + re.sub(r"[^A-Za-z0-9]", "", e["message_id"])[:12] + ".json"
    json.dump({"event": e, "draft": text, "sticker": sticker, "reason": reason}, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return name


def handle(batch):
    """v2.8：任何回复都先写草稿交本人确认，不自动发出任何消息（包括表情）。"""
    e = batch[-1]
    d = decide(batch)
    remember(e, d)
    log("决定", e.get("sender"), d.get("action"), d.get("risk"), d.get("reason"), d.get("emoji") or "", d.get("sticker") or "")
    ats = re.findall(r"@([^\s@]+)", str(e.get("content") or ""))
    if ats and CFG["my_name"] not in ats and "所有人" not in ats:              # @ 的是别人：不插话（v2.6，11-18 梦无矶回了 项目助手 @ 另一位同事 的消息）
        log("别人之间的对话，不回", e.get("sender"), ats[:3]); return "别人之间的对话，不回复、不生成草稿"
    if d.get("action") == "ignore":
        return "不回复：" + (d.get("reason") or "按职责和群规则跳过")
    brief = f"{e.get('sender')}：{str(e.get('content'))[:200]}"
    if d.get("mine") is not True and d.get("action") == "reply":
        d["action"] = "escalate"                                           # 不确定归我就不替我回（v2.5.1）
    if d.get("action") != "reply" or not can_reply(e.get("conversation_id")):
        no = open_add(e, "escalate", d.get("reason") or "")
        x = _open_load(); x[no]["reason"] = d.get("reason") or ""; _open_save(x)
        if d.get("mine") is True:
            notify(f"🔔 {no} 需要你处理", f"{brief}\n原因：{d.get('reason')}\n想先问清楚：回「{no} 问：……」。你在原会话回复后，这里会自动补一条「已处理」。")
        else:
            notify(f"❓ {no} 是不是归你？", f"{brief}\n原因：{d.get('reason')}\n群里没回任何话。归你就在原会话自己回；不归你在这里回「{no} 不归我」；拿不准回「{no} 问：……」。")
        return f"{no} 等待本人处理，原群未回复；原因：" + (d.get("reason") or "需要本人判断")
    sticker = d.get("sticker") if CFG.get("emoji") and d.get("sticker") in stickers() else ""
    name = save_draft(e, d.get("text", ""), sticker=sticker, reason=d.get("reason") or "")
    no = open_add(e, "draft", "草稿：" + d.get("text", "")[:20])
    dd = json.load(open(os.path.join(HOME, "drafts", name), encoding="utf-8")); dd["todo"] = no
    json.dump(dd, open(os.path.join(HOME, "drafts", name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    notify(f"📝 {no} 草稿待你确认", f"{brief}\n草稿：{d.get('text', '')[:200]}" + (f"\n配表情包：{sticker}" if sticker else "") + f"\n依据：{(d.get('reason') or '')[:120]}"
           f"\n回：「{no} 可以发送」/「{no} 不发」/「{no} 改成：新内容」/「{no} 问：……」")
    return f"{no} 草稿待确认，尚未发送；依据：{d.get('reason') or 'AI 未提供依据'}；草稿：{d.get('text', '')}"


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
                    f.write(json.dumps({**x, "_t": int(time.time())}, ensure_ascii=False) + "\n")   # _t：保留期清理用
            status_event("开始处理", f"合并同一会话 {len(batch)} 条消息，正在核对职责、记忆和判断依据", announce=True, event=batch[-1])
            try:
                result = handle(batch)
                status_event("处理完成", result or "本批处理结束，具体发送/待办状态见记录", announce=True, event=batch[-1])
            except SendFailed:
                status_event("等待重发", "消息已转为草稿，等待发送恢复或本人确认，尚未发出", announce=True, event=batch[-1])
                pass                                                       # 发不出去已用机器人通知本人，回复存成了草稿
            except Exception as ex:
                e = batch[-1]
                log("处理失败", repr(ex)); status_event("处理失败", repr(ex)[:300], announce=True, event=e)
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


def remind_due(now=None):
    """超过 remind_after_minutes（默认 120 分钟，0 = 不再提醒）还没处理的事，在提醒群合并再提醒一次；之后每隔同样时间再提醒（v2.8，梦无矶 11-18）。"""
    mins = int(CFG.get("remind_after_minutes") or 0)
    if mins <= 0:
        return []
    now = now or time.time(); due = []
    d = _open_load()                                                       # _open_save 自己会加锁，这里不能再套 LOCK（会死锁）
    for no, x in d.items():
        last = x.get("reminded") or x.get("ts")
        if last and now - last >= mins * 60:
            due.append((no, x)); x["reminded"] = now
    if due:
        _open_save(d)
    if due:
        hrs = f"{mins // 60} 小时" if mins % 60 == 0 else f"{mins} 分钟"
        rows = [f"{no} {x['who']}：{x['what'][:40]}（{x['at']}）" for no, x in due]
        notify(f"⏰ {len(due)} 件超过 {hrs}还没处理", "\n".join(rows) + f"\n处理：回「#编号 可以发送 / 不发 / 问：…」，或在原会话自己回。改提醒间隔：发「提醒间隔 3小时」，关掉发「提醒间隔 关」。")
    return due


def reminder_loop():
    while in_window():
        try:
            remind_due()
        except Exception as ex:
            log("超时提醒失败", repr(ex))
        time.sleep(300)


def daily_summary():
    """21:00 退出前写当天总结（结构化），第二天上班由 morning_report() 发到本人私聊。"""
    today = dt.date.today().isoformat()
    p = os.path.join(HOME, "logs", today + ".log")
    lines = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []
    cnt = lambda k: sum(1 for l in lines if k in l)
    acts = [l.split("决定 ", 1)[1] for l in lines if "决定 " in l]
    body = [f"- 处理相关消息 {len(acts)} 批：写草稿 {sum(1 for a in acts if ' reply ' in a)}（都由你确认后才发），"
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
    msg = f"【群消息助手每日汇报｜{dt.date.today():%m-%d}】\n前一天（{day}）：\n{body}\n今天：09:00–21:00 监听，所有回复都先写草稿，你确认后才发。"
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
        reply(d["event"], d["draft"]); audit(d.get("todo", ""), d["event"], d["draft"], "命令行 review 确认", reason=d.get("reason", "")); os.remove(d["_f"]); open_close(d.get("todo", ""), "草稿已发送"); print("已发送", n)


def status():
    today = dt.date.today().isoformat()
    p = os.path.join(HOME, "logs", today + ".log")
    lines = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []
    acts = [l for l in lines if "决定 " in l]
    print(f"今天（{today}）：处理 {len(acts)} 批，你确认后发出 {sum(1 for l in (open(AUDIT, encoding='utf-8') if os.path.exists(AUDIT) else []) if today in l)} 条，"
          f"交给你 {sum(' escalate ' in l for l in acts)} 件，忽略 {sum(' ignore ' in l for l in acts)} 批，失败 {sum('处理失败' in l for l in lines)} 次")
    op = _open_load()
    print(f"还没处理完：{len(op)} 件（提醒群里也有）")
    for no, x in op.items():
        print(f"  {no} {x['at']} {x['who']}：{x['what']}｜{x['why']}")
    print("最近 5 条记录：")
    for l in acts[-5:]:
        print(" ", l[:150])


def _ver(v):
    m = re.search(r"v?(\d+(?:\.\d+)*)", str(v or ""))
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def self_update_check():
    """每天第一次启动时查一次助手有没有新版本（v2.7）：读 update_url（内网网页的 version.json，或开源仓库的 agent.py），比本机 VERSION 新就在提醒群说一声；同一个新版本只提醒一次。"""
    url = CFG.get("update_url")
    if not url:
        return
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "group-assistant"}), timeout=20, context=SSLCTX) as r:
            text = r.read(200000).decode("utf-8", "replace")
    except Exception as ex:
        log("新版本检查失败", repr(ex)[:120]); return
    m = re.search(r'(?i)"?version"?\s*[:=]\s*"(v[\d.]+)', text)
    if not m or _ver(m.group(1)) <= _ver(VERSION):
        log("新版本检查", "已是最新" if m else "没读到版本号"); return
    mark = os.path.join(HOME, "logs", f"update-told-{m.group(1)}")
    if os.path.exists(mark):
        return
    open(mark, "w").close()
    notify(f"⬆️ 群消息助手有新版本 {m.group(1)}", f"你现在是 {VERSION.split()[0]}。升级：下载最新部署文档（{CFG.get('update_page') or url}），拖进你的 AI 助手，发「升级到 {m.group(1)}」。升级不会覆盖你已有的规则。")


def cleanup_old():
    """保留期（v2.7，config keep_days，默认 30 天，0 = 不清）：只清原始记录——收到的消息原文 inbox.jsonl、建记忆导出的群历史 history/、旧日志；
    提炼好的记忆（memory/）和没处理完的草稿不动。"""
    days = int(CFG.get("keep_days") or 0)
    if days <= 0:
        return 0
    cut = time.time() - days * 86400; n = 0
    inbox = os.path.join(HOME, "inbox.jsonl")
    if os.path.exists(inbox):
        with LOCK:
            def _t(line):
                try:
                    return json.loads(line).get("_t") or 0
                except ValueError:
                    return 0
            keep = [l for l in open(inbox, encoding="utf-8") if _t(l) >= cut]
            n += sum(1 for _ in open(inbox, encoding="utf-8")) - len(keep)
            open(inbox, "w", encoding="utf-8").writelines(keep)
    for f in glob.glob(os.path.join(HOME, "history", "*")) + glob.glob(os.path.join(HOME, "logs", "*")):
        if os.path.isfile(f) and os.path.getmtime(f) < cut and not f.endswith(dt.date.today().isoformat() + ".log"):
            os.remove(f); n += 1
    log("保留期清理", days, "天，清掉", n, "条 / 个")
    return n


def purge_now():
    """「清理记录」：立刻清掉全部原始记录（消息原文、群历史导出、今天以前的日志）；提炼好的记忆和草稿不动。"""
    n = 0
    inbox = os.path.join(HOME, "inbox.jsonl")
    if os.path.exists(inbox):
        n += sum(1 for _ in open(inbox, encoding="utf-8")); open(inbox, "w").close()
    for f in glob.glob(os.path.join(HOME, "history", "*")) + [x for x in glob.glob(os.path.join(HOME, "logs", "*.log")) if not x.endswith(dt.date.today().isoformat() + ".log")]:
        if os.path.isfile(f):
            os.remove(f); n += 1
    return n


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
    pong = _ai_once(ai_name, ai_args, _, "只回复两个字：正常", 120) if ai_args else ""   # 只测主 AI，不走备用
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
    print("回复方式：一律草稿，本人确认后发（v2.8 无自动回复）", "| 常驻并行", CFG["workers"], "| 积压超过", CFG["burst_threshold"], "条开子 Agent，最多", CFG["max_workers"], "个 | 合并秒数", CFG["merge_seconds"], "| 模型", CFG["codex_model"] or "默认")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "watch":
        if sys.argv[2:] not in ([], ["--once"], ["--auto"]):
            raise SystemExit("用法：python agent.py watch [--once]")
        return watch(once="--once" in sys.argv[2:], auto="--auto" in sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "setup-notify":
        opt = dict(zip(sys.argv[2::2], sys.argv[3::2]))                   # --group 群名/cid  --webhook 地址  --secret SEC…
        setup_notify(group=opt.get("--group", ""), webhook=opt.get("--webhook", ""), secret=opt.get("--secret", "")); return
    if len(sys.argv) >= 2 and sys.argv[1] == "clear":
        n, k = clear_all(); print(f"已清空：{n} 件没处理完的事、{k} 份草稿，都没有发出"); return
    if len(sys.argv) >= 2 and sys.argv[1] == "audit":
        rows = [json.loads(l) for l in open(AUDIT, encoding="utf-8")] if os.path.exists(AUDIT) else []
        for r in rows[-int(sys.argv[2]) if len(sys.argv) > 2 else -20:]:
            print(r["发出时间"], r["群"], "←", r["原消息"]["谁"], "｜发出：", r["发出内容"][:60], "｜确认：", r["确认人"], "｜问过 AI", len(r["确认前问过 AI"]), "次")
        print("共", len(rows), "条，文件", AUDIT); return
    if len(sys.argv) >= 2 and sys.argv[1] == "purge":
        print("已清理原始记录", purge_now(), "条 / 个（记忆和草稿没动）"); return
    if len(sys.argv) >= 2 and sys.argv[1] == "stickers":
        print("表情包已下载", build_stickers(), "张 →", STICKERS); return
    if len(sys.argv) >= 2 and sys.argv[1] in ("review", "check", "status"):
        return {"review": review, "check": check, "status": status}[sys.argv[1]]()
    if len(sys.argv) == 3 and sys.argv[1] == "send":
        d = json.load(open(os.path.join(HOME, "drafts", sys.argv[2]), encoding="utf-8"))
        reply(d["event"], d["draft"]); audit(d.get("todo", ""), d["event"], d["draft"], "命令行 send 确认", reason=d.get("reason", "")); os.remove(os.path.join(HOME, "drafts", sys.argv[2])); print("已发送"); return
    if not in_window():
        log("窗口外，不启动"); return
    open_report_window()
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
    log("启动", VERSION, "（无自动回复，草稿确认）")
    status_event("已上岗", status_snapshot(), announce=True)
    try:                                                                   # v3.0 本机操作台：页面上直接处理，和提醒群指令同步
        import console
        if console.start(globals()):
            if CFG.get("open_on_start", True) and not console.lan():   # 上岗 / 部署 / 升级后自动在浏览器打开操作台，不用复制链接（11-19）
                console.popup()
            notify("🖥 打开操作台", f"[点这里打开操作台]({console.url()})\n" + ("内网其他电脑也能打开（链接带密钥，别外传）" if console.lan() else "只能在本机打开；有新的要处理会弹桌面通知") + "，处理后提醒群和页面同步。")
    except Exception as ex:
        log("操作台没开起来", repr(ex)[:200])
    threading.Thread(target=morning_report, daemon=True).start()
    threading.Thread(target=dws_version_check, daemon=True).start()
    threading.Thread(target=reminder_loop, daemon=True).start()
    threading.Thread(target=backfill_loop, daemon=True).start()
    threading.Thread(target=self_update_check, daemon=True).start()
    threading.Thread(target=cleanup_old, daemon=True).start()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    upgrade_ask()
    while in_window():
        time.sleep(30)
    daily_summary()
    status_event("已停止", "值守窗口结束；" + status_snapshot(), announce=True)
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
# ---- 开机自启（LaunchAgent / systemd / 计划任务）带的 PATH 很短，找不到装在用户目录下的 AI 命令和钉钉 CLI
# （macOS 上 claude / codex 默认在 ~/.local/bin，launchd 的 PATH 里没有，11-18 实测）。把常见安装目录补到 PATH 末尾，已有的不重复加。
def _extend_path():
    h = os.path.expanduser("~")
    if os.name == "nt":
        extra = [os.path.join(os.environ.get("APPDATA", ""), "npm"), os.path.join(h, ".local", "bin"), os.path.join(h, "AppData", "Local", "Programs", "Python", "Launcher")]
    else:
        extra = [os.path.join(h, ".local", "bin"), os.path.join(h, ".npm-global", "bin"), "/opt/homebrew/bin", "/usr/local/bin",
                 os.path.join(h, ".bun", "bin"), os.path.join(h, ".cargo", "bin"), os.path.join(h, "bin"), "/snap/bin"]
        extra += sorted(glob.glob(os.path.join(h, ".nvm", "versions", "node", "*", "bin")), reverse=True)[:1]   # nvm 装的 node / npm 全局命令
    cur = os.environ.get("PATH", "").split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join(cur + [d for d in extra if d and os.path.isdir(d) and d not in cur])


_extend_path()

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
$pythonw = (Get-Command pythonw.exe).Source
$act  = New-ScheduledTaskAction -Execute $pythonw -Argument '"C:\qa-agent\agent.py"' -WorkingDirectory "C:\qa-agent"   # 主进程隐藏；它自动用 python.exe 打开只读汇报控制台
$trg1 = New-ScheduledTaskTrigger -Daily -At 09:00
$trg2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set  = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 13) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "QA-群消息助手" -Action $act -Trigger $trg1,$trg2 -Settings $set -Principal $principal -Description "钉钉群监听 + Codex 决策，09:00-21:00，自动实时汇报"
```

暂停：`Disable-ScheduledTask -TaskName "QA-群消息助手"`；恢复：`Enable-ScheduledTask …`；卸载：`Unregister-ScheduledTask -TaskName "QA-群消息助手" -Confirm:$false`，再删 `C:\qa-agent` 和 `%USERPROFILE%\.qa-agent`。（任务名保留旧名；升级时核对任务在本人登录桌面会话中运行，必要时更新其主体，不改用户其他配置。）

Windows 后台首次启动后自动打开的控制台只负责显示；关闭它不会停止计划任务。`check` / `status` / `review` 等一次性命令不会自动开汇报窗口。

**B. macOS：LaunchAgent**（登录后生效，不需要管理员）。先取 python3 的绝对路径：`python3 -c "import sys;print(sys.executable)"`，替换下面的 `<PYTHON3>`；`<HOME>` 换成 `echo $HOME` 的结果。写入 `~/Library/LaunchAgents/com.group-assistant.agent.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.group-assistant.agent</string>
  <key>ProgramArguments</key><array><string><PYTHON3></string><string><HOME>/qa-agent/agent.py</string></array>
  <key>WorkingDirectory</key><string><HOME>/qa-agent</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string><HOME>/.local/bin:<HOME>/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string><HOME>/qa-agent/logs/launchd.err</string>
</dict></plist>
```

```bash
plutil -lint ~/Library/LaunchAgents/com.group-assistant.agent.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.group-assistant.agent.plist
```

- 后台默认用 `open -a Terminal` 打开安装目录 `logs/实时汇报.command`，由同一个 Python 解释器运行只读查看器；必须在本人登录的桌面会话（`gui/<uid>`）中启动。升级保留机器人通知偏好。
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
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY   # 在本人已登录的图形桌面终端执行，导入实际存在的变量
systemctl --user daemon-reload
systemctl --user enable --now group-assistant.service group-assistant.timer   # service：登录时拉起；timer：每天 09:00
loginctl enable-linger $USER    # 可选：不登录桌面也运行（需要管理员同意时再做）
```

- 图形桌面会依次选择 `x-terminal-emulator`、`gnome-terminal`、`konsole`、`xterm` 打开只读汇报。部署时确认桌面会话环境已导入 systemd 用户管理器；未设置的环境变量提示可忽略。无桌面的服务器不能显示 GUI 窗口，会在提醒群明确提示并继续保留日志；原有服务和定时器照常运行。
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

### 3.6 console.py（v3.0 本机操作台，写入 `C:\qa-agent\console.py`，和 agent.py 放一起）

助手启动时自动开：只监听本机 `127.0.0.1:8765`（`console_port` 可改），链接带密钥。三列「要你判断 / 草稿待发 / 已处理」，点卡片看原会话、改草稿、问 AI、发送；页面上的操作和提醒群指令走同一条路，三处同步。助手上岗（部署完、升级重启后、每天自启时）会**自动在默认浏览器打开操作台**，不用复制链接（`open_on_start: false` 关掉）；有新的要处理时也自动用浏览器弹出操作台（60 秒内最多一次；提醒群「弹出 关」关掉），并弹桌面通知。

**在别的电脑上看（比如助手装在 Mac，人在 Windows 上看）**：`config.json` 加 `"console_host": "0.0.0.0"`，重启助手后提醒群发来的「打开操作台」链接就是本机内网地址（如 `http://192.168.x.x:8765/?k=…`），同一内网的电脑都能打开，靠链接里的密钥挡住别人（别外传）；地址认错了可以用 `console_url_host` 指定 IP。这种用法下桌面通知在浏览器里弹不出来（浏览器只给本机或 https 页面弹），自动弹出也会弹在助手那台电脑上，建议加 `"popup": false`，靠提醒群机器人和标签页件数提醒。

```python
"""本机操作台（v3.0）：助手在本机起一个网页，三列看「要你判断 / 草稿待发 / 已处理」，在页面上直接处理。
- 只监听 127.0.0.1，链接带密钥（~/.qa-agent/console_token，只本人可读），同局域网别人打不开。
- 页面上的每个操作都转成和提醒群一模一样的指令（「#编号 可以发送」等）交给 agent.command 执行：
  发出、留痕、提醒群里的「✅ 已处理」都走原来那套，所以页面 / 提醒群 / 桌面通知三处天然同步。
- 只用 Python 标准库。agent.py 启动时调用 console.start(globals())。
"""
import glob
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

A = {}                     # agent.py 的全局变量（start 时传进来）
TOKEN = ""
CLOSED_N = 20              # 「已处理」列只显示最近 20 条（11-19 梦无矶：3 天内为主，但始终保证 20 条）
POP = {"t": 0}             # 上次把操作台弹到前面的时间


def _p(*parts):
    return os.path.join(A["HOME"], *parts)


def _token():
    path = os.path.join(os.path.expanduser("~"), ".qa-agent", "console_token")
    try:
        t = open(path, encoding="utf-8").read().strip()
        if len(t) >= 16:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(18)
    with open(path, "w", encoding="utf-8") as f:
        f.write(t)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return t


def _closed_log(no, why, x):
    rec = {"no": no, "why": why, "who": x.get("who"), "what": x.get("what"), "kind": x.get("kind"), "at": x.get("at"),
           "done": time.strftime("%m-%d %H:%M"), "ts": time.time(), "cid": x.get("cid")}
    with A["LOCK"], open(_p("logs", "closed.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _wrap_open_close():
    """所有「处理完」都会经过 open_close（提醒群指令、页面、本人在原会话亲自回复），在这里顺手记一笔给「已处理」列。"""
    orig = A["open_close"]

    def open_close(no, why):
        x = A["_open_load"]().get(no)
        orig(no, why)
        if x:
            try:
                _closed_log(no, why, x)
            except OSError:
                pass
    A["open_close"] = open_close


def popup(no=""):
    """有新的要处理 → 用系统默认浏览器打开操作台并定位到这件事（浏览器会切到最前面）。
    同一时间只留一个操作台标签页：新打开的页面会通知旧页面自己关掉。提醒群「弹出 关」可以关掉，默认 60 秒内最多弹一次。"""
    cfg = A["CFG"]
    if not cfg.get("popup", True) or not A["in_window"]() or time.time() - POP["t"] < int(cfg.get("popup_seconds") or 60):
        return False
    POP["t"] = time.time()
    u = url() + ("&focus=" + urllib.parse.quote(no) if no else "")
    try:
        if os.name == "nt":
            os.startfile(u)                                   # noqa: S606
        elif os.uname().sysname == "Darwin":
            A["popen"](["open", u])
        else:
            A["popen"](["xdg-open", u])
        A["log"]("操作台已弹出", no)
        return True
    except Exception as ex:
        A["log"]("操作台弹出失败", repr(ex)[:120])
        return False


def _wrap_open_add():
    orig = A["open_add"]

    def open_add(e, kind, why):
        no = orig(e, kind, why)
        threading.Thread(target=popup, args=(no,), daemon=True).start()
        return no
    A["open_add"] = open_add


def _wrap_group_command():
    orig = A["group_command"]

    def group_command(text):
        m = re.fullmatch(r"弹出\s*(开|关|打开|关闭)", text or "")
        if m:
            on = m.group(1) in ("开", "打开")
            A["save_cfg"]("popup", on)
            A["notify"]("🖥 操作台弹出已" + ("打开" if on else "关闭"), "有新的要处理时" + ("会自动把操作台弹到最前面（60 秒内最多一次）" if on else "不再弹出，只发桌面通知和提醒群消息") + "；发「弹出 开 / 关」切换。")
            return True
        return orig(text)
    A["group_command"] = group_command


def _drafts():
    out = {}
    for f in glob.glob(_p("drafts", "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("todo"):
            out[d["todo"]] = d
    return out


def _groups():
    return {**A["CFG"].get("groups", {}), **A["CFG"].get("readonly_groups", {})}


def state():
    items, drafts, groups, now = A["_open_load"](), _drafts(), _groups(), time.time()
    remind = max(1, int(A["CFG"].get("remind_after_minutes") or 120)) * 60
    judge, send = [], []
    for no, x in sorted(items.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True):
        d = drafts.get(no) or {}
        ev = x.get("event") or {}
        card = {"no": no, "who": x.get("who"), "group": groups.get(x.get("cid"), "私聊" if x.get("cid") and x.get("cid") not in groups else ""),
                "text": str(ev.get("content") or x.get("what") or "")[:600], "at": x.get("at"), "reason": x.get("reason") or d.get("reason") or x.get("why", ""),
                "draft": d.get("draft", ""), "qa": x.get("qa", [])[-5:], "overdue": now - x.get("ts", now) > remind,
                "can_send": A["can_reply"](x.get("cid"))}
        (send if card["draft"] else judge).append(card)
    done = []
    path = _p("logs", "closed.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8").readlines()[-CLOSED_N:]:
            try:
                done.append(json.loads(line))
            except ValueError:
                pass
    done.reverse()
    alive = sum(1 for v in A["LISTENERS"].values() if v.get("alive"))
    beat = A.get("LAST_EVENT", {}).get("t") or 0
    fails = {k: v for k, v in A.get("FAILS", {}).items() if v and v != 0}
    duty = ("ok", "值守中") if alive and alive == len(A["LISTENERS"]) and not fails else (("warn", "部分监听断开") if alive else ("bad", "没在监听"))
    if not A["in_window"]():
        duty = ("off", "值守时间外")
    return {"version": A["VERSION"], "me": A["CFG"].get("my_name"), "listeners": f"{alive}/{len(A['LISTENERS'])}",
            "duty": duty[0], "duty_text": duty[1], "last_event_t": time.strftime("%H:%M", time.localtime(beat)) if beat else "",
            "last_event": A["LAST_EVENT"].get("summary", ""), "judge": judge, "send": send, "done": done[:CLOSED_N],
            "today_done": sum(1 for x in done if x.get("done", "").startswith(time.strftime("%m-%d"))), "time": time.strftime("%H:%M:%S")}


def thread(no):
    """会话面板：这件事所在会话最近 20 条消息（群用 dws 拉；私聊只显示原消息）。"""
    x = A["_open_load"]().get(no) or {}
    cid = x.get("cid")
    if not cid or cid not in _groups():
        ev = x.get("event") or {}
        return [{"who": ev.get("sender"), "time": "", "text": str(ev.get("content") or "")}]
    r = A["run"]([A["DWS"], "chat", "message", "list", "--group", cid, "--limit", "20", "--format", "json"], timeout=60)
    try:
        msgs = json.loads(r.stdout).get("messages") or []
    except (ValueError, AttributeError):
        return [{"who": "（读取失败）", "time": "", "text": str(getattr(r, "stderr", "") or getattr(r, "stdout", ""))[:200]}]
    rows = [{"who": m.get("sender"), "time": m.get("createTime", ""), "text": str(m.get("content") or m.get("text") or ""),
             "mid": m.get("openMessageId") or m.get("messageId")} for m in msgs]
    return sorted(rows, key=lambda m: m["time"])


HISTORY_N = 30            # 历史消息：每个群看最近 30 条（只为页面上翻看方便，全量去钉钉看）


def history(cid):
    """顶栏「值守中」点开：按群看最近 30 条消息（直接从钉钉拉，不存本地）。"""
    if cid not in _groups():
        return []
    r = A["run"]([A["DWS"], "chat", "message", "list", "--group", cid, "--limit", str(HISTORY_N), "--format", "json"], timeout=60)
    try:
        msgs = json.loads(r.stdout).get("messages") or []
    except (ValueError, AttributeError):
        return [{"who": "（读取失败）", "time": "", "text": str(getattr(r, "stderr", "") or "")[:200]}]
    return sorted(({"who": m.get("sender"), "time": m.get("createTime", ""), "text": str(m.get("content") or m.get("text") or "")} for m in msgs), key=lambda m: m["time"])


def act(no, action, text=""):
    """页面按钮 → 提醒群同款指令，交给 agent.command（发出、留痕、提醒群「已处理」都走原逻辑）。"""
    if not re.fullmatch(r"#[A-Za-z0-9]{3,8}", no or ""):
        return "编号不对"
    text = (text or "").strip()
    if action == "reply_new":                       # 要你判断的事，自己写一段回复：先挂成草稿再按确认发出
        if not text:
            return "回复内容是空的"
        A["stash"](no, text)
        action = "send"
    cmd = {"send": f"{no} 可以发送", "drop": f"{no} 不发", "edit_send": f"{no} 改成：{text}", "stash": f"{no} 暂存：{text}",
           "ask": f"{no} 问：{text}", "not_mine": f"{no} 不归我"}.get(action)
    if not cmd or (action in ("edit_send", "stash", "ask") and not text):
        return "操作不对或内容为空"
    A["log"]("操作台", cmd[:80])
    A["command"]({"content": cmd, "sender": A["CFG"].get("my_name"), "conversation_id": A["CFG"].get("notify_group"), "message_id": f"console-{time.time_ns()}"})
    return "ok"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return secrets.compare_digest((q.get("k") or [""])[0], TOKEN) or secrets.compare_digest(self.headers.get("X-Key", ""), TOKEN)

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._ok():
            return self._send(403, "需要带密钥的链接：在提醒群里找「打开操作台」那条。", "text/plain; charset=utf-8")
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/state":
            return self._send(200, json.dumps(state(), ensure_ascii=False))
        if u.path == "/api/groups":
            return self._send(200, json.dumps([{"cid": c, "name": n} for c, n in _groups().items()], ensure_ascii=False))
        if u.path == "/api/history":
            return self._send(200, json.dumps(history((urllib.parse.parse_qs(u.query).get("cid") or [""])[0]), ensure_ascii=False))
        if u.path == "/api/thread":
            no = (urllib.parse.parse_qs(u.query).get("no") or [""])[0]
            return self._send(200, json.dumps(thread(no), ensure_ascii=False))
        self._send(404, "{}")

    def do_POST(self):
        if not self._ok():
            return self._send(403, "{}")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, '{"msg": "格式不对"}')
        if urllib.parse.urlparse(self.path).path != "/api/act":
            return self._send(404, "{}")
        no, action, text = body.get("no"), body.get("action"), body.get("text", "")
        if action == "ask":                          # 问 AI 要几十秒，后台跑，答案回来后卡片自动更新
            threading.Thread(target=act, args=(no, action, text), daemon=True).start()
            return self._send(200, '{"msg": "已经去问 AI 了，答案出来会显示在卡片里，提醒群也会收到"}')
        try:
            msg = act(no, action, text)
        except Exception as ex:                      # 发送失败等：原逻辑已用机器人通知
            msg = "失败：" + repr(ex)[:200]
        self._send(200, json.dumps({"msg": "已处理" if msg == "ok" else msg}, ensure_ascii=False))


def _lan_ip():
    import socket
    try:
        x = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); x.connect(("223.5.5.5", 80)); ip = x.getsockname()[0]; x.close(); return ip
    except OSError:
        return "127.0.0.1"


def lan():
    """console_host 设成 0.0.0.0（或本机内网 IP）= 允许内网其他电脑打开（比如助手装在 Mac、人在 Windows 上看）。"""
    return (A["CFG"].get("console_host") or "127.0.0.1") not in ("127.0.0.1", "localhost")


def url():
    host = A["CFG"].get("console_url_host") or (_lan_ip() if lan() else "127.0.0.1")
    return f"http://{host}:{int(A['CFG'].get('console_port') or 8765)}/?k={TOKEN}"


def start(ns):
    """agent.py 启动时调用。端口被占用（比如开了两个助手）就不开，只记日志。"""
    global TOKEN, A
    if A or not ns.get("CFG", {}).get("console", True):
        return None
    A = ns                                       # 直接用 agent 的全局变量（不拷贝），之后的替换 / 更新都能看到
    TOKEN = _token()
    _wrap_open_close()
    _wrap_open_add()
    _wrap_group_command()
    try:
        srv = ThreadingHTTPServer((A["CFG"].get("console_host") or "127.0.0.1", int(A["CFG"].get("console_port") or 8765)), H)   # console_host 只给演示用，平时只本机
    except OSError as ex:
        A["log"]("操作台没开起来（端口被占用？）", repr(ex)[:120])
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    A["log"]("操作台已开", url().split("?")[0])
    return srv


PAGE = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>群消息助手 · 操作台</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%233360e6'/%3E%3Ctext x='16' y='22' font-size='17' text-anchor='middle' fill='white' font-family='sans-serif'%3E群%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#f4f6fb;--surface:#fff;--soft:#f6f8fc;--border:#e4e9f2;--line:#eef1f7;--text:#1b2638;--muted:#6b7688;--faint:#97a1b2;
--blue:#3360e6;--blue-2:#5b7ff0;--blue-soft:#ecf1ff;--amber:#c27a00;--amber-soft:#fff4dc;--red:#d23b3b;--red-soft:#fdeeee;--green:#1c8a4a;--green-soft:#e7f6ed;
--shadow:0 1px 2px rgba(20,35,70,.04),0 4px 14px rgba(20,35,70,.06);--shadow-h:0 2px 6px rgba(20,35,70,.08),0 10px 28px rgba(20,35,70,.10)}
@media (prefers-color-scheme:dark){:root{--bg:#0f131b;--surface:#171d29;--soft:#1c2331;--border:#2a3242;--line:#222a38;--text:#e7ebf2;--muted:#9aa5b6;--faint:#6f7a8c;
--blue:#7d9bff;--blue-2:#94acff;--blue-soft:#1d2848;--amber:#f0b44c;--amber-soft:#3a2d12;--red:#ff8a80;--red-soft:#3a1e22;--green:#6fd59a;--green-soft:#163222;--shadow:0 1px 2px rgba(0,0,0,.3);--shadow-h:0 6px 22px rgba(0,0,0,.4)}}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--text);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:16px;padding:12px 24px;background:var(--surface);border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:16px}.logo{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,var(--blue),var(--blue-2));color:#fff;display:grid;place-items:center;font-size:15px}
.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:99px;background:var(--soft);border:1px solid var(--border);font-size:12.5px;color:var(--muted)}
.chip b{color:var(--text);font-weight:600}.dot{width:7px;height:7px;border-radius:50%;background:var(--green)}.dot.bad{background:var(--red)}
.duty .dot{box-shadow:0 0 0 0 currentColor;animation:pulse 2s infinite}.d-ok{color:var(--green);background:var(--green-soft);border-color:transparent}.d-ok b{color:var(--green)}
.d-warn{color:var(--amber);background:var(--amber-soft);border-color:transparent}.d-warn .dot{background:var(--amber)}.d-warn b{color:var(--amber)}
.d-bad{color:var(--red);background:var(--red-soft);border-color:transparent}.d-bad .dot{background:var(--red)}.d-bad b{color:var(--red)}.d-off .dot{background:var(--faint);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(28,138,74,.45)}70%{box-shadow:0 0 0 7px rgba(28,138,74,0)}100%{box-shadow:0 0 0 0 rgba(28,138,74,0)}}
.sp{flex:1}.ver{color:var(--faint);font-size:12px}
.btn{border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:9px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer;transition:.15s}
.btn:hover{border-color:var(--blue);color:var(--blue)}.btn.p{background:var(--blue);border-color:var(--blue);color:#fff}.btn.p:hover{filter:brightness(1.08);color:#fff}
.btn.d{color:var(--red)}.btn.d:hover{border-color:var(--red)}.btn.sm{padding:4px 10px;font-size:12.5px}
main{flex:1;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;padding:18px 24px 22px}
.col{display:flex;flex-direction:column;min-height:0}
.ch{display:flex;align-items:center;gap:10px;padding:2px 4px 12px}.ch .ic{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;font-size:14px}
.ch h2{margin:0;font-size:15px}.ch .sub{color:var(--faint);font-size:12px}.ch .cnt{margin-left:auto;min-width:26px;text-align:center;padding:1px 8px;border-radius:99px;font-weight:700;font-size:12.5px}
.c1 .ic,.c1 .cnt{background:var(--amber-soft);color:var(--amber)}.c2 .ic,.c2 .cnt{background:var(--blue-soft);color:var(--blue)}.c3 .ic,.c3 .cnt{background:var(--green-soft);color:var(--green)}
.list{flex:1;overflow:auto;padding:2px 6px 8px 2px;scrollbar-width:thin}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 16px;margin-bottom:12px;cursor:pointer;box-shadow:var(--shadow);transition:.15s;position:relative}
.card:hover{box-shadow:var(--shadow-h);transform:translateY(-1px)}.card.sel{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-soft)}
.c1 .card{border-left:4px solid var(--amber)}.c2 .card{border-left:4px solid var(--blue)}.c3 .card{border-left:4px solid var(--green);cursor:default;opacity:.92}.c3 .card:hover{transform:none}
.top{display:flex;align-items:center;gap:10px}.av{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:600;font-size:13px;flex:none}
.who{font-weight:600}.where{color:var(--muted);font-size:12px}.when{margin-left:auto;color:var(--faint);font-size:12px;white-space:nowrap}
.no{font-size:11.5px;color:var(--faint);font-family:ui-monospace,Menlo,monospace}
.txt{margin:10px 0 0;white-space:pre-wrap;word-break:break-word;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.draft{margin-top:10px;background:var(--blue-soft);border-radius:10px;padding:8px 10px;white-space:pre-wrap;word-break:break-word;font-size:13.5px}
.draft::before{content:"草稿";display:block;font-size:11px;color:var(--blue);font-weight:600;margin-bottom:2px}
.why{margin-top:8px;color:var(--muted);font-size:12.5px;display:flex;gap:6px}.why::before{content:"💡"}
.tag{display:inline-block;border-radius:99px;padding:0 8px;font-size:11.5px;font-weight:600}.t-red{background:var(--red-soft);color:var(--red)}.t-ok{background:var(--green-soft);color:var(--green)}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.empty{color:var(--faint);text-align:center;padding:48px 10px}.empty .big{font-size:30px;display:block;margin-bottom:6px}
.mask{position:fixed;inset:0;background:rgba(10,18,35,.25);opacity:0;pointer-events:none;transition:.2s;z-index:9}.mask.on{opacity:1;pointer-events:auto}
aside{position:fixed;top:0;right:0;height:100%;width:min(560px,100%);background:var(--surface);box-shadow:none;transform:translateX(100%);transition:transform .22s ease;display:flex;flex-direction:column;z-index:10}
aside.on{transform:none;box-shadow:-12px 0 40px rgba(10,20,45,.18)}.ph{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}.ph .t{font-weight:700}.ph .s{color:var(--muted);font-size:12.5px}
.pb{flex:1;overflow:auto;padding:16px 20px;background:var(--soft)}.pf{border-top:1px solid var(--border);padding:14px 20px;background:var(--surface)}
.bub{display:flex;gap:10px;margin-bottom:14px}.bub .av{width:28px;height:28px;font-size:12px}.bub .b{background:var(--surface);border:1px solid var(--border);border-radius:4px 12px 12px 12px;padding:8px 12px;max-width:100%}
.bub .w{font-size:12px;color:var(--muted);margin-bottom:2px}.bub .w span{color:var(--faint);margin-left:6px}.bub .tx{white-space:pre-wrap;word-break:break-word}
.bub.hl .b{border-color:var(--amber);box-shadow:0 0 0 3px var(--amber-soft)}
.note{background:var(--surface);border:1px dashed var(--border);border-radius:10px;padding:10px 12px;margin-top:6px;font-size:13px}.note h4{margin:0 0 4px;font-size:12px;color:var(--muted)}
.qa{border-left:3px solid var(--blue);padding:2px 0 2px 10px;margin:8px 0;font-size:13px}
textarea,input.q{width:100%;border:1px solid var(--border);border-radius:10px;padding:10px 12px;font:inherit;background:var(--soft);color:var(--text);outline:none;transition:.15s}
textarea{min-height:96px;resize:vertical}textarea:focus,input.q:focus{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-soft);background:var(--surface)}
.askrow{display:flex;gap:8px;margin-top:10px}.askrow input{flex:1}.lbl{font-size:12px;color:var(--muted);margin:0 0 6px}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(20px);opacity:0;background:#1b2638;color:#fff;padding:10px 16px;border-radius:10px;box-shadow:var(--shadow-h);transition:.2s;z-index:20;font-size:13px}.toast.on{opacity:1;transform:translateX(-50%)}
@media (max-width:980px){main{grid-template-columns:1fr;overflow:auto}.col{min-height:auto}.list{overflow:visible}header{flex-wrap:wrap}}
</style></head><body>
<header><div class="brand"><span class="logo">群</span>操作台</div><div class="chips" id="stat"><span class="chip">连接中…</span></div><span class="sp"></span>
<button class="btn sm" id="notif" style="display:none">🔔 开启桌面通知</button><span class="ver" id="ver"></span></header>
<main>
<section class="col c1"><div class="ch"><span class="ic">✋</span><div><h2>要你判断</h2><div class="sub">拿不准是不是归你、要不要接</div></div><span class="cnt" id="n1">0</span></div><div class="list" id="judge"></div></section>
<section class="col c2"><div class="ch"><span class="ic">✉️</span><div><h2>草稿待发</h2><div class="sub">AI 写好了，你点头才发</div></div><span class="cnt" id="n2">0</span></div><div class="list" id="send"></div></section>
<section class="col c3"><div class="ch"><span class="ic">✓</span><div><h2>已处理</h2><div class="sub">页面、提醒群、原会话里处理的都算</div></div><span class="cnt" id="n3">0</span></div><div class="list" id="done"></div></section>
</main>
<div class="mask" id="mask" onclick="closeP()"></div>
<aside id="panel"><div class="ph"><span class="av" id="pav"></span><div><div class="t" id="ptitle"></div><div class="s" id="psub"></div></div><span class="sp"></span><button class="btn sm" onclick="closeP()">关闭</button></div><div class="pb" id="pbody"></div><div class="pf" id="pfoot"></div></aside>
<div class="toast" id="toast"></div>
<script>
const K=new URLSearchParams(location.search).get('k')||'';let S=null,sel=null,seen=new Set(),first=true;const notes={};
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const COLORS=['#3360e6','#1c8a4a','#c27a00','#8a4fd8','#d23b3b','#0f8f9e','#c2477d','#5b6b86'];
function av(n){n=String(n||'?');let h=0;for(const ch of n)h=(h*31+ch.charCodeAt(0))>>>0;return `<span class="av" style="background:${COLORS[h%COLORS.length]}">${esc(n.replace(/[-_ ].*/,'').slice(-2))}</span>`}
function toast(t){const x=$('toast');x.textContent=t;x.classList.add('on');clearTimeout(x._t);x._t=setTimeout(()=>x.classList.remove('on'),2600)}
async function api(p,b){const r=await fetch(p+(p.includes('?')?'&':'?')+'k='+encodeURIComponent(K),b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}:{cache:'no-store'});return r.json()}
function head(c){return `<div class="top">${av(c.who)}<div><div class="who">${esc(c.who)}</div><div class="where">${esc(c.group||'')} <span class="no">${c.no}</span></div></div><span class="when">${c.overdue?'<span class="tag t-red">超时</span> ':''}${esc(c.at)}</span></div>`}
function card(c,kind){return `<div class="card${sel===c.no?' sel':''}" onclick="openP('${c.no}')">${head(c)}<div class="txt">${esc(c.text)}</div>
${kind==='send'?`<div class="draft">${esc(c.draft)}</div>`:(c.reason?`<div class="why">${esc(c.reason)}</div>`:'')}
<div class="btns" onclick="event.stopPropagation()">${kind==='send'?`<button class="btn p" onclick="go('${c.no}','send')">发送</button><button class="btn" onclick="openP('${c.no}')">修改</button><button class="btn d" onclick="go('${c.no}','drop')">不发</button>`:
`<button class="btn p" onclick="openP('${c.no}')">回复</button><button class="btn" onclick="go('${c.no}','not_mine')">不归我</button>`}<button class="btn" onclick="openP('${c.no}',1)">问 AI</button></div></div>`}
function empty(t){return `<div class="empty"><span class="big">☕</span>${t}</div>`}
function render(){const s=S,ok=/^(\d+)\/\1$/.test(s.listeners)&&s.listeners!=='0/0';
$('stat').innerHTML=`<span class="chip duty d-${s.duty}" style="cursor:pointer" onclick="openH()" title="点开按群看最近消息；最近收到消息 ${esc(s.last_event_t||'无')}；${esc(s.last_event||'')}"><span class="dot"></span><b>${esc(s.duty_text)}</b> · 监听 ${s.listeners}${s.last_event_t?' · 最近 '+s.last_event_t:''}</span><span class="chip">要你判断 <b>${s.judge.length}</b></span><span class="chip">草稿待发 <b>${s.send.length}</b></span><span class="chip">今天已处理 <b>${s.today_done}</b></span><span class="chip">${esc(s.me)} · ${s.time}</span>`;$('ver').textContent=s.version;
$('judge').innerHTML=s.judge.map(c=>card(c,'judge')).join('')||empty('没有要你判断的事');$('send').innerHTML=s.send.map(c=>card(c,'send')).join('')||empty('没有待发的草稿');
$('done').innerHTML=s.done.map(d=>`<div class="card">${head({who:d.who,group:'',no:d.no,at:d.done})}<div class="txt">${esc(d.what)}</div><div class="why" style="--x:0">${esc(d.why)}</div></div>`).join('')||empty('今天还没有处理记录');
$('n1').textContent=s.judge.length;$('n2').textContent=s.send.length;$('n3').textContent=s.done.length;
const open=[...s.judge,...s.send],n=open.length;document.title=(n?'('+n+') ':'')+'群消息助手 · 操作台';const now=new Set(open.map(c=>c.no));
open.forEach(c=>{if(!seen.has(c.no)&&!first&&window.Notification&&Notification.permission==='granted'){const x=new Notification(`${c.draft?'草稿待发':'要你判断'} · ${c.who}`,{body:c.text.slice(0,90),tag:c.no});x.onclick=()=>{window.focus();openP(c.no)};notes[c.no]=x}});
Object.keys(notes).forEach(no=>{if(!now.has(no)){notes[no].close();delete notes[no]}});seen=now;first=false;
if(sel&&!now.has(sel)){closeP();toast(sel+' 已处理')}else if(sel)fillFoot()}
async function tick(){try{S=await api('/api/state');render()}catch(e){$('stat').innerHTML='<span class="chip"><span class="dot bad"></span>连不上助手（助手停了？）</span>'}}
function cur(){return [...S.judge,...S.send].find(c=>c.no===sel)}
async function openP(no,ask){sel=no;const c=cur();if(!c)return;$('pav').outerHTML=av(c.who).replace('class="av"','class="av" id="pav"');$('ptitle').textContent=c.who;$('psub').textContent=`${c.group||''} · ${no} · ${c.at}`;
$('panel').classList.add('on');$('mask').classList.add('on');render();$('pbody').innerHTML='<div class="empty">正在读会话…</div>';fillFoot(ask);
const t=await api('/api/thread?no='+encodeURIComponent(no));if(sel!==no)return;
$('pbody').innerHTML=t.map(m=>`<div class="bub${m.text&&c.text&&c.text.startsWith(m.text.slice(0,30))?' hl':''}">${av(m.who)}<div class="b"><div class="w">${esc(m.who)}<span>${esc((m.time||'').slice(5,16))}</span></div><div class="tx">${esc(m.text)}</div></div></div>`).join('')+
(c.reason?`<div class="note"><h4>AI 的判断依据</h4>${esc(c.reason)}</div>`:'')+((c.qa||[]).length?`<div class="note"><h4>问过 AI</h4>${c.qa.map(q=>`<div class="qa"><b>问</b> ${esc(q['问'])}<br><b>答</b> ${esc(q['答'])}</div>`).join('')}</div>`:'');$('pbody').scrollTop=1e9}
function fillFoot(ask){const c=cur();if(!c)return;const f=$('pfoot');if(f.contains(document.activeElement))return;
f.innerHTML=`<div class="lbl">${c.draft?'草稿（可以直接改）':'你的回复'}</div><textarea id="ta" placeholder="${c.draft?'':'写一段回复，点发送前还会再确认一次'}">${esc(c.draft)}</textarea>
<div class="btns">${c.can_send?`<button class="btn p" onclick="go('${c.no}','${c.draft?'edit_send':'reply_new'}',$('ta').value)">发送到原会话</button>`:'<span class="where">这个群设成了「只看」，请在钉钉里自己回</span>'}
<button class="btn" onclick="go('${c.no}','stash',$('ta').value)">暂存不发</button>${c.draft?`<button class="btn d" onclick="go('${c.no}','drop')">不发</button>`:`<button class="btn" onclick="go('${c.no}','not_mine')">不归我</button>`}</div>
<div class="askrow"><input class="q" id="q" placeholder="问 AI：依据是什么？帮我改得客气点…" onkeydown="if(event.key==='Enter')go('${c.no}','ask',this.value)"><button class="btn" onclick="go('${c.no}','ask',$('q').value)">问 AI</button></div>`;if(ask)setTimeout(()=>$('q').focus(),60)}
// 顶栏「值守中」点开：按群看最近消息（复用右侧面板）
let hsel=null;async function openH(cid){sel=null;const gs=await api('/api/groups');if(!gs.length)return toast('没有监听的群');hsel=cid||hsel||gs[0].cid;
$('pav').outerHTML='<span class="av" id="pav" style="background:var(--green)">群</span>';$('ptitle').textContent='最近消息';$('psub').textContent='按群看，每个群最近 30 条';
$('panel').classList.add('on');$('mask').classList.add('on');
const tabs='<div class="btns" style="margin:0 0 14px;position:sticky;top:-16px;background:var(--soft);padding:8px 0;z-index:1">'+gs.map(g=>`<button class="btn sm${g.cid===hsel?' p':''}" onclick="openH('${g.cid}')">${esc(g.name)}</button>`).join('')+'</div>';
$('pfoot').innerHTML='<div class="where">只读：这里只看消息，要回复请在卡片或钉钉里处理</div>';$('pbody').innerHTML=tabs+'<div class="empty">正在读…</div>';const t=await api('/api/history?cid='+encodeURIComponent(hsel));if(!$('panel').classList.contains('on'))return;
$('pbody').innerHTML=tabs+t.map(m=>`<div class="bub">${av(m.who)}<div class="b"><div class="w">${esc(m.who)}<span>${esc((m.time||'').slice(5,16))}</span></div><div class="tx">${esc(m.text)}</div></div></div>`).join('')||'<div class="empty">没有消息</div>';$('pbody').scrollTop=1e9}
function closeP(){sel=null;hsel=hsel;$('panel').classList.remove('on');$('mask').classList.remove('on');render()}
async function go(no,action,text){if(['send','edit_send','reply_new'].includes(action)&&!confirm('确认发到原会话？'))return;
const r=await api('/api/act',{no,action,text:text||''});toast(r.msg||'好了');if(action==='ask'&&$('q'))$('q').value='';document.activeElement&&document.activeElement.blur();tick()}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeP()});
if(window.Notification&&Notification.permission==='default'){$('notif').style.display='';$('notif').onclick=()=>Notification.requestPermission().then(()=>$('notif').style.display='none')}
// 有新事件时助手会用浏览器打开带 focus 的链接（弹到最前面）；新页面打开后通知旧页面关掉，始终只留一个操作台
const FOCUS=new URLSearchParams(location.search).get('focus');let alive=true;
try{const bc=new BroadcastChannel('qa-console');const me=Date.now()+Math.random();bc.postMessage({t:'new',me});
bc.onmessage=m=>{if(m.data&&m.data.t==='new'&&m.data.me!==me){alive=false;window.close();setTimeout(()=>{document.body.innerHTML='<div class="empty" style="margin-top:20vh"><span class="big">↗</span>操作台已在新标签页打开，这一页可以关掉了。</div>'},300)}}}catch(e){}
tick().then(()=>{if(FOCUS)openP(FOCUS);if(FOCUS)history.replaceState(null,'',location.pathname+'?k='+encodeURIComponent(K))});setInterval(()=>{if(alive)tick()},3000);
</script></body></html>"""
```

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
| 打开操作台（v3.0） | 助手上岗时在提醒群发「打开操作台」链接；提醒群问「有什么待办」「还有什么没处理的」也会附上链接。在页面上三列看、直接处理；有新的会自动弹出来，不想弹就在提醒群发「弹出 关」 |
| 草稿要不要发 | 在提醒群里直接回：「#编号 可以发送」/「#编号 不发」/「#编号 改成：新内容」/「全部发送」；发「草稿」两个字列出待确认的。也可以运行 `python C:\qa-agent\agent.py review` |
| 看还有哪些没回 / 先写个草稿晚点发 / 全清掉 | 在提醒群发「待回复」列出全部没处理完的事（带草稿）；「#编号 暂存：内容」只存草稿不发，之后「#编号 可以发送」；「清空」全部清掉、不发（v2.5，一位同事提议） |
| 表情包（默认关） | 提醒群发「表情 开 / 关」；开了以后只在草稿里建议一张，你确认发送时才一起发；「表情包」看张数，「删表情包 名字」拉黑 |
| 先问清楚再决定（v2.8） | 提醒群发「#编号 问：依据是什么？」「#编号 问：帮我改得客气点」；AI 只在提醒群回答或改草稿，不往群里发任何东西 |
| 看发出去的记录（v2.8） | 运行 `python agent.py audit`：每条发出的消息谁、何时确认、问过 AI 什么、依据是什么；记录不随保留期清理 |
| 没处理的事多久再提醒（v2.8） | 默认 2 小时；提醒群发「提醒间隔 3小时」「提醒间隔 30分钟」「提醒间隔 关」 |
| 哪些群可以往里发 | 提醒群发「群列表」看；「群名 只看」以后连草稿也不往这个群发，「群名 可发草稿」恢复 |
| 提醒群问「❓ #编号 是不是归你？」 | 归你就在原会话自己回；不归你在提醒群回「#编号 不归我」，群里不会有任何回复（v2.5.1） |
| 看一下今天的待处理 | 读 `待处理.md`，列给你 |
| 实时汇报窗口 | 默认随后台自动打开：Windows 独立控制台、macOS「终端」、Linux 桌面终端；不用自己输入命令。关闭后临时重开用 Windows `python C:\qa-agent\agent.py watch`，macOS / Linux `python3 ~/qa-agent/agent.py watch`；加 `--once` 只看最近 20 条 |
| 助手正常吗 | 运行 `python C:\qa-agent\agent.py check` |
| 今天处理得怎么样 / 还有什么没处理 | 运行 `python C:\qa-agent\agent.py status`；交给你的事和待确认草稿都在提醒群里，处理完会补一条「✅ 已处理」 |
| 昨天干了什么 | 每天上班自动发到你和自己的钉钉私聊；也可以直接看 `memory\每日总结.md` |
| 提醒群收到「⚠️ 钉钉消息没发出去」 | 先在电脑上运行 `dws doctor`；提示有新版本就 `dws upgrade -y`；同事也都发不出去就是钉钉那边的问题，等恢复。没发出去的回复已存成草稿，恢复后在提醒群回「#编号 可以发送」重发；要紧的先手动发 |
| 角色职责库加一个角色 / 删掉某个角色 / 改某条 | AI 助手改 `C:\qa-agent\角色职责库.json`；改的是你在用的角色时先念给你二次确认，再同步进工作手册 |
| 提醒群收到「⬆️ 群消息助手有新版本」 | 按提示下载最新部署文档，拖进 AI 助手发「升级到 新版本号」；升级不会覆盖你已有的规则 |
| 提醒群收到「🔁 判断用的 AI 换成了备用」 | 你设的 AI 这次没给结果，已自动换本机另一个 AI；经常出现就检查一下原来那个 AI 在终端里能不能用 |
| 不想留聊天原文 / 清理一下 | 提醒群发「清理记录」，或运行 `python agent.py purge`：立刻清掉消息原文、群历史导出、旧日志；记忆和草稿不动。平时自动只留最近 30 天 |
| 角色职责库里缺了某个角色 | 不用管，AI 助手发现了会自行补充（标「AI 补充」），补完告诉你；补的是你在用的角色时先念给你确认 |
| 我换角色了 / 多负责一个角色 | AI 助手按第 2 步重走一遍角色职责（展示 → 你修改补充 → 二次确认） |
| 「XX 这事以后归 YY 管」，记一下 | 追加进 `memory\负责人.md` |
| 以后这类问题不要自己回 | 追加进 `memory\偏好与禁区.md` 和工作手册 |
| 多监控一个群 / 少监控一个群 | 你说群名，它查到后问你能不能回复，更新配置 |
| 暂停助手 / 恢复助手 | Windows 停用 / 启用计划任务；macOS `launchctl bootout / bootstrap`；Linux `systemctl --user disable / enable --now`（见 3.4） |
| 看 TODO | 在协作库跑待办报告，按 P0 / P1 / P2 给你 |

**换电脑**（也可以换系统，比如 Windows 换 Mac）：把安装目录整个拷走（记忆都在 `memory` 里）；`config.json` 不要拷，到新电脑让 AI 助手重新走一遍第 0–2 步。

> Windows 版已有同事在用；macOS 在维护人电脑上实测（自检、常驻、停止）；Linux 在内网 Ubuntu 24.04 实测（自检、systemd 启停、定时器、停止无残留；钉钉登录部分用替身，未接真实群）。判断用的 AI：Claude Code 在 macOS 实测过；Codex、DSH、WorkBuddy、Qoder 按官方文档接入（DSH 用模拟命令验过参数和传法），未在真机实测；Trae 用自定义命令。遇到问题把 AI 助手的报错截图发给梦无矶。

---

## 六、常见问题

**能看到和 AI 对话窗口一样的逐条汇报吗？**

默认随助手启动自动显示，不需要使用者运行命令：Windows 独立控制台、macOS「终端」、Linux 桌面终端。每条记录包括：时间、群名、发送人、消息编号、原消息摘要、判断依据摘要和实际结果。不是模型内部推理，也不会自动插入已有的 Codex / Claude Code 对话。它是后台日志的只读窗口，不另开监听、不取走事件，不需要新增凭据。

**为什么只有旧记录，或者窗口没有动静？**

升级后要先重启后台，自动开窗并生成带上下文的新记录；旧记录不能补出当时没有写下的依据。窗口每分钟会提示最近记录时间，但这不代表后台健康。确认后台已启动，运行 `agent.py check`、`agent.py status` 并查看异常日志。`watch --once` 没记录会提示，而不是假报正常。

**跨版本升级会影响配置和通知吗？**

可直接升级，不必逐级安装。先备份配置和工作手册，停止旧后台，替换程序，再启动一份后台；保留配置、记忆、草稿、手册和角色职责库，机器人通知偏好也保留。v2.8 起回复均先写草稿，由本人确认后才发送；运行窗口不会改变这条规则。Windows 后台保持 `pythonw`，程序自动用同目录的 `python.exe` 打开查看窗口；本人需已登录桌面。macOS / Linux 同样自动开窗，不需要手动运行；已有前台终端直接显示，Linux 无图形桌面则明确提示。`report_window: false` 可显式关闭自动开窗，旧配置不含此字段时默认开启。

---
