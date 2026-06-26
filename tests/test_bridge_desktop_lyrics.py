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
    """默认位置应在主屏可视区内; 目标宽 900 但**钳到屏宽** (窄屏不许超界).

    offscreen 平台屏幕 800 宽, 恰好充当"窄屏"用例: max(900, ...) 不钳屏时
    窗口默认就超出屏幕 —— 这是真实缺陷, 不是测试环境问题.
    """
    from PySide6.QtGui import QGuiApplication

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    geo = w.geometry()
    screen_geo = QGuiApplication.primaryScreen().availableGeometry()
    assert geo.width() >= min(900, screen_geo.width())
    assert geo.height() > 0
    # 窗口完全在屏幕内 (含窄屏)
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
        self.currentLineTranslation = ""
        self.activeIndex = -1
        self.positionMs = 0
        self.lyric_lines: list[dict] = []

    @property
    def lyricModel(self) -> _FakeLyricModel:
        return _FakeLyricModel(self.lyric_lines)

    def set_line(self, text: str, translation: str = "") -> None:
        self.currentLineText = text
        self.currentLineTranslation = translation
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


def test_controller_pushes_line_timing_for_unworded_lines(qapp):
    """无逐字行也要把当前行 / 下一行 timestamp 传给桌面歌词滚动."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    fake.activeIndex = 0
    fake.lyric_lines = [
        {"timestampMs": 1000, "lineText": "OP: 五十环音乐 Straight To Music", "words": []},
        {"timestampMs": 5000, "lineText": "下一行", "words": []},
    ]
    fake.currentLineText = "OP: 五十环音乐 Straight To Music"

    ctrl = DesktopLyricsController(fake)
    fake.currentLineChanged.emit()
    qapp.processEvents()

    assert ctrl.window._line_start_ms == 1000
    assert ctrl.window._line_end_ms == 5000


def test_word_fractions_no_words(qapp):
    """无 word -> 整句作为单段, fraction=1.0 (始终高亮色填充)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line("整行", [])
    fractions = w._word_fractions()
    assert fractions == [("整行", 1.0)]


def test_word_fractions_partial_wipe(qapp):
    """ms 在 word 中段时, fraction 介于 0~1 (按 elapsed/duration 比例)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    words = [
        {"text": "啊", "startMs": 0, "durationMs": 200},
        {"text": "我", "startMs": 200, "durationMs": 200},
    ]
    w.set_line("啊我", words)
    w.set_progress_ms(100)  # 第一个字过了一半
    fractions = w._word_fractions()
    # 由于 effective_ms 可能因 timer 已启动而稍微超过 100, 容忍 ±0.05
    assert fractions[0][0] == "啊"
    assert 0.45 <= fractions[0][1] <= 0.6
    assert fractions[1] == ("我", 0.0)  # 还没开始


def test_word_fractions_after_word_end(qapp):
    """word 结束后 fraction = 1.0."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    words = [{"text": "啊", "startMs": 0, "durationMs": 100}]
    w.set_line("啊", words)
    w.set_progress_ms(200)
    fractions = w._word_fractions()
    assert fractions[0] == ("啊", 1.0)


def test_wipe_timer_starts_when_word_active(qapp):
    """有 word 正在 wipe 时, 内部 30fps 定时器自动启动以插值平滑动画.
    必须先 set_playing(True) 才允许 timer 跑."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_playing(True)
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 500}])
    w.set_progress_ms(100)  # 中段
    assert w._wipe_timer.isActive()


def test_wipe_timer_stops_when_no_active_word(qapp):
    """无 word 正在 wipe (全过完 / 全没到) -> 定时器停, 不浪费 CPU."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 100}])
    w.set_progress_ms(200)  # 完全过了
    assert not w._wipe_timer.isActive()


