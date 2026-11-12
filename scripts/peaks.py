"""在素材里找动作峰值，给分镜单提供入点候选。

主体区（画面中央）和背景区（四周）分开算光流。主体区每个像素取「自身光流」和「减去背景中位光流后」两个幅值里小的那个，
再取 90 分位当主体运动量：环绕运镜（主体不动、背景动）和平移运镜（主体跟背景一起动）都接近 0，只有主体自己在动才高。
取主体运动量的局部峰值，按突出度排前 N 个，打印 素材@秒，可另出一张 960 宽联系表。
AV1 录屏 OpenCV 解不了，所以读帧一律走 ffmpeg 管道。

用法:
  peaks.py 素材.mp4 [--top 20] [--fps 10] [--sheet 联系表.jpg]
  peaks.py selftest
"""
import argparse, subprocess, sys
import numpy as np

W, H = 320, 180


def frames(path, fps):
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', path, '-vf', f'fps={fps},scale={W}:{H},format=gray', '-f', 'rawvideo', '-'],
                         stdout=subprocess.PIPE)
    while len(b := p.stdout.read(W * H)) == W * H:
        yield np.frombuffer(b, np.uint8).reshape(H, W)


def subject_motion(fr):
    """灰度帧序列 -> 每对相邻帧一行 (主体运动量, 背景运动量, 清晰度)。"""
    import cv2
    y0, y1, x0, x1 = H // 5, H * 4 // 5, W // 4, W * 3 // 4
    bgmask = np.ones((H, W), bool)
    bgmask[y0:y1, x0:x1] = False
    out, prev = [], None
    for g in fr:
        if prev is not None:
            f = cv2.calcOpticalFlowFarneback(prev, g, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            bg = np.median(f[bgmask], axis=0)
            d = f[y0:y1, x0:x1]
            sub = np.percentile(np.minimum(np.linalg.norm(d, axis=2), np.linalg.norm(d - bg, axis=2)), 90)
            out.append((sub, np.linalg.norm(bg), cv2.Laplacian(g, cv2.CV_32F).var()))
        prev = g
    return np.array(out)


def peaks(sub, fps, top):
    from scipy.signal import find_peaks
    idx, pr = find_peaks(sub, distance=max(1, int(fps)), prominence=0)  # 相邻候选至少隔 1 秒
    return sorted(idx[np.argsort(-pr['prominences'])[:top]])


def contact(path, times, sheet, cols=4, tw=240, th=135):
    import cv2
    rows = -(-len(times) // cols)
    canvas = np.zeros((rows * th, cols * tw, 3), np.uint8)
    for k, t in enumerate(times):
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.2f}', '-i', path, '-frames:v', '1', '-vf', f'scale={tw}:{th}',
                              '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], capture_output=True).stdout
        if len(raw) == tw * th * 3:
            im = np.frombuffer(raw, np.uint8).reshape(th, tw, 3).copy()
            cv2.putText(im, f'{t:.1f}s', (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            canvas[k // cols * th:(k // cols + 1) * th, k % cols * tw:(k % cols + 1) * tw] = im
    cv2.imencode('.jpg', canvas)[1].tofile(sheet)  # imwrite 写不了中文路径
    print(sheet)


def main(path, top, fps, sheet):
    m = subject_motion(frames(path, fps))
    if not len(m):
        raise SystemExit(f'没读到帧：{path}')
    pk = peaks(m[:, 0], fps, top)
    for i in pk:
        print(f'{path}@{(i + 1) / fps:.1f}  主体 {m[i, 0]:.2f}  背景 {m[i, 1]:.2f}  清晰度 {m[i, 2]:.0f}')
    if sheet:
        contact(path, [(i + 1) / fps for i in pk], sheet)


def selftest():
    import cv2
    rng = np.random.default_rng(0)
    tex = lambda h, w: cv2.GaussianBlur(rng.integers(0, 255, (h, w)).astype(np.uint8), (0, 0), 3)
    bg, obj = tex(H, W + 80), tex(60, 60)
    fr = []
    for i in range(80):
        pan = 4 * max(0, min(i - 60, 5))  # 60–65 帧背景平移、中央小块不动：环绕运镜，不该算动作
        g = bg[:, pan:pan + W].copy()
        x = 130 + 6 * max(0, min(i - 30, 5))  # 30–35 帧中央小块移动：动作
        g[60:120, x:x + 60] = obj
        fr.append(g)
    m = subject_motion(fr)
    pk = peaks(m[:, 0], 10, 3)
    assert any(29 <= i <= 35 for i in pk), pk
    assert m[60:65, 0].max() < 0.5 * m[30:35, 0].max(), (m[60:65, 0].max(), m[30:35, 0].max())
    assert m[60:65, 1].max() > 2, m[60:65, 1]
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']:
        selftest()
    else:
        ap = argparse.ArgumentParser()
        ap.add_argument('path')
        ap.add_argument('--top', type=int, default=20)
        ap.add_argument('--fps', type=float, default=10)
        ap.add_argument('--sheet')
        a = ap.parse_args()
        main(a.path, a.top, a.fps, a.sheet)
