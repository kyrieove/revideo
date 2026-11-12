# Antigravity Code Review Request [req-revideo-smart-workflow-r5-review]

- **Task ID**: `revideo-smart-workflow`
- **Round**: 5
- **Reviewed Head Commit SHA**: `c039a381a7ae189e665ce96754ec120b0b058db3`
- **Repository Root (Local Context)**: `D:/2/dev/revideo`

## Readable Materials & Remote Entry Points
- **Exact Commit URL**: https://github.com/kyrieove/revideo/commit/c039a381a7ae189e665ce96754ec120b0b058db3
- **Source Tree at Commit**: https://github.com/kyrieove/revideo/tree/c039a381a7ae189e665ce96754ec120b0b058db3
- **Pull Request URL**: Not configured
- **Commit Publish Status**: PUSHED_TO_REMOTE
- **Task Brief Remote Path**: `handoffs/revideo-smart-workflow/TASK_BRIEF.md`
- **Test Evidence Remote Path**: `handoffs/revideo-smart-workflow/TEST_RESULTS.md`

## Task Brief & Acceptance Scope
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

## Recent Git Commits
```
c039a38 fix(smart-workflow): address round-4 review on gates and boundaries
676ca34 feat(dual-mode): address F-002 through F-007 (approval validation, real video sampling, beam search, draft preview, original timeline & E2E tests)
482e1ad feat(dual-mode): address F-001 through F-007 (approval gate, real ffmpeg sample, original timeline generator, smart compose)
4d4f67e feat(smart-workflow): implement M0-M3 core modules and gates (schema, index, match, approval, preview)
ce5beca docs: add revideo smart workflow task brief
```

## Diff Stat for Reviewed Commit (Metadata Only)
```
scripts/material_index.py |  1 +
 scripts/remake.py         | 43 ++++++++++++++-----------
 scripts/smart_compose.py  | 31 ++++++++++++++++--
 scripts/smart_match.py    | 25 ++++++++++++---
 scripts/smart_preview.py  | 18 ++++++++++-
 scripts/smart_schema.py   | 41 ++++++++++++++++--------
 scripts/smart_timeline.py | 81 +++++++++++++++++++++++++++++++++++++++--------
 tests/test_remake_gate.py |  8 +++++
 8 files changed, 193 insertions(+), 55 deletions(-)
```

