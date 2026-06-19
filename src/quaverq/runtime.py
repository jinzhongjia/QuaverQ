"""运行时环境判断。"""

from __future__ import annotations

import sys


def is_packaged() -> bool:
    """当前是否运行在 PyInstaller / Nuitka 等打包产物中."""
    return bool(getattr(sys, "frozen", False) or globals().get("__compiled__") is not None)
