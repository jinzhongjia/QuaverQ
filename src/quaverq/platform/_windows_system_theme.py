"""Windows 系统主题跟随 —— 注册表 + ``QStyleHints.colorSchemeChanged`` 信号驱动.

类比 Linux ``SystemThemeWatcher`` (走 freedesktop portal ``color-scheme``):
- 暴露 ``dark`` Property + ``darkChanged`` Signal, 接口与 Linux 实现保持一致.
- 数据源: 注册表
  ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize\\AppsUseLightTheme``
  DWORD: 0 = 系统深色, 1 = 系统浅色.

**触发机制**: 订阅 ``QGuiApplication.styleHints().colorSchemeChanged`` 信号 ——
Qt 内部已经钩 Windows ``WM_SETTINGCHANGE`` / ``WM_THEMECHANGED`` 广播, 系统主题
改变时它会 emit 此信号. 我们用它**作为触发器**, 收到后重读注册表拿准确值
(Qt 自身的 ``styleHints().colorScheme()`` 在某些环境上把值错映射, 不可靠;
但 SIGNAL 本身的 fire 时机是准的, 当触发器用没问题).

为什么不用 ``QAbstractNativeEventFilter`` 直接钩 ``WM_SETTINGCHANGE``: 实测
PySide6 6.x 上 ``installNativeEventFilter`` 装的 Python filter 不被调到
(filter 的 ``nativeEventFilter`` 方法压根不进, 看不到任何 WM 消息). 应该是
跟 frameless 自绘 chrome / QML 窗口组合下 Qt 派发逻辑有关, 不深挖.

为什么不轮询: 见 AGENTS.md "禁止用轮询监听外部变化".
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QGuiApplication

if TYPE_CHECKING or sys.platform == "win32":
    import winreg

logger = logging.getLogger(__name__)

_THEME_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_VALUE_NAME = "AppsUseLightTheme"


class WindowsSystemThemeWatcher(QObject):
    """事件驱动版: 注册表 + ``QStyleHints.colorSchemeChanged`` 信号.

    与 Linux ``SystemThemeWatcher`` 接口对齐:
    - ``async start(timeout=1.0)``: 同步读一次注册表 + 接 Qt colorSchemeChanged 信号.
    - ``async stop()``: 摘信号连接.
    - ``dark`` (Property[bool], notify=``darkChanged``).
    """

    darkChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dark = False
        self._connected = False

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
            logger.debug("注册表读 %s 失败, 默认浅色: %s", _VALUE_NAME, exc)
            return False
        # AppsUseLightTheme: 0 = dark, 1 = light
        return value == 0

    @Slot()
    def _on_color_scheme_changed(self) -> None:
        """Qt 内部已检测到系统主题切换 -> 我们重读注册表拿准确值."""
        new_value = self._read_registry()
        logger.info("colorSchemeChanged 触发 -> 注册表 dark=%s", new_value)
        self._set_dark(new_value)

    def _poll_once(self) -> None:
        """同步重读注册表 + 发 darkChanged. 仅测试用 (生产由 Qt 信号驱动)."""
        self._set_dark(self._read_registry())

    async def start(self, timeout: float = 1.0) -> None:
        """启动: 立刻同步读一次, 然后接 Qt colorSchemeChanged 信号."""
        del timeout  # 兼容签名, 不使用
        self._set_dark(self._read_registry())
        app = QGuiApplication.instance()
        if app is None:
            logger.warning("QGuiApplication 未实例化, colorSchemeChanged 接不上, 退化到仅初始值")
        elif not self._connected:
            try:
                app.styleHints().colorSchemeChanged.connect(self._on_color_scheme_changed)
                self._connected = True
            except (AttributeError, RuntimeError) as exc:
                logger.warning("colorSchemeChanged 连接失败: %s", exc)
        logger.info(
            "Windows 系统主题跟随启动: 初始 dark=%s (event-driven via colorSchemeChanged)",
            self._dark,
        )
        await asyncio.sleep(0)

    async def stop(self) -> None:
        if self._connected:
            app = QGuiApplication.instance()
            if app is not None:
                with contextlib.suppress(RuntimeError, TypeError):
                    app.styleHints().colorSchemeChanged.disconnect(self._on_color_scheme_changed)
            self._connected = False
        await asyncio.sleep(0)
