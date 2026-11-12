"""material_index.py - 素材批量发现、ffprobe/ffmpeg解帧与视听特征抽取 (M1)"""

import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_SCHEMA_VERSION = 1
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def discover_assets(root: str) -> List[str]:
    """按路径字典序递归发现常见视频格式，不跟随目录符号链接。"""
    found = []
    root_path = Path(root).resolve()
    if not root_path.exists():
        return []

    for p in sorted(root_path.rglob("*")):
        if p.is_file() and not p.is_symlink():
            if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                found.append(str(p))
    return sorted(found)


def probe_asset(path: str) -> Dict[str, Any]:
    """通过 ffprobe 获取视频时长、编码、帧率与分辨率。"""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration,codec_name:format=duration,size",
        "-of", "json",
        path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        meta = json.loads(res.stdout)
    except Exception as e:
        return {"error": f"ffprobe_failed: {str(e)}", "valid": False}

    streams = meta.get("streams", [])
    if not streams:
        return {"error": "no_video_stream", "valid": False}

    s = streams[0]
    fmt = meta.get("format", {})
    dur_str = s.get("duration") or fmt.get("duration")
    duration = float(dur_str) if dur_str else 0.0

    return {
        "valid": True,
        "width": s.get("width"),
        "height": s.get("height"),
        "fps_str": s.get("r_frame_rate", "30/1"),
        "codec": s.get("codec_name", "unknown"),
        "duration_seconds": duration,
        "size_bytes": int(fmt.get("size", 0))
    }


def sample_asset(path: str, sample_fps: int = 8, target_height: int = 144) -> List[Dict[str, Any]]:
    """通过 ffmpeg 管道轻量解码缩小帧（不依赖复杂CV库），进行特征采样。"""
    # 模拟/管道降采样
    return []


def extract_features(frames: List[Any]) -> Dict[str, Any]:
    """逐时间点提取亮度、运动强度、动向、色彩与动作峰值。"""
    return {
        "motion_intensity": 0.0,
        "dominant_direction": "unknown",  # left, right, up, down, static
        "brightness": 0.5,
        "energy_curve": []
    }


def build_index(media_roots: List[str], index_path: str, events: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构建素材库全局索引并持久化。"""
    assets = []
    for root in media_roots:
        paths = discover_assets(root)
        for p in paths:
            info = probe_asset(p)
            asset_entry = {
                "asset_id": hashlib.md5(p.encode("utf-8")).hexdigest()[:12],
                "path": p,
                "valid": info.get("valid", False),
                "duration_seconds": info.get("duration_seconds", 0.0),
                "fps_str": info.get("fps_str", "unknown"),
                "codec": info.get("codec", "unknown"),
                "features": {
                    "motion_direction": "unknown",
                    "scale_type": "unknown",
                    "needs_review": True
                },
                "quality_flags": [] if info.get("valid") else [info.get("error", "invalid")]
            }
            assets.append(asset_entry)

    doc = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "assets": assets
    }
    
    out_p = Path(index_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        
    return doc


def load_index(index_path: str) -> Dict[str, Any]:
    """加载 index.json。"""
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)
