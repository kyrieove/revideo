"""smart_timeline.py - 原创自主时间轴生成器 (双模自主创作模式核心)"""

from fractions import Fraction
from typing import Any, Dict, List, Optional


def generate_original_timeline(
    highlights: Optional[List[Dict[str, Any]]] = None,
    fps_str: str = "30/1",
    target_frames: Optional[int] = None,
    beat_frames: Optional[List[int]] = None,
    narrative: str = "auto"
) -> Dict[str, Any]:
    """无参考片自主创作模式：根据素材高光、节奏卡点与叙事逻辑，自动生成连续完整的原创时间线。
    严格保证帧数覆盖与契约规范，无 BGM 时明确标记 audio.mode='none'。
    """
    fps = float(Fraction(fps_str))
    has_audio_beats = bool(beat_frames)

    # 1. 确定分镜切点
    if beat_frames:
        # 有外部音频节奏点时，依节奏点顺序切分
        cut_points = sorted([int(b) for b in beat_frames if b > 0])
        if target_frames:
            cut_points = [p for p in cut_points if p < target_frames]
            cut_points.append(target_frames)
    else:
        # 无音频时：按高光与叙事节奏自动生成分镜
        num_shots = len(highlights) if highlights else 4
        if target_frames:
            # 严格均分 target_frames，保证无漂移
            shot_len = max(1, target_frames // num_shots)
            cut_points = [shot_len * i for i in range(1, num_shots)]
            cut_points.append(target_frames)
        else:
            default_shot_len = int(fps * 2.0)  # 默认每镜 2.0s
            cut_points = [default_shot_len * i for i in range(1, num_shots + 1)]

    # 2. 构建连续镜头序列
    shots = []
    start = 0
    for idx, end in enumerate(cut_points):
        if end <= start:
            continue
        shots.append({
            "id": idx + 1,
            "start": start,
            "end": end,
            "role": "highlight" if idx % 2 == 1 else "ambient",
            "scale_ref": 1.0,
            "target_energy": 0.8 if idx % 2 == 1 else 0.4
        })
        start = end

    total_frames = start
    return {
        "mode": "original",
        "fps": fps,
        "fps_str": fps_str,
        "frames": total_frames,
        "audio": {
            "mode": "bgm" if has_audio_beats else "none"
        },
        "shots": shots
    }
