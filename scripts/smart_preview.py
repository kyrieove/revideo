"""smart_preview.py - 生成自包含低清草稿预览与离线审查 HTML (M3)"""

import base64
import html
import os
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict


def render_draft_video(events: Dict[str, Any], output_mp4: str, target_w: int = 320, target_h: int = 180) -> str:
    """使用轻量低码率快速拼接生成自包含草稿预览视频（用于离线人机协同拍板）。"""
    shots = events.get("shots", [])
    if not shots:
        raise ValueError("Cannot render draft video: no shots in events")

    fps_str = events.get("fps_str") or f"{events.get('fps', 30.0)}/1"
    fps = float(Fraction(fps_str))
    out_p = Path(output_mp4).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix="revideo_draft_")
    clip_files = []

    try:
        for idx, shot in enumerate(shots):
            mat = shot.get("material")
            if not mat or not Path(mat).exists():
                # 若素材缺失，生成纯色占位视频片段
                p = os.path.join(tmp_dir, f"blank_{idx:03d}.mp4")
                dur = (shot["end"] - shot["start"]) / fps
                subprocess.run([
                    "ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", f"color=c=gray:s={target_w}x{target_h}:d={dur:.4f}:r={fps}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p", p
                ], check=True)
                clip_files.append(p)
                continue

            in_sec = shot.get("material_in", 0.0)
            p = os.path.join(tmp_dir, f"clip_{idx:03d}.mp4")
            # 按帧数截取：按秒 -t 逐镜取整会累计切点漂移
            subprocess.run([
                "ffmpeg", "-v", "error", "-y",
                "-ss", str(in_sec), "-i", mat, "-frames:v", str(shot["end"] - shot["start"]),
                "-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},setsar=1",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-an", "-pix_fmt", "yuv420p", "-r", str(fps), p
            ], check=True)
            clip_files.append(p)

        concat_list = os.path.join(tmp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for c in clip_files:
                f.write(f"file '{Path(c).resolve().as_posix()}'\n")

        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p", str(out_p)
        ], check=True)
        return str(out_p)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def generate_preview(
    events: Dict[str, Any],
    output_html: str,
    draft_video_path: str = "",
    generate_draft_if_missing: bool = True
) -> str:
    """生成单文件离线 preview.html，内嵌可播放的草稿视频、帧边界交互条与候选对比表。"""
    shots = events.get("shots", [])
    fps_str = events.get("fps_str") or f"{events.get('fps', 30.0)}/1"
    fps = float(Fraction(fps_str))
    total_frames = events.get("frames", sum((s.get("end", 0) - s.get("start", 0)) for s in shots))

    # 验证时间线连续性
    curr = 0
    timeline_ok = True
    for s in shots:
        if s.get("start") != curr:
            timeline_ok = False
            break
        curr = s.get("end", curr)
    if curr != total_frames:
        timeline_ok = False

    # 若草稿视频不存在且允许生成，则自动渲染低清快速草稿
    video_path = draft_video_path
    if (not video_path or not Path(video_path).is_file()) and generate_draft_if_missing and shots:
        try:
            auto_draft = Path(output_html).parent / "draft_preview.mp4"
            render_draft_video(events, str(auto_draft))
            video_path = str(auto_draft)
        except Exception:
            video_path = ""

    video_tag = ""
    if video_path and Path(video_path).is_file():
        try:
            v_size = os.path.getsize(video_path)
            # 若大于 15MB，以更低码率重编，确保单文件自包含
            if v_size > 15 * 1024 * 1024:
                compressed_mp4 = str(Path(video_path).parent / "draft_compressed.mp4")
                try:
                    subprocess.run([
                        "ffmpeg", "-v", "error", "-y",
                        "-i", video_path,
                        "-c:v", "libx264", "-crf", "34", "-preset", "veryfast",
                        "-vf", "scale=240:-2", "-an", compressed_mp4
                    ], check=True)
                    if Path(compressed_mp4).exists():
                        video_path = compressed_mp4
                        v_size = os.path.getsize(video_path)
                except Exception:
                    pass

            if v_size <= 20 * 1024 * 1024:  # <= 20MB 采用 Base64 内嵌保证离线单文件
                with open(video_path, "rb") as vf:
                    v_b64 = base64.b64encode(vf.read()).decode("utf-8")
                    video_tag = f'<div style="margin-bottom:20px;"><video id="main-player" controls width="540" src="data:video/mp4;base64,{v_b64}"></video></div>'
            else:
                rel_url = html.escape(Path(video_path).name)
                video_tag = f'<div style="margin-bottom:20px;"><video id="main-player" controls width="540" src="{rel_url}"></video></div>'
        except Exception as e:
            video_tag = f'<div style="color:#e66;">[草稿加载异常: {html.escape(str(e))}]</div>'
    else:
        video_tag = '<div style="padding:10px; background:#2a2a2a; color:#bbb; border-radius:4px; margin-bottom:15px;">[无内嵌草稿视频，显示纯分镜清单]</div>'

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>revideo 智能分镜草稿审查</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #141414; color: #eee; padding: 20px; }}
        .header {{ display: flex; align-items: baseline; gap: 15px; margin-bottom: 15px; }}
        .badge {{ background: {"#2e7d32" if timeline_ok else "#c62828"}; padding: 3px 8px; border-radius: 4px; font-size: 13px; font-weight: bold; }}
        .shot {{ border: 1px solid #333; margin-bottom: 12px; padding: 12px; border-radius: 6px; background: #1e1e1e; cursor: pointer; transition: background 0.15s; }}
        .shot:hover {{ background: #282828; border-color: #555; }}
        .shot-id {{ font-weight: bold; color: #4da6ff; margin-right: 10px; }}
        .meta-tag {{ font-size: 12px; background: #2d2d2d; padding: 2px 6px; border-radius: 3px; color: #aaa; margin-right: 6px; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>revideo 智能分镜审查与草稿预览</h2>
        <span class="badge">{"时间线连续一致" if timeline_ok else "时间线存在间隙/漂移"}</span>
        <span style="color:#888;">总帧数: {total_frames} ({total_frames / fps:.2f}s @ {fps_str})</span>
    </div>
    {video_tag}
    <div id="shots-list">
"""
    for s in shots:
        sid = html.escape(str(s.get("id", "")))
        start = int(s.get("start", 0))
        end = int(s.get("end", 0))
        dur_frames = end - start
        dur_sec = dur_frames / fps
        start_sec = start / fps
        mat = html.escape(str(s.get("material", "未指定")))
        mat_in = html.escape(str(s.get("material_in", 0)))
        score = html.escape(str(s.get("selection", {}).get("score", "N/A")))
        role = html.escape(str(s.get("role", "ambient")))

        html_content += f"""
        <div class="shot" onclick="seekPlayer({start_sec})" data-start-frame="{start}" data-end-frame="{end}">
            <span class="shot-id">镜头 #{sid}</span>
            <span class="meta-tag">{role}</span>
            <span>区间: {start} ~ {end} 帧 ({dur_frames} 帧 / {dur_sec:.2f}s)</span> | 
            <span>匹配分: <b>{score}</b></span>
            <div style="margin-top:6px; color:#bbb; font-size: 13px;">素材: <code>{mat}</code> (入点: {mat_in}s)</div>
        </div>
"""
    html_content += """
    </div>
    <script>
        function seekPlayer(sec) {
            const p = document.getElementById('main-player');
            if (p) {
                p.currentTime = sec;
                p.play();
            }
        }
    </script>
</body>
</html>
"""
    out_p = Path(output_html)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        f.write(html_content)
    return str(out_p)
