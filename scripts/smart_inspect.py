"""smart_inspect.py - 工业级音画同轴走带卡点可视化检验看板生成引擎

提供：
1. 100Hz 音频时域 RMS 振幅包络提取
2. 逐帧像素差分动作能量采样
3. 单页自包含、零外部外链、Dark Studio 电影级深色主题的 Canvas 走带交互页面
"""

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np


def extract_audio_envelope(video_or_audio_path: str, sample_rate_hz: int = 100) -> List[float]:
    """通过 ffmpeg 管道流式提取音频 100Hz RMS 时域包络。"""
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(video_or_audio_path),
        "-ac", "1", "-ar", "8000", "-f", "s16le", "-"
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        raw_audio = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        if len(raw_audio) == 0:
            return []
        
        hop_size = 8000 // sample_rate_hz  # 80
        num_windows = len(raw_audio) // hop_size
        waveform_env = []
        for i in range(num_windows):
            chunk = raw_audio[i * hop_size : (i + 1) * hop_size]
            rms = float(np.sqrt(np.mean(chunk**2))) if len(chunk) > 0 else 0.0
            waveform_env.append(round(min(1.0, rms * 4.0), 3))
        return waveform_env
    except Exception:
        return []


def extract_motion_curve(video_path: str, fps: float = 30.0) -> List[float]:
    """通过 ffmpeg 灰度管道逐帧抽取像素平均绝对差分作为动作能量。"""
    cmd_v = [
        "ffmpeg", "-v", "error", "-i", str(video_path),
        "-vf", f"fps={fps},scale=120:68,format=gray", "-f", "rawvideo", "-"
    ]
    try:
        proc_v = subprocess.run(cmd_v, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        raw_v = proc_v.stdout
        frame_bytes = 120 * 68
        num_v_frames = len(raw_v) // frame_bytes
        motion_curve = []
        prev_f = None
        for i in range(num_v_frames):
            chunk = np.frombuffer(raw_v[i * frame_bytes : (i + 1) * frame_bytes], dtype=np.uint8)
            if prev_f is not None:
                diff = float(np.mean(np.abs(chunk.astype(np.float32) - prev_f.astype(np.float32))) / 255.0)
            else:
                diff = 0.0
            prev_f = chunk
            motion_curve.append(round(min(1.0, diff * 5.0), 3))
        return motion_curve
    except Exception:
        return []


def generate_rhythm_inspector(video_path: str, events: Dict[str, Any], out_path: str) -> str:
    """构建工业级音画同轴走带卡点可视化检验页面并写入指定文件。"""
    video_p = Path(video_path).resolve()
    out_p = Path(out_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fps = float(events.get("fps", 30.0))
    shots_raw = events.get("shots", [])
    drums_raw = events.get("music", {}).get("drums", [])
    total_frames = int(events.get("frames", 0))

    if not total_frames and shots_raw:
        total_frames = max(s.get("end", 0) for s in shots_raw)
    total_dur = total_frames / fps if fps > 0 else 0.0

    # 1. 整理镜头与切点数据
    shots_data = []
    for idx, s in enumerate(shots_raw, 1):
        f_in = s.get("start", 0)
        f_out = s.get("end", f_in + 1)
        dur_f = f_out - f_in
        dur_s = dur_f / fps
        t_in = f_in / fps
        t_out = f_out / fps
        closest_drum = min(drums_raw, key=lambda d: abs(d.get("f", 0) - f_in)) if drums_raw else None
        diff_f = (f_in - closest_drum["f"]) if closest_drum else 0
        diff_ms = round((diff_f / fps) * 1000, 1) if fps > 0 else 0.0

        shots_data.append({
            "index": idx,
            "id": s.get("id", f"shot_{idx:03d}"),
            "f_in": f_in,
            "f_out": f_out,
            "dur_frames": dur_f,
            "dur_seconds": round(dur_s, 3),
            "t_in": round(t_in, 3),
            "t_out": round(t_out, 3),
            "diff_frames": diff_f,
            "diff_ms": diff_ms
        })

    # 2. 提取波形与动作曲线
    waveform = extract_audio_envelope(str(video_p), 100)
    motion = extract_motion_curve(str(video_p), fps)

    drums_data = [{"t": round(d.get("t", 0.0), 3), "f": d.get("f", 0), "s": round(d.get("s", 0.5), 2)} for d in drums_raw]

    # 相对路径用于同一目录或子目录
    try:
        video_rel = video_p.relative_to(out_p.parent).as_posix()
    except Exception:
        video_rel = video_p.name

    payload = {
        "title": video_p.stem,
        "video_src": video_rel,
        "fps": fps,
        "total_frames": total_frames,
        "total_seconds": round(total_dur, 3),
        "shots": shots_data,
        "drums": drums_data,
        "waveform": waveform,
        "motion": motion
    }

    json_str = json.dumps(payload, ensure_ascii=False)

    html_code = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rhythm Inspector - {payload['title']}</title>
<style>
:root {{
  --bg: #090a0f;
  --surface: #12151e;
  --surface-2: #1b202e;
  --border: #262c3e;
  --primary: #3b82f6;
  --accent: #f59e0b;
  --danger: #ef4444;
  --drum: #fbbf24;
  --text: #f3f4f6;
  --text-muted: #8b92a5;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; user-select: none; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", sans-serif;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}
header {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 10px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}}
.title-area {{ display: flex; align-items: center; gap: 12px; }}
h1 {{ font-size: 15px; font-weight: 700; color: #fff; }}
.badge {{
  background: rgba(59, 130, 246, 0.12);
  color: #60a5fa;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(59, 130, 246, 0.25);
}}
.controls-area {{ display: flex; align-items: center; gap: 12px; }}
.btn-group {{ display: flex; gap: 6px; }}
button {{
  background: #202534;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  transition: all 0.15s;
}}
button:hover {{ background: #2a3144; color: #fff; }}
button.active {{
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
  font-weight: 600;
}}
.telemetry {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  font-weight: 700;
  color: #60a5fa;
  background: #0f121a;
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
}}

/* 视频播放主视口 */
.main-stage {{
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #000;
  position: relative;
  overflow: hidden;
  padding: 12px;
}}
.video-wrapper {{
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  min-width: 0;
  display: flex;
  justify-content: center;
  align-items: center;
}}
video {{
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.8);
  outline: none;
}}

/* 画面实时卡点状态浮层 */
.cut-flash-overlay {{
  position: absolute;
  top: 14px;
  left: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  pointer-events: none;
}}
.status-pill {{
  background: rgba(18, 21, 30, 0.88);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  padding: 5px 12px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.pill-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #10b981; }}
.hit-indicator {{
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(239, 68, 68, 0.9);
  color: #fff;
  font-size: 20px;
  font-weight: 800;
  padding: 10px 24px;
  border-radius: 10px;
  box-shadow: 0 0 32px rgba(239, 68, 68, 0.8);
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.08s ease-out;
}}

/* 走带式时间轴 */
.timeline-section {{
  background: var(--surface);
  border-top: 1px solid var(--border);
  height: 220px;
  display: flex;
  flex-direction: column;
  position: relative;
  flex-shrink: 0;
}}
.legend-bar {{
  height: 26px;
  padding: 0 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--text-muted);
  border-bottom: 1px solid rgba(255,255,255,0.04);
}}
.legend-group {{ display: flex; gap: 14px; align-items: center; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.color-dot {{ width: 8px; height: 8px; border-radius: 2px; }}

.scroller-box {{
  flex: 1;
  position: relative;
  background: #0b0d13;
  overflow: hidden;
  cursor: ew-resize;
}}
canvas#flowCanvas {{ width: 100%; height: 100%; display: block; }}

/* 中央瞄准游标 */
.center-playhead {{
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  background: #fff;
  box-shadow: 0 0 8px #3b82f6, 0 0 16px #3b82f6;
  pointer-events: none;
  transform: translateX(-50%);
  z-index: 10;
}}
.center-playhead::before {{
  content: "";
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 7px solid #fff;
}}
.center-playhead::after {{
  content: "";
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 7px solid #fff;
}}
</style>
</head>
<body>

<header>
  <div class="title-area">
    <h1>{payload['title']} · 卡点走带工作台</h1>
    <span class="badge">{payload['total_seconds']}s · {payload['total_frames']} 帧 · {len(shots_data)} 镜头</span>
    <span class="badge" style="color:#10b981; border-color:rgba(16,185,129,0.3);">{len(drums_data)} 处鼓点</span>
  </div>

  <div class="controls-area">
    <div class="btn-group">
      <button id="btnPlay" class="active">▶ 播放 (空格/K)</button>
      <button id="btnRate05">0.5x 慢放</button>
      <button id="btnRate1" class="active">1.0x 原速</button>
      <button id="btnZoomIn">放大 (+)</button>
      <button id="btnZoomOut">缩小 (-)</button>
    </div>
    <div class="telemetry">
      <span id="txtTime">00:00.000</span> · <span id="txtFrame">F0</span>
    </div>
  </div>
</header>

<div class="main-stage">
  <div class="video-wrapper">
    <video id="refVideo" src="{payload['video_src']}" playsinline preload="auto"></video>
    <div class="cut-flash-overlay">
      <div class="status-pill">
        <div class="pill-dot" id="pillDot"></div>
        <span id="curShotLabel">Shot #01 · 正在播放</span>
      </div>
      <div class="status-pill" style="font-size: 11px; color: var(--text-muted);">
        <span id="curRhythmStatus">离最近鼓点偏差: 0 帧</span>
      </div>
    </div>
    <div class="hit-indicator" id="hitIndicator">⚡ 镜头硬切点！</div>
  </div>
</div>

<div class="timeline-section">
  <div class="legend-bar">
    <div class="legend-group">
      <div class="legend-item"><div class="color-dot" style="background:#ef4444;"></div><b>红色竖线 = 切点</b>（到达中央白线瞬间画面切换）</div>
      <div class="legend-item"><div class="color-dot" style="background:#fbbf24;"></div><b>黄色发光圆点 = 音乐重音鼓点</b></div>
      <div class="legend-item"><div class="color-dot" style="background:#ec4899;"></div><b>粉红曲线 = 画面动作能量</b></div>
      <div class="legend-item"><div class="color-dot" style="background:#3b82f6;"></div><b>声学能量渐变波形</b></div>
    </div>
    <div>
      💡 快捷键：<b>空格/K</b> 播放/暂停 · <b>J/L</b> 倒放/快进 · <b>←/→</b> 逐帧 · <b>滚轮</b> 缩放时间轴
    </div>
  </div>

  <div class="scroller-box" id="scrollerBox">
    <canvas id="flowCanvas"></canvas>
    <div class="center-playhead"></div>
  </div>
</div>

<script>
const RHYTHM_DATA = {json_str};
const video = document.getElementById('refVideo');
const canvas = document.getElementById('flowCanvas');
const ctx = canvas.getContext('2d');
const scrollerBox = document.getElementById('scrollerBox');

const txtTime = document.getElementById('txtTime');
const txtFrame = document.getElementById('txtFrame');
const curShotLabel = document.getElementById('curShotLabel');
const curRhythmStatus = document.getElementById('curRhythmStatus');
const hitIndicator = document.getElementById('hitIndicator');
const pillDot = document.getElementById('pillDot');

const totalDur = RHYTHM_DATA.total_seconds;
const fps = RHYTHM_DATA.fps;
const totalFrames = RHYTHM_DATA.total_frames;
const shots = RHYTHM_DATA.shots;
const drums = RHYTHM_DATA.drums;
const env = RHYTHM_DATA.waveform;
const motion = RHYTHM_DATA.motion;

// 动态缩放比例：支持 60px/s 至 400px/s，默认 180px/s
let pixelsPerSecond = 180;

function resizeCanvas() {{
  canvas.width = scrollerBox.clientWidth * window.devicePixelRatio;
  canvas.height = scrollerBox.clientHeight * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  renderFrame();
}}
window.addEventListener('resize', resizeCanvas);

// 鼠标滚轮缩放时间轴
scrollerBox.addEventListener('wheel', (e) => {{
  e.preventDefault();
  const delta = e.deltaY < 0 ? 25 : -25;
  pixelsPerSecond = Math.max(60, Math.min(400, pixelsPerSecond + delta));
  renderFrame();
}}, {{ passive: false }});

document.getElementById('btnZoomIn').onclick = () => {{ pixelsPerSecond = Math.min(400, pixelsPerSecond + 30); renderFrame(); }};
document.getElementById('btnZoomOut').onclick = () => {{ pixelsPerSecond = Math.max(60, pixelsPerSecond - 30); renderFrame(); }};

function renderFrame() {{
  const w = scrollerBox.clientWidth;
  const h = scrollerBox.clientHeight;
  const curT = video.currentTime;
  const centerX = w / 2;

  ctx.clearRect(0, 0, w, h);

  // 1. 镜头切块条带 (上部，高度 34px)
  const shotBarY = 22;
  const shotBarH = 32;

  shots.forEach((s, idx) => {{
    const x1 = centerX + (s.t_in - curT) * pixelsPerSecond;
    const x2 = centerX + (s.t_out - curT) * pixelsPerSecond;
    if (x2 < 0 || x1 > w) return;

    const isCurrent = (curT >= s.t_in && curT < s.t_out);
    ctx.fillStyle = isCurrent ? 'rgba(59, 130, 246, 0.45)' : (idx % 2 === 0 ? 'rgba(30, 41, 59, 0.65)' : 'rgba(42, 53, 74, 0.45)');
    ctx.fillRect(x1, shotBarY, x2 - x1, shotBarH);

    ctx.strokeStyle = isCurrent ? '#60a5fa' : 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1;
    ctx.strokeRect(x1, shotBarY, x2 - x1, shotBarH);

    if (x2 - x1 > 28) {{
      ctx.fillStyle = isCurrent ? '#fff' : '#94a3b8';
      ctx.font = isCurrent ? 'bold 11px sans-serif' : '10px sans-serif';
      ctx.fillText('#' + s.index, x1 + 5, shotBarY + 20);
    }}
  }});

  // 2. 音频波形 (声学色彩渐变：青蓝 -> 金黄)
  const waveY = shotBarY + shotBarH + 6;
  const waveH = h - waveY - 12;
  const envLen = env.length;

  const grad = ctx.createLinearGradient(0, waveY + waveH, 0, waveY);
  grad.addColorStop(0, 'rgba(59, 130, 246, 0.4)');
  grad.addColorStop(0.7, 'rgba(56, 189, 248, 0.7)');
  grad.addColorStop(1, 'rgba(245, 158, 11, 0.9)');
  ctx.fillStyle = grad;

  const visibleStartTime = curT - (centerX / pixelsPerSecond);
  const visibleEndTime = curT + ((w - centerX) / pixelsPerSecond);
  const startIdx = Math.max(0, Math.floor(visibleStartTime * 100));
  const endIdx = Math.min(envLen - 1, Math.ceil(visibleEndTime * 100));

  for (let i = startIdx; i <= endIdx; i++) {{
    const t = i / 100.0;
    const x = centerX + (t - curT) * pixelsPerSecond;
    const val = env[i];
    const barH = val * waveH;
    ctx.fillRect(x, waveY + waveH - barH, Math.max(1.5, pixelsPerSecond / 100), barH);
  }}

  // 3. 画面动作运动量曲线 (粉红色)
  if (motion && motion.length) {{
    ctx.strokeStyle = '#ec4899';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let started = false;
    const mLen = motion.length;
    for (let i = 0; i < mLen; i++) {{
      const t = i / fps;
      if (t < visibleStartTime - 0.2 || t > visibleEndTime + 0.2) continue;
      const x = centerX + (t - curT) * pixelsPerSecond;
      const y = waveY + waveH - (motion[i] * waveH * 0.9);
      if (!started) {{ ctx.moveTo(x, y); started = true; }}
      else {{ ctx.lineTo(x, y); }}
    }}
    ctx.stroke();
  }}

  // 4. 重音鼓点 (黄色微发光圆点与垂线)
  drums.forEach(d => {{
    const x = centerX + (d.t - curT) * pixelsPerSecond;
    if (x < -10 || x > w + 10) return;

    ctx.strokeStyle = 'rgba(251, 191, 36, 0.35)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, waveY);
    ctx.lineTo(x, waveY + waveH);
    ctx.stroke();

    // 鼓点顶部微发光
    ctx.save();
    ctx.shadowColor = '#fbbf24';
    ctx.shadowBlur = 6;
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(x, waveY + 4, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }});

  // 5. 31/46 处切点硬切实线 (大红色贯穿粗线与顶部三角)
  shots.forEach(s => {{
    if (s.index > 1) {{
      const x = centerX + (s.t_in - curT) * pixelsPerSecond;
      if (x < -10 || x > w + 10) return;

      const isTight = Math.abs(curT - s.t_in) < 0.05;
      ctx.save();
      if (isTight) {{
        ctx.shadowColor = '#ef4444';
        ctx.shadowBlur = 12;
      }}
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = isTight ? 3.5 : 2.5;
      ctx.beginPath();
      ctx.moveTo(x, 4);
      ctx.lineTo(x, h - 4);
      ctx.stroke();

      ctx.fillStyle = '#ef4444';
      ctx.beginPath();
      ctx.moveTo(x - 5, 4);
      ctx.lineTo(x + 5, 4);
      ctx.lineTo(x, 12);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }}
  }});

  // 6. 顶部时间刻度
  const startSec = Math.floor(visibleStartTime);
  const endSec = Math.ceil(visibleEndTime);
  ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
  ctx.font = '10px monospace';
  for (let s = startSec; s <= endSec; s++) {{
    if (s >= 0 && s <= totalDur) {{
      const x = centerX + (s - curT) * pixelsPerSecond;
      ctx.fillRect(x, 0, 1, 6);
      ctx.fillText(s + 's', x + 3, 14);
    }}
  }}

  // 瞬时切镜高亮提醒
  let inCutZone = false;
  for (let s of shots) {{
    if (s.index > 1 && Math.abs(curT - s.t_in) < 0.06) {{
      inCutZone = true;
      break;
    }}
  }}
  hitIndicator.style.opacity = inCutZone ? '1' : '0';
}}

function updateLoop() {{
  renderFrame();

  const curT = video.currentTime;
  const curF = Math.round(curT * fps);

  const mm = String(Math.floor(curT / 60)).padStart(2, '0');
  const ss = String((curT % 60).toFixed(3)).padStart(6, '0');
  txtTime.textContent = mm + ':' + ss;
  txtFrame.textContent = 'F' + curF;

  const curShot = shots.find(s => curF >= s.f_in && curF < s.f_out) || shots[shots.length - 1];
  if (curShot) {{
    curShotLabel.textContent = `镜头 #${{String(curShot.index).padStart(2, '0')}} · ${{curShot.dur_seconds}}秒 (${{curShot.f_in}}–${{curShot.f_out}}帧)`;
    const diff = curShot.diff_frames;
    const sign = diff > 0 ? '+' : '';
    curRhythmStatus.textContent = `离最近鼓点偏差: ${{sign}}${{diff}} 帧 (${{sign}}${{curShot.diff_ms}} ms)`;
    pillDot.style.background = Math.abs(diff) <= 1 ? '#10b981' : (Math.abs(diff) <= 2 ? '#34d399' : '#f59e0b');
  }}

  requestAnimationFrame(updateLoop);
}}
requestAnimationFrame(updateLoop);

// 点击/拖拽时间线跳转
let isDragging = false;
function seekFromMouse(e) {{
  const rect = scrollerBox.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const deltaX = clickX - (rect.width / 2);
  const targetT = video.currentTime + (deltaX / pixelsPerSecond);
  video.currentTime = Math.max(0, Math.min(totalDur, targetT));
}}
scrollerBox.addEventListener('mousedown', (e) => {{ isDragging = true; seekFromMouse(e); }});
window.addEventListener('mousemove', (e) => {{ if (isDragging) seekFromMouse(e); }});
window.addEventListener('mouseup', () => {{ isDragging = false; }});

// 播放控制
const btnPlay = document.getElementById('btnPlay');
function togglePlay() {{
  if (video.paused) {{
    video.play();
    btnPlay.textContent = '⏸ 暂停 (空格/K)';
  }} else {{
    video.pause();
    btnPlay.textContent = '▶ 播放 (空格/K)';
  }}
}}
btnPlay.addEventListener('click', togglePlay);

function setSpeed(rate, activeBtn) {{
  video.playbackRate = rate;
  document.getElementById('btnRate05').classList.remove('active');
  document.getElementById('btnRate1').classList.remove('active');
  activeBtn.classList.add('active');
}}
document.getElementById('btnRate05').onclick = function() {{ setSpeed(0.5, this); }};
document.getElementById('btnRate1').onclick = function() {{ setSpeed(1.0, this); }};

// 经典 J/K/L 与快捷键支持
window.addEventListener('keydown', (e) => {{
  if (e.code === 'Space' || e.code === 'KeyK') {{
    e.preventDefault();
    togglePlay();
  }} else if (e.code === 'KeyJ') {{
    e.preventDefault();
    video.currentTime = Math.max(0, video.currentTime - 1.0);
  }} else if (e.code === 'KeyL') {{
    e.preventDefault();
    video.currentTime = Math.min(totalDur, video.currentTime + 1.0);
  }} else if (e.code === 'ArrowLeft') {{
    e.preventDefault();
    video.currentTime = Math.max(0, video.currentTime - (1 / fps));
  }} else if (e.code === 'ArrowRight') {{
    e.preventDefault();
    video.currentTime = Math.min(totalDur, video.currentTime + (1 / fps));
  }}
}});

resizeCanvas();
</script>
</body>
</html>
"""

    with open(out_p, "w", encoding="utf-8") as f:
        f.write(html_code)

    return str(out_p)
