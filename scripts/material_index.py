"""material_index.py - 素材批量发现、ffprobe/ffmpeg解帧与真实视听特征抽取 (M1)"""

import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

CURRENT_SCHEMA_VERSION = 1
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def compute_source_fingerprint(path: str) -> str:
    """计算素材文件的快速指纹（文件大小 + mtime + 首尾64KB内容），检测素材是否被替换或篡改。"""
    try:
        stat = os.stat(path)
        h = hashlib.sha256()
        h.update(f"{stat.st_size}_{stat.st_mtime}".encode("utf-8"))
        with open(path, "rb") as f:
            head = f.read(65536)
            h.update(head)
            if stat.st_size > 65536:
                f.seek(max(0, stat.st_size - 65536))
                tail = f.read(65536)
                h.update(tail)
        return h.hexdigest()
    except Exception:
        return ""


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


def sample_asset(path: str, sample_fps: int = 8, target_w: int = 160, target_h: int = 90) -> List[Dict[str, Any]]:
    """分块读取 FFmpeg 灰度帧，避免把长视频全部像素加载到内存。

    基于半屏差分的方向只是一种 screen-motion 代理信号，不等于 camera_motion。
    """
    if min(sample_fps, target_w, target_h) <= 0:
        raise ValueError("采样帧率与图像尺寸必须大于 0")
    frame_size = target_w * target_h
    cmd = [
        "ffmpeg", "-v", "error", "-i", path,
        "-vf", f"fps={sample_fps},scale={target_w}:{target_h},format=gray",
        "-f", "rawvideo", "-"
    ]
    proc = None
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        samples = []
        prev_frame = None
        while True:
            chunk = proc.stdout.read(frame_size)
            if not chunk:
                break
            if len(chunk) != frame_size:
                break
            frame = np.frombuffer(chunk, dtype=np.uint8).reshape(
                (target_h, target_w)
            ).astype(np.int16)
            avg_lum = float(np.mean(frame)) / 255.0
            motion = 0.0
            direction = "static"
            if prev_frame is not None:
                diffs = np.abs(frame - prev_frame)
                motion = float(np.mean(diffs)) / 255.0
                if motion > 0.02:
                    left_diff = float(diffs[:, :target_w // 2].sum())
                    right_diff = float(diffs[:, target_w // 2:].sum())
                    if left_diff > right_diff * 1.25:
                        direction = "right_to_left"
                    elif right_diff > left_diff * 1.25:
                        direction = "left_to_right"
                    else:
                        direction = "pan"
            prev_frame = frame
            samples.append({
                "timestamp": round((len(samples)) / float(sample_fps), 3),
                "luminance": round(avg_lum, 3),
                "motion": round(motion, 3),
                "direction": direction
            })
        if proc.wait() != 0:
            return []
        return samples
    except Exception:
        if proc is not None:
            proc.kill()
            proc.wait()
        return []
    finally:
        if proc is not None and proc.stdout is not None:
            proc.stdout.close()


def extract_features(frames: List[Dict[str, Any]]) -> Dict[str, Any]:
    """根据真实采样切片聚合素材的特征标签（亮度、运动强度、优势动向与能量曲线）。"""
    if not frames:
        return {
            "motion_intensity": 0.0,
            "motion_direction": "unknown",
            "dominant_direction": "unknown",
            "brightness": 0.0,
            "energy_curve": [],
            "needs_review": True
        }

    lums = [f["luminance"] for f in frames if "luminance" in f]
    motions = [f["motion"] for f in frames if "motion" in f]
    directions = [f["direction"] for f in frames if "direction" in f and f["direction"] != "static"]

    avg_lum = sum(lums) / len(lums) if lums else 0.5
    avg_motion = sum(motions) / len(motions) if motions else 0.0
    
    # 统计出现次数最多的非静止动向
    dom_dir = "static"
    if directions:
        from collections import Counter
        dom_dir = Counter(directions).most_common(1)[0][0]

    # 能量曲线由亮度和运动共同决定
    energy_curve = [round(l * m * 2.0, 3) for l, m in zip(lums, motions)]

    return {
        "motion_intensity": round(avg_motion, 3),
        "motion_direction": dom_dir,
        "dominant_direction": dom_dir,
        "brightness": round(avg_lum, 3),
        "energy_curve": energy_curve[:16],
        "needs_review": False
    }


def build_index(media_roots: List[str], index_path: str, events: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构建素材库全局特征索引并持久化，记录 source_fingerprint 防篡改。"""
    assets = []
    for root in media_roots:
        paths = discover_assets(root)
        for p in paths:
            info = probe_asset(p)
            frames = sample_asset(p) if info.get("valid") else []
            feats = extract_features(frames)
            sf = compute_source_fingerprint(p)
            asset_entry = {
                "asset_id": hashlib.md5(p.encode("utf-8")).hexdigest()[:12],
                "path": p,
                "source_fingerprint": sf,
                "valid": info.get("valid", False),
                "duration_seconds": info.get("duration_seconds", 0.0),
                "fps_str": info.get("fps_str", "unknown"),
                "codec": info.get("codec", "unknown"),
                "sampled_frames": frames,
                "semantic_segments": [],
                "semantic_scope": "unknown",
                "semantic_verified": False,
                "features": {
                    "motion_direction": feats.get("dominant_direction", "unknown"),
                    "motion_intensity": feats.get("motion_intensity", 0.0),
                    "brightness": feats.get("brightness", 0.5),
                    "energy_curve": feats.get("energy_curve", []),
                    "scale_type": "medium",
                    "needs_review": feats.get("needs_review", False)
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
