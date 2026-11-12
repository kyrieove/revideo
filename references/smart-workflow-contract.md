# Smart Workflow Contract (M0)

## 1. 范围与愿景
revideo 智能工作流升级旨在解决剪辑中的视听语言逻辑、素材池自动化装配，以及前置人机协同确认机制。
同时支持：
1. **复刻模式**：严格根据参考片（reference）的时间线与节奏切点，智能检索、对齐并卡点匹配素材。
2. **自主创作模式**：在无参考片情况下，基于素材池特征（镜头运动、高光峰值、色彩光影、景别）与背景音乐，由智能时间轴生成器规划叙事/律动时间线并装配。

## 2. JSON 契约规范

### 2.1 索引契约 (`index.json` v1)
记录素材特征分析结果：
- `schema_version`: 整数，当前固定为 1。
- `assets`: 字典或列表，包含每个素材的分析对象：
  - `asset_id`: 唯一标识（基于路径或内容哈希）
  - `path`: 相对或规范化路径
  - `source_fingerprint`: 文件大小 + mtime + sha256 采样
  - `duration_seconds`: 浮点数，时长
  - `fps_str`: 字符串（如 "30/1" 或 "29.97"）
  - `codec`: 视频编码格式
  - `features`: 时间序列特征（亮度、色彩直方图、运动向量/强度、运动方向、动作峰值）
  - `quality_flags`: 质量标记列表（如 `low_res`, `vfr`, `black_frames`）

### 2.2 候选推荐契约 (`candidates.json` v1)
记录为各个镜头槽位匹配的候选列表：
- `schema_version`: 1
- `source_events_sha256`: 绑定的事件表哈希
- `slots`: 镜头推荐列表：
  - `shot_id`: 镜头编号
  - `target`: 目标镜头特征画像（景别、动向、色彩、节奏点）
  - `candidates`: 最多 3 个候选对象：
    - `candidate_id`: 候选唯一标识（格式：`<asset_id>@<in_sec>`）
    - `asset_path`: 素材路径
    - `in_sec`: 切入秒数
    - `out_sec`: 切出秒数
    - `score`: 综合匹配分 (0.0 ~ 1.0)
    - `sub_scores`: 各维度细分得分（母题、动作、方向、色彩、能量、景别）
    - `reason_codes`: 推荐理由代码
    - `needs_review`: 是否有未知维度需人工确认

### 2.3 审查决策契约 (`decisions.json` v1)
记录人工或自动审核决策：
- `schema_version`: 1
- `candidates_sha256`: 关联的候选表哈希
- `decisions`:
  - `shot_id`: 镜头编号
  - `selected_candidate_id`: 选中的候选 ID
  - `override`: 布尔值，是否人工指定
  - `comment`: 审批说明

### 2.4 智能工作流审批元数据 (`smart_workflow` v1)
嵌入在 `events.approved.json` 中的门禁对象：
- `schema_version`: 1
- `status`: `"proposed"` | `"in_review"` | `"approved"`
- `source_events_sha256`: 源事件表哈希
- `approval_sha256`: 对最终渲染计划的 SHA-256 指纹

## 3. 防篡改指纹逻辑
`fingerprint_render_plan(doc)` 计算规则：
1. 深拷贝一份事件表；
2. 剥离 `smart_workflow` 键本身；
3. 对剩余字典使用 `json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)` 进行规范化序列化；
4. 输出 SHA-256 十六进制字符串。
一旦审批后有人手动篡改任何切点、素材路径或转场参数，渲染引擎 `remake.py` 会因指纹不符立即阻断。
