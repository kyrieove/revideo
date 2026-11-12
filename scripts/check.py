"""给 events.json 打分。不过时退出码 1。
  python tools/revideo/check.py score <events.json> <golden 键>   切点/事件召回（±1 帧，一对一）、多报切点、鼓点漏检（原片本来不卡鼓的事件只列出）
  python tools/revideo/check.py ssim <ref.mp4> <remake.mp4>       逐帧 SSIM，全部 ≥ 0.9 且帧数与参考片相同才过
  python tools/revideo/check.py side <ref.mp4> <remake.mp4> <out.mp4>   左右并排对比片（音轨用新片）
  python tools/revideo/check.py energy <events.json> <ref.mp4> <remake.mp4> <out.svg> [参考起始帧]   逐镜能量曲线，亮度或运动量和参考片逐镜相关 ≤ 0 算 FAIL，见 effects.py
  python tools/revideo/check.py identity <events.json> <ref.mp4> <out_dir> <golden 键>
      原样复刻：按标准答案的切点把参考片切成每镜素材（尾部冻结 3 帧，模拟素材比镜头长），
      再按 events.json 测出的镜头长度渲染、比逐帧 SSIM。测错的切点会让那几帧对不上，所以这条能验证检测；
      没有标准答案的新片做不了这条验证。
  python tools/revideo/check.py review <events.json>              参考复核记录完整性
  python tools/revideo/check.py strips ...                        参考/成片帧条，见 strips.py
  python tools/revideo/check.py anchors ...                       动作阶段帧差，见 anchors.py
  python tools/revideo/check.py scorecard <score.json> [--baseline]  盲审评分表，见 scorecard.py
  python tools/revideo/check.py loudness <ref.mp4> <out.mp4>      I/Peak/ΔI，不预设阈值"""
import argparse, json, os, re, subprocess, sys
from fractions import Fraction

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DRUM_ENV = 0.15


def golden(key):
    return json.load(open(os.path.join(HERE, 'golden.json'), encoding='utf-8'))[key]


def match(found, gold, tol=1):
    """一对一配对：两边都按帧号排好，每个标准答案认领最早一个还没被用、且在 ±tol 内的检测（一维区间匹配，这样配数最多）。
    返回 (命中的标准答案, 没配上的检测)，重复的检测各算一个。"""
    fs = sorted(found)
    used = [False] * len(fs)
    hit = []
    for g in sorted(gold):
        j = next((k for k, f in enumerate(fs) if not used[k] and g - tol <= f <= g + tol), None)
        if j is not None:
            used[j] = True; hit.append(g)
    return hit, [f for f, u in zip(fs, used) if not u]


assert match([99, 100, 101], [100]) == ([100], [100, 101])
assert match([99, 100], [100, 101]) == ([100, 101], [])
assert match([100, 100], [100]) == ([100], [100])


