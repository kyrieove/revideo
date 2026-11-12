"""smart_timeline.py - 原创自主时间轴生成器 (双模自主创作模式核心)"""

import subprocess
import json
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple
from scripts.smart_schema import CURRENT_SCHEMA_VERSION


def probe_audio_duration_and_beats(bgm_path: str) -> Tuple[float, List[int], str]:
    """通过 ffprobe 获取真实音频时长，并可预估节拍帧数。"""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=duration:format=duration",
        "-of", "json",
        bgm_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        meta = json.loads(res.stdout)
        dur_str = meta.get("streams", [{}])[0].get("duration") or meta.get("format", {}).get("duration")
        dur = float(dur_str) if dur_str else 0.0
        return dur
    except Exception:
        return 0.0


def generate_original_timeline(
    highlights: Optional[List[Dict[str, Any]]] = None,
    fps_str: str = "30/1",
    target_frames: Optional[int] = None,
    beat_frames: Optional[List[int]] = None,
    bgm_path: Optional[str] = None,
    narrative: str = "auto"
) -> Dict[str, Any]:
    """无参考片自主创作模式：根据素材高光、节奏卡点与叙事逻辑，自动生成连续完整的原创时间线。
    严格保证帧数覆盖与契约规范，初始化 smart_workflow 状态为 proposed，杜绝越权跳过审批。
    """
    fps = float(Fraction(fps_str))

    # 若指定了 bgm_path，优先探查真实音频
    if bgm_path and not target_frames and not beat_frames:
        dur = probe_audio_duration_and_beats(bgm_path)
        if dur > 0:
            target_frames = int(dur * fps)
            # 生成默认 4 拍每小节的节奏卡点
            beat_sec = 0.5  # 120 bpm 基础间隔
            beat_frames = [int(i * beat_sec * fps) for i in range(1, int(dur / beat_sec))]

    has_audio_beats = bool(beat_frames)

    # 1. 确定分镜切点
    if beat_frames:
        # 有外部音频节奏点时，依节奏点顺序切分
        cut_points = sorted([int(b) for b in beat_frames if b > 0])
        if target_frames is not None:
            cut_points = [p for p in cut_points if p < target_frames]
            cut_points.append(target_frames)
    else:
        # 无音频时：按高光与叙事节奏自动生成分镜
        desired_shots = len(highlights) if highlights else 4
        if target_frames is not None:
            # 严格控制镜头数不超过 target_frames，解决 target_frames 极短（如 <= 3）越界缺陷
            num_shots = max(1, min(desired_shots, target_frames))
            shot_len = target_frames // num_shots
            remainder = target_frames % num_shots
            cut_points = []
            curr = 0
            for i in range(num_shots):
                # 均分余数，保证刚好填满 target_frames
                cur_len = shot_len + (1 if i < remainder else 0)
                curr += cur_len
                cut_points.append(curr)
        else:
            default_shot_len = int(fps * 2.0)  # 默认每镜 2.0s
            cut_points = [default_shot_len * i for i in range(1, desired_shots + 1)]

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
    audio_cfg = {
        "mode": "bgm" if (has_audio_beats or bgm_path) else "none"
    }
    if bgm_path:
        audio_cfg["source"] = bgm_path

    return {
        "mode": "original",
        "fps": fps,
        "fps_str": fps_str,
        "frames": total_frames,
        "audio": audio_cfg,
        "shots": shots,
        "smart_workflow": {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "status": "proposed",
            "mode": "original",
            "approved_at": None,
            "approval_sha256": None
        }
    }

