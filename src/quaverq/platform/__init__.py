"""PAL (Platform Abstraction Layer) 入口.

应用启动期调一次 ``get_platform()`` 拿到当前平台的 adapter, 之后所有平台相关的能力
(单实例 / 系统主题 / 媒体会话) 都从 adapter 取, 不在业务代码里 import 平台特定模块.

派发规则:
- ``sys.platform == "linux"``   -> LinuxPlatform
- ``sys.platform == "win32"``   -> WindowsPlatform (Stage 1 stub, 能力全 None)
- ``sys.platform == "darwin"``  -> MacOSPlatform (TODO, 当前回退 stub)
- 其他                          -> _NullPlatform (能力全 None, 不崩)

实现按需 (惰性) import 各平台模块, 避免在 Windows 上 import LinuxPlatform 时被
PySide6 / dbus_next 误连接 D-Bus (实际上现有实现都是惰性连的, 但保持惰性 import
能让冷启动更轻).
"""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Any

from .base import PlatformAdapter, SingleInstance

__all__ = ["PlatformAdapter", "SingleInstance", "get_platform"]


class _NullPlatform:
    """未知平台的兜底 adapter (功能全 None, 不崩)."""

    name = "stub"

    def single_instance(self) -> Any | None:
        return None

    def system_theme(self) -> Any | None:
        return None

    def media_session(
        self,
        player_controller: Any,
        *,
        raise_window: Any = None,
        quit_app: Any = None,
        cover_cache: Any = None,
        stream_proxy: Any = None,
    ) -> Any | None:
        return None

    def lyric_publisher(
        self,
        *,
        lyric_controller: Any,
        player_controller: Any,
    ) -> Any | None:
        return None

    def desktop_lyrics(self, lyric_controller: Any) -> Any | None:  # noqa: ARG002
        return None


@lru_cache(maxsize=1)
def get_platform() -> PlatformAdapter:
    """返回当前平台的 adapter (单例).

    多次调用返回同一实例, 避免重复构造 / 触发底层资源初始化.
    """
    if sys.platform == "linux":
        from .linux import LinuxPlatform

        return LinuxPlatform()
    if sys.platform == "win32":
        from .windows import WindowsPlatform

        return WindowsPlatform()
    # darwin 暂时回退 stub, Stage 4 替换为 MacOSPlatform.
    return _NullPlatform()
