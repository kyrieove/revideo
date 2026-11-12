"""smart_timeline.py - 原创自主时间轴生成器 (双模自主创作模式核心)"""

from fractions import Fraction
from typing import Any, Dict, List, Optional


def generate_original_timeline(
    highlights: List[Dict[str, Any]],
    fps_str: str = "30/1",
    target_frames: Optional[int] = None,
    beat_frames: Optional[List[int]] = None,
    narrative: str = "auto"
) -> Dict[str, Any]:
    """无参考片自主创作模式：根据素材高光、节奏卡点与叙事逻辑，自动生成连续完整的事件时间线。"""
    fps = float(Fraction(fps_str))
    
    # 若提供音乐节奏点，按节拍切分；否则按高光片段自然呼吸节奏切分（默认每镜 1.5s ~ 2.5s）
    if not beat_frames:
        default_shot_frames = int(fps * 2.0)
        num_shots = len(highlights) if highlights else 4
        beat_frames = [i * default_shot_frames for i in range(1, num_shots + 1)]
    
    shots = []
    start = 0
    for idx, end in enumerate(beat_frames):
        dur = end - start
        shots.append({
            "id": idx + 1,
            "start": start,
            "end": end,
            "role": "highlight" if idx % 2 == 1 else "ambient",
            "scale_ref": 1.0,
            "target_energy": 0.8 if idx % 2 == 1 else 0.4
        })
        start = end
        if target_frames and start >= target_frames:
            break
            
    total_frames = start
    return {
        "mode": "original",
        "fps": fps,
        "fps_str": fps_str,
        "frames": total_frames,
        "audio": {
            "mode": "none" if not beat_frames else "bgm"
        },
        "shots": shots
    }