def test_horizontal_wipe_clip_rectangle_when_upright(qapp):
    """直立字体: wipe clip 退化为矩形 (顶 / 底 dx = 0)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_font_config(family="Microsoft YaHei UI", size=32, bold=True, italic=False)
    w.resize(800, 100)
    path = w._make_horizontal_wipe_clip(100.0, 50.0, 60.0)
    rect = path.boundingRect()
    # 直立矩形: 宽 = width_px, 高 = widget.height
    assert abs(rect.width() - 50.0) < 0.01
    assert abs(rect.height() - 100.0) < 0.01


def test_horizontal_wipe_clip_skewed_when_italic(qapp):
    """斜体: clip 是平行四边形, bounding rect 比矩形宽 (上下边各 shear 一段)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_font_config(family="Microsoft YaHei UI", size=32, bold=True, italic=True)
    w.resize(800, 100)
    path = w._make_horizontal_wipe_clip(100.0, 50.0, 60.0)
    rect = path.boundingRect()
    # 斜体: bounding 比矩形多了 (baseline*shear + (h-baseline)*shear) = h * shear
    # h=100, shear≈0.213 -> 多了 ~21.3, 总宽 > 70
    assert rect.width() > 65.0
    assert abs(rect.height() - 100.0) < 0.01


def test_outline_width_is_thin(qapp):
    """描边收细到 3px (粗描边遮字, 像贴纸)."""
    from quaverq.bridge import desktop_lyrics as dl

    assert dl._OUTLINE_WIDTH == 3


def test_default_font_is_extra_bold(qapp):
    """默认字重应到 Black (900) 区间; 字号大时字脚才有"印刷"质感.
    family 缺 Black 时 Qt 会自动 fallback 到家族最接近的字重 (通常是 Bold)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    weight = w.current_font().weight()
    assert weight >= 800  # ExtraBold(800) 或 Black(900) 都算合格


def test_fill_brush_for_gradient(qapp):
    """填色 brush 应该是 LinearGradient (单色 + 微暗下半截), 不是纯色."""
    from PySide6.QtCore import Qt as Qt_

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w._ensure_brush_cache()
    brush = w._cached_brush_highlight
    # 渐变 brush 的 style != SolidPattern
    assert brush.style() == Qt_.BrushStyle.LinearGradientPattern


def test_font_has_letter_spacing(qapp):
    """默认字体应当带 PercentageSpacing > 100, 让字之间不挤."""
    from PySide6.QtGui import QFont

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    f = w.current_font()
    assert f.letterSpacingType() == QFont.SpacingType.PercentageSpacing
    assert f.letterSpacing() > 100.0


def test_set_font_config_preserves_letter_spacing(qapp):
    """改字体 family / size / bold 不该把字间距重置回默认 100%."""
    from PySide6.QtGui import QFont

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    original_spacing = w.current_font().letterSpacing()
    w.set_font_config(family="SimHei", size=40, bold=True, italic=True)
    f = w.current_font()
    assert f.letterSpacingType() == QFont.SpacingType.PercentageSpacing
    assert abs(f.letterSpacing() - original_spacing) < 0.01


def test_default_not_playing(qapp):
    """初始默认 playing=False, 避免启动期 timer 自己往前跑."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    assert w.is_playing() is False


def test_set_playing_false_blocks_wipe_timer(qapp):
    """playing=False 时即使 active wipe 也不该启动 timer."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_playing(False)
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 500}])
    w.set_progress_ms(100)  # active wipe 中段
    assert not w._wipe_timer.isActive()


def test_set_playing_true_starts_wipe_timer(qapp):
    """playing=True 时 active wipe 自动启 timer."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_playing(True)
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 500}])
    w.set_progress_ms(100)
    assert w._wipe_timer.isActive()


def test_effective_ms_no_interpolation_when_paused(qapp):
    """暂停时 effective_ms == anchor_ms, 不允许 wall-clock 把字"自己唱过去"."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_playing(False)
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 500}])
    w.set_progress_ms(100)
    # 即使 perf_counter 走了, 仍返 anchor_ms
    import time

    time.sleep(0.05)
    assert w._effective_ms() == 100


def test_effective_ms_caps_extrapolation_when_no_recent_tick(qapp):
    """超过 _MAX_INTERP_DELTA_MS 没新 position tick -> 冻在 anchor, 不让 wall-clock 把字"自己唱过去".

    场景: 用户点播放 -> playbackState=playing -> set_playing(True) 但 positionMs 还停在 0
    (音乐在加载). 30fps timer 不允许靠 perf_counter 一路推到 effective_ms=N 秒,
    否则真实 positionChanged 来时 anchor 重置, 视觉跳回起点.
    """
    import time

    from quaverq.bridge import desktop_lyrics as dl
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_playing(True)
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 5000}])
    w.set_progress_ms(100)
    # 立刻取: 与 anchor 差距很小
    assert abs(w._effective_ms() - 100) < 30
    # 等到超过 cap 没新 tick -> 应冻在 anchor=100, 不外推到几百
    time.sleep((dl._MAX_INTERP_DELTA_MS + 50) / 1000.0)
    assert w._effective_ms() == 100


def test_wipe_timer_stops_when_position_tick_stale(qapp):
    """timer tick 中发现已 stale (无新 position 超过 cap) -> 自动停, 等下一次 set_progress_ms 重启."""
    import time

    from quaverq.bridge import desktop_lyrics as dl
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_playing(True)
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 5000}])
    w.set_progress_ms(100)
    assert w._wipe_timer.isActive()
    time.sleep((dl._MAX_INTERP_DELTA_MS + 50) / 1000.0)
    qapp.processEvents()  # 让 timer tick 跑一次, 应当自停
    assert not w._wipe_timer.isActive()


def test_set_playing_false_stops_running_timer(qapp):
    """播放中暂停: timer 立刻停 (不允许暂停后还 30fps 跑)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_playing(True)
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 500}])
    w.set_progress_ms(100)
    assert w._wipe_timer.isActive()
    w.set_playing(False)
    assert not w._wipe_timer.isActive()


