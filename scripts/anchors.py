"""按 events.json 的 shots[].anchors 抽参考/成片同阶段帧并排，帧差超过 --max-diff 才 FAIL。
用法: python anchors.py events.json ref.mp4 out.mp4 <dir> [--max-diff N]
anchors 结构: [{"phase": "收刀完成", "ref_frame": 470, "out_frame": 470}]；out_frame 为 null 表示成片未出现该阶段。"""
import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

W, H = 480, 270


def grab(video, frame):
    p = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-vf',
                        f"select='eq(n\\,{frame})',scale={W}:{H}", '-frames:v', '1',
                        '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True)
    if p.returncode or not p.stdout:
        return None
    return Image.open(io.BytesIO(p.stdout)).convert('RGB')


def count_frames(video):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                                   '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(video)])
    return int(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('events', type=Path)
    ap.add_argument('ref', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('dir', type=Path)
    ap.add_argument('--max-diff', type=int)
    o = ap.parse_args()
    doc = json.loads(o.events.read_text(encoding='utf-8'))
    try:
        ref_n, out_n = count_frames(o.ref), count_frames(o.out)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f'FAIL_ANCHORS 无法读取视频：{exc}')
        return False
    o.dir.mkdir(parents=True, exist_ok=True)
    rows, bad = [], 0
    for shot in doc['shots']:
        for i, anchor in enumerate(shot.get('anchors') or []):
            phase, rf, of = anchor.get('phase'), anchor.get('ref_frame'), anchor.get('out_frame')
            if not isinstance(phase, str) or not phase.strip() or type(rf) is not int or not 0 <= rf < ref_n:
                print(f"FAIL_ANCHORS shot {shot['id']} 第 {i + 1} 项 anchors 无效")
                bad += 1
                continue
            if of is not None and (type(of) is not int or not 0 <= of < out_n):
                print(f"FAIL_ANCHORS shot {shot['id']} {phase} 成片帧 {of} 超出范围")
                bad += 1
                continue
            pair = []
            for tag, video, frame in (('ref', o.ref, rf), ('out', o.out, of if of is not None else rf)):
                image = grab(video, frame) if frame is not None else None
                if image is None:
                    print(f'FAIL_ANCHORS shot {shot["id"]} {phase} 抽帧失败：{tag} F{frame}')
                    bad += 1
                    break
                pair.append((tag, frame, image))
            else:
                canvas = Image.new('RGB', (W * 2 + 20, H + 30), '#181818')
                draw = ImageDraw.Draw(canvas)
                for j, (tag, frame, image) in enumerate(pair):
                    canvas.paste(image, (j * (W + 20), 30))
                    label = f'{tag} F{frame}' + ('（阶段未出现）' if tag == 'out' and of is None else '')
                    draw.text((j * (W + 20) + 4, 8), label, fill='white')
                path = o.dir / f"shot_{shot['id']:03d}_anchor_{i + 1}.png"
                canvas.save(path)
                rows.append({'shot': shot['id'], 'phase': phase, 'ref_frame': rf, 'out_frame': of,
                             'diff': None if of is None else of - rf, 'image': str(path)})
    (o.dir / 'anchors.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    if not rows and not bad:
        print('FAIL_ANCHORS 没有 anchors；先人工填写参考帧与成片帧')
        return False
    for row in rows:
        if row['out_frame'] is None:
            print(f"FAIL_ANCHORS shot {row['shot']} {row['phase']} 成片未出现（参考 F{row['ref_frame']}）")
            bad += 1
        elif o.max_diff is not None and abs(row['diff']) > o.max_diff:
            print(f"FAIL_ANCHORS shot {row['shot']} {row['phase']} 差 {row['diff']:+d} 帧 > {o.max_diff}")
            bad += 1
        else:
            print(f"INFO shot {row['shot']} {row['phase']} 参考 F{row['ref_frame']} 成片 F{row['out_frame']} 差 {row['diff']:+d}")
    print(f"{'FAIL_ANCHORS' if bad else 'PASS_ANCHORS'} {bad} 项失败；"
          + (f'阈值 ±{o.max_diff} 帧' if o.max_diff is not None else '未给阈值，只报数'))
    return not bad and bool(rows)


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