def score(ev_path, key):
    ev = json.load(open(ev_path, encoding='utf-8'))
    gold = golden(key)
    ok = True
    cuts = [e['f'] for e in ev['events'] if e['kind'] == 'cut']
    allf = [e['f'] for e in ev['events']]
    if 'cuts' in gold:
        hit, extra = match(cuts, gold['cuts'])
        r = len(hit) / len(gold['cuts'])
        print(f'切点召回 {len(hit)}/{len(gold["cuts"])} = {r:.0%}  多报 {extra}  漏 {sorted(set(gold["cuts"]) - set(hit))}')
        ok &= r >= 0.95 and len(extra) <= 1
    if 'events' in gold:
        hit, extra = match(allf, gold['events'])
        r = len(hit) / len(gold['events'])
        mainf = [e['f'] for e in ev['events'] if e.get('tier', 'main') == 'main']
        m_hit, m_extra = match(mainf, gold['events'])
        tier_msg = f'（主事件 {len(mainf)} 个：召回 {len(m_hit)}/{len(gold["events"])}，另报 {len(m_extra)} 个；次要/噪波 {len(allf) - len(mainf)} 个）' if len(mainf) != len(allf) else ''
        print(f'事件召回 {len(hit)}/{len(gold["events"])} = {r:.0%}  漏 {sorted(set(gold["events"]) - set(hit))}  '
              f'另报 {len(extra)} 个（这份标准答案只列了部分真事件，另报的要看图，不计入判定）{tier_msg}')
        ok &= r >= 0.95
    # 离最近鼓点 >2 帧的事件分两种：±1 帧内打击乐包络强（≥ DRUM_ENV）却没测到鼓点 = 鼓点漏检，算 FAIL；
    # 包络弱 = 原片那一帧本来没鼓（原片不卡鼓），照搬帧号即可，只列出来。
    # shortcut: DRUM_ENV=0.15 是看 tanyb 277 帧（0.06）和它两侧真鼓（0.25）定的，碰到误判再调
    # 连续运动段里的非切点事件不按单帧卡点，不查鼓点
    far = [e for e in ev['events'] if abs(e['drum_dt']) > 2
           and (e['kind'] == 'cut' or not any(a <= e['f'] <= b for a, b in ev.get('continuous', [])))]
    missed = [(e['f'], e['drum_dt'], e.get('drum_env', 0.0)) for e in far if e.get('drum_env', 0.0) >= DRUM_ENV]
    off = [(e['f'], e['drum_dt']) for e in far if e.get('drum_env', 0.0) < DRUM_ENV]
    n = len(ev['events'])
    print(f'离鼓点 ≤2 帧：{n - len(far)}/{n}')
    print(f'  原片这里没鼓（±1 帧包络 < {DRUM_ENV}，照搬即可）：{off}')
    print(f'  鼓点漏检（包络强却没测到鼓点）：{missed}')
    ok &= not missed
    print('PASS' if ok else 'FAIL')
    return ok


def ssim(ref, new):
    def timing(path):
        stream = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_read_frames,avg_frame_rate,r_frame_rate,time_base',
            '-of', 'json', path]))['streams'][0]
        return (int(stream['nb_read_frames']), Fraction(stream['avg_frame_rate']),
                Fraction(stream['r_frame_rate']), Fraction(stream['time_base']))
    rt, nt = timing(ref), timing(new)
    want = rt[0]
    if want <= 0 or rt[:3] != nt[:3] or rt[1] != rt[2] or rt[3] <= 0 or nt[3] <= 0:
        print(f'FAIL 帧数/帧率不一致或非 CFR：参考 {rt}，复刻 {nt}')
        return False
    # 容器 time_base 可不同；按已核对的 CFR 帧号重建共同时间轴，禁止末帧重复。
    filters = (f'[0:v]settb=AVTB,setpts=N/({rt[1]})/TB[a];'
               f'[1:v]settb=AVTB,setpts=N/({rt[1]})/TB[b];'
               '[a][b]ssim=stats_file=-:shortest=1:repeatlast=0')
    p = subprocess.run(['ffmpeg', '-v', 'info', '-i', new, '-i', ref, '-lavfi', filters, '-f', 'null', '-'],
                       capture_output=True, text=True, errors='ignore')
    v = np.array([float(x) for x in re.findall(r'All:([0-9.]+)', p.stdout)])
    if p.returncode or len(v) != want:
        print(f'FAIL ffmpeg 退出码 {p.returncode}，比了 {len(v)} 帧，参考片 {want} 帧')
        return False
    bad = np.nonzero(v < 0.9)[0].tolist()
    print(f'{len(v)} 帧  SSIM 中位 {np.median(v):.4f}  最低 {v.min():.4f}（第 {int(v.argmin())} 帧）  低于 0.9：{bad[:40]}')
    print('PASS' if not bad else 'FAIL')
    return not bad


