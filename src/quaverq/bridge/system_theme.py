"""系统亮/暗主题探测 —— 直接读 freedesktop portal ``color-scheme``。

**不依赖 Qt ``styleHints.colorScheme``**：实测某些 PySide6 版本在 GNOME / Wayland 下，
把 portal 的 freedesktop 约定（1 = prefer-dark）错误映射成 Qt 的 ``Light``（Qt 约定
1=Light / 2=Dark），导致"跟随系统"在系统暗色时仍显示浅色。SystemPalette 在 Basic
样式下也不反映系统暗色，fallback 同样失效。

freedesktop ``org.freedesktop.appearance / color-scheme`` 约定：
``0`` = no preference，``1`` = prefer dark，``2`` = prefer light。
"""

from __future__ import annotations

import contextlib
import logging

from PySide6.QtCore import Property, QObject, Signal

logger = logging.getLogger(__name__)

_PORTAL_DEST = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_IFACE = "org.freedesktop.portal.Settings"
_APPEARANCE_NS = "org.freedesktop.appearance"
_COLOR_SCHEME_KEY = "color-scheme"
_PREFER_DARK = 1


def color_scheme_is_dark(value: object) -> bool:
    """freedesktop color-scheme 值是否表示暗色（1 = prefer dark）。"""
    return value == _PREFER_DARK


def unwrap_variant(value: object) -> object:
    """递归解包 dbus ``Variant``（可能多层嵌套），取底层值。"""
    seen = 0
    while hasattr(value, "value") and seen < 8:
        value = value.value
        seen += 1
    return value


class SystemThemeWatcher(QObject):
    """读 portal color-scheme 并监听变化，把"系统是否暗色"暴露给 QML。"""

    darkChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dark = False
        self._bus = None

    @Property(bool, notify=darkChanged)
    def dark(self) -> bool:
        return self._dark

    def _set_dark(self, value: bool) -> None:
        if self._dark == value:
            return
        self._dark = value
        self.darkChanged.emit()

    async def start(self) -> None:
        # 直接 bus.call，不 introspect：portal 对象里有含连字符的非法 D-Bus 成员名
        # (如 power-saver-enabled)，dbus-next introspect 会因严格校验整体抛错。
        try:
            from dbus_next import BusType, Message, MessageType
            from dbus_next.aio import MessageBus

            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
            reply = await self._bus.call(
                Message(
                    destination=_PORTAL_DEST,
                    path=_PORTAL_PATH,
                    interface=_PORTAL_IFACE,
                    member="Read",
                    signature="ss",
                    body=[_APPEARANCE_NS, _COLOR_SCHEME_KEY],
                )
            )
            if reply.message_type == MessageType.METHOD_RETURN and reply.body:
                self._set_dark(color_scheme_is_dark(unwrap_variant(reply.body[0])))
            await self._bus.call(
                Message(
                    destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    interface="org.freedesktop.DBus",
                    member="AddMatch",
                    signature="s",
                    body=[
                        f"type='signal',sender='{_PORTAL_DEST}',"
                        f"interface='{_PORTAL_IFACE}',member='SettingChanged'"
                    ],
                )
            )
            self._bus.add_message_handler(self._on_message)
            logger.info("系统主题跟随 portal color-scheme: dark=%s", self._dark)
        except Exception as exc:
            logger.warning("portal color-scheme 不可用，跟随系统回退默认浅色: %s", exc)

    def _on_message(self, message: object) -> None:
        from dbus_next import MessageType

        if (
            getattr(message, "message_type", None) == MessageType.SIGNAL
            and getattr(message, "interface", None) == _PORTAL_IFACE
            and getattr(message, "member", None) == "SettingChanged"
            and len(message.body) >= 3
            and message.body[0] == _APPEARANCE_NS
            and message.body[1] == _COLOR_SCHEME_KEY
        ):
            self._set_dark(color_scheme_is_dark(unwrap_variant(message.body[2])))

    async def stop(self) -> None:
        if self._bus is not None:
            with contextlib.suppress(Exception):
                self._bus.disconnect()
            self._bus = None