## Verified Test Evidence
- Command: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast`
- Exit Code: `0`
- Tested Commit: `c039a381a7ae189e665ce96754ec120b0b058db3`
- Execution Timestamp: `2026-11-12T18:51:00Z`
- Evidence File: `handoffs\revideo-smart-workflow\TEST_RESULTS.json`
- Evidence Hash: `c5114808b4abd46b34f1d75878f286d42bd549ae4f937ff5c0ec9a3243657881`
```
{
  "command": "python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast",
  "tested_sha": "c039a381a7ae189e665ce96754ec120b0b058db3",
  "summary": "37 unit tests and 28 media tests passed (100% OK)",
  "exit_code": 0,
  "unit_tests_passed": 37,
  "media_tests_passed": 28,
  "timestamp": "2026-11-12T18:51:00Z"
}
```

## Continuation Context
# Continuation Brief for Task revideo-smart-workflow
- Title / Goal: revideo素材智能选择与人机协同交互优化
- Stage: BLOCKED
- Round: 2
- Fixed Commit SHA: 4d4f67ef83da2030a3a3c87815c1aebd3ccb6b4d
- Active Chat URL: https://chatgpt.com/g/g-p-68d1848f372081918ae13ad310a7fff8-ove-phd/c/6af5cb00-1fd4-83ea-866b-acd8ea649665
- Previous Chat URLs: None
- Diagnosis Mode: False
- Feedback ID: fb-56bf6beed9be45bde9f67abf010bc14fe5e0fcf5b921b936f8d6c459a066a262
- Last Feedback Summary: {"feedback_id": "fb-56bf6beed9be45bde9f67abf010bc14fe5e0fcf5b921b936f8d6c459a066a262", "decision": "BLOCKED", "round": 1, "reviewed_head_sha": "4d4f67ef83da2030a3a3c87815c1aebd3ccb6b4d"}
- Last User Decision: CONTINUE
- Selected Finding IDs: None
- User Instructions:
已将分支 feat/smart-workflow 完整推送到 GitHub 远端（Commit SHA: 4d4f67ef83da2030a3a3c87815c1aebd3ccb6b4d）。请核验该提交中的真实代码与测试，同时我们将继续实现你提出的 TimelinePlan 契约、smart_timeline 原创时间轴生成器与 smart_compose 组接引擎。
- User-Selected Findings:
  None
- Next Action: Address browser exchange failure: Response generation returned TIMEOUT: 


## Previous Unresolved Findings (Please explicitly re-verify each)
- `F-008`: 新增的原创模式允许在没有 smart_workflow 审批元数据时直接通过正式渲染门禁。旧人工事件表的兼容例外被错误地应用到了新智能工作流。
- `F-002`: 人工确认检查已实现，但审批关联摘要仍是可选项，素材指纹仅在旧数据之间比较，没有读取实际文件验证。人工审批与素材来源绑定不完整。
- `F-003`: 像素亮度和帧差已实现，但运动方向通过左右半屏变化面积猜测，不能测量方向符号。景别被固定成 medium，未知视觉语义却被标记为无需审查。素材索引尚不能满足审美特征契约。
- `F-004`: Beam Search 已真正执行，但仍使用整条素材统一评分，候选窗口最多只覆盖前20个采样入点，最终只返回最佳路径而非2至3套完整组接方案。
- `F-005`: 草稿视频生成已经实现，但没有复用正式渲染的转场和音频逻辑；失败时仍返回仅含文字的 HTML；超过20MB时输出依赖外部视频文件，违反单文件离线契约。
- `F-006`: 无BGM渲染分支已实现，但原创时间轴存在短目标帧数超限、缺少素材仍生成占位镜头、没有使用高光实际长度以及未提供真正BGM路径接口的问题。
- `F-007`: 真实FFmpeg端到端测试已经加入，但只覆盖成功路径，审批绕过、素材变更、草稿一致性等关键失败场景未测试；指定SHA中的测试证据仍标记NOT RUN，无法独立验证执行端声称的36项成功。

## User Instructions for This Review Round
采纳第4轮审查意见F-008及F-002至F-007，全面闭环原创模式未审批门禁、素材文件当前真实指纹校验、片段级动态特征打分、多方案输出、转场草稿与负向测试覆盖
Selected finding IDs: F-008, F-002, F-003, F-004, F-005, F-006, F-007
Only selected findings are in the authorized implementation scope. Unselected findings remain unaccepted.
## 复审范围
本轮为复审，只审 `676ca349dd36a0bb76814df639c168e4a955c535..c039a381a7ae189e665ce96754ec120b0b058db3` 的改动：逐条确认用户选择的 findings 是否已修复；新问题均应报告并按实际严重程度分类。finding 的等级和用户未选择的状态都不能表示已接受。

## Review Instructions
请针对上述精确 SHA (`c039a381a7ae189e665ce96754ec120b0b058db3`) 的实际源码与已验证测试证据进行严格、独立的审查（注意：Diff Stat 仅为摘要，不能替代真实代码）。
注意：本次审查仅覆盖指定 SHA 及其关联测试证据，本地未跟踪差异不包含在内。
若因未推送或网络无法读取指定 SHA 代码，必须直接返回 decision 为 BLOCKED 或 NEEDS_INPUT，严禁在未读取真实源码的情况下直接给出 ACCEPTED。
按实际影响为每条 finding 标记 P0/P1/P2/P3。不得假设任何等级会被自动接受或延后；用户会在完整反馈中选择下一步。
每条 finding 必须附能证实它的代码行，证实不了就不要报。
P0/P1 必须给出执行端可直接照做的 fix_steps。
请在回复末尾附带严格符合下述契约的机器可读 JSON 区块（注意：禁止使用默认 ACCEPTED，请根据真实审查结论判定）：

```json:chatgpt-review
{
  "task_id": "revideo-smart-workflow",
  "round": 5,
  "reviewed_head_sha": "c039a381a7ae189e665ce96754ec120b0b058db3",
  "decision": "<ACCEPTED | CHANGES_REQUESTED | NEEDS_INPUT | BLOCKED>",
  "findings": [
    // 若 decision 为 CHANGES_REQUESTED，必须提供非空列表：
    {"id": "F-001", "severity": "P1", "description": "问题简述", "file": "路径", "line": 1, "evidence": "证实问题的那一行代码", "fix_steps": ["文件 → 函数 → 具体改动"], "regression_test": "测试名与断言", "introduced_by_fix": false}
  ],
  "next_action": "下一步动作说明"
}
```
