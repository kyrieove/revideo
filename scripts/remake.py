"""普通快切与基础转场型的本地渲染：只读 events.json 的 shots 和素材，不读参考片。
用法：python tools/revideo/remake.py <events.json> <out.mp4> [--music <音频>] [--offset 秒] [--transition <类型:帧数>]
每镜 shots[i].material 是素材路径（视频或图片），可选 material_in（素材里的起点秒，默认 0）、
可选 transition（如 "fade:6" 或 {"type": "fade", "frames": 6}，表示进入本镜的 xfade 转场；"cut" 强制硬切）。
镜头长度 = end - start 帧，照搬参考片，转场需要的重叠帧自动向后延长/克隆补齐，总帧数与切点绝不漂移。
音乐优先 --music（默认 offset 0），其次 music.song + song_offset，最后 events.ref 原声（默认 offset 0）；--offset 覆盖起点。"""
import argparse, json, math, os, subprocess, tempfile
from fractions import Fraction
from pathlib import Path


def parse_trans(spec):
    if not spec or spec in ('cut', 'none', 'hard'):
        return None, 0
    if isinstance(spec, dict):
        return spec.get('type', 'fade'), int(spec.get('frames', 6))
    if ':' in str(spec):
        t, d = str(spec).split(':', 1)
        return t, int(d)
    return str(spec), 6


def probe(path, count=False):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', *(['-count_frames'] if count else []),
        '-show_streams', '-show_format', '-of', 'json', str(path)]))


