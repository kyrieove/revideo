"""semantic_extract.py - 毫秒级语音对白转写、关键词意图与叙事三阶段切分"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional


def extract_speech_and_phases(audio_path: str, video_duration: float = 0.0) -> Dict[str, Any]:
    """使用 faster_whisper 提取对白字幕并对齐为序幕 (setup)、高潮 (montage) 与尾声 (resolution) 三阶段。"""
    if not os.path.exists(audio_path):
        setup_end = min(3.5, video_duration * 0.1) if video_duration > 0 else 0.0
        res_start = max(setup_end, video_duration - 15.0) if video_duration > 20 else video_duration
        return {
            "dialogue": [],
            "phases": [
                {"phase": "setup", "start": 0.0, "end": round(setup_end, 2), "description": "序幕：开拍铺垫与人物建立"},
                {"phase": "montage", "start": round(setup_end, 2), "end": round(res_start, 2), "description": "高潮：多场景风光/动作极速巡礼"},
                {"phase": "resolution", "start": round(res_start, 2), "end": round(video_duration, 2), "description": "尾声：台词揭秘、主角pose与定格关机"}
            ],
            "keywords": []
        }

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, beam_size=5)
        dialogue = []
        for s in segments:
            text = s.text.strip()
            if text:
                dialogue.append({
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": text
                })
    except Exception as e:
        dialogue = []

    # 关键词挖掘与时间锚点定位
    setup_end = 3.5
    resolution_start = max(0.0, video_duration - 25.0) if video_duration > 35.0 else video_duration * 0.6
    keywords_found = []

    for line in dialogue:
        txt = line["text"]
        # 序幕开镜关键词
        if any(kw in txt for kw in ["三二一", "321", "画面好", "预备", "开始"]):
            keywords_found.append({"type": "countdown", "time": line["start"], "text": txt})
            setup_end = max(setup_end, line["end"] + 0.5)
        # 尾声揭秘与摆 pose 关键词
        if any(kw in txt for kw in ["转场", "摆pose", "pose", "离开我", "往右走", "关掉镜头", "你在那"]):
            keywords_found.append({"type": "punchline", "time": line["start"], "text": txt})
            if line["start"] < resolution_start:
                resolution_start = line["start"] - 0.5

    # 规范化三阶段生命周期
    if video_duration > 0:
        setup_end = min(setup_end, video_duration * 0.25)
        resolution_start = max(setup_end + 2.0, min(resolution_start, video_duration - 1.0))
        phases = [
            {"phase": "setup", "start": 0.0, "end": round(setup_end, 2), "description": "序幕：开拍铺垫与人物建立"},
            {"phase": "montage", "start": round(setup_end, 2), "end": round(resolution_start, 2), "description": "高潮：多场景风光/动作极速巡礼"},
            {"phase": "resolution", "start": round(resolution_start, 2), "end": round(video_duration, 2), "description": "尾声：台词揭秘、主角pose与定格关机"}
        ]
    else:
        phases = [{"phase": "montage", "start": 0.0, "end": 0.0, "description": "默认"}]

    return {
        "dialogue": dialogue,
        "keywords": keywords_found,
        "phases": phases
    }


def main():
    parser = argparse.ArgumentParser(description="提取音轨对白并划分叙事三阶段")
    parser.add_argument("audio", help="音频文件路径 (wav/mp3/aac)")
    parser.add_argument("--duration", type=float, default=0.0, help="视频总时长 (秒)")
    parser.add_argument("--out", "-o", help="输出 JSON 路径")
    args = parser.parse_args()

    res = extract_speech_and_phases(args.audio, args.duration)
    output_str = json.dumps(res, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Narrative analysis written to: {args.out}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
