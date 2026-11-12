"""参考片与复刻的逐帧画像对比：清晰度凹陷、停帧、运动量、非黑内容范围。

analyze.py 只找切点和鼓点；连续转场、每圈结尾的模糊动效、补帧留下的停帧、素材被裁切这几类差别它看不见，
这里补上。每帧缩到 480 宽后算三个量：
  sharp   Laplacian 方差；与前后 10 帧中位数的比值 < 0.6 的帧是「凹陷」（模糊、闪白、转场特效）
  motion  与上一帧的平均绝对差；比前后帧都低一半以上的单帧是「停帧」（内容没更新）
  extent  亮度 > 30 的像素的外接框面积占画面比例（内容被裁切会缩小）

用法:
  effects.py dips  video.mp4 [起始帧] [帧数]        列出凹陷帧段和停帧，先看图再往下做
  effects.py compare ref.mp4 out.mp4 [参考起始帧] [帧数]   逐项对比，缺少参考片里的凹陷 / 内容范围缩水算 FAIL，清晰度不到一半只 WARN
  effects.py energy events.json ref.mp4 out.mp4 out.svg [参考起始帧]   逐镜亮度、运动量、景别、drum_env 的参考/成片对比图
  effects.py selftest
"""
import sys
import numpy as np

W = 480


