	

初始权重




视觉母题与镜头目的

	

28%




动作阶段、峰值与重音对齐

	

23%




运动方向

	

10%




色彩与光影

	

12%




能量变化

	

15%




景别与主体占比

	

12%

单镜匹配后，再通过相邻镜头衔接评分和全局候选搜索选择一组镜头，而不是每一镜独立取最高分。重复素材惩罚、视线连续性和动作方向关系由全局搜索处理。

审批状态应独立于原有 review.action / review.effects。后者是参考片证据复核，不能代表用户认可自动选材。

Python
运行
# scripts/remake.py 中新增的核心门禁逻辑示意
if "smart_workflow" in ev:
    if ev["smart_workflow"]["status"] != "approved":
        raise ValueError("SMART_WORKFLOW_NOT_APPROVED")


    expected = fingerprint_render_plan(ev)
    if ev["smart_workflow"]["approval_sha256"] != expected:
        raise ValueError("SMART_WORKFLOW_APPROVAL_STALE")

预览采用显式低分辨率草稿模式；正常正式渲染必须通过审批门禁。原有不含 smart_workflow 的人工事件表保持向后兼容。

4. 分阶段实施路线

阶段

	

交付结果

	

验收标准




M0 · 数据契约

	

smart_schema.py 与规范文档

	

旧事件表兼容，参考切点不变




M1 · 素材索引

	

批量分析素材，生成特征索引及缩略图

	

可定位到 素材@秒，无效素材有排除原因




M2 · 智能匹配

	

每镜推荐最多 3 个候选，生成多套全片方案

	

单镜评分可解释，组接考虑前后关系




M3 · 协同工作流

	

参考确认、候选切换、联系表、预览和审批

	

未审批不能正式渲染，审批后修改会失效




M4 · 集成验收

	

回归测试、完整操作文档、运行证据

	

自动化测试通过，原有命令不回退

5. 数据结构示例

下面是已有 events.json 的建议扩展结构节选，不是完整可直接运行的事件表。

JSON
{
  "shots": [
    {
      "id": 1,
      "start": 0,
      "end": 15,
      "material": "../clips/shot_a.mp4",
      "material_in": 2.4,
      "selection": {
        "asset_id": "asset-001",
        "candidate_id": "asset-001@2.4",
        "score": 0.84,
        "reason_codes": [
          "energy_match",
          "direction_match"
        ],
        "needs_review": true,
        "human_override": false
      }
    }
  ],
  "smart_workflow": {
    "schema_version": 1,
    "status": "proposed",
    "source_events_sha256": "...",
    "approval_sha256": null
  }
}

本方案保留 shots[].scale_ref、shots[].scale 等现有字段用途，不创建语义重复且相互矛盾的并行字段。评分、素材特征及人工标注的完整记录另外存放，事件表只保留最终渲染必需的选择信息和审计信息。

验收测试必须覆盖以下风险：参考切点被修改、候选素材时长不足、低帧率素材不适配、未知特征被误判为已验证、相邻镜头重复、未经审批渲染、审批后篡改参数以及预览和正式渲染时间线不一致。

审查进度：规划审查已完成；实际实施为 0/5。本轮没有执行本地测试，也没有修改或推送代码。

下一步： 将下面完整 JSON 交给 Antigravity，由你确认后执行 M0。要求先编写在当前旧代码下失败的测试，再实现对应功能，并在每个阶段保留可见验收证据。

机器可读审查结果
json:chatgpt-review


