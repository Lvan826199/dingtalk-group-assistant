# 路线图

## 待验证（v2.7 发版前后）

- [ ] **完整部署实测**：用 AI 助手按部署文档从头走一遍，「有协作库」「没有协作库」两条路径都走，接提醒群真实收发一条消息。
- [ ] **Windows 实测 v2.7**：请已在用的 Windows 同事升级，重点看三项：停掉助手时监听进程有没有残留、钉钉发不出去时的提醒、判断用的 AI 是不是自己在用的那个。（CI 已在 Windows 上跑自动化测试，含子进程清理。）
- [ ] **其他 AI 真机实测**：WorkBuddy（codebuddy）、Qoder（qodercli）、DSH（dsh headless）、Trae（自定义命令）各找一位在用的同事试一次判断和自检。

## 计划中

- [ ] **建记忆读更多 AI 的对话记录**：现在读 Codex、Claude Code；补 DSH、WorkBuddy 等（先确认各自的会话记录位置和格式）。
- [ ] **支持飞书**：监听和回复走飞书（参考做法：通过 MCP 连接器读写会话）。
- [ ] **一键卸载**：`agent.py uninstall`，按系统停掉自启（计划任务 / LaunchAgent / systemd）并删除安装目录和配置，删除前二次确认。
- [ ] **英文 README**：开源仓库加 `README.en.md`。
- [ ] **GitHub Release**：每个版本在 Releases 页附更新说明和部署文档，方便下载和订阅更新。

## 已完成（v2.7）

全角色 + 角色职责库（AI 可自行补充）、协作库可选、Windows / macOS / Linux、任意 AI 编程助手（含 DSH）、AI 失败自动换备用、助手新版本提醒、钉钉 CLI 新版本提醒、发不出去用机器人通知（带草稿编号）、原始记录保留期、自动化测试 + 三系统 CI。详见 [CHANGELOG](CHANGELOG.md)。