def test_wipe_timer_stops_on_hide(qapp):
    """窗口隐藏时定时器停 (即便有 active word)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_playing(True)
    w.set_line("啊", [{"text": "啊", "startMs": 0, "durationMs": 500}])
    w.show()
    qapp.processEvents()
    w.set_progress_ms(100)
    assert w._wipe_timer.isActive()
    w.hide()
    qapp.processEvents()
    assert not w._wipe_timer.isActive()


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


# ============================================================== 翻译


def test_set_line_with_translation(qapp):
    """set_line 接受 translation 参数."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line("Don't Cry", [], translation="说好不哭")
    assert w._text == "Don't Cry"
    assert w._translation == "说好不哭"


def test_set_text_clears_translation(qapp):
    """set_text 应清空之前的翻译."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line("Don't Cry", [], translation="说好不哭")
    assert w._translation == "说好不哭"
    w.set_text("Another line")
    assert w._translation == ""


def test_paint_horizontal_with_translation_no_crash(qapp):
    """横向 + 翻译: paintEvent 不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line("Don't Cry", [], translation="说好不哭")
    w.resize(800, 130)
    assert not w.grab().isNull()


def test_paint_vertical_cjk_with_translation_no_crash(qapp):
    """竖向 CJK + 翻译: paintEvent 不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line("离别的眼泪", [], translation="Tears of parting")
    w.resize(120, 600)
    assert not w.grab().isNull()


def test_paint_vertical_rotated_with_translation_no_crash(qapp):
    """竖向拉丁 (旋转 90°) + 翻译: paintEvent 不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line("Don't Cry", [], translation="说好不哭")
    w.resize(120, 600)
    assert not w.grab().isNull()


def test_paint_horizontal_mixed_translation_no_crash(qapp):
    """横向 + 中英混合翻译: paintEvent 不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line("夜に駆ける", [], translation="向夜晚奔去 Racing into the Night")
    w.resize(800, 130)
    assert not w.grab().isNull()


def test_horizontal_long_lyric_scrolls_with_progress(qapp):
    """横向超长歌词保持字号不缩放, 按逐字进度向左滚动."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    words = [
        {"text": "I need to ", "startMs": 0, "durationMs": 1000},
        {"text": "shoot right up ", "startMs": 1000, "durationMs": 1000},
        {"text": "into the night ", "startMs": 2000, "durationMs": 1000},
        {"text": "and keep running forever", "startMs": 3000, "durationMs": 1000},
    ]
    w.set_line("".join(word["text"] for word in words), words)
    w.resize(360, 130)

    w.set_progress_ms(0)
    early = w._horizontal_layout()
    w.set_progress_ms(3800)
    late = w._horizontal_layout()

    assert early.scale == 1.0
    assert late.scale == 1.0
    assert w._h_total_w > w.width()
    assert late.main_x < early.main_x
    assert late.main_x < 0


def test_controller_syncs_translation(qapp):
    """controller 从 LyricController 拉 currentLineTranslation."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    ctrl = DesktopLyricsController(fake)
    fake.set_line("Shape of You", "你的轮廓")
    qapp.processEvents()
    assert ctrl.window._text == "Shape of You"
    assert ctrl.window._translation == "你的轮廓"


def test_controller_clears_translation_when_absent(qapp):
    """翻译为空时 controller 也正确传 ''."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsController

    fake = _FakeLyricController()
    ctrl = DesktopLyricsController(fake)
    fake.set_line("Shape of You", "你的轮廓")
    qapp.processEvents()
    assert ctrl.window._translation == "你的轮廓"
    fake.set_line("Next line")
    qapp.processEvents()
    assert ctrl.window._translation == ""