```json:chatgpt-review
{
  "task_id": "revideo-smart-workflow",
  "round": 1,
  "reviewed_head_sha": "ce5beca8c1545d81e2561914ac2cc9e3fdd29349",
  "decision": "PLAN_READY",
  "steps": [
    "1. [M0/P0] 新增 references/smart-workflow-contract.md、scripts/smart_schema.py、tests/test_smart_schema.py。smart_schema.py 实现 validate_source_events(doc)、validate_index(index)、validate_proposal(proposal)、fingerprint_render_plan(doc)。使用 scripts/remake.py::validate_timeline 验证原始时间线；使用 scripts/reference_review.py::timeline 验证参考镜头结构。原始 events.json 不得被原地覆盖。定义 index v1、candidates v1、decisions v1、smart_workflow v1 四个 JSON 契约，明确必填字段、unknown/null 语义和版本拒绝规则。index 包含 asset_id、path、source_fingerprint、duration_seconds、fps_str、codec、features、quality_flags。candidates 包含 source_events_sha256、shot_id、target、排名、候选区间、各项分数、人工检查项。decisions 包含 candidates_sha256、shot_id、candidate_id、人工覆盖说明。smart_workflow 包含 schema_version、status、source_events_sha256、approval_sha256。fingerprint_render_plan 应对移除 smart_workflow 后的完整渲染事件表做 sort_keys=True、separators=(',',':')、ensure_ascii=False 的规范 JSON 序列化，再计算 SHA-256。测试 test_smart_schema.py::test_rejects_changed_reference_boundaries 必须拒绝任一 start/end/fps_str/frames 改动；test_rejects_unknown_schema 必须拒绝未知版本；test_does_not_mutate_source 必须确认原事件表逐字节不变。旧代码缺少 smart_schema.py，测试在旧基线必须先呈 RED，修复后 GREEN。",
    "2. [M1/P1] 新增 scripts/material_index.py、tests/test_smart_index.py。实现 discover_assets(root)、probe_asset(path)、sample_asset(path, sample_fps=8)、extract_features(frames)、build_index(events,index_path,media_roots)、load_index(index_path)。按路径排序递归发现常见视频格式，不跟随目录符号链接。复用 scripts/peaks.py::subject_motion 的主体运动测量思想；通过 ffprobe 获得视频编码、时长、帧率，通过 ffmpeg 管道解码缩小帧，避免直接依赖 OpenCV 视频解码器。逐时间点提取灰度亮度、Lab 颜色、Laplacian 清晰度、主体及背景运动强度、光流方向、动作峰值；记录首尾画面特征供相邻组接。运动方向明确标记为图像运动方向，不冒充摄像机运镜方向。景别、主体位置、语义母题及 UI 遮挡若无可靠测量或人工标注，设为 unknown 并保留 needs_review，禁止编造标签。视频 VFR、解码失败、时长不足、素材变化必须显式记录原因；索引使用 size、mtime_ns 与内容指纹做缓存失效检查。为候选素材生成带时间戳的联系表。test_smart_index.py::test_extracts_two_distinct_motion_segments 用合成左右运动视频验证方向；test_rejects_undecodable_asset 验证失败记录；test_cache_invalidates_after_source_change 验证修改后重建。上述测试在旧代码上因模块不存在而失败。",
    "3. [M2/P1] 新增 scripts/smart_reference.py、scripts/smart_match.py、tests/test_smart_match.py。smart_reference.py 实现 derive_targets(events, reference_video, manual_labels)，只把 shots[].reference.aspects 视作来源明确的待核实线索，参考镜头的景别及动作语义必须结合现有 shots[].role、shots[].scale_ref、人工标注或真实视频测量；保留来源和置信状态。smart_match.py 实现 enumerate_windows(asset, required_frames, target_fps)、score_candidate(target,candidate,weights)、score_transition(previous,current)、beam_search(slots,beam_width=8)、propose(events,index,top_k=3)。候选窗口必须满足有效素材余量、非负 material_in、可解码帧范围、帧率和安全区要求；关键质量红线命中时排除，unknown 仅允许进入待人工复核候选。单镜默认权重：母题0.28、动作0.23、方向0.10、色彩0.12、能量0.15、景别0.12；只对已知维度重新归一化，另输出 coverage、component_scores 和 reason_codes。动作峰值偏差使用目标时间轴帧数度量；无可核实峰值时不得声称已对齐。相邻评分考虑主体位置、运动衔接、色彩关系和重复惩罚；使用固定顺序及 beam_width=8 生成最多三套全局方案，所有并列情况确定性排序。候选不足时返回 missing_slots 和明确原因，不强制填满。测试 test_smart_match.py::test_preserves_reference_frames、test_excludes_short_material、test_unknown_scale_requires_review、test_global_sequence_beats_greedy、test_deterministic_ranking、test_reports_missing_slot。每项测试先验证旧版 RED，再验证实现后 GREEN。",
    "4. [M3/P0] 新增 scripts/smart_workflow.py、scripts/smart_review.py、scripts/smart_preview.py、tests/test_smart_approval.py、tests/test_smart_preview.py；修改 scripts/remake.py::main 和 validate_timeline 调用后的渲染前检查。smart_workflow.py 提供 index、propose、review、approve、preview 五个子命令。propose 只输出 events.proposed.json 与 candidates.json，不修改原始 events.json。smart_review.py 用 Python 标准库实现仅绑定 127.0.0.1 的本地审查服务，提供参考镜头结构确认、每镜最多三个候选、来源时间戳、评分依据、质量警告、人工替换和分镜联系表；所有 POST 校验请求来源、请求大小、候选 ID、文件路径及工作流状态。review 服务将选择写入 decisions.json，禁止浏览器传入任意系统命令。approve 逐镜核对候选、用户确认、source_events_sha256、candidates_sha256 和素材指纹，输出独立的 events.approved.json，status=approved，approval_sha256=fingerprint_render_plan(doc)。scripts/remake.py 新增 validate_smart_approval(ev)：检测到 smart_workflow 时，非 approved 拒绝正式渲染，完整渲染指纹不匹配则拒绝；无 smart_workflow 的原人工事件表继续采用原行为。smart_preview.py 调用与正式渲染相同的镜头时间线和转场代码生成低分辨率草稿，不另行推算切点；草稿渲染必须显式使用 --draft-preview，限制最大画面高度为360并标记为未审批。输出单文件离线 preview.html，内嵌低分辨率视频与必要图片，不引用远程 CDN；HTML 内包含逐镜查看、候选 A/B 对比及移动端播放。视频超出预设嵌入容量时明确报错，允许降低草稿码率重试，不静默输出非自包含页面。复杂运动方案若不受当前 remake.py 支持，标为 unsupported 并要求项目专属 render.py 适配，不伪称预览等价。测试 test_smart_approval.py::test_rejects_unapproved_render、test_rejects_tampered_approval、test_accepts_legacy_manual_events、test_rejects_stale_asset；test_smart_preview.py::test_preview_has_exact_frame_boundaries、test_preview_is_self_contained、test_rejects_unsupported_motion_plan。当前旧代码没有审批门禁，必须先观察测试失败。",
    "5. [M4/P1] 修改 README.md、SKILL.md、references/editor-review.md；新增 tests/test_smart_workflow_e2e.py。README 增加从素材文件夹到候选建议、人工确认、草稿预览和正式输出的完整命令；SKILL.md 第5步增加智能选材可选流程，保留既有 reference_review、anchors、NOTES.md、独立盲审和第8步技术验收。editor-review.md 明确参考片证据复核、素材质量复核、用户选材审批是三种不同确认，不能互相替代。E2E 测试在临时目录用 ffmpeg 创建含音轨的合成参考片和候选素材，生成两镜事件表，依次执行 index、propose、review 决策导入、approve、remake，并用 ffprobe 验证输出总帧数、帧率、镜头边界及音频存在；测试不得依赖作者电脑上的硬编码辅助路径。并运行 scripts/peaks.py selftest、scripts/effects.py selftest、compileall 和全部 smart 单元测试。记录测试环境、退出码、stdout/stderr、产物路径、被测 Git SHA 到 handoffs/revideo-smart-workflow/TEST_RESULTS.md；在 REVIEW_REPORT.md 对 A-001/A-002/A-003 逐项给出证据。实施必须在基于指定 SHA 的非默认开发分支进行，保留本地现存改动；不得未经用户明确批准推送、强制更新分支或创建 PR。"
  ],
  "check": "PowerShell（仓库根目录执行；以下命令为实施完成后的验收命令，本次未运行）：Set-Location 'D:/2/dev/revideo'; python -X utf8 -m unittest discover -s tests -p 'test_smart_*.py' -v; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python -X utf8 scripts/peaks.py selftest; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python -X utf8 scripts/effects.py selftest; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python -X utf8 -m compileall -q scripts; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python -X utf8 -m unittest discover -s tests -p 'test_smart_workflow_e2e.py' -v; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; Write-Output 'PASS_SMART_WORKFLOW_ALL'",
  "findings": [
    {
      "id": "REV-P0-001",
      "severity": "P0",
      "location": "scripts/remake.py::main",
      "evidence": "当前入口直接读取 shots[].material/material_in 并启动渲染，没有智能方案审批状态和完整配置指纹验证。",
      "required_test": "tests/test_smart_approval.py::test_rejects_unapproved_render"
    },
    {
      "id": "REV-P1-001",
      "severity": "P1",
      "location": "scripts/analyze.py::main",
      "evidence": "生成的 shots[].material 初始为 None，没有素材库扫描、候选窗口及排序接口。",
      "required_test": "tests/test_smart_index.py::test_extracts_two_distinct_motion_segments"
    },
    {
      "id": "REV-P1-002",
      "severity": "P1",
      "location": "scripts/reference_review.py::attach",
      "evidence": "reference.aspects、readers 和上游分类属于参考证据，不能未经核实就变成自动选材的确定事实。",
      "required_test": "tests/test_smart_match.py::test_unknown_scale_requires_review"
    },
    {
      "id": "REV-P1-003",
      "severity": "P1",
      "location": "scripts/strips.py::VIEW",
      "evidence": "帧条工具依赖 C:/Users/ASUS/.claude/skills/video-use/helpers/timeline_view.py，不能作为独立可移植预览方案。",
      "required_test": "tests/test_smart_preview.py::test_preview_is_self_contained"
    },
    {
      "id": "REV-P1-004",
      "severity": "P1",
      "location": "SKILL.md 与 references/editor-review.md",
      "evidence": "文档已有分镜、选材和 HTML 预览要求，但指定 SHA 下没有通用候选推荐、审批与预览生成接口。",
      "required_test": "tests/test_smart_workflow_e2e.py"
    }
  ],
  "next_action": "PLAN_READY，等待用户决定后由 Antigravity 实施。先执行 M0：创建数据契约、验证函数及旧基线失败测试，不修改现有渲染结果。每个 M 完成后提供可见产物、测试输出和源码差异供用户确认；尚未授权任何 GitHub 写入。"
}
```
