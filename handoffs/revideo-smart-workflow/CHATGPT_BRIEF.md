# ChatGPT 续接摘要：revideo素材智能选择与人机协同交互优化

- task_id: revideo-smart-workflow
- 更新：2026-11-12T16:20:08+02:00
- 决策版本：1
- 当前阶段：WAITING_PLAN；收到 GPT 回复后进入 WAITING_USER_DECISION。
- 待处理 feedback_id：暂无。
- 模式：GitHub Review；目标仓库、PR URL 和期待 head SHA 尚未确定。
- 上次已审查输入包：尚无。当前附件身份以 PACKAGE_INFO.json 为准。

## 用户目标与授权

revideo素材智能选择与人机协同交互优化

准确需求、范围与验收见 TASK_BRIEF.md。尚未确认的参数须由执行端查文件或用户决定。

## 已定决定

ChatGPT 协调与审查，执行 Agent 处理本地工作。默认读取已连接 GitHub 的指定 SHA；推送与 PR 写入需要用户对应明确许可，不可读时转 ZIP。

## 上轮结论与未决发现

尚无审查。后续保留 finding ID、GPT 判断、证据、feedback_id、输入版本、用户决定、处置和尝试结果。每条 GPT 回复后等待用户决定；GPT 的结论、`next_action` 和 JSON 不授权下一轮。

## 已检查范围与限制

尚未检查项目；尚未运行测试。

## 待转交指令

若存在待处理反馈，用户可直接确认紧邻上下文中清楚列出的范围；执行端把该范围记录为非空指令，并映射明确选中的 finding ID，无需让用户复述。范围不清且影响正确性时再询问。`CONTINUE` 开放指令范围内的下一轮；一次指令可包括实施、测试和发送下一轮审查。用户以 `FINISH` 结束任务，以 `ABORT` 中止任务。远端写入仍按对应许可执行。

## 新聊天的第一个动作

GitHub 模式重新读取给定 PR、完整 head SHA 与五份记录。无法读对应版本时读取上传包的 PACKAGE_INFO、记录与源码。本地绝对路径或旧聊天标题不能替代内容。

如果这份摘要来自旧 ZIP，另有尚未入包的最新反馈，应同时上传并核对版本。