def profile(frames):
    """frames: 灰度 uint8 图的可迭代对象 -> (sharp, motion, extent) 三个 numpy 数组。"""
    import cv2
    sharp, motion, extent, prev = [], [], [], None
    for g in frames:
        h = round(g.shape[0] * W / g.shape[1])
        g = cv2.resize(g, (W, h), interpolation=cv2.INTER_AREA)
        sharp.append(cv2.Laplacian(g.astype(np.float32), cv2.CV_32F).var())
        motion.append(np.abs(g.astype(np.float32) - prev).mean() if prev is not None else np.nan)
        ys, xs = np.where(g > 30)
        extent.append(((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) / g.size if len(xs) else 0.0)
        prev = g
    return np.array(sharp), np.array(motion), np.array(extent)


def dips(sharp, ratio=0.6, win=10):
    """清晰度比（对前后 win 帧中位数）< ratio 的帧号列表。"""
    med = np.array([np.median(sharp[max(0, i - win):i + win + 1]) for i in range(len(sharp))])
    return [i for i, r in enumerate(sharp / np.maximum(med, 1e-6)) if r < ratio]


def holds(motion):
    """比前后两帧运动量都低一半以上的单帧（补帧留下的内容停顿）。"""
    return [i for i in range(1, len(motion) - 1) if motion[i] < 0.5 * min(motion[i - 1], motion[i + 1])]


def runs(idx):
    out = []
    for i in idx:
        if out and i - out[-1][1] <= 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


def read_gray(path, start=0, n=None):
    import cv2
    c = cv2.VideoCapture(path)
    c.set(cv2.CAP_PROP_POS_FRAMES, start)
    k = 0
    while n is None or k < n:
        ok, im = c.read()
        if not ok:
            return
        yield cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        k += 1


def detail(path, start, k, m=12):
    """均匀取 m 帧，统一到 1080 高后 Laplacian 方差的中位数。profile 缩到 480 宽，量不出放大和多次转码造成的发虚。"""
    import cv2
    c, v = cv2.VideoCapture(path), []
    for f in np.linspace(start, start + k - 1, m).astype(int):
        c.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, im = c.read()
        if ok:
            g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
            g = cv2.resize(g, (round(g.shape[1] * 1080 / g.shape[0]), 1080), interpolation=cv2.INTER_AREA)
            v.append(cv2.Laplacian(g.astype(np.float32), cv2.CV_32F).var())
    return float(np.median(v)) if v else 0.0


def cmd_energy(events, ref, out, svg, ref_start=0):
    """逐镜能量曲线：参考片和成片每镜的亮度、运动量，加手填的景别和 drum_env，画进一张 SVG。亮度或运动量和参考片的逐镜相关 ≤ 0 算 FAIL。
    镜头帧号按成片（从 0 起）算，参考片从 ref_start 读。景别读 shots[].scale / scale_ref（1 远 2 全 3 中 4 近 5 特），没填就空着。"""
    import json, cv2
    with open(events, encoding='utf-8') as stream:
        ev = json.load(stream)
    shots = ev.get('shots', [])
    if len(shots) < 2:  # 没有硬切的片按 1 秒一格
        step = round(ev.get('fps', 30))
        shots = [{'id': a // step, 'start': a, 'end': min(a + step, ev['frames'])} for a in range(0, ev['frames'], step)]
    end = shots[-1]['end']

    def per_shot(path, start):
        L, M, prev = [], [], None
        for g in read_gray(path, int(start), end):
            g = cv2.resize(g, (W, round(g.shape[0] * W / g.shape[1])), interpolation=cv2.INTER_AREA).astype(np.float32)
            L.append(g.mean())
            M.append(np.abs(g - prev).mean() if prev is not None else 0.0)
            prev = g
        if len(L) < end:
            raise SystemExit(f"{path} 只读到 {len(L)} 帧，事件表要 {end} 帧")
        L, M = np.array(L), np.array(M)
        # 运动量不算切点那一帧的跳变
        return [L[s['start']:s['end']].mean() for s in shots], [M[s['start'] + 1:s['end']].mean() if s['end'] - s['start'] > 1 else 0.0 for s in shots]

    (rl, rm), (ol, om) = per_shot(ref, ref_start), per_shot(out, 0)
    drum = [max([e.get('drum_env') or 0 for e in ev.get('events', []) if s['start'] <= e['f'] < s['end']] or [0]) for s in shots]
    rows = [('亮度', rl, ol), ('运动量', rm, om), ('景别', [s.get('scale_ref') for s in shots], [s.get('scale') for s in shots]), ('drum_env', drum, None)]
    ok, n, pw, ph, x0 = True, len(shots), 900, 120, 70
    xs = [x0 + (i + 0.5) * (pw - x0 - 10) / n for i in range(n)]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{pw}" height="{ph * len(rows) + 30}" font-family="sans-serif" font-size="12"><rect width="100%" height="100%" fill="#111"/>']
    for k, (name, a, b) in enumerate(rows):
        vals = [v for v in list(a) + list(b or []) if v is not None]
        note = '未填' if not vals else ''
        lo, hi = (min(vals), max(vals)) if vals else (0, 1)
        y = lambda v: ph * k + ph - 15 - (v - lo) / max(hi - lo, 1e-6) * (ph - 35)
        if b and all(v is not None for v in list(a) + list(b)):
            # 两个样本也能判方向；不足两个或常量序列无法证明正相关。
            c = np.corrcoef(a, b)[0, 1] if n > 1 and np.std(a) > 0 and np.std(b) > 0 else float('nan')
            note = f'相关 {c:.2f}'
            bad = name != '景别' and not c > 0  # 景别是手填的，只画不判
            ok &= not bad
            print(f'[{name}] 参考与成片逐镜相关 {c:.2f}', 'FAIL 相关系数非正或无法计算' if bad else '')
        parts.append(f'<text x="6" y="{ph * k + 20}" fill="#ddd">{name} {note}</text>')
        for series, color, dash in ((a, '#999', '4 3'), (b, '#ff6b35', '')):
            if series and all(v is not None for v in series):
                pts = ' '.join(f'{x:.0f},{y(v):.0f}' for x, v in zip(xs, series))
                parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/>')
    parts += [f'<text x="{x:.0f}" y="{ph * len(rows) + 12}" fill="#888" text-anchor="middle">{s["id"]}</text>' for x, s in zip(xs, shots)]
    parts.append(f'<text x="{pw - 10}" y="{ph * len(rows) + 26}" fill="#888" text-anchor="end">灰色虚线 参考片　橙色 成片　横轴 镜号</text></svg>')
    with open(svg, 'w', encoding='utf-8') as stream:
        stream.write(''.join(parts))
    for s, a, b, c, d, e in zip(shots, rl, ol, rm, om, drum):
        print(f"镜 {s['id']:>2} 帧 {s['start']:>4}-{s['end']:<4} 亮度 {a:5.1f}/{b:5.1f}  运动 {c:5.2f}/{d:5.2f}  drum_env {e:.2f}")
    print(svg)
    print('PASS' if ok else 'FAIL')
    return ok


def cmd_dips(video, start=0, n=None):
    s, m, e = profile(read_gray(video, int(start), int(n) if n else None))
    d, h = dips(s), holds(m)
    off = int(start)
    print("凹陷帧段 (起,止,最低清晰度比):", [(a + off, b + off, round(float(np.min(s[a:b + 1] / max(np.median(s), 1e-6))), 2)) for a, b in runs(d)])
    print(f"停帧 {len(h)} 个，占 {len(h) / len(s):.0%}:", [i + off for i in h][:60])
    print(f"内容外接框占比 均值 {np.mean(e):.2f}  最小 {np.min(e):.2f}")
    return True


def cmd_compare(ref, out, ref_start=0, n=None):
    n = int(n) if n else None
    rs, rm, re_ = profile(read_gray(ref, int(ref_start), n))
    os_, om, oe = profile(read_gray(out, 0, len(rs)))
    k = min(len(rs), len(os_))
    if k < 20:
        raise SystemExit(f"读到的帧太少（参考 {len(rs)}，复刻 {len(os_)}）：文件不完整，或正在被别的进程写入？")
    ok = True
    rd, od = dips(rs[:k]), set(dips(os_[:k]))
    miss = [a for a, b in runs(rd) if not any(j in od for j in range(a - 1, b + 2))]
    print(f"[凹陷] 参考 {len(runs(rd))} 段，复刻缺 {len(miss)} 段:", [m + int(ref_start) for m in miss])
    ok &= not miss
    hr, ho = len(holds(rm[:k])) / k, len(holds(om[:k])) / k
    print(f"[停帧] 参考 {hr:.0%}  复刻 {ho:.0%}", "WARN 差 > 5 个百分点" if abs(hr - ho) > 0.05 else "")
    for lo in range(1, k, 60):
        a, b = np.nanmean(rm[lo:lo + 60]), np.nanmean(om[lo:lo + 60])
        if not 0.7 <= b / max(a, 1e-6) <= 1.4:
            print(f"[运动量] 帧 {lo}-{lo + 60}: 参考 {a:.2f} 复刻 {b:.2f}  WARN 比值超出 0.7–1.4")
    er, eo = np.median(re_[:k]), np.median(oe[:k])
    print(f"[内容范围] 外接框占比中位数 参考 {er:.2f}  复刻 {eo:.2f}", "FAIL 复刻缩水超过 10%（素材被裁切？）" if eo < 0.9 * er else "")
    ok &= eo >= 0.9 * er
    dr, do = detail(ref, int(ref_start), k), detail(out, 0, k)
    print(f"[清晰度] 1080 高 Laplacian 方差中位数 参考 {dr:.0f}  复刻 {do:.0f}", "WARN 复刻不到参考的一半（素材放大或多次转码？）" if do < 0.5 * dr else "")
    print("PASS" if ok else "FAIL")
    return ok


def selftest():
    import cv2
    rng = np.random.default_rng(0)
    fr = []
    for i in range(80):
        fr.append(rng.integers(0, 255, (120, 160), dtype=np.uint8))
    for i in range(20, 24):
        fr[i] = cv2.GaussianBlur(fr[i], (0, 0), 6)  # 模糊动效
    fr[40], fr[60] = fr[39].copy(), fr[59].copy()  # 停帧
    s, m, _ = profile(fr)
    d = dips(s)
    assert set(range(20, 24)) <= set(d) and len(d) <= 6, d
    assert {40, 60} <= set(holds(m)), holds(m)
    # 内容范围：只有中间亮的帧，外接框应明显小于整幅
    small = np.zeros((120, 160), np.uint8)
    small[40:80, 50:110] = 200
    assert profile([small])[2][0] < 0.25
    print("selftest ok")
    return True


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    sys.exit(0 if {'dips': cmd_dips, 'compare': cmd_compare, 'energy': cmd_energy, 'selftest': selftest}[cmd](*a) else 1)
