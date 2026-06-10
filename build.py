#!/usr/bin/env python3
"""QuaverQ 打包入口（构建逻辑见 quaverq.packaging）。

使用方法:
    uv run python build.py              # Nuitka standalone → dist/quaverq.dist/
    uv run python build.py --onefile    # 单文件 exe
    uv run python build.py --appimage   # standalone + AppImage（Linux, 需 linuxdeploy）
    uv run python build.py --msi        # standalone + MSI 安装包 (Windows, 需 WiX 5)
    uv run python build.py --portable   # standalone + portable zip (跨平台, 解压即跑)
"""

from __future__ import annotations

from quaverq.packaging import main

if __name__ == "__main__":
    main()