def test_translation_font_is_smaller(qapp):
    """翻译字体应为主字体的 60%."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_line("Test", [], translation="测试")
    main_size = w._font.pointSize()
    trans_size = w._trans_font.pointSize()
    assert trans_size == max(12, int(main_size * 0.6))


# ============================================================== 竖向混排 (CJK + Latin)


def test_segment_for_vertical_mixed():
    """验证文本分段: CJK 字符竖排堆叠, 长 Latin 连续段成组旋转."""
    from quaverq.bridge.desktop_lyrics import _segment_for_vertical

    segs = _segment_for_vertical("曲：Douji-T")
    # "曲" CJK, "：" fullwidth punct → vertical; "Douji-T" 长 Latin → rotated
    assert len(segs) >= 2
    assert all(s[1] is True for s in segs if all(_is_v(c) for c in s[0]))
    assert segs[-1] == ("Douji-T", False)


def test_segment_for_vertical_pure_cjk():
    """纯 CJK 文本只有一个竖排段."""
    from quaverq.bridge.desktop_lyrics import _segment_for_vertical

    segs = _segment_for_vertical("离别的眼泪")
    assert len(segs) == 1
    assert segs[0] == ("离别的眼泪", True)


def test_segment_for_vertical_pure_latin():
    """纯 Latin 文本整段作为一个旋转块, 不拆词."""
    from quaverq.bridge.desktop_lyrics import _segment_for_vertical

    segs = _segment_for_vertical("Hello World")
    assert segs == [("Hello World", False)]


def test_segment_for_vertical_interleaved():
    """中英交替: '我爱你baby再见'."""
    from quaverq.bridge.desktop_lyrics import _segment_for_vertical

    segs = _segment_for_vertical("我爱你baby再见")
    assert segs == [("我爱你", True), ("baby", False), ("再见", True)]


def test_segment_for_vertical_latin_multi_word():
    """Latin 多词整段作为一个旋转块, CJK 段正立."""
    from quaverq.bridge.desktop_lyrics import _segment_for_vertical

    segs = _segment_for_vertical("Can't read my 读不懂我")
    assert segs == [
        ("Can't read my", False),
        ("读不懂我", True),
    ]


def test_segment_for_vertical_latin_with_trailing_space():
    """QRC 逐字常带尾部空格, 拆分后应去掉."""
    from quaverq.bridge.desktop_lyrics import _segment_for_vertical

    segs = _segment_for_vertical("Fold ")
    assert segs == [("Fold", False)]


def test_segment_for_vertical_short_uppercase_acronym_rotates():
    """简化后短大写缩写不再特判直立, 与普通拉丁一样整段旋转."""
    from quaverq.bridge.desktop_lyrics import _segment_for_vertical

    segs = _segment_for_vertical("如果我是 DJ")
    assert segs == [("如果我是", True), ("DJ", False)]


def test_segment_for_vertical_lowercase_word_still_rotates():
    """普通英文短词仍旋转, 避免把翻译词 'my' 拆成 m/y 竖排."""
    from quaverq.bridge.desktop_lyrics import _segment_for_vertical

    segs = _segment_for_vertical("读不懂 my")
    assert segs == [("读不懂", True), ("my", False)]


def test_vertical_acronym_rotates_as_single_block(qapp):
    """简化后竖排中 'DJ' 不再特判直立, 作为单个旋转块."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line(
        "如果我是 DJ 是 DJ",
        [
            {"text": "如果我是 ", "startMs": 0, "durationMs": 500},
            {"text": "DJ ", "startMs": 500, "durationMs": 300},
            {"text": "是 ", "startMs": 800, "durationMs": 300},
            {"text": "DJ", "startMs": 1100, "durationMs": 300},
        ],
    )

    dj_word_blocks = [
        blocks
        for word, blocks in zip(w._display_words, w._v_word_blocks, strict=True)
        if word.text.strip() == "DJ"
    ]
    assert len(dj_word_blocks) == 2
    for blocks in dj_word_blocks:
        assert len(blocks) == 1
        assert blocks[0].rotated is True


