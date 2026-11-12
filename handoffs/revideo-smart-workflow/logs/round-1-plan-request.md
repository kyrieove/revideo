# Antigravity Task Plan Request [req-revideo-smart-workflow-r1-plan]

- **Task ID**: `revideo-smart-workflow`
        - **Round**: 1 (Planning)
- **Input Baseline Commit SHA**: `ce5beca8c1545d81e2561914ac2cc9e3fdd29349`
- **Repository Root (Local Context)**: `D:/2/dev/revideo`
- **Task Title**: revideo素材智能选择与人机协同交互优化

## Readable Materials & Remote Entry Points
- **Exact Commit URL**: https://github.com/kyrieove/revideo/commit/ce5beca8c1545d81e2561914ac2cc9e3fdd29349
- **Source Tree at Commit**: https://github.com/kyrieove/revideo/tree/ce5beca8c1545d81e2561914ac2cc9e3fdd29349
- **Pull Request URL**: Not configured
- **Commit Publish Status**: PUSHED_TO_REMOTE
- **Task Brief Remote Path**: `handoffs/revideo-smart-workflow/TASK_BRIEF.md`

## Task Brief & Requirements
# 任务书：revideo 素材智能选择、审美连贯性与人机协同交互优化

- task_id: revideo-smart-workflow
- 更新：2026-11-12T16:20:00+02:00
- 决策版本：1
- 用户授权来源：用户明确痛点输入与 Hindsight 记忆库沉淀

## 核心痛点与背景

revideo 工具目前具备对参考视频进行分析（逐镜切点、运动速度、能量峰值、音频重音）以及硬卡点重剪的能力，但在实际工业化使用中存在以下三大严重瓶颈：

1. **素材匹配不够懂审美与连贯关系**：
   - 当前主要依靠人工手写/硬编码把新素材填入 `events.json`，或只能机械做时长截取。
   - 缺乏对镜头景别（特写/全景）、运动走向（左移/右移/推拉）、主色调/光影、能量情绪的审美理解，镜头组接生硬，缺少蒙太奇逻辑与视听连贯性。

2. **多素材场景下无法自动筛选组接**：
   - 当用户给出一批候选素材/文件夹时，工具无法自动提取关键片段、筛选最优镜头、并根据参考片的节奏和视觉特征自动完成初剪装配。

3. **工作流黑盒、缺少合理的人机协同参与点**：
   - 流程透明度低，用户介入时机过晚（往往是在整条视频渲染出成片后，才发现某处素材不搭、某处镜头不对，导致返工成本极高）。
   - 缺少低成本的阶段性决策入口（例如：参考片结构确认阶段、素材候选单与多套方案比选阶段、分镜联系表/样帧预览阶段）。

## 优化目标与范围

1. **审美与特征表征体系**：设计轻量且可落地的镜头特征标签方案（景别、动向、色彩、动作高潮），打通与 `events.json` 的匹配打分。
2. **素材自动推荐/装配引擎**：基于参考镜头的特征需求，从候选池自动打分、推荐 2~3 个候选片段，并支持一键组接初始版本。
3. **人机协同透明交互机制**：重塑工作流阶段划分，在渲染整片前引入前置检查点（如分镜单/联系表比选、一键多方案预览），让用户在成本最低的阶段拍板。

## 可观察验收

| ID | 用户可观察的结果 | 验证方法 | 必需证据 |
|---|---|---|---|
| A-001 | 产出切实可行、分阶段演进的技术设计方案与人机协同工作流规范 | ChatGPT 协调审查 | 方案包含镜头特征定义、打分算法、前置决策交互点设计 |
| A-002 | 定义素材库特征索引与参考镜头匹配逻辑契约 | 规范审查与单元推演 | 接口规范、配置示例与事件表扩展字段 |
| A-003 | 制定分步实施演进路线（最小原型到自动化装配） | 用户与 ChatGPT 共同验收 | 清晰的 Milestone 与验证手段 |

## 决策变更记录

版本 1：根据用户核心反馈及项目记忆初始化。

## Planning Instructions
请务必实际访问并阅读上述精确 SHA (`ce5beca8c1545d81e2561914ac2cc9e3fdd29349`) 的代码及改动。
注意：本次规划与审查仅覆盖指定 SHA 代码，本地可能存在的未跟踪文件或差异不包含在内。
若因未推送或网络无法读取指定 SHA 代码，必须直接返回 decision 为 BLOCKED 或 NEEDS_INPUT，严禁在未读取真实源码的情况下直接判定。
你负责设计：steps 必须写到执行端无需再读代码判断的程度（文件、函数、具体改动；容易写错的地方给代码片段）。每个 P0/P1 修复都要配一个在旧代码上会失败的测试。执行端只照 steps 做，有疑问会回 NEEDS_INPUT。
请在回复末尾附带严格符合下述契约的机器可读 JSON 区块：

```json:chatgpt-review
{
  "task_id": "revideo-smart-workflow",
  "round": 1,
  "reviewed_head_sha": "ce5beca8c1545d81e2561914ac2cc9e3fdd29349",
  "decision": "<PLAN_READY | NEEDS_INPUT | BLOCKED>",
  "steps": [
    "1. 文件 → 函数 → 具体改动",
    "..."
  ],
  "check": "完整测试命令",
  "findings": [],
  "next_action": "实施计划说明"
}
```
