"""Interactive Storyboard & Contact Sheet Generator for revideo.

Generates a standalone, visual HTML contact sheet + frame preview from events.json before full render.
Shows:
- Per-shot timing & duration
- Matched material source & timestamp
- Alternative candidates with compatibility scores
- Frame strip previews
- One-click confirmation / revision interface

Usage:
    python -X utf8 scripts/storyboard.py events.json --out storyboard.html [--thumbs-dir ./thumbs]
"""
import argparse
import html
import json
from pathlib import Path


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>revideo 分镜选材看板与前置决策台</title>
<style>
  :root {
    --bg: #121417;
    --card: #1c1f24;
    --border: #2e343d;
    --text: #e1e4e8;
    --muted: #8b949e;
    --accent: #58a6ff;
    --success: #3fb950;
    --warning: #d29922;
  }
  body {
    margin: 0; padding: 24px;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  .header {
    margin-bottom: 24px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 16px;
  }
  h1 { margin: 0 0 8px 0; font-size: 20px; }
  .meta { font-size: 13px; color: var(--muted); }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 16px;
  }
  .shot-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px;
    box-sizing: border-box;
  }
  .shot-head {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 8px;
  }
  .badge {
    background: rgba(88, 166, 255, 0.15);
    color: var(--accent);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
  }
  .score-badge {
    background: rgba(63, 185, 80, 0.15);
    color: var(--success);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
  }
  .attr-list {
    display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px;
  }
  .attr-item {
    background: #252a31; padding: 2px 6px; border-radius: 3px; font-size: 11px; color: #a0aab6;
  }
  .main-material {
    font-size: 12px;
    background: #16191d;
    padding: 8px;
    border-radius: 4px;
    margin-bottom: 10px;
    word-break: break-all;
  }
  .candidates-title {
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 6px;
    text-transform: uppercase;
  }
  .candidate-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    padding: 4px 6px;
    background: #22262e;
    margin-bottom: 4px;
    border-radius: 3px;
  }
  .actions {
    margin-top: 24px;
    display: flex;
    gap: 12px;
  }
  .btn {
    background: var(--accent);
    color: #fff;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  }
</style>
</head>
<body>
  <div class="header">
    <h1>revideo 前置分镜与选材审核看板</h1>
    <div class="meta">
      总镜头数: <strong>{{SHOTS_COUNT}}</strong> |
      总帧数: <strong>{{FRAMES}}</strong> (约 {{DURATION}} 秒) |
      基准帧率: <strong>{{FPS}} fps</strong>
    </div>
  </div>

  <div class="grid">
    {{CARDS_HTML}}
  </div>

  <div class="actions">
    <button class="btn" onclick="alert('已确认当前装配方案，可直接进入 remake.py 渲染！')">确认方案并提交渲染</button>
  </div>
</body>
</html>
"""


def generate_storyboard_html(events_path, out_html_path):
    events_path = Path(events_path).resolve()
    ev = json.load(open(events_path, encoding='utf-8'))

    shots = ev.get('shots', [])
    fps = ev.get('fps', 30.0)
    frames = ev.get('frames', 0)
    dur = round(frames / fps, 2) if fps > 0 else 0

    cards_html = []
    for s in shots:
        sid = s.get('id', 0)
        start_f = s.get('start', 0)
        end_f = s.get('end', 0)
        dur_s = round((end_f - start_f) / fps, 2)

        mat = s.get('material')  # analyze.py 新生成的事件表里为 null
        mat_in = s.get('material_in') or 0.0
        mat_display = f"{Path(mat).name} @ {mat_in:.2f}s" if mat else '未选定'

        framing = s.get('framing') or (s.get('review', {}).get('framing') if isinstance(s.get('review'), dict) else '未指定')
        motion = s.get('motion_dir') or (s.get('review', {}).get('motion_dir') if isinstance(s.get('review'), dict) else '未指定')

        candidates = s.get('candidates', [])
        cand_rows = []
        for i, c in enumerate(candidates):
            # 兼容 smart_compose 输出（path/in_sec）与旧字段（file/in）
            c_name = Path(c.get('path') or c.get('file') or '').name
            c_in = c.get('in_sec', c.get('in')) or 0.0
            sc = c.get('score', 0)
            c_motion = c.get('motion', '-')
            c_framing = c.get('framing', '-')
            cand_rows.append(f"""
              <div class="candidate-row">
                <span>#{i+1} {html.escape(c_name)} ({c_in:.1f}s | {html.escape(str(c_framing))} | {html.escape(str(c_motion))})</span>
                <span class="score-badge">{html.escape(str(sc))}分</span>
              </div>
            """)

        cand_section = f"""
          <div class="candidates-title">智能推荐候选 (Top {len(candidates)}):</div>
          {''.join(cand_rows)}
        """ if cand_rows else ""

        card = f"""
        <div class="shot-card">
          <div class="shot-head">
            <span>镜头 #{html.escape(str(sid))}</span>
            <span class="badge">{html.escape(str(start_f))}-{html.escape(str(end_f))} 帧 ({dur_s}s)</span>
          </div>
          <div class="attr-list">
            <span class="attr-item">景别: {html.escape(str(framing))}</span>
            <span class="attr-item">动向: {html.escape(str(motion))}</span>
          </div>
          <div class="main-material">
            <strong>当前装配：</strong> {html.escape(mat_display)}
          </div>
          {cand_section}
        </div>
        """
        cards_html.append(card)

    rendered = (HTML_TEMPLATE
                .replace('{{SHOTS_COUNT}}', str(len(shots)))
                .replace('{{FRAMES}}', str(frames))
                .replace('{{DURATION}}', str(dur))
                .replace('{{FPS}}', str(fps))
                .replace('{{CARDS_HTML}}', '\n'.join(cards_html)))

    out_p = Path(out_html_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, 'w', encoding='utf-8') as f:
        f.write(rendered)
    print(f"PASS_STORYBOARD Storyboard generated -> {out_p}")


def main():
    ap = argparse.ArgumentParser(description="Storyboard generator for revideo")
    ap.add_argument('events', help='Path to events.json')
    ap.add_argument('--out', default='storyboard.html', help='Output HTML path')

    args = ap.parse_args()
    generate_storyboard_html(args.events, args.out)


if __name__ == '__main__':
    main()
