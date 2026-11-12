"""revideo 门禁：部署副本一致性 + 参考复核/媒体测试 + 原回归。
用法: python -B -X utf8 tools/check_revideo.py [--fast]（--fast 跳过 53 项原回归，pre-commit 用）"""
import subprocess
import sys
from pathlib import Path

PY = sys.executable
VIDEO = Path('D:/2/dev/claude-video')
SKILL = Path('C:/Users/ASUS/.claude/skills/revideo')
TESTS = Path(__file__).resolve().parent


def run(args):
    return subprocess.run([PY, '-B', '-X', 'utf8', *map(str, args)]).returncode


def main():
    steps = [('部署副本一致性', [VIDEO / 'tools/revideo/sync_install.py', SKILL]),
             ('参考复核测试', [TESTS / 'test_revideo_reference.py']),
             ('媒体测试', [TESTS / 'test_revideo_media.py'])]
    if '--fast' not in sys.argv[1:]:
        steps.append(('原回归', [TESTS / 'test_revideo.py']))
    for name, args in steps:
        code = run(args)
        if code:
            print(f'FAIL {name}（退出码 {code}）')
            return 1
        print(f'PASS {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
