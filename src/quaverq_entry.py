"""Nuitka 入口 shim: 把 ``quaverq.__main__:main`` 调起来.

为什么需要这个文件:
- Nuitka 直接用 ``-m src/quaverq`` 启动时, ``quaverq.__main__`` 同时是
  "主程序入口"和 ``--include-package=quaverq`` 列表里的"包内子模块",
  Nuitka 自己去重后打 INFO 警告:
  "Not allowed to include module 'quaverq.__main__' due to 'Main program is already included in package mode.'"
  功能上无影响, 但每次构建刷屏.
- 把入口换成本文件 (包**外**), ``--include-package=quaverq`` 不再与之冲突;
  ``__main__`` 通过正常的 import 路径被纳入, 警告消失.

只用于 Nuitka 打包. 开发态 ``uv run quaverq`` 走 ``pyproject [project.scripts]``
里配置的 ``quaverq.__main__:main``, 与本文件无关.
"""

from __future__ import annotations

from quaverq.__main__ import main

if __name__ == "__main__":
    main()
