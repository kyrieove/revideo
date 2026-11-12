"""逐帧拆参考片，写统一事件表 events.json（格式见 ~/.claude/skills/revideo/SKILL.md）。
用法：python tools/revideo/analyze.py <ref.mp4> <out_dir> [--rea <breakdown.json>] [--song <整首歌>]
  --rea   rea-video decompose 的 breakdown.json，切点以它为准，PySceneDetect 只做对照
  --song  原声出自的整首歌，算出参考片音轨在歌里的起点（song_offset）
事件帧只报告离鼓点多远，绝不吸附到拍点上：原片画面常比鼓点早 1 帧，这本身要照搬。"""
import argparse, json, os, subprocess

import cv2
import librosa
import numpy as np
from scipy.signal import find_peaks

from reference_review import attach, has_review

SW = 192          # 测量用的缩小宽度
DIFF_T = 18       # 像素亮度变化超过这个值算「变了」（0–255）


def probe(v):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                   'stream=width,height,r_frame_rate,avg_frame_rate,nb_frames', '-of', 'json', v])
    s = json.loads(out)['streams'][0]
    if s['r_frame_rate'] != s['avg_frame_rate']:
        raise SystemExit(f"可变帧率 {s['r_frame_rate']} vs {s['avg_frame_rate']}：先 ffmpeg -fps_mode cfr 转恒定帧率再拆")
    a, b = map(int, s['r_frame_rate'].split('/'))
    return s['width'], s['height'], a / b, s['r_frame_rate']


def gray_frames(v, w, h):
    sh = round(h * SW / w / 2) * 2
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', v, '-vf', f'scale={SW}:{sh}', '-fps_mode', 'passthrough',
                          '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, sh, SW).astype(np.int16)


def change_signal(g):
    """每帧相对上一帧：变化面积占比、变化区外接框（缩小坐标）。"""
    area, boxes, peak = np.zeros(len(g)), [None] * len(g), np.zeros(len(g))
    for i in range(1, len(g)):
        d = np.abs(g[i] - g[i - 1])
        peak[i] = d.max()
        m = (d > DIFF_T).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        area[i] = m.mean()
        if m.any():
            boxes[i] = cv2.boundingRect(m)
    return area, boxes, peak


def detect_events(area, peak):
    """三种事件帧：
    尖峰 = 比前后几帧都明显高的单帧变化；
    起动 = 静止 ≥3 帧后第一帧变化（淡入淡出、甩镜头这类多帧过渡的起点，小主体也能抓到）；
    持续高的段落 = 连续运动（扫光、推拉），段内的尖峰不当事件。"""
    base = np.array([np.median(np.r_[area[max(0, i - 4):i], area[i + 1:i + 5]]) for i in range(len(area))])
    score = area / (base + 0.003)
    peaks, _ = find_peaks(score, height=4, distance=2)
    peaks = [int(p) for p in peaks if area[p] > 0.004]
    moving = base > 0.02                       # 前后几帧本身就在变
    cont, s = [], None
    for i, m in enumerate(np.r_[moving, False]):
        if m and s is None: s = i
        if not m and s is not None:
            if i - s >= 6: cont.append([s, i - 1])
            s = None
    still = peak < DIFF_T
    onsets = [i for i in range(3, len(peak)) if not still[i] and still[i - 3:i].all()]
    return peaks, onsets, cont, score


def scenedetect_cuts(v):
    from scenedetect import detect, AdaptiveDetector
    return [a.frame_num for a, _ in detect(v, AdaptiveDetector(min_scene_len=4))][1:]


def drums(v, fps):
    """HPSS 打击乐成分的起音峰。返回 (BPM, [{f, t, s}], env_at)：
    f 按 round(t*fps)，s 是 0–1 强度；env_at(f) = 视频第 f 帧 ±1 帧内打击乐包络的最大值（相对全片最大，0–1）。"""
    y, sr = librosa.load(audio_wav(v), sr=22050, mono=True)
    _, perc = librosa.effects.hpss(y)
    env = librosa.onset.onset_strength(y=perc, sr=sr, hop_length=256)
    env = env / (env.max() or 1)
    tt = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=256)
    # ±1 帧：只问「这一帧本身有没有鼓」；±2 会把隔壁那下鼓的峰框进来（尼康 26 帧）
    env_at = lambda f: round(float(env[(tt >= (f - 1) / fps) & (tt <= (f + 1) / fps)].max(initial=0)), 2)
    on = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=256, units='frames')
    tempo = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=sr)[0])[0])
    if len(on) == 0:
        return round(tempo, 1), [], env_at
    t = librosa.frames_to_time(on, sr=sr, hop_length=256)
    s = env[on] / (env[on].max() or 1)
    return round(tempo, 1), [{'f': int(round(x * fps)), 't': round(float(x), 3), 's': round(float(k), 2)}
                             for x, k in zip(t, s)], env_at


def audio_wav(src):
    """librosa 读不了 mp4，先抽成 wav（放在源文件旁的缓存里）。"""
    if src.lower().endswith('.wav'):
        return src
    out = src + '.revideo.wav'
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-vn', '-ac', '1', '-ar', '22050', out], check=True)
    return out


