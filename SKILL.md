---
name: revideo
description: "复刻剪辑视频：同一段音乐、逐帧照搬参考片的切点和镜头内动作，只换素材。用户说「复刻」一条视频、给参考片要做同款卡点、要对照参考片接着改进已有的复刻成片、或输入 /revideo 时使用。Exclude: 仅拆解分析不重剪（用 rea-video）、换歌重新对拍、从零生成动画（用 hyperframes）、纯 AI 人物替换。"
---

# revideo

**复刻** = 原片的音乐不变，切点帧号和镜头内每个动作的帧号照搬，只把画面素材换掉。不借手法另配歌，不重新对拍。用户说「换」某一段时，换的是素材，运镜模式、时间曲线和切点照旧。

所有步骤都往同一份**事件表** `events.json` 里填数据。`$R` 指脚本仓库（默认 `D:/2/dev/claude-video`），`$T` 指 `$R/tools/revideo`（维护源；技能包 `scripts/` 是部署副本，并非链接），`$P` 指 `$R/.venv/Scripts/python`（Windows）或 `$R/.venv/bin/python`。复刻项目常在别的仓库，脚本一律按全路径调用。命令按 Bash 写。修改脚本后运行 `$P $T/sync_install.py <技能目录> --apply`，再不带 `--apply` 校验两处所有脚本一致；技能更新后先核对维护源，不能覆盖本地修复。同步会移除部署副本中的旧剪映导出脚本，保留任何草稿与素材。

---

## 从哪一步开始

| 情况 | 做法 |
|---|---|
| **新参考片** | 从第 0 步（环境与素材体检）做起 |
| **已有成片，接着改或优化** | 先读参考目录的 `NOTES.md`（裁决台账与偏离清单），先跑第 8 步的 `compare`、`side` 和项目的 `accept.py`，再做第 7 步审查 |
| **用户换了素材或参考片** | 先写 `HANDOFF.md` 换会话。新会话从第 5 步（换素材与分镜）或第 1 步（换参考片）做起 |

---

## 标准复刻九步法

### 0. 环境自检与素材前置体检
- **环境检查**：`$P -c "import cv2, librosa, scenedetect" && ffmpeg -version >/dev/null && rea-video --help >/dev/null`。
- **素材前置自检（Checklist）**：
  1. *全角字符转义*：下载或导入素材后，第一步跑 `link_sources.py` 创建英文命名符号链接/硬链接，防止 `ffmpeg` 和 `OpenCV` 闪退。
  2. *AV1 管道解码*：录屏为 AV1 且 OpenCV 无法直接硬解时，必须走 `ffmpeg` 原始帧管道读取。
  3. *安全区预设*：带 UID 水印与界面的录屏，按 1.06 倍居中裁切安全区核算，杜绝穿帮。
  4. *10 秒试录验证*：录全套前要求用户先录 10 秒试录片，核验机位、光线与无 UI 后再开拍。

### 1. 建参考目录与分型预判
- 建目录：`videos/_refs/<作者>-<id>/`，放 `video.mp4`、`music.mp3`（原声）和 `NOTES.md`。
- **CFR 转换**：`ffprobe` 检查 `r_frame_rate == avg_frame_rate`。不相等先用 `ffmpeg -fps_mode cfr` 转恒定帧率。
- **流派归属预判**：依 [patterns-and-pitfalls.md](references/patterns-and-pitfalls.md) 确定归属三大流派之一：
  - **A. 硬切/快闪卡点型**（Teto）：测切点、HPSS 鼓点起音、入场重模糊消退点；
  - **B. 连续几何动效型**（千斤坠）：测扫圈角速度（`verify_wipe.py`）、羽化、凹陷帧段与停帧（HOLDS）；
  - **C. 动作相位对齐型**（横刀）：测关键动作阶段（`ANCHOR`）、分段变速与局部插帧。

### 2. 切点、BPM、花字分解
- 运行：`rea-video decompose video.mp4 --out <dir> [--no-vlm]`。结果在 `breakdown.json`，字幕花字在 `packaging/`。

### 3. 事件表生成与动作测量
- 运行：`$P $T/analyze.py video.mp4 <dir> --rea <dir>/breakdown.json [--song 整首歌]`。
- 自动保留逐镜上游证据，建立动作/效果待核对项；按 [reference-review.md](references/reference-review.md) 填写同一事件表的 `shots[].review`。已有表用 `$P $T/reference_review.py events.json [--rea breakdown.json]` 初始化。
- 切点分歧逐个抽帧（`rea-video tiles`）看图裁决；传 `--song` 时要求 `song_corr ≥ 0.9`，低于 0.9 必须更换音频版本。
- **连续动效与动作相位**：
  - 动效型跑 `$P $T/effects.py dips video.mp4 <起始帧> <帧数>` 记录清晰度凹陷与停帧；
  - 动作型在 `events.json` 每镜写 `anchors`（阶段、参考帧、成片帧；未出现填 null），用 `$P $T/check.py anchors events.json ref.mp4 out.mp4 review/ --max-diff N` 抽帧并排；阈值先量再定。

### 4. 分型与视觉母题确立
- 按 [references/patterns-and-pitfalls.md](references/patterns-and-pitfalls.md) 明确流派约束。
- 给每个 `shot` 和 `event` 写上 `role`（画面物理作用）；确立整片统一的**视觉母题**（如“脸转向正面”、“两收一拔”），避免杂乱切片。

