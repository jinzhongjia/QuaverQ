"""DesktopLyricsWindow / DesktopLyricsController 测试."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_window_has_transparent_input_flag(qapp):
    """关键: WindowTransparentForInput 让鼠标穿透到下方 (歌词窗口不挡用户点击桌面/任务栏)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    flags = w.windowFlags()
    assert flags & Qt.WindowType.WindowTransparentForInput, "缺鼠标穿透 flag, 会挡操作"
    assert flags & Qt.WindowType.FramelessWindowHint, "应当无边框"
    assert flags & Qt.WindowType.WindowStaysOnTopHint, "应当置顶"
    assert flags & Qt.WindowType.Tool, "应当不在任务栏占位"
    assert w.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert w.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_set_text_updates_internal_state(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_text("Hello QQ")
    assert w._text == "Hello QQ"
    # 相同文字不应触发 update (cheap dedup)
    w.set_text("Hello QQ")
    assert w._text == "Hello QQ"


def test_set_text_none_becomes_empty(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_text(None)  # type: ignore[arg-type]
    assert w._text == ""


def test_default_geometry_in_screen_bounds(qapp):
    """默认位置应在主屏可视区内, 至少 900 宽."""
    from PySide6.QtGui import QGuiApplication

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    geo = w.geometry()
    assert geo.width() >= 900
    assert geo.height() > 0
    screen_geo = QGuiApplication.primaryScreen().availableGeometry()
    # 窗口完全在屏幕内
    assert screen_geo.contains(geo)


class _FakeLyricController(QObject):
    currentLineChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.currentLineText = ""

    def set_line(self, text: str) -> None:
        self.currentLineText = text
        self.currentLineChanged.emit()


def test_controller_syncs_text_on_signal(qapp):
    """LyricController.currentLineChanged -> 窗口文字更新."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    ctrl = DesktopLyricsController(fake)
    fake.set_line("Test Line 1")
    qapp.processEvents()
    assert ctrl.window._text == "Test Line 1"

    fake.set_line("第二行歌词")
    qapp.processEvents()
    assert ctrl.window._text == "第二行歌词"


def test_controller_show_syncs_current_text(qapp):
    """show() 应当主动从 lyric_controller 拿当前行 (即使没新信号也能显示)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    fake.currentLineText = "已有的歌词"
    ctrl = DesktopLyricsController(fake)
    ctrl.show()
    qapp.processEvents()
    assert ctrl.window._text == "已有的歌词"
    ctrl.hide()


def test_paint_event_no_crash_with_text(qapp):
    """有文字时 paintEvent 走全流程 (路径 + 描边 + 渐变填充) 不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_text("Test")
    # 触发 paintEvent (用真实 QPaintEvent 必须 widget 已 show); 用 grab 间接触发
    w.resize(800, 100)
    pixmap = w.grab()
    assert not pixmap.isNull()


def test_paint_event_no_crash_with_empty(qapp):
    """空文字时 paintEvent 早退不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.resize(800, 100)
    pixmap = w.grab()
    assert not pixmap.isNull()


# ============================================================== Lock / Unlock 切换


def test_default_is_locked_with_input_passthrough(qapp):
    """默认锁定: 鼠标穿透."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    assert w.is_locked() is True
    assert w.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_unlock_removes_input_passthrough(qapp):
    """解锁: 去掉鼠标穿透 flag, 用户能拖动 / 右键菜单."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_locked(False)
    assert w.is_locked() is False
    assert not (w.windowFlags() & Qt.WindowType.WindowTransparentForInput)


def test_relock_restores_input_passthrough(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_locked(False)
    w.set_locked(True)
    assert w.is_locked() is True
    assert w.windowFlags() & Qt.WindowType.WindowTransparentForInput


# ============================================================== Font 设置


def test_set_font_applies(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_font_config(family="SimHei", size=40, bold=True, italic=False)
    f = w.current_font()
    assert f.family() == "SimHei"
    assert f.pointSize() == 40
    assert f.bold() is True
    assert f.italic() is False


def test_set_font_with_italic(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_font_config(family="Microsoft YaHei UI", size=28, bold=False, italic=True)
    f = w.current_font()
    assert f.italic() is True
    assert f.bold() is False


# ============================================================== Orientation


def test_default_orientation_horizontal(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    assert w.orientation() == "horizontal"


def test_set_orientation_vertical(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    assert w.orientation() == "vertical"


def test_set_orientation_unknown_rejected(qapp):
    """非 horizontal/vertical 的值应当被拒绝, 保持原值."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("diagonal")  # 不识别
    assert w.orientation() == "horizontal"


def test_vertical_orientation_paint_does_not_crash(qapp):
    """竖向画 CJK 多字不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_text("离别的眼泪我还不懂")
    w.resize(80, 600)
    pixmap = w.grab()
    assert not pixmap.isNull()


# ============================================================== Controller


def test_controller_apply_settings(qapp):
    """controller.apply_settings 应该同时设字体 / 方向 / 锁定."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    ctrl = DesktopLyricsController(fake)
    ctrl.apply_settings(
        locked=False,
        font_family="SimHei",
        font_size=30,
        bold=True,
        italic=False,
        orientation="vertical",
    )
    f = ctrl.window.current_font()
    assert f.family() == "SimHei"
    assert f.pointSize() == 30
    assert ctrl.window.orientation() == "vertical"
    assert ctrl.window.is_locked() is False
