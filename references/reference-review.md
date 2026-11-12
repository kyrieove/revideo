# 参考内容复核契约

`analyze.py` 自动把参考证据和待核对项写入同一份 `events.json`。已有事件表可用 `$P $T/reference_review.py events.json [--rea breakdown.json]` 初始化；它拒绝覆盖已有复核，旧成片不用重渲染。初始化会修改传入的事件表，研究或历史版本请先用工作副本。

## 上游证据

- `reference_review.rea` 记录报告绝对路径、文件 SHA-256、schema 和工具版本；参考片沿用上游首 64 MiB 的 SHA-256 指纹约定。帧率、尺寸、完整镜头边界和原片指纹不匹配时拒绝导入。
- 每镜 `reference` 保留 `base`、`deterministic`、景别/运镜/布光/调色 `aspects`、`layers`、`beats`、看图描述与截图位置。它们是待核实的推断/测量，不能直接写入素材选择、调色或变速参数。
- `base.seen` / `base.measured` 在新上游存在时原样保留；旧报告的合并 `evidence` 不自动改称“看图事实”。`readers.vlm` 与 `readers.review` 单独保留来源。没有看图描述就保留缺失，不生成描述补齐。
- 只支持 `rea_video.breakdown.v1`。没有 schema 的历史切点文件降级为仅切点，显式警告，仍要求参考内容复核；未知 schema 直接失败。v1 缺少核心元数据时失败，不静默降级。
- `layers` 仅是图层候选。空列表不能证明没有扫圈、局部模糊、停帧或其他镜头内效果；这些必须通过实际参考帧确认。

## 待核对项与完成记录

每镜都有 `review.action` 和 `review.effects`。上游明确标出 `disputed` / `uncertain` 时追加 `review.upstream`；两种切点检测结果不同时，在相关镜头追加 `review.boundary`，差异帧保存在 `reference.cut_disagreement`。不复制上游分类概率阈值来决定游戏素材的制作方式。

- `action`：描述可观察动作、关键阶段、起止/完成状态及推进顺序。动作型不能只看镜头开头或一个静帧，须覆盖变速、完成、停留、反向等相邻阶段，并在事件表事件/项目动作阶段表中标定。横刀 v12 的 F470 尚未完成而 F475 已反向，是需要覆盖的边界。
- `effects`：覆盖镜头起、中、尾，注明发生帧段、范围、方向、清晰度/停帧/遮罩变化等可观察要求。千斤坠参考 F173–178 等圈尾模糊不能被“扫圈角速度对了”替代。
- `upstream`：对照原片核实分歧，说明保留的判断或不适用于本次复刻的推断。分类冲突不必强行裁定成某一种素材来源，但必须说明与本次复刻约束的关系。
- `boundary`：逐帧看差异帧，记录是否为真实切点/闪白/动作变化及最终裁决。若要修改已导入的镜头边界，保留旧记录，重新生成工作事件表并复核，不直接挪动旧签核的范围。

填写示例（结构示例，帧号和说明必须换成实际观察，不得直接拿来关闭任务）：

```json
{
  "status": "verified",
  "note": "写清参考动作/效果及帧段，并指出项目事件或动作阶段表的对应记录",
  "reviewer": "实际执行复核的工具或审查者",
  "evidence": [
    {"file": "../video.mp4", "frame": 470},
    {"file": "review/reference_F473.png", "frame": 473}
  ]
}
```

`status` 初始为 `pending`；完成可用 `verified`、`not_applicable` 或 `deviation`。三种完成状态均须有非空说明、复核者和至少一个实际存在的证据文件，帧号必须在该镜半开区间 `[start,end)` 内。没有动作/效果也必须说明并举证。`deviation` 的说明须指向 NOTES 中已认可的偏离，不能用它自行批准删掉效果。

## 动作阶段与评分

动作型每镜写 `anchors`：`{"phase":"收刀完成","ref_frame":470,"out_frame":470}`；成片未出现该阶段填 `null`。`$P $T/check.py anchors events.json ref.mp4 out.mp4 review/ --max-diff N` 抽参考/成片同阶段帧并排，输出 `anchors.json`；未给阈值只报数，给了才判 FAIL。阈值先量 v11–v13 的阶段帧差再定。

盲审评分表按 [review-scorecard.md](review-scorecard.md)，每版写 `docs/reviews/<version>/score.json`，用 `$P $T/check.py scorecard score.json [--baseline prev.json]` 校验并对比基线。效果参数见 `$T/fx/manifest.json`。

## 使用与边界

运行 `$P $T/check.py review events.json`。它会打印上游依据、看图描述、图层候选、分歧及未完成项。填写证据前用 `$P $T/check.py strips events.json ref.mp4 out.mp4 review/` 为待核对镜头生成参考/成片帧条（按 `review.status` 选取；`--all` 含已核对镜头，旧表本就全量；`--shot ID` 默认只在待核对镜头里取）；切点分歧用 `--boundaries` 生成逐帧帧条。帧条只作证据，记录是否完整仍以 `check.py review` 为准。缺项、未知状态、无证据、证据帧越界、报告改变、参考片指纹/时间基准/镜头范围变化均失败；无复核契约的旧事件表也失败，须先初始化。

该检查只证明参考复核记录完整、可定位，不读取或判定成片动作，也不能判断说明是否真实、关键阶段是否穷尽。证据文件只是存在性检查，内容变化不自动撤销记录；参考片指纹只覆盖首 64 MiB。这些限制不得省略。继续执行 `compare`、`side`、`energy`、项目 `accept.py` 和独立成片盲审；动作/效果的真正一致性由这些检查与参考片观察共同证明。

本契约不阻止生成审查小样，也不修改正式渲染参数。技能第 7、8 步必须消费复核结果，未完成不能宣称完成复刻。
