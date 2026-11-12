"""Deploy the maintained revideo scripts; default mode only checks for drift."""
import argparse
from pathlib import Path
import shutil
import sys

DEFAULT_TARGETS = [
    Path(r"C:\Users\ASUS\.skills-manager\skills\revideo"),
]
ALT_REPO = Path(r"D:\2\dev\revideo")


def sync_one(source: Path, target: Path, apply: bool):
    identity = target / 'SKILL.md'
    if not identity.is_file() or 'name: revideo' not in identity.read_text(encoding='utf-8').split('---')[1].splitlines():
        return False, f'{target}: 目标必须是现有 revideo 技能目录'
    destination = target / 'scripts'
    if not destination.is_dir() or destination.resolve() == source.resolve():
        return True, f'{target.name}: 忽略自身'
    drift = []
    for src in sorted(source.rglob('*')):
        if not src.is_file() or src.suffix not in ('.py', '.json'):
            continue
        rel = src.relative_to(source)
        dst = destination / rel
        if not dst.is_file() or src.read_bytes() != dst.read_bytes():
            drift.append(str(rel))
            if apply:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    retired = destination / 'to_jianying.py'
    if retired.exists():
        drift.append(retired.name + ' (retired)')
        if apply:
            retired.unlink()
    if drift and not apply:
        return False, f'{target.name}: FAIL 部署漂移：' + ', '.join(drift)
    msg = f'{target.name}: PASS 已同步' if apply else f'{target.name}: PASS 维护源与部署脚本逐字节一致'
    return True, msg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('skill_dir', type=Path, nargs='?', default=None,
                    help='目标技能目录（可选；未提供时默认同步所有已知部署副本）')
    ap.add_argument('--apply', action='store_true',
                    help='将维护源同步写入目标部署目录')
    o = ap.parse_args()
    source = Path(__file__).resolve().parent

    if o.skill_dir:
        targets = [o.skill_dir.resolve()]
    else:
        targets = [t.resolve() for t in DEFAULT_TARGETS if t.exists()]
        if ALT_REPO.exists() and (ALT_REPO / 'scripts').resolve() != source.resolve():
            targets.append(ALT_REPO.resolve())

    all_ok = True
    single = len(targets) == 1 and bool(o.skill_dir)
    for target in targets:
        ok, msg = sync_one(source, target, o.apply)
        if single:
            print('PASS 已同步' if o.apply else 'PASS 维护源与部署脚本逐字节一致' if ok else msg)
        else:
            print(msg)
        if not ok:
            all_ok = False

    return 0 if all_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