def song_offset(clip, song):
    """参考片音轨在整首歌里的起点：整段波形归一化互相关（按歌里每个窗口的能量归一）。
    tanyb 原声：13.15 s 处相关 0.98，燕云 render 里记的 59.6 s 处只有 0.55。
    返回 (秒, 相关系数)；相关 < 0.9 说明歌的版本不对，别用。"""
    from scipy.signal import fftconvolve
    sr = 22050
    a, _ = librosa.load(audio_wav(clip), sr=sr)
    b, _ = librosa.load(audio_wav(song), sr=sr)
    c = fftconvolve(b, a[::-1], 'valid')
    e = np.sqrt(np.maximum(fftconvolve(b ** 2, np.ones(len(a)), 'valid'), 0)) * np.linalg.norm(a)
    r = c / (e + 1e-9)
    best = int(np.argmax(r))
    return round(best / sr, 4), round(float(r[best]), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('out')
    ap.add_argument('--rea'); ap.add_argument('--song')
    o = ap.parse_args()
    os.makedirs(o.out, exist_ok=True)
    W, H, fps, fps_str = probe(o.video)
    g = gray_frames(o.video, W, H)
    n, k = len(g), W / SW
    area, boxes, peak = change_signal(g)
    peaks, onsets, cont, score = detect_events(area, peak)

    sd = scenedetect_cuts(o.video)
    if o.rea:
        cuts = [s['start_frame'] for s in json.load(open(o.rea, encoding='utf-8'))['shots']][1:]
        cut_src = 'rea-video'
    else:
        cuts, cut_src = sd, 'scenedetect'
    tempo, dr, env_at = drums(o.video, fps)
    df = np.array([d['f'] for d in dr]) if dr else np.array([10 ** 9])

    bounds = [0] + cuts + [n]
    shot_of = lambda f: next(j for j in range(len(bounds) - 1) if bounds[j] <= f < bounds[j + 1]) + 1
    strong = set(peaks) | set(cuts)
    events = []
    for f in sorted(strong | set(onsets)):
        if f not in strong and (f - 1 in strong or f + 1 in strong):
            continue
        if any(a < f <= b for a, b in cont) and f not in cuts and f not in onsets:
            continue
        j = int(np.argmin(np.abs(df - f)))
        b = boxes[f]
        kind = 'cut' if f in cuts else 'onset' if f in onsets and f not in peaks else 'change'
        ar, sc, dt, env = round(float(area[f]), 3), round(float(score[f]), 2), int(f - df[j]), env_at(f)
        is_main = kind == 'cut' or (abs(dt) <= 2 and (ar >= 0.024 or env >= 0.4) and not (ar < 0.024 and 0 < sc < 6.0))
        events.append({'f': f, 't': round(f / fps, 3), 'kind': kind, 'tier': 'main' if is_main else 'sub',
                       'area': ar, 'score': sc,
                       'box': [round(x * k) for x in b] if b else None,
                       'drum_f': int(df[j]), 'drum_dt': dt, 'drum_s': dr[j]['s'] if dr else None,
                       'drum_env': env,
                       'shot': shot_of(f), 'role': ''})

    off = song_offset(o.video, o.song) if o.song else None
    doc = {
        'version': 1, 'ref': os.path.abspath(o.video), 'fps': fps, 'fps_str': fps_str, 'frames': n, 'size': [W, H],
        'tools': tool_versions(),
        'music': {'bpm': tempo, 'drums': dr, 'song': o.song and os.path.abspath(o.song),
                  'song_offset': off and off[0], 'song_corr': off and off[1]},
        'cuts_from': cut_src, 'cuts_scenedetect': sd,
        'shots': [{'id': j + 1, 'start': a, 'end': b, 'source': 'local', 'material': None, 'role': ''}
                  for j, (a, b) in enumerate(zip(bounds, bounds[1:]))],
        'events': events, 'continuous': cont, 'tracks': {},
    }
    try:
        attach(doc, o.out, o.rea)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        ap.exit(1, f'FAIL_REFERENCE_REVIEW {exc}\n')
    events_path = os.path.join(o.out, 'events.json')
    if os.path.exists(events_path):
        try:
            with open(events_path, encoding='utf-8') as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = {}
        if has_review(old):
            ap.exit(1, 'FAIL_REFERENCE_REVIEW 已有参考复核记录，拒绝覆盖；先备份移走 events.json 再重新分析\n')
    json.dump(doc, open(events_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    np.savetxt(os.path.join(o.out, 'change.txt'), np.c_[np.arange(n), area, score], fmt=['%d', '%.4f', '%.2f'],
               header='frame area score')
    only_rea = sorted(set(cuts) - set(sd)) if o.rea else []
    only_sd = sorted(set(sd) - set(cuts)) if o.rea else []
    main_n = sum(1 for e in events if e['tier'] == 'main')
    print(f'{n} 帧 {fps_str}  切点 {len(cuts)}（{cut_src}）  事件 {len(events)}（主 {main_n} / 次 {len(events) - main_n}）  连续段 {cont}')
    if o.rea:
        print(f'  切点分歧：只有 rea-video {only_rea}  只有 scenedetect {only_sd}')
    print(f'  BPM {tempo}  鼓点 {len(dr)}' + (f'  song_offset {off[0]} s（相关 {off[1]}）' if off else ''))


def tool_versions():
    v = {'librosa': librosa.__version__, 'opencv': cv2.__version__}
    try:
        import scenedetect; v['scenedetect'] = scenedetect.__version__
    except ImportError:
        pass
    try:
        r = subprocess.run(['uv', 'tool', 'list', '--show-version-specifiers'], capture_output=True, text=True)
        v['rea-video'] = next((l.strip() for l in r.stdout.splitlines() if l.startswith('rea-video')), None)
    except OSError:
        pass
    return v


if __name__ == '__main__':
    main()
