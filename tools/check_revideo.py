"""revideo 门禁：部署副本一致性（可选） + 参考复核/媒体测试 + 原回归。
用法: python -B -X utf8 tools/check_revideo.py [--fast] [--with-deploy]"""
import os
import subprocess
import sys
from pathlib import Path

PY = sys.executable
# 基于当前文件动态定位仓库根目录与 tools 目录，彻底消除硬编码绝对路径 (F-012)
REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
VIDEO = Path(os.environ.get('REVIDEO_VIDEO_ROOT', 'D:/2/dev/claude-video'))
SKILL = Path(os.environ.get('REVIDEO_SKILL_ROOT', 'C:/Users/ASUS/.claude/skills/revideo'))


def run(args):
    return subprocess.run([PY, '-B', '-X', 'utf8', *map(str, args)], cwd=str(REPO_ROOT)).returncode


def check_no_hardcoded_paths():
    """扫描 scripts 与 tools 目录，禁止在源码与测试脚本中硬编码机器特定盘符路径 (F-012 守护门禁)"""
    violations = []
    import re
    # 匹配字面量盘符路径，例如 'C:/...', 'D:\...', 排除正则转义如 'I:\s'
    pattern = re.compile(r'[\'"][A-Za-z]:[/\\](?![sdwbSDWB])')
    
    for folder in [REPO_ROOT / 'scripts', TESTS]:
        if not folder.exists():
            continue
        for py_file in folder.glob('**/*.py'):
            if py_file.name in ('check_revideo.py', 'sync_install.py'):
                continue # 排除门禁脚本自身与专用同步部署脚本
            lines = py_file.read_text(encoding='utf-8', errors='replace').splitlines()
            for idx, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if pattern.search(line) and 'os.environ' not in line:
                    violations.append(f"{py_file.relative_to(REPO_ROOT)}:{idx}: {stripped}")
                    
    if violations:
        print(f"FAIL 发现硬编码宿主机盘符路径 (共 {len(violations)} 处，已拦截):")
        for v in violations[:10]:
            print(f"  - {v}")
        return False
    print("PASS 静态盘符路径检查 (零硬编码绝对路径)")
    return True


def main():
    if not check_no_hardcoded_paths():
        return 1

    steps = []
    # 仅在显式指定 --with-deploy 或外部部署路径实际存在时检查部署一致性
    sync_script = VIDEO / 'tools/revideo/sync_install.py'
    if '--with-deploy' in sys.argv[1:] or (sync_script.exists() and SKILL.exists()):
        steps.append(('部署副本一致性', [sync_script, SKILL]))
    else:
        print('INFO 外部部署目录不存在，已跳过部署副本一致性检查（本地独立运行模式）')

    steps.extend([
        ('参考复核测试', [TESTS / 'test_revideo_reference.py']),
        ('媒体测试', [TESTS / 'test_revideo_media.py'])
    ])

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
