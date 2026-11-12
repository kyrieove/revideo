"""smart_preview.py - 生成自包含低清草稿预览与离线审查 HTML (M3)"""

import base64
import html
import json
from pathlib import Path
from typing import Any, Dict


def generate_preview(events: Dict[str, Any], output_html: str, draft_video_path: str = "") -> str:
    """生成单文件离线 preview.html，内嵌可播放的草稿视频或 Base64 媒体与安全转义。"""
    shots = events.get("shots", [])
    
    video_tag = ""
    if draft_video_path and Path(draft_video_path).is_file():
        try:
            with open(draft_video_path, "rb") as vf:
                v_b64 = base64.b64encode(vf.read()).decode("utf-8")
                video_tag = f'<div style="margin-bottom:20px;"><video controls width="480" src="data:video/mp4;base64,{v_b64}"></video></div>'
        except Exception:
            video_tag = f'<div style="color:#aaa;">[草稿视频文件存在: {html.escape(draft_video_path)}]</div>'

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>revideo 智能分镜草稿审查</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121212; color: #eee; padding: 20px; }}
        .shot {{ border: 1px solid #333; margin-bottom: 12px; padding: 12px; border-radius: 6px; background: #1e1e1e; }}
        .shot-id {{ font-weight: bold; color: #4da6ff; margin-right: 10px; }}
    </style>
</head>
<body>
    <h1>revideo 智能分镜审查与草稿预览</h1>
    {video_tag}
    <div id="shots-list">
"""
    for s in shots:
        sid = html.escape(str(s.get("id", "")))
        start = html.escape(str(s.get("start", 0)))
        end = html.escape(str(s.get("end", 0)))
        mat = html.escape(str(s.get("material", "未指定")))
        mat_in = html.escape(str(s.get("material_in", 0)))
        score = html.escape(str(s.get("selection", {}).get("score", "N/A")))
        
        html_content += f"""
        <div class="shot">
            <span class="shot-id">镜头 #{sid}</span>
            <span>区间: {start} ~ {end} 帧</span> | 
            <span>匹配分: {score}</span>
            <div style="margin-top:6px; color:#bbb;">素材: <code>{mat}</code> (入点: {mat_in}s)</div>
        </div>
"""
    html_content += """
    </div>
</body>
</html>
"""
    out_p = Path(output_html)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        f.write(html_content)
    return str(out_p)
