#!/usr/bin/env python3
"""QuaverQ 打包入口（构建逻辑见 quaverq.packaging）。

使用方法:
    uv run python build.py              # Nuitka standalone → dist/__main__.dist/
    uv run python build.py --onefile    # 单文件
    uv run python build.py --appimage   # standalone + AppImage（需 linuxdeploy + qt 插件）
"""

from __future__ import annotations

from quaverq.packaging import main

if __name__ == "__main__":
    main()