def test_vertical_pure_latin_single_rotated_block(qapp):
    """纯拉丁整行作为一个旋转块 (无逐字数据时单 display word)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_text("Hello World")
    assert len(w._v_word_blocks) == 1
    blocks = w._v_word_blocks[0]
    assert len(blocks) == 1
    assert blocks[0].rotated is True
    assert w._v_total_v_height > 0


def test_vertical_credit_line_no_crash(qapp):
    """制作信息行统一走块模型: 标点正立 + 拉丁旋转, 不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_text("SP：五十环音乐 Straight50 Music")
    w.resize(120, 600)
    assert not w.grab().isNull()


def test_paint_vertical_mixed_no_crash(qapp):
    """竖向混合中英文 (如 '曲：Douji-T') paintEvent 不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_text("曲：Douji-T")
    w.resize(120, 600)
    assert not w.grab().isNull()


def test_paint_vertical_mixed_with_words_no_crash(qapp):
    """竖向混合中英文 + 逐字数据 + wipe 动画不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line(
        "我爱你baby",
        [
            {"text": "我", "startMs": 0, "durationMs": 200},
            {"text": "爱", "startMs": 200, "durationMs": 200},
            {"text": "你", "startMs": 400, "durationMs": 200},
            {"text": "baby", "startMs": 600, "durationMs": 400},
        ],
    )
    w.set_progress_ms(500)
    w.resize(120, 600)
    assert not w.grab().isNull()


def test_paint_vertical_mixed_with_translation_no_crash(qapp):
    """竖向混排 + 翻译不抛."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line("词：Douji-T/一只然", [], translation="Lyrics by Douji-T")
    w.resize(200, 600)
    assert not w.grab().isNull()


def test_vertical_trans_cjk_blocks_not_rotated(qapp):
    """翻译 CJK 块必须 rotated=False (正着堆叠, 不旋转)."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line(
        "Fold 'em 让他们",
        [
            {"text": "Fold ", "startMs": 0, "durationMs": 500},
            {"text": "'em ", "startMs": 500, "durationMs": 500},
            {"text": "让他们", "startMs": 1000, "durationMs": 500},
        ],
        translation="Can't read my 读不懂我",
    )
    assert w._has_trans is True
    for blk in w._v_trans_blocks:
        if not blk.rotated:
            assert blk.v_height > 0


def test_vertical_dual_column_layout(qapp):
    """竖排有翻译时, 歌词右列 + 翻译左列, main_cx > trans_cx."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line("你好世界", [], translation="Hello World")
    w.resize(200, 600)
    main_cx, trans_cx = w._vcol_positions()
    assert main_cx > trans_cx


def test_vertical_translation_is_centered_to_main_lyric(qapp):
    """竖排翻译列应围绕主歌词中心线居中, 不能从主歌词顶端开始排."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line("我要直冲云霄奔向夜空", [], translation="I need to shoot right up into the night")
    w.resize(240, 900)

    layout = w._vertical_column_layout()
    main_center = (
        layout.main_start_y - layout.main_ascent * layout.scale + layout.main_h * layout.scale / 2.0
    )
    trans_center = (
        layout.trans_start_y
        - layout.trans_ascent * layout.scale
        + layout.trans_h * layout.scale / 2.0
    )

    assert abs(main_center - trans_center) < 1.0


def test_vertical_long_main_lyric_scrolls_with_progress(qapp):
    """竖排超长歌词保持字号不缩放, 按逐字进度向上滚动."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    text = "我要直冲云霄奔向夜空穿过黑暗直到黎明"
    words = [{"text": ch, "startMs": i * 200, "durationMs": 200} for i, ch in enumerate(text)]
    w.set_line(text, words)
    w.resize(160, 360)

    w.set_progress_ms(0)
    early = w._vertical_column_layout()
    w.set_progress_ms((len(text) - 1) * 200)
    late = w._vertical_column_layout()

    assert early.scale == 1.0
    assert late.scale == 1.0
    assert early.main_h > w.height()
    assert late.main_start_y < early.main_start_y
    assert late.main_start_y - late.main_ascent < 0


def test_vertical_long_line_without_words_scrolls_by_line_timing(qapp):
    """无逐字 timing 的长信息行也要按行级 timing 滚到末尾, 不能静态裁掉最后字符."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line(
        "OP: 五十环音乐 Straight To Music",
        [],
        line_start_ms=1000,
        line_end_ms=5000,
    )
    w.resize(180, 520)

    w.set_progress_ms(1000)
    early = w._vertical_column_layout()
    w.set_progress_ms(5000)
    late = w._vertical_column_layout()

    assert early.scale == 1.0
    assert late.scale == 1.0
    assert late.main_start_y < early.main_start_y
    assert late.main_start_y - late.main_ascent + late.main_h <= w.height()


