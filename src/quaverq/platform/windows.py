"""Windows 平台适配器.

已实现:
- single_instance: 命名 Mutex (ctypes CreateMutexW, 见 _windows_single_instance.py)
- system_theme: 注册表 AppsUseLightTheme + QTimer 2s 轮询 (见 _windows_system_theme.py)

待实现 (Stage 3c):
- media_session: SMTC (Windows.Media.SystemMediaTransportControls, 经 winrt)
- lyric_publisher: 暂无对应机制 (Linux D-Bus 的等价物在 Windows 上没有标准, 长尾)
"""

from __future__ import annotations

from typing import Any


class WindowsPlatform:
    """Windows 平台门面."""

    name = "windows"

    def single_instance(self) -> Any | None:
        from ._windows_single_instance import WindowsSingleInstance

        return WindowsSingleInstance()

    def system_theme(self) -> Any | None:
        from ._windows_system_theme import WindowsSystemThemeWatcher

        return WindowsSystemThemeWatcher()

    def media_session(
        self,
        player_controller: Any,
        *,
        raise_window: Any = None,
        quit_app: Any = None,
    ) -> Any | None:
        return None

    def lyric_publisher(
        self,
        *,
        lyric_controller: Any,
        player_controller: Any,
    ) -> Any | None:
        return None
