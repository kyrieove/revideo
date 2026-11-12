"""定向运动模糊（圈尾动效）。长度上限 130 px 来自千斤坠参考片实测。
用法: python motion_blur.py in.mp4 out.mp4 --start 173 --end 179 --angle 42 --length 90 [--radial]
--start/--end 为帧号，半开区间；--radial 按到画面中心的距离渐入模糊。"""
import argparse
import json
import subprocess
import sys

import cv2
import numpy as np

MAX_LEN = 130


def validate_length(length):
    if not 0 <= length <= MAX_LEN:
        raise ValueError(f'模糊长度 {length} 超出 0–{MAX_LEN} px；过大会把主体糊成一片')


def kernel(length, angle):
    if length < 1.5:
        return None
    k = int(length) // 2 * 2 + 3
    ker = np.zeros((k, k), np.float32)
    c = k // 2
    dx, dy = np.cos(np.radians(angle)) * length / 2, np.sin(np.radians(angle)) * length / 2
    cv2.line(ker, (int(round(c - dx)), int(round(c - dy))), (int(round(c + dx)), int(round(c + dy))), 1.0, 1)
    return ker / ker.sum()


def alpha(radius_px, scale):
    """径向权重：70px 内清晰，230px 外全糊（按 1080 短边归一，源实现同）。"""
    return float(np.clip((radius_px / scale - 70 / 1080) / (230 / 1080), 0, 1))


def apply(img, ker, radial=False):
    blurred = cv2.filter2D(img, -1, ker, borderType=cv2.BORDER_REFLECT)
    if not radial:
        return blurred
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - w / 2, yy - h / 2)
    a = np.clip((r / min(h, w) - 70 / 1080) / (230 / 1080), 0, 1)[..., None]
    return (img * (1 - a) + blurred * a).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--start', type=int, required=True)
    ap.add_argument('--end', type=int, required=True)
    ap.add_argument('--angle', type=float, default=42)
    ap.add_argument('--length', type=float, required=True)
    ap.add_argument('--radial', action='store_true')
    o = ap.parse_args()
    try:
        validate_length(o.length)
    except ValueError as exc:
        print(f'FAIL_FX {exc}')
        return False
    ker = kernel(o.length, o.angle)
    try:
        meta = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,avg_frame_rate', '-of', 'json', o.input]))['streams'][0]
        w, h, fps = meta['width'], meta['height'], meta['avg_frame_rate']
    except (OSError, subprocess.CalledProcessError, KeyError, ValueError, IndexError) as exc:
        print(f'FAIL_FX 无法读取输入：{exc}')
        return False
    dec = subprocess.Popen(['ffmpeg', '-v', 'error', '-noautorotate', '-i', o.input,
                            '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], stdout=subprocess.PIPE)
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                            '-s', f'{w}x{h}', '-r', fps, '-i', '-', '-c:v', 'libx264', '-crf', '14',
                            '-pix_fmt', 'yuv420p', o.output], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n, broken = 0, None
    try:
        while True:
            buf = dec.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                break
            img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            if ker is not None and o.start <= n < o.end:
                img = apply(img, ker, o.radial)
            enc.stdin.write(img.tobytes())
            n += 1
    except (BrokenPipeError, OSError) as exc:
        broken = exc
    finally:
        dec.stdout.close()
        enc.stdin.close()
        dec.wait()
        enc.wait()
    if broken is not None or n == 0 or dec.returncode or enc.returncode:
        detail = enc.stderr.read().decode('utf-8', 'replace').strip().splitlines()
        print(f'FAIL_FX 处理失败：{n} 帧，退出码 {dec.returncode}/{enc.returncode}'
              + (f'，{detail[-1]}' if detail else '') + (f'，{broken}' if broken else ''))
        return False
    print(f'PASS_FX {n} 帧，模糊帧 [{o.start},{o.end}) 角度 {o.angle}° 长度 {o.length} px（不含音轨）')
    return True


def selftest():
    validate_length(MAX_LEN)
    try:
        validate_length(MAX_LEN + 1)
    except ValueError:
        pass
    else:
        raise AssertionError('超长模糊未被拒绝')
    img = np.zeros((64, 64, 3), np.uint8)
    img[:, ::2] = 255
    out = apply(img, kernel(9, 0))
    assert np.abs(np.diff(out.astype(float), axis=1)).mean() < np.abs(np.diff(img.astype(float), axis=1)).mean()
    radial = apply(img, kernel(9, 0), radial=True)
    center = np.abs(np.diff(radial[:, 30:34].astype(float), axis=1)).mean()
    edge = np.abs(np.diff(radial[:, 0:4].astype(float), axis=1)).mean()
    assert center > edge, (center, edge)
    assert alpha(70, 1080) == 0 and alpha(300, 1080) == 1
    assert abs(alpha(185, 1080) - 0.5) < 1e-9
    print('selftest ok')


if __name__ == '__main__':
    if '--selftest' in sys.argv[1:]:
        selftest()
    else:
        sys.exit(0 if main() else 1)
