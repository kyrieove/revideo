"""为待核对镜头或每个切点生成参考/成片帧条，作为 shots[].review 的证据。
用法: python strips.py events.json ref.mp4 out.mp4 <dir> [--n-frames 8] [--all] [--shot ID] [--boundaries]
依赖 video-use 的 timeline_view.py（Pillow）。按 review.status 选取待核对镜头；记录是否完整以 check.py review 为准。"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

VIEW = Path('C:/Users/ASUS/.claude/skills/video-use/helpers/timeline_view.py')
DONE = ('verified', 'not_applicable', 'deviation')


def pending_shots(doc):
    """没有复核契约的旧表按全部镜头处理。"""
    shots = doc.get('shots') or []
    if not any(isinstance(s.get('review'), dict) and s['review'] for s in shots):
        return shots
    return [s for s in shots if not isinstance(s.get('review'), dict) or not s['review']
            or any((r or {}).get('status') not in DONE for r in s['review'].values())]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('events', type=Path)
    ap.add_argument('ref', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('dir', type=Path)
    ap.add_argument('--n-frames', type=int, default=8)
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--shot', type=int)
    ap.add_argument('--boundaries', action='store_true')
    o = ap.parse_args()
    if not VIEW.is_file():
        print(f'FAIL_STRIPS 缺少 timeline_view.py：{VIEW}')
        sys.exit(1)
    doc = json.loads(o.events.read_text(encoding='utf-8'))
    fps = float(doc['fps'])
    if o.boundaries:
        # 每个切点前后各 4 帧，一帧一采样；帧号偏移 1 帧会在帧条上直接看到
        items = [(f"cut_{c:04d}", a, b, b - a) for c in (s['start'] for s in doc['shots'][1:])
                 for a, b in [(max(0, c - 4), min(doc['frames'], c + 5))]]
    else:
        shots = doc['shots'] if o.all else pending_shots(doc)
        if o.shot is not None:
            shots = [s for s in shots if s['id'] == o.shot]
            if not shots:
                print(f'FAIL_STRIPS 镜头 {o.shot} 不在待核对列表；旧表可加 --all')
                sys.exit(1)
        items = [(f"shot_{s['id']:03d}", s['start'], s['end'], min(o.n_frames, s['end'] - s['start']))
                 for s in shots]
    o.dir.mkdir(parents=True, exist_ok=True)
    index = []
    for name, start, end, n in items:
        pair = {}
        # -ss 取第一个 pts >= 时间；取到帧起点前 1ms，避免落到下一帧
        view_start = max(0.0, math.floor(start * 1000 / fps) / 1000 - 0.001)
        view_end = max(view_start, math.floor((end - 1) * 1000 / fps) / 1000 - 0.001)
        if n == 1:
            view_end = view_start + 0.002  # timeline_view 取中点，中点仍须在帧起点之前
        elif view_end <= view_start:
            view_end = view_start + 0.001
        for tag, video in (('ref', o.ref), ('out', o.out)):
            p = o.dir / f'{name}_{tag}.png'
            try:
                subprocess.run([sys.executable, '-B', '-X', 'utf8', str(VIEW), str(video),
                                f'{view_start:.3f}', f'{view_end:.3f}',
                                '--n-frames', str(n), '-o', str(p)], check=True)
            except subprocess.CalledProcessError as exc:
                print(f'FAIL_STRIPS 帧条生成失败：{video}（退出码 {exc.returncode}）')
                sys.exit(1)
            pair[tag] = str(p)
        index.append({'name': name, 'start': start, 'end': end, **pair})
    (o.dir / 'strips.json').write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'PASS_STRIPS {len(index)} 项；帧条在 {o.dir}')


if __name__ == '__main__':
    main()