def test_vertical_rotated_latin_block_height_covers_visual_bounds(qapp):
    """旋转 Latin 块高度必须按真实路径 bbox 计算, 不只用 horizontalAdvance."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_text("我听见 Straight50 Music")

    last_block = w._v_word_blocks[-1][-1]
    bounds = last_block.path.boundingRect()

    assert last_block.rotated is True
    assert bounds.left() >= 0
    assert bounds.right() <= last_block.content_h


def test_paint_vertical_mixed_credit_line_no_crash(qapp):
    """制作信息行 '曲：Douji-T' 竖向渲染不抛, Latin 段旋转显示."""
    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_text("词：Douji-T/一只然/1E")
    w.resize(120, 600)
    assert not w.grab().isNull()


def test_vertical_mixed_wipe_clip_covers_rotated_block(qapp):
    """竖向混排 wipe clip 必须覆盖旋转 Latin 块的完整视觉高度.

    修复前 clip_h = word_h * fraction, 顶部偏移 ascent 消耗了 clip 空间,
    导致末尾旋转块底部 ~(ascent-gap) px 永远不被高亮.
    """
    from PySide6.QtGui import QFontMetrics

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_orientation("vertical")
    w.set_line(
        "我baby",
        [{"text": "我baby", "startMs": 0, "durationMs": 1000}],
    )
    w.resize(200, 600)
    fm = QFontMetrics(w._font)
    ascent = fm.ascent()

    assert len(w._v_word_blocks) == 1
    blocks = w._v_word_blocks[0]
    rotated_blocks = [b for b in blocks if b.rotated]
    assert rotated_blocks, "应有旋转 Latin 块"
    last_blk = blocks[-1]
    assert last_blk.rotated is True

    word_h = w._v_word_v_heights[0]
    clip_total = word_h + ascent
    clip_h_full = int(round(clip_total * 1.0))
    assert clip_h_full >= last_blk.content_h + ascent, (
        f"clip_h ({clip_h_full}) 必须覆盖旋转块视觉高度 + ascent 偏移 "
        f"({last_blk.content_h} + {ascent})"
    )


def _is_v(c):
    """test helper: inline CJK/fullwidth char check."""
    cp = ord(c)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x3040 <= cp <= 0x309F
        or 0x30A0 <= cp <= 0x30FF
        or 0xAC00 <= cp <= 0xD7AF
        or 0x3000 <= cp <= 0x303F
        or 0xFF00 <= cp <= 0xFF60
        or 0xFE30 <= cp <= 0xFE4F
    )


# ============================================================== 记住拖动后的位置


def _mouse_event(kind):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    p = QPointF(0.0, 0.0)
    buttons = (
        Qt.MouseButton.LeftButton
        if kind == QEvent.Type.MouseButtonPress
        else Qt.MouseButton.NoButton
    )
    return QMouseEvent(
        kind, p, p, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier
    )


def test_drag_persists_geometry_and_emits(qapp):
    """解锁后拖动结束应记住当前几何并发 geometryEdited(orientation, x, y, w, h)."""
    from PySide6.QtCore import QEvent

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_locked(False)
    captured = []
    w.geometryEdited.connect(lambda *a: captured.append(a))

    w.setGeometry(123, 234, 400, 120)
    w.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress))
    w.mouseReleaseEvent(_mouse_event(QEvent.Type.MouseButtonRelease))

    assert captured, "拖动结束应发 geometryEdited"
    orientation, x, y, ww, hh = captured[-1]
    g = w.geometry()
    assert orientation == "horizontal"
    assert (x, y, ww, hh) == (g.x(), g.y(), g.width(), g.height())
    assert w._saved_geometries["horizontal"] is not None


def test_locked_drag_does_not_persist(qapp):
    """锁定态: 鼠标穿透, 不进入拖动, 不应回写位置."""
    from PySide6.QtCore import QEvent

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()  # 默认锁定
    captured = []
    w.geometryEdited.connect(lambda *a: captured.append(a))

    w.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress))
    w.mouseReleaseEvent(_mouse_event(QEvent.Type.MouseButtonRelease))

    assert captured == []


def test_saved_geometry_applied_per_orientation(qapp):
    """切方向时各用各方向记忆的位置."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    avail = QGuiApplication.primaryScreen().availableGeometry()
    h_rect = QRect(avail.x() + 10, avail.y() + 10, 300, 100)
    v_rect = QRect(avail.x() + 20, avail.y() + 20, 180, 360)

    w = DesktopLyricsWindow()
    w.set_saved_geometries(h_rect, v_rect)
    assert w.geometry().topLeft() == h_rect.topLeft()

    w.set_orientation("vertical")
    assert w.geometry().topLeft() == v_rect.topLeft()

    w.set_orientation("horizontal")
    assert w.geometry().topLeft() == h_rect.topLeft()


