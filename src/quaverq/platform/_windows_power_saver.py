"""Windows 防睡眠 (SetThreadExecutionState).

播放期间通过 ``ES_CONTINUOUS | ES_SYSTEM_REQUIRED`` 阻止 OS 进入待机 / 休眠;
暂停 / 停止时清除请求, 让系统正常省电.

**为什么需要**: Windows 不会因为应用在播放音频就自动阻止待机
(比如 Spotify / 网易云都各自显式调用此 API). 不做的话用户挂机听歌
电脑会因为无操作待机, 音乐中断, 用户感知极差.

**ES_DISPLAY_REQUIRED 故意不加**: 我们是音乐应用, 用户大概率把屏幕关了听歌,
保持显示器亮是 power-hostile (类似视频 / 演示应用才需要). 仅阻止系统挂起即可.

参考: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
"""

from __future__ import annotations

import ctypes
import logging
from typing import Any

from PySide6.QtCore import QObject, Slot

logger = logging.getLogger(__name__)

# 文档常量 (winbase.h)
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class WindowsPowerSaver(QObject):
    """订阅 ``player_controller.playbackStateChanged``, 播放 / 暂停时切换待机抑制."""

    def __init__(self, player_controller: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player_controller = player_controller
        self._active = False
        try:
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
            self._kernel32.SetThreadExecutionState.restype = ctypes.c_uint32
        except (OSError, AttributeError):
            self._kernel32 = None
            logger.warning("Windows kernel32 不可用, 防睡眠功能降级到 no-op")
        pb_signal = getattr(player_controller, "playbackStateChanged", None)
        if pb_signal is not None:
            pb_signal.connect(self._on_state_changed)
        self._sync()  # 启动期同步一次 (可能恢复了播放快照)

    @Slot()
    def _on_state_changed(self) -> None:
        self._sync()

    def _sync(self) -> None:
        if self._kernel32 is None:
            return
        state = str(getattr(self._player_controller, "playbackState", "") or "")
        should_keep_awake = state == "playing"
        if should_keep_awake == self._active:
            return
        if should_keep_awake:
            self._kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
            logger.info("Windows 防睡眠: 已启用 (播放中)")
        else:
            self._kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
            logger.info("Windows 防睡眠: 已撤销 (%s)", state or "stopped")
        self._active = should_keep_awake

    def release(self) -> None:
        """显式撤销, 用于退出清理. 重复调用幂等."""
        if self._kernel32 is None or not self._active:
            return
        self._kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        self._active = False
