"""Linux 平台适配器.

把现有的 ``core.single_instance.SingleInstanceGuard`` / ``bridge.system_theme.SystemThemeWatcher``
/ ``bridge.mpris_controller.MprisController`` 包装在统一接口下, 不动现有实现.

D-Bus 实际连接由这些类内部惰性触发 (acquire / start), import 时不连; 因此本模块在
Windows / macOS 上 import 也不会崩 —— 但 ``get_platform()`` 不会派发到这里, 不必担心.
"""

from __future__ import annotations

from typing import Any


class LinuxPlatform:
    """Linux 平台门面."""

    name = "linux"

    def single_instance(self) -> Any:
        from ..core.single_instance import SingleInstanceGuard

        return SingleInstanceGuard()

    def system_theme(self) -> Any:
        from ..bridge.system_theme import SystemThemeWatcher

        return SystemThemeWatcher()

    def media_session(
        self,
        player_controller: Any,
        *,
        raise_window: Any = None,
        quit_app: Any = None,
    ) -> Any:
        from ..bridge.mpris_controller import MprisController

        return MprisController(
            player_controller,
            raise_window=raise_window,
            quit_app=quit_app,
        )

    def lyric_publisher(
        self,
        *,
        lyric_controller: Any,
        player_controller: Any,
    ) -> Any:
        from ..bridge.lyric_dbus_controller import LyricsDBusController

        return LyricsDBusController(
            lyric_controller=lyric_controller,
            player_controller=player_controller,
        )