def validate_timeline(ev):
    frames, fps = ev['frames'], ev['fps']
    if type(frames) is not int or frames <= 0 or not math.isfinite(fps) or fps <= 0:
        raise ValueError('frames 必须为正整数，fps 必须有限且为正')
    rate = Fraction(ev['fps_str'])
    if rate <= 0 or not math.isclose(float(rate), fps, rel_tol=1e-9):
        raise ValueError('fps 与 fps_str 不一致')
    shots = ev['shots']
    if not shots:
        raise ValueError('shots 不能为空')
    ids, end = set(), 0
    for s in shots:
        if type(s['id']) is not int or s['id'] in ids:
            raise ValueError('镜头 ID 必须为唯一整数')
        ids.add(s['id'])
        if type(s['start']) is not int or type(s['end']) is not int or s['start'] != end or s['end'] <= end:
            raise ValueError('镜头须从 0 起连续覆盖，区间必须为正整数帧')
        end = s['end']
        if not math.isfinite(s.get('material_in', 0)) or s.get('material_in', 0) < 0:
            raise ValueError('material_in 必须有限且非负')
    if end != frames:
        raise ValueError(f'镜头覆盖 {end} 帧，与 frames={frames} 不一致')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('events'); ap.add_argument('out')
    ap.add_argument('--music'); ap.add_argument('--offset', type=float)
    ap.add_argument('--transition', help='全局默认转场，如 fade:6 或 wipeleft:4（shots[i].transition 可单独覆盖）')
    o = ap.parse_args()
    ev = json.load(open(o.events, encoding='utf-8'))
    validate_timeline(ev)
    base = Path(o.events).resolve().parent
    def resolve(path):
        p = Path(path)
        return str(p if p.is_absolute() else base / p)
    for shot in ev['shots']:
        if shot.get('material'):
            shot['material'] = resolve(shot['material'])
    m = ev.get('music') or {}
    music = o.music or m.get('song') or ev.get('ref')
    if not music:
        raise ValueError('没有音源：需要 --music、music.song 或带音轨的 events.ref')
    music = str(Path(o.music).resolve()) if o.music else resolve(music)
    off = o.offset if o.offset is not None else (m.get('song_offset') or 0) if not o.music and m.get('song') else 0
    if not math.isfinite(off) or off < 0:
        raise ValueError('音轨起点必须有限且非负')
    dur = ev['frames'] / ev['fps']
    audio = [s for s in probe(music)['streams'] if s['codec_type'] == 'audio']
    if not audio:
        raise ValueError(f'音源没有音轨：{music}')
    available = float(audio[0].get('duration', 'nan'))
    if not math.isfinite(available) or available + 0.001 < off + dur:
        raise ValueError(f'音源不足或无法确认时长：需要 {off + dur:.4f} 秒，实际 {available}')
    W, H = ev['size']
    fr, fps = ev['fps_str'], float(ev['fps'])
    shots = ev['shots']
    missing = [f"#{s['id']}[role: {s.get('role') or '未填'}]" for s in shots if not s.get('material')]
    if missing:
        raise SystemExit(f"这些镜头还没有素材：{', '.join(missing)}")
    tmp = tempfile.mkdtemp(prefix='revideo_')

    # in_trans[i] = 进入第 i 镜的转场 (type, frames)，首镜无进入转场
    in_trans = [(None, 0)]
    for i in range(1, len(shots)):
        raw = shots[i].get('transition') if 'transition' in shots[i] else o.transition
        t_type, d = parse_trans(raw)
        max_d = min(shots[i - 1]['end'] - shots[i - 1]['start'], shots[i]['end'] - shots[i]['start']) - 1
        d = max(0, min(d, max_d)) if t_type else 0
        in_trans.append((t_type if d > 0 else None, d))

    raw_parts = []
    for i, s in enumerate(shots):
        n = s['end'] - s['start']
        d_next = in_trans[i + 1][1] if i + 1 < len(shots) else 0
        want_n = n + d_next
        p = os.path.join(tmp, f"{s['id']:03d}.mkv")
        src = s['material']
        is_img = os.path.splitext(src)[1].lower() in ('.jpg', '.jpeg', '.png', '.webp')
        inp = ['-loop', '1', '-framerate', fr, '-i', src] if is_img else ['-ss', str(s.get('material_in', 0)), '-i', src]
        vf = f'fps={fr},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1'
        if d_next > 0 and not is_img:
            vf += f',tpad=stop_mode=clone:stop={d_next}'
        # 无损中间件，避免逐镜重编码把 SSIM 拉低
        subprocess.run(['ffmpeg', '-v', 'error', '-y', *inp, '-vf', vf, '-frames:v', str(want_n), '-an',
                        '-c:v', 'ffv1', '-pix_fmt', 'yuv420p', p], check=True)
        got = int(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                                           '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', p]))
        if got != want_n:
            raise SystemExit(f"第 {s['id']} 镜素材不够长：要 {n} 帧，只有 {got - d_next} 帧（{src}）")
        raw_parts.append(p)

    # 按硬切（in_trans[i].frames == 0）拆成连续段，段内有转场时用 xfade 合成段文件
    chains = [[0]]
    for i in range(1, len(shots)):
        if in_trans[i][1] > 0:
            chains[-1].append(i)
        else:
            chains.append([i])

    parts = []
    for ci, ch in enumerate(chains):
        if len(ch) == 1:
            parts.append(raw_parts[ch[0]])
            continue
        cp = os.path.join(tmp, f'chain_{ci:03d}.mkv')
        inps, fc, cur = [], [], '[0:v]'
        start_0 = shots[ch[0]]['start']
        for k, idx in enumerate(ch):
            inps += ['-i', raw_parts[idx]]
            if k == 0:
                continue
            t_type, d = in_trans[idx]
            trans_off = (shots[idx]['start'] - start_0) / fps
            trans_dur = d / fps
            nxt = f'[v{k}]'
            fc.append(f'{cur}[{k}:v]xfade=transition={t_type}:duration={trans_dur:.6f}:offset={trans_off:.6f}{nxt}')
            cur = nxt
        subprocess.run(['ffmpeg', '-v', 'error', '-y', *inps, '-filter_complex', ';'.join(fc),
                        '-map', cur, '-an', '-c:v', 'ffv1', '-pix_fmt', 'yuv420p', cp], check=True)
        parts.append(cp)

    lst = os.path.join(tmp, 'list.txt')
    open(lst, 'w', encoding='utf-8').write(''.join(f"file '{p}'\n" for p in parts))

    aud = ['-ss', f'{off:.8f}', '-t', f'{dur:.8f}', '-i', music]
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, *aud,
                    '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac', '-b:a', '256k',
                    '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', '-r', fr, o.out], check=True)
    measured = probe(o.out, count=True)
    video = next(s for s in measured['streams'] if s['codec_type'] == 'video')
    audio_out = next((s for s in measured['streams'] if s['codec_type'] == 'audio'), None)
    got = int(video['nb_read_frames'])
    if (got != ev['frames'] or Fraction(video['avg_frame_rate']) != Fraction(fr)
            or abs(float(video['duration']) - dur) > 1 / fps
            or audio_out is None or abs(float(audio_out.get('duration', 'nan')) - dur) > 1 / fps
            or not math.isfinite(float(audio_out.get('duration', 'nan')))):
        raise ValueError(f'渲染后验收失败：声明 {ev["frames"]} 帧，实际 {got} 帧；音视频时长须在 1 帧内一致')
    print(o.out, len(shots), '镜', got, '帧，音视频时长核对通过')


if __name__ == '__main__':
    main()
