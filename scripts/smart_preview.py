"""smart_preview.py - 生成自包含低清草稿预览与离线审查 HTML (M3)"""

import json
from pathlib import Path
from typing import Any, Dict


def generate_preview(events: Dict[str, Any], output_html: str, draft_video_path: str = "") -> str:
    """生成单文件离线 preview.html，包含镜头对比与时间轴查看。"""
    shots = events.get("shots", [])
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>revideo 智能分镜草稿审查</title>
    <style>
        body {{ font-family: sans-serif; background: #121212; color: #eee; padding: 20px; }}
        .shot {{ border: 1px solid #333; margin-bottom: 15px; padding: 12px; border-radius: 6px; }}
        .shot-id {{ font-weight: bold; color: #4da6ff; }}
    </style>
</head>
<body>
    <h1>revideo 智能草稿预览</h1>
    <div id="shots-list">
"""
    for s in shots:
        html_content += f"""
        <div class="shot">
            <span class="shot-id">镜头 #{s.get('id')}</span>
            <span>帧范围: {s.get('start')} ~ {s.get('end')}</span>
            <div>选用素材: {s.get('material')} (入点: {s.get('material_in')}s)</div>
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
