# revideo 叙事镜头契约与补录工作流

本文件说明基于 b244621 安全修复的使用方式。目标是防止素材库里没有正确人物动作时，智能组接用无关镜头强行凑满整片。

**当前边界**：本分支没有新增视觉语言模型。素材索引能自动得到亮度、像素运动和方向代理信号，但不能可靠自动识别收剑、举杯、镜头推拉、主体彩色构图或姿态。必要的语义字段应来自手动标注或经人工核验的模型输出。未知字段会进入 REVIEW_REQUIRED，而不是冒充匹配成功。

## 1. events.json 中的镜头契约

将 contracts 列表与现有 shots 对齐；镜头数量、id、start/end 帧及 FPS 必须一致。例如 30 FPS 的一秒镜头：

    {
      "fps": 30.0,
      "fps_str": "30/1",
      "frames": 30,
      "contract_required": true,
      "shots": [{"id": 1, "start": 0, "end": 30}],
      "contracts": [{
        "id": 1, "start_frame": 0, "end_frame": 30,
        "duration_frames": 30, "duration_seconds": 1.0,
        "subject": "player_character",
        "action": "sheathing_sword",
        "camera_motion": "pan_right",
        "scene_type": "snow_mountain",
        "framing": "full_shot",
        "match_cut": false,
        "notes": "收剑结束时对齐音乐重音"
      }]
    }

action、subject、camera_motion 和 scene_type 是必要条件，不允许错误动作靠其他权重补足。beat_peak_frame、action_anchors、transition_contract 等字段用于记录更多证据；**尚未自动实现动作相位与音频重音的联合对齐**。

## 2. 素材索引的局部语义证据

material_index.build_index() 构建索引后，找到实际素材对应的 asset。经人工确认视频动作与时间范围，再将以下字段补充在该 asset 中：

    {
      "semantic_segments": [{
        "start": 40.0, "end": 43.0,
        "source": "manual", "verified": true,
        "features": {
          "subject": "player_character",
          "action": "sheathing_sword",
          "camera_motion": "pan_right",
          "dominant_scene": "snow_mountain"
        }
      }]
    }

这是追加字段，不是完整 asset；不要覆盖原有文件路径、素材真实指纹、时长或采样数据。

只有时间窗口完全落在该段已核验的区间内，才能直接使用上述动作标签。模型未经复核的片段不得将 source 标为 manual 或 verified 标为 true；否则会错误放行。重新索引只有在素材真实指纹保持不变时才保留之前的语义标注。

如果整段素材的每一帧都满足相同语义标签，可使用 semantic_scope=full_asset 和 semantic_verified=true。普通长录屏包含大量不同动作，请使用 semantic_segments，不要错误地声明整段有效。

## 3. Match Cut 接缝证据

若第二镜的契约 match_cut=true，须在相邻两段素材的实际剪切边界记录姿态和位置。示例为某段素材的结尾锚点：

    "transition_anchors": [{
      "time": 1.0,
      "pose": "sword_raised",
      "position": {"x": 0.50, "y": 0.50},
      "verified": true
    }]

下一镜头的起始锚点需要同名 pose，主体中心坐标接近；默认最大归一化欧氏距离 0.16。标注 time 必须确实对应剪切时间点，而不是整段素材的平均姿态。没有经核验的接缝锚点时不能自动放行 Match Cut。

## 4. 组接与补录

在项目根目录创建一个 Python 文件，例如 run_compose.py，内容：

    import json
    from pathlib import Path
    from scripts.smart_compose import compose
    from scripts.gap_analyzer import MaterialDeficitError

    events = json.loads(Path("events.json").read_text(encoding="utf-8"))
    index = json.loads(Path("index.json").read_text(encoding="utf-8"))
    try:
        plan = compose(
            events, index,
            allow_forced_fill=False,
            task_sheet_out="capture_task_sheet.md",
        )
    except MaterialDeficitError as error:
        print(error)
        print("请查看 capture_task_sheet.md，区分缺口与待复核镜头")
    else:
        Path("events.proposed.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

运行：

    python run_compose.py

判定：
- PASSED：窗口证据已核验，可以作为候选参与组接。
- REVIEW_REQUIRED：还缺少动作/主体/运镜的可靠证据，应先核对而不是立即补录。
- BLOCKED/GAP：明确素材不足或有冲突，参照补录任务单执行。
- NO_FEASIBLE_COMPOSITION：虽然每镜存在候选，全片依然不满足素材复用或 Match Cut 等组合约束。

生成 proposed 时间轴不是渲染授权。仍须经过 smart_workflow.approve() 的逐镜人工确认与 remake.py 的签名/审计校验。

## 5. 人工例外强剪

compose(..., allow_forced_fill=True) 只允许探索替代方案，不等于批准。后续逐镜决策中必须写入：

    {
      "shot_id": 7,
      "confirmed": true,
      "selected_candidate_id": "<该镜头实际候选 ID>",
      "force_contract_override": true,
      "override_reason": "人工确认允许使用替代动作"
    }

审批函数必须为该镜头写入 contract_audit；修改已批准的素材或入点会令审批指纹失效。

## 6. 测试与未实现功能

完整测试命令：

    python -m unittest discover -s tests -v

GitHub Actions 还安装了 FFmpeg/ffprobe、NumPy、OpenCV 测试依赖。

尚未实现：从参考片自动生成可验证的多模态契约、自动人物动作识别、动作相位/速度曲线重定时、精确视线连续性和音频重音到动作峰值的帧级自动对齐。当前新增的是可追溯的数据契约与保守的安全门禁，不能把它宣传为已有完整的 AI 视频理解流水线。
