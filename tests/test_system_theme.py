"""系统主题探测测试（freedesktop portal color-scheme）。"""

from __future__ import annotations

import sys

import pytest

from quaverq.bridge import system_theme


def test_color_scheme_dark_for_prefer_dark():
    # freedesktop 约定：1 = prefer dark
    assert system_theme.color_scheme_is_dark(1) is True


def test_color_scheme_not_dark_for_prefer_light():
    assert system_theme.color_scheme_is_dark(2) is False


def test_color_scheme_not_dark_for_no_preference():
    assert system_theme.color_scheme_is_dark(0) is False


def test_unwrap_variant_handles_nesting():
    class _V:
        def __init__(self, value):
            self.value = value

    assert system_theme.unwrap_variant(_V(_V(1))) == 1
    assert system_theme.unwrap_variant(_V(2)) == 2
    assert system_theme.unwrap_variant(0) == 0


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="portal / dbus-next 仅 Linux 装",
)
async def test_start_times_out_when_portal_unresponsive():
    """portal 挂死时 start() 必须超时返回, 不能拖慢 engine.load() 之前的同步等待."""
    import asyncio

    from PySide6.QtWidgets import QApplication

    _ = QApplication.instance() or QApplication([])
    watcher = system_theme.SystemThemeWatcher()

    from dbus_next.aio import MessageBus

    orig_connect = MessageBus.connect

    async def _stuck_connect(self):
        await asyncio.sleep(60)
        return self

    MessageBus.connect = _stuck_connect  # type: ignore[method-assign]
    try:
        # wait_for(timeout=0.05) 内部 raise TimeoutError, start() except 兜底
        # -> 不传播异常, _dark 保持初值 False.
        await watcher.start(timeout=0.05)
        assert watcher.dark is False
    finally:
        MessageBus.connect = orig_connect  # type: ignore[method-assign]