def side(ref, new, out):
    win_font = os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts', 'arial.ttf')
    ff = f"fontfile='{win_font.replace(':', chr(92) + ':')}':" if os.path.exists(win_font) else ''
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', ref, '-i', new, '-filter_complex',
                    f'[0:v]scale=-2:720,drawtext={ff}text=REF %{{n}}:x=10:y=10:fontsize=28:fontcolor=yellow:box=1:boxcolor=black[a];'
                    f'[1:v]scale=-2:720,drawtext={ff}text=NEW %{{n}}:x=10:y=10:fontsize=28:fontcolor=yellow:box=1:boxcolor=black[b];'
                    '[a][b]hstack[v]', '-map', '[v]', '-map', '1:a?', '-c:v', 'libx264', '-crf', '20', '-c:a', 'aac', '-shortest', out],
                   check=True)
    print(out)


def negative(*args):
    """negative --control-json '[验证器, 正常输入]' --fail-marker 标记 [--expect-code 1] -- 验证器 缺陷输入。
    正向控制须成功，负向须同时匹配失败码和明确标记；裸非零退出不再作为证据。"""
    ap = argparse.ArgumentParser(description=negative.__doc__)
    ap.add_argument('--control-json', required=True)
    ap.add_argument('--fail-marker', required=True)
    ap.add_argument('--expect-code', type=int, default=1)
    ap.add_argument('command', nargs=argparse.REMAINDER)
    o = ap.parse_args(args)
    control = json.loads(o.control_json)
    cmd = o.command[1:] if o.command[:1] == ['--'] else o.command
    if (not isinstance(control, list) or not control or not all(isinstance(x, str) for x in control)
            or not cmd or o.expect_code in (0, 2) or o.expect_code < 0 or not o.fail_marker.strip()):
        ap.error('需要正向命令、负向命令、明确失败标记及非 0/2 的验收失败码')
    try:
        positive = subprocess.run(control, capture_output=True, text=True, errors='replace')
        p = subprocess.run(cmd, capture_output=True, text=True, errors='replace') if positive.returncode == 0 else None
    except OSError as exc:
        print(f'FAIL 验证器无法启动：{exc}')
        return False
    if p is None or p.returncode != o.expect_code or o.fail_marker not in p.stdout:
        print(f'FAIL 负向证据无效：正向退出 {positive.returncode}，负向退出 {p.returncode if p else "未执行"}')
        return False
    print(f'PASS 负向门禁：正向控制通过，负向匹配退出码 {p.returncode} 和标记 {o.fail_marker!r}')
    return True


def luma_drift(film_path, raw_path, film_t, raw_t, max_mae=3.0, crop=None):
    """通用黑位色阶漂移检测：在指定时刻抽检成片与原素材基准帧的最小 MAE 误差，超标算 FAIL。"""
    max_mae = float(max_mae)
    def extract_film(path, t):
        p = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-t', '0.04', '-i', path,
                            '-vf', 'scale=480:270,fps=30', '-frames:v', '1', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'],
                           capture_output=True, check=True)
        return np.frombuffer(p.stdout, np.uint8).reshape(270, 480).astype(np.float32)

    def extract_raw_bank(path, t):
        vf = f"{crop}," if crop else ""
        vf += "scale=480:270,fps=60"
        # 抽取 0.1 秒窗口 (约 6 帧) 消除 60fps-30fps 对齐相位误差
        p = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-t', '0.1', '-i', path,
                            '-vf', vf, '-pix_fmt', 'gray', '-f', 'rawvideo', '-'],
                           capture_output=True, check=True)
        return np.frombuffer(p.stdout, np.uint8).reshape(-1, 270, 480).astype(np.float32)

    im_film = extract_film(film_path, film_t)
    bank_raw = extract_raw_bank(raw_path, raw_t)
    errors = np.abs(bank_raw - im_film).mean(axis=(1, 2))
    best_idx = int(np.argmin(errors))
    mae = float(errors[best_idx])
    ok = mae <= max_mae
    print(f"{'PASS' if ok else 'FAIL'} [色阶漂移] MAE={mae:.2f} (offset={best_idx}/60s, 门限 <= {max_mae})")
    return ok


