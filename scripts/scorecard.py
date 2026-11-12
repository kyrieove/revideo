"""校验盲审评分表：五维 0–10、P0/P1 带证据、版本与评审者；可选对比基线。
用法: python scorecard.py score.json [--baseline prev.json]"""
import argparse
import json
import re
import sys
from pathlib import Path

DIMS = {'action': '动作', 'pacing': '节奏', 'framing': '构图', 'quality': '画质', 'audio': '声音'}


def load(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('评分表必须是 JSON 对象')
    for key in ('version', 'reviewer'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'缺少 {key}')
    scores = data.get('scores')
    if not isinstance(scores, dict) or set(scores) != set(DIMS):
        raise ValueError('scores 必须且只能包含 ' + '、'.join(DIMS))
    for key, value in scores.items():
        if type(value) not in (int, float) or not 0 <= value <= 10:
            raise ValueError(f'{key} 必须是 0–10 的数字')
    for key in ('p0', 'p1'):
        items = data.get(key)
        if not isinstance(items, list) or any(not isinstance(x, str) or not x.strip() for x in items):
            raise ValueError(f'{key} 必须是字符串列表（可为空）')
        if any(not re.search(r'(F\d+|\d+\s*帧|\S+:\d+)', x) for x in items):
            raise ValueError(f'{key} 每条须带帧号或 file:line')
    if any(x in data['reviewer'] for x in ('实际执行', '占位', '示例')):
        raise ValueError('reviewer 仍是占位文字')
    return data


def total(data):
    return sum(data['scores'].values())


def main_path(score, baseline=None):
    try:
        current = load(Path(score))
        base = load(Path(baseline)) if baseline else None
    except (OSError, ValueError) as exc:
        print(f'FAIL_SCORECARD {exc}')
        return False
    print(f"{current['version']} 评审 {current['reviewer']}  总分 {total(current):.1f}/50  "
          f"P0 {len(current['p0'])}  P1 {len(current['p1'])}")
    for key, name in DIMS.items():
        print(f"  {name} {current['scores'][key]:.1f}/10")
    if base is not None:
        drop = total(base) - total(current)
        if drop > 0:
            print(f"FAIL_SCORECARD 总分低于基线 {base['version']}：{total(current):.1f} < {total(base):.1f}")
            return False
        print(f"PASS_SCORECARD 不低于基线 {base['version']}（{total(base):.1f}）")
    print('PASS_SCORECARD 评分表有效')
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('score')
    ap.add_argument('--baseline')
    o = ap.parse_args()
    return main_path(o.score, o.baseline)


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