def test_offscreen_saved_geometry_falls_back_to_default(qapp):
    """记忆位置完全离屏 (拔副屏) 时回退默认几何, 不把窗口定位到看不见处."""
    from PySide6.QtCore import QRect

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    w = DesktopLyricsWindow()
    w.set_saved_geometries(QRect(100000, 100000, 300, 100), None)
    g = w.geometry()
    assert g.x() < 100000 and g.y() < 100000


def test_show_event_reapplies_saved_geometry(qapp):
    """模拟 Windows show() 把 frameless 窗口移回默认: showEvent 应拉回记忆位置."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication, QShowEvent

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    avail = QGuiApplication.primaryScreen().availableGeometry()
    saved = QRect(avail.x() + 12, avail.y() + 34, 360, 110)
    w = DesktopLyricsWindow()
    w.set_saved_geometries(saved, None)
    # 模拟窗口管理器在 show 时把窗口挪到别处
    w.setGeometry(avail.x() + 250, avail.y() + 250, 360, 110)
    w.showEvent(QShowEvent())
    assert w.geometry().topLeft() == saved.topLeft()


def test_set_locked_preserves_position(qapp):
    """锁 / 解锁切换 (setWindowFlags) 不应丢失当前位置."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication

    from quaverq.bridge.desktop_lyrics import DesktopLyricsWindow

    avail = QGuiApplication.primaryScreen().availableGeometry()
    w = DesktopLyricsWindow()
    target = QRect(avail.x() + 15, avail.y() + 25, 360, 110)
    w.setGeometry(target)
    w.set_locked(False)
    assert w.geometry().topLeft() == target.topLeft()
    w.set_locked(True)
    assert w.geometry().topLeft() == target.topLeft()


def test_controller_persists_dragged_geometry_to_settings(qapp, tmp_path):
    """窗口 geometryEdited -> SettingsController 落盘, 重载后可读回."""
    from PySide6.QtCore import QSettings

    from quaverq.bridge.desktop_lyrics import DesktopLyricsController
    from quaverq.bridge.settings_controller import SettingsController

    path = tmp_path / "s.ini"
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.clear()
    sc = SettingsController(settings=settings)
    fake = _FakeLyricController()
    ctrl = DesktopLyricsController(fake, settings_controller=sc)

    ctrl.window.geometryEdited.emit("horizontal", 50, 60, 400, 120)
    qapp.processEvents()

    assert sc.desktopLyricsGeometryHorizontal == "50,60,400,120"
    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.desktopLyricsGeometryHorizontal == "50,60,400,120"
    assert reloaded.desktopLyricsGeometryVertical == ""
    ctrl.hide()


def test_controller_positions_window_from_saved_geometry(qapp, tmp_path):
    """启动期 SettingsController 里已有记忆位置 -> 窗口定位到该位置."""
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QGuiApplication

    from quaverq.bridge.desktop_lyrics import DesktopLyricsController
    from quaverq.bridge.settings_controller import SettingsController

    avail = QGuiApplication.primaryScreen().availableGeometry()
    x = avail.x() + 30
    y = avail.y() + 40
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.clear()
    settings.setValue("desktopLyrics/geometryHorizontal", f"{x},{y},420,140")
    settings.sync()
    sc = SettingsController(settings=settings)
    fake = _FakeLyricController()
    ctrl = DesktopLyricsController(fake, settings_controller=sc)
    qapp.processEvents()

    g = ctrl.window.geometry()
    assert (g.x(), g.y()) == (x, y)
    ctrl.hide()
