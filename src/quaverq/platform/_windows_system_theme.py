"""Windows 系统主题跟随 —— 读注册表 + QTimer 2s 轮询.

类比 Linux ``SystemThemeWatcher`` (走 freedesktop portal ``color-scheme``):
- 暴露 ``dark`` Property + ``darkChanged`` Signal, 接口与 Linux 实现保持一致, QML 端无需改.
- 数据源: 注册表
  ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize\\AppsUseLightTheme``
  DWORD: 0 = 系统深色, 1 = 系统浅色 (Windows 约定; 不要混 freedesktop "1 = prefer dark" 的反向).
- 变化监听: 用 QTimer 每 2s 轮询. 比 ``RegNotifyChangeKeyValue`` 简单 + 不引线程,
  延迟最差 2s 用户可接受; QML / Qt palette 切换本身也不是即时.

为什么不用 ``RegNotifyChangeKeyValue`` 或 ``WM_SETTINGCHANGE``:
- 前者要单独线程 + Win32 同步等, 复杂度涨; 后者要监听 Qt event 拿到 Windows 消息, frameless
  窗口 + QML 这套 chrome 下接消息不直白. 等 Stage 3c SMTC 引入 winrt 时再考虑统一化.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, QTimer, Signal

if TYPE_CHECKING or sys.platform == "win32":
    import winreg

logger = logging.getLogger(__name__)

_THEME_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_VALUE_NAME = "AppsUseLightTheme"
_POLL_INTERVAL_MS = 2000


class WindowsSystemThemeWatcher(QObject):
    """读 Windows 注册表 AppsUseLightTheme, 暴露 dark Property 给 QML.

    与 Linux ``SystemThemeWatcher`` 接口对齐:
    - ``async start(timeout=1.0)``: 触发一次同步读 + 启动轮询; timeout 参数为接口兼容, 实际不用
      (注册表读是 ms 级, 不会卡, 不需要超时保护).
    - ``async stop()``: 停轮询.
    - ``dark`` (Property[bool], notify=``darkChanged``).
    """

    darkChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dark = False
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll_once)

    @Property(bool, notify=darkChanged)
    def dark(self) -> bool:  # type: ignore[override]
        return self._dark

    def _set_dark(self, value: bool) -> None:
        if self._dark == value:
            return
        self._dark = value
        self.darkChanged.emit()

    def _read_registry(self) -> bool:
        """返回"系统当前是深色吗". 读不到 (key 缺失 / 权限) -> 安全降级 False (浅色)."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _THEME_KEY_PATH) as key:
                value, _vtype = winreg.QueryValueEx(key, _VALUE_NAME)
        except (FileNotFoundError, OSError) as exc:
            # OSError 兜底覆盖 WinError 各种子类 (访问拒绝等)
            logger.debug("注册表读 %s 失败, 默认浅色: %s", _VALUE_NAME, exc)
            return False
        # AppsUseLightTheme: 0 = dark, 1 = light
        return value == 0

    def _poll_once(self) -> None:
        """同步轮询一次注册表, 触发 darkChanged (如果值变了)."""
        self._set_dark(self._read_registry())

    async def start(self, timeout: float = 1.0) -> None:
        """启动: 立刻同步读一次, 然后启动 QTimer 2s 轮询.

        timeout 是为了与 Linux ``SystemThemeWatcher.start(timeout=)`` 接口对齐, 这里没用 ——
        winreg 调用是 ms 级同步本地操作, 不需要超时保护.
        """
        del timeout  # 兼容签名, 不使用
        self._poll_once()  # 首次同步读, engine.load() 前应当已经有正确值, 避免首帧闪
        self._timer.start()
        logger.info(
            "Windows 系统主题跟随启动: 初始 dark=%s, 每 %dms 轮询", self._dark, _POLL_INTERVAL_MS
        )
        # async 接口对齐 Linux 实现; 这里没真正 await 点
        await asyncio.sleep(0)

    async def stop(self) -> None:
        self._timer.stop()
        await asyncio.sleep(0)
