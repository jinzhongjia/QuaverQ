"""Windows 平台适配器 (Stage 1 stub).

当前所有能力返回 None —— 让应用至少能在 Windows 上启动到主界面,
媒体键 / 单实例 / 系统主题暂不工作. Stage 3 会用真实实现填充:
- single_instance: 命名 Mutex (pywin32 win32event.CreateMutex)
- system_theme: 注册表 HKCU\\...\\AppsUseLightTheme + WM_SETTINGCHANGE
- media_session: SMTC (Windows.Media.SystemMediaTransportControls, 经 winrt)
"""

from __future__ import annotations

from typing import Any


class WindowsPlatform:
    """Windows 平台门面 (降级 stub)."""

    name = "windows"

    def single_instance(self) -> Any | None:
        return None

    def system_theme(self) -> Any | None:
        return None

    def media_session(self, player_controller: Any) -> Any | None:
        return None