### 5. 编排、分镜单与可播放 HTML 预览（强制前置卡点）
严格按 [references/editor-review.md](references/editor-review.md) 流程推进：
1. **分镜单先行**：每镜列清起止帧、重音帧、一句话目的（观众看什么）、景别、转向方向、主色调、候选 `素材@秒`。
2. **画质链防劣退**：从源素材单次 Lanczos 复合重采样（裁切、缩放、推拉、旋转一次完成）；严禁整镜帧平均；严禁全屏加高频伪噪点；结合 `cas=0.35` 锐化。
3. **调色与抠像核验**：参考片提亮 5 倍确认背景灰度；动效型调色在 Lab 空间做逐通道直方图规定化；人物动作严禁倒放（改用 swing 曲线）。
4. **生成单页自包含 `preview.html`**：按项目编写 `edit/preview.py`（不是包内通用命令），读取同一份 `events.json` 和项目渲染计划，导出真实切点、时间曲线、裁切和原声；输入/输出契约见 editor-review.md。允许先渲染三镜小样和低分辨率全片预览。
5. **用户手机端看片验收**：手机实放确认视觉逻辑与节奏。**用户确认前不启动耗时的正式全片渲染**。

### 6. 渲染
- **常规硬切/转场**：`$P $T/remake.py events.json out.mp4 [--transition fade:6]`。音源优先 `--music`，其次 `music.song`，最后 `events.ref` 原声；仅 `music.song` 默认使用 `song_offset`，其余起点默认 0，`--offset` 显式覆盖。缺音轨或音源不足会失败。事件表中的相对素材/音源路径相对事件表目录，命令行路径相对工作目录。
- **动效/复杂运动**：按项目写 `render.py`，帧号严格读自 `events.json`。
- **局部补帧**：低帧率慢放只允许在单镜头内部使用本地 RIFE v4.6 插帧，**绝对严禁跨转场补帧**。音视频分离拼接，防音频 1 帧溢出漂移。

### 7. 剪辑审查与无上下文盲审（每次必做）
- 自审：按 [references/editor-review.md](references/editor-review.md) 建立镜头表/转场表/动作阶段表，排查视线、重复度、人脸亮度下限（≥40）。
- **盲审**：派一个完全未接触制作过程的独立子 Agent 基于成片和参考片盲审打分，产出 10 分制评分与 P0/P1 清单。
- 完成标准：P0/P1 清零，P2/P3 记为 `deferred:` 并落盘；每条 finding 带证据帧或代码行。最多两轮（一次审查、一次只看修复差异的复查），两轮后仍有 P0/P1 交用户裁决；用户不在场则修复并标 `unreviewed-fix:`，交用户验收。首版建立独立评分基线，后续总分不低于上一版；已确认的偏离按台账处理。

### 8. 综合技术验收（全部通过才交付）
先看过参考片，按片型确定执行项：
1. **逐帧画像比对**：`$P $T/check.py compare ref.mp4 out.mp4 <起始帧> <帧数>`，清晰度、停帧、运动量无 FAIL。
2. **并排对比与响度**：`$P $T/check.py side ref.mp4 out.mp4 side.mp4`；`$P $T/check.py loudness ref.mp4 out.mp4` 测 I/Peak 并报差值。当前不自动分离原声与音乐，只报数字，不替代人工判断；有分轨标注时才按原声比音乐低 6–12 dB 判定。并排片随成片交付。
3. **能量曲线**：`$P $T/check.py energy events.json ref.mp4 out.mp4 energy.svg`，亮度和运动量逐镜相关必须为正。
4. **项目专属断言**：运行项目目录下的 `edit/accept.py`，退出码必须为 0。
5. **参考复核完整性**：`$P $T/check.py review events.json` 必须通过；它只检查动作/效果及分歧复核记录，不能替代成片与参考片的独立比对。
6. **动作阶段与评分**：`$P $T/check.py anchors events.json ref.mp4 out.mp4 review/ --max-diff N` 无 FAIL；`$P $T/check.py scorecard docs/reviews/<version>/score.json [--baseline 上一版]` 通过。首版只建立基线。

---

## 交付台账规范（唯一接手契约）

每一版的决定、实测数字和裁决必须落盘到参考目录的 `NOTES.md`，包含以下两张标准化表格：

### 1. 裁决台账（Verdict Ledger）
每版一行，作为后续版本及 `accept.py` 阈值的唯一事实来源：
```markdown
| 版 | 用户原话反馈 | 当时量到的物理量与依据 | 结论与动作 |
|---|---|---|---|
| v1 | 「原片的每一圈转完都是有一个动效在的」 | 扫圈中位差 0.33 帧，段尾存在 6 帧运动模糊与停帧 | 否；补齐 effects.py dips 凹陷帧段 |
| v7 | 「先不录了 暂定第七版最佳」 | 半径 400–560 灰度 32→8（参考 27→8），Laplacian 方差 119 | 暂定最佳；以此基准编写 accept.py |
```

### 2. 偏离清单（Deviations List）
记录成片有意不照搬参考片的地方，防止新会话发生反复返工：
```markdown
| 参考片做法 | 成片做法 | 为什么（实测证据或用户裁决） |
|---|---|---|
| 汽车正放加倒放折返 | 人物正放加闪进后匀速 | 人物动作倒放生理违和，用户定「像鬼畜，要丝滑」 |
| 素材缩放到约 0.72 倍 | 新素材放大 1.68 倍 | 新素材内主体直径偏小，放大后增加 CAS 锐化 |
| 画面四角完整无露黑 | 旋转后四角露黑 ≤6.3% | 旋转是为了严格对齐爆发方向，经用户确认认可 |
```

跨会话交接统一通过根目录或子模块的 `HANDOFF.md` 传递，严禁口头转述。
