#!/usr/bin/env python3
"""QuaverQ Nuitka 编译脚本.

将 Python 源码编译为独立二进制文件，无需运行时解压。

使用方法:
    python build.py              # 编译为 standalone 二进制
    python build.py --onefile    # 编译为单文件
    python build.py --qt         # 仅打包 Qt 后端
    python build.py --gtk        # 仅打包 GTK 后端
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"


def build(mode: str = "standalone", ui_backend: str = "all") -> None:
    """运行 Nuitka 编译.

    Args:
        mode: standalone | onefile
        ui_backend: qt | gtk | all
    """
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        f"--{mode}",
        "--assume-yes-for-downloads",
        "--output-dir=dist",
        # 入口
        str(SRC_DIR / "quaverq" / "__main__.py"),
        # 包含包
        f"--include-package=quaverq",
        f"--include-package-data-dir={SRC_DIR / 'quaverq'}={SRC_DIR / 'quaverq'}",
        # 优化
        "--enable-plugin=pylint-warnings",
        # 排除不需要的
        "--noinclude-pytest-mode=nofollow",
        "--noinclude-unittest-mode=nofollow",
    ]

    # 根据后端选择排除未使用的 UI 框架
    if ui_backend == "qt":
        cmd.append("--nofollow-import-to=gi")
        cmd.append("--nofollow-import-to=gi.repository")
    elif ui_backend == "gtk":
        cmd.append("--nofollow-import-to=PySide6")

    # 编译优化级别
    cmd.append("--lto=yes")
    cmd.append("--jobs=auto")

    print(f"[build] 运行: {' '.join(shlex.quote(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="QuaverQ Nuitka 编译")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="编译为单文件 (默认: standalone 目录)",
    )
    parser.add_argument(
        "--qt",
        action="store_true",
        help="仅打包 Qt 后端",
    )
    parser.add_argument(
        "--gtk",
        action="store_true",
        help="仅打包 GTK 后端",
    )
    args = parser.parse_args()

    mode = "onefile" if args.onefile else "standalone"

    if args.qt:
        ui_backend = "qt"
    elif args.gtk:
        ui_backend = "gtk"
    else:
        ui_backend = "all"

    build(mode=mode, ui_backend=ui_backend)


if __name__ == "__main__":
    main()
