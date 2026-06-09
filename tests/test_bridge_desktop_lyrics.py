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


class _FakeLyricModel(QObject):
    """模拟 LyricLineListModel: 只需要 lineAt(idx) -> dict."""

    def __init__(self, lines: list[dict]) -> None:
        super().__init__()
        self._lines = lines

    def lineAt(self, idx: int) -> dict:
        if 0 <= idx < len(self._lines):
            return self._lines[idx]
        return {}


class _FakeLyricController(QObject):
    currentLineChanged = Signal()
    positionMsChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.currentLineText = ""
        self.activeIndex = -1
        self.positionMs = 0
        self.lyric_lines: list[dict] = []

    @property
    def lyricModel(self) -> _FakeLyricModel:
        return _FakeLyricModel(self.lyric_lines)

    def set_line(self, text: str) -> None:
        self.currentLineText = text
        self.currentLineChanged.emit()

    def advance_position(self, ms: int) -> None:
        self.positionMs = ms
        self.positionMsChanged.emit()


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


# ============================================================== 颜色 + 逐字高亮


def test_default_colors(qapp):
    """默认颜色: 未唱白 + 已唱 QQ 风格暖黄."""
    from PySide6.QtGui import QColor

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    base, hi = w.colors()
    assert isinstance(base, QColor) and isinstance(hi, QColor)
    assert base.name().upper() == "#FFFFFF"
    assert hi.name().upper() == "#FFA200"


def test_set_colors_applies(qapp):
    from PySide6.QtGui import QColor

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_colors(QColor("#112233"), QColor("#abcdef"))
    base, hi = w.colors()
    assert base.name().upper() == "#112233"
    assert hi.name().upper() == "#ABCDEF"


def test_set_line_without_words(qapp):
    """无 word 数据 -> 整句作为单 word, sung_count 总为 1 (整句高亮)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line("整行歌词", [])
    assert w._text == "整行歌词"
    assert w._words == []
    # 无 word 时, _is_sung 应该对任何 idx 都返 True
    assert w._is_word_sung(0) is True
    assert w._is_word_sung(99) is True


def test_set_line_with_words(qapp):
    """有 word 数据时, sung_count 随 progress 推进, 跨字才变."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    words = [
        {"text": "整", "startMs": 0, "durationMs": 200},
        {"text": "行", "startMs": 200, "durationMs": 200},
        {"text": "歌", "startMs": 400, "durationMs": 200},
        {"text": "词", "startMs": 600, "durationMs": 200},
    ]
    w.set_line("整行歌词", words)
    assert w._words == words
    assert w._sung_count == 0  # set_line 重置, 还没收到 progress

    w.set_progress_ms(100)
    assert w._sung_count == 1
    w.set_progress_ms(350)
    assert w._sung_count == 2
    w.set_progress_ms(1000)
    assert w._sung_count == 4  # 全部唱完
    # 拖进度条回 0: 首字 startMs=0 <= 0 算"已开始唱", 其余未到 -> sung=1
    # (与 LyricPanel.qml 用 pos>=startMs 的判定保持一致, QQ Music 风格)
    w.set_progress_ms(0)
    assert w._sung_count == 1


def test_set_line_resets_progress(qapp):
    """切到新行 -> sung_count 归 0 (新行起算)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    words = [{"text": "a", "startMs": 0, "durationMs": 100}]
    w.set_line("a", words)
    w.set_progress_ms(50)
    assert w._sung_count == 1
    w.set_line("b", [{"text": "b", "startMs": 1000, "durationMs": 100}])
    assert w._sung_count == 0  # 新行未到 startMs


def test_paint_with_words_horizontal_no_crash(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line(
        "Hello QQ",
        [
            {"text": "Hel", "startMs": 0, "durationMs": 200},
            {"text": "lo ", "startMs": 200, "durationMs": 200},
            {"text": "QQ", "startMs": 400, "durationMs": 200},
        ],
    )
    w.set_progress_ms(300)  # 1 个 word 已唱
    w.resize(800, 100)
    assert not w.grab().isNull()


def test_paint_with_words_vertical_no_crash(qapp):
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line(
        "离别",
        [
            {"text": "离", "startMs": 0, "durationMs": 200},
            {"text": "别", "startMs": 200, "durationMs": 200},
        ],
    )
    w.set_progress_ms(100)
    w.resize(80, 400)
    assert not w.grab().isNull()


def test_controller_pushes_line_with_words(qapp):
    """controller 拿到 LyricController 的 activeIndex + lyricModel.lineAt(idx) -> 推 words."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    fake.activeIndex = 0
    fake.positionMs = 150
    fake.lyric_lines = [
        {
            "lineText": "啊我啊",
            "words": [
                {"text": "啊", "startMs": 0, "durationMs": 100},
                {"text": "我", "startMs": 100, "durationMs": 100},
                {"text": "啊", "startMs": 200, "durationMs": 100},
            ],
        }
    ]
    fake.currentLineText = "啊我啊"
    ctrl = DesktopLyricsController(fake)
    fake.set_line("啊我啊")  # 重发 signal
    qapp.processEvents()
    assert ctrl.window._text == "啊我啊"
    assert len(ctrl.window._words) == 3
    # positionMs=150 -> 第 1 字唱完 (sung=2)
    assert ctrl.window._sung_count == 2


def test_controller_apply_enabled_false_hides_window(qapp):
    """apply_settings(enabled=False) -> 隐藏窗口."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    ctrl = DesktopLyricsController(fake)
    ctrl._window.show()
    qapp.processEvents()
    ctrl.apply_settings(enabled=False)
    qapp.processEvents()
    assert ctrl._window.isHidden()


def test_controller_apply_enabled_true_shows_window(qapp):
    """apply_settings(enabled=True) -> 显示窗口 (从 hidden 状态)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    ctrl = DesktopLyricsController(fake)
    ctrl.apply_settings(enabled=False)
    qapp.processEvents()
    assert ctrl._window.isHidden()
    ctrl.apply_settings(enabled=True)
    qapp.processEvents()
    assert ctrl._window.isVisible()


def test_controller_position_updates_sung_count(qapp):
    """positionMs 改变只重发不当行的话, controller 应当走 set_progress_ms 推 sung_count."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    fake.activeIndex = 0
    fake.positionMs = 0
    fake.lyric_lines = [
        {
            "lineText": "abc",
            "words": [
                {"text": "a", "startMs": 0, "durationMs": 100},
                {"text": "b", "startMs": 100, "durationMs": 100},
                {"text": "c", "startMs": 200, "durationMs": 100},
            ],
        }
    ]
    fake.currentLineText = "abc"
    ctrl = DesktopLyricsController(fake)
    fake.set_line("abc")
    qapp.processEvents()
    assert ctrl.window._sung_count == 1  # pos=0, 首字 startMs=0 已开始唱

    fake.advance_position(250)
    qapp.processEvents()
    assert ctrl.window._sung_count == 3