def identity(ev_path, ref, out_dir, key):
    os.makedirs(out_dir, exist_ok=True)
    ev = json.load(open(ev_path, encoding='utf-8'))
    truth = [0] + golden(key)['cuts'] + [ev['frames']]
    if len(truth) - 1 != len(ev['shots']):
        print(f"FAIL 测出 {len(ev['shots'])} 镜，标准答案 {len(truth) - 1} 镜")
        return False
    for s, a, b in zip(ev['shots'], truth, truth[1:]):
        p = os.path.join(out_dir, f"{s['id']:03d}.mkv")
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', ref, '-vf',
                        f"select='between(n,{a},{b - 1})',setpts=N/FRAME_RATE/TB,tpad=stop_mode=clone:stop=3",
                        '-an', '-c:v', 'ffv1', p], check=True)
        s['material'], s['material_in'] = p, 0
    idj, out = os.path.join(out_dir, 'events.identity.json'), os.path.join(out_dir, 'identity.mp4')
    json.dump(ev, open(idj, 'w', encoding='utf-8'), ensure_ascii=False)
    subprocess.run([sys.executable, os.path.join(HERE, 'remake.py'), idj, out, '--music', ref], check=True)
    return ssim(ref, out)


def _loudness(path):
    r = subprocess.run(['ffmpeg', '-nostats', '-hide_banner', '-i', path, '-af', 'ebur128=peak=true',
                        '-f', 'null', '-'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    tail = r.stderr[r.stderr.rfind('Summary:'):] if r.returncode == 0 else ''
    i, p = re.search(r'I:\s*(-?[\d.]+) LUFS', tail), re.search(r'Peak:\s*(-?[\d.]+) dBFS', tail)
    return (float(i.group(1)), float(p.group(1))) if i and p else None


def loudness(ref, out):
    """只报数字；成片没有独立原声轨时不下 6–12 dB 判定。"""
    a, b = _loudness(ref), _loudness(out)
    if a is None or b is None:
        print('FAIL_LOUDNESS 无法测量（缺音轨或 ffmpeg 失败）')
        return False
    print(f'参考 I={a[0]:.1f} LUFS  Peak={a[1]:.1f} dBFS')
    print(f'成片 I={b[0]:.1f} LUFS  Peak={b[1]:.1f} dBFS  ΔI={b[0] - a[0]:+.1f} LU')
    streams = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index',
                              '-of', 'csv=p=0', out], capture_output=True, text=True).stdout.split()
    if len(streams) < 2:
        print('INFO 成片只有 1 条音轨，无法分离原声与音乐；只报数字')
    if a[1] > 0:
        print(f'WARN_LOUDNESS 参考片峰值 {a[1]:+.1f} dBFS 超过 0 dBFS，需换音源或限幅')
    print('PASS_LOUDNESS 已测量')
    return True


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    if cmd == 'review':
        from reference_review import check
        sys.exit(0 if check(*a) else 1)
    if cmd in ('compare', 'energy'):  # 逐帧画像对比、逐镜能量曲线，见 effects.py
        sys.exit(subprocess.call([sys.executable, os.path.join(HERE, 'effects.py'), cmd, *a]))
    if cmd == 'strips':
        sys.exit(subprocess.call([sys.executable, os.path.join(HERE, 'strips.py'), *a]))
    if cmd in ('anchors', 'scorecard'):
        sys.exit(subprocess.call([sys.executable, os.path.join(HERE, f'{cmd}.py'), *a]))
    fn = {'score': score, 'ssim': ssim, 'side': side, 'identity': identity,
          'negative': negative, 'luma_drift': luma_drift, 'loudness': loudness}[cmd]
    sys.exit(0 if fn(*a) is not False else 1)
