"""Deploy the maintained revideo scripts; default mode only checks for drift."""
import argparse
from pathlib import Path
import shutil


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('skill_dir', type=Path)
    ap.add_argument('--apply', action='store_true')
    o = ap.parse_args()
    source = Path(__file__).resolve().parent
    target = o.skill_dir.resolve()
    identity = target / 'SKILL.md'
    if not identity.is_file() or 'name: revideo' not in identity.read_text(encoding='utf-8').split('---')[1].splitlines():
        ap.error('目标必须是现有 revideo 技能目录')
    destination = target / 'scripts'
    if not destination.is_dir() or destination.resolve() == source:
        ap.error('目标 scripts 必须是现有且独立的部署目录')
    drift = []
    for src in sorted(source.rglob('*')):
        if not src.is_file() or src.suffix not in ('.py', '.json'):
            continue
        rel = src.relative_to(source)
        dst = destination / rel
        if not dst.is_file() or src.read_bytes() != dst.read_bytes():
            drift.append(str(rel))
            if o.apply:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    retired = destination / 'to_jianying.py'
    if retired.exists():
        drift.append(retired.name + ' (retired)')
        if o.apply:
            retired.unlink()
    if drift and not o.apply:
        print('FAIL 部署漂移：' + ', '.join(drift))
        return 1
    print('PASS 已同步' if o.apply else 'PASS 维护源与部署脚本逐字节一致')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
