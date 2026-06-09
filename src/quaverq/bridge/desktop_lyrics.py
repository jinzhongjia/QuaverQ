"""桌面悬浮歌词窗 —— **仅 Windows**.

类似 QQ 音乐 / 网易云的桌面歌词: 大字号歌词文字 + 描边 + 逐字高亮 (已唱 / 未唱
两种颜色), 鼠标完全穿透, 总是置顶但不抢焦点. 用户可以:

- 解锁后拖动调整位置
- 调字体 / 字号 / 粗细 / 斜体
- 切换横向 / 竖向显示
- 选未唱 / 已唱两种颜色 (QColorDialog)

**Linux / macOS 故意不启用** (见 ``platform/base.py`` ``desktop_lyrics`` docstring):
Wayland 多家 compositor 下 frameless + transparent + input-passthrough 组合行为
不一致 (焦点抢占 / z-order / 透明合成怪异), 不写跨 compositor 兜底.

Qt 实现要点:
- ``Qt.FramelessWindowHint``: 无边框无装饰
- ``Qt.WindowStaysOnTopHint``: 置顶
- ``Qt.Tool``: 不在任务栏占位 / 不参与 Alt-Tab
- ``Qt.WindowTransparentForInput``: 鼠标事件穿透到下层窗口 (锁定状态才加)
- ``WA_TranslucentBackground``: 窗口背景透明
- ``WA_ShowWithoutActivating``: show 时不抢焦点
- 绘制: ``QPainterPath.addText`` 拿文字路径, 描边 (黑色) + 逐字色块填充

逐字高亮契约 (与 ``LyricController`` / ``LyricLineListModel`` 对齐):
- ``set_line(text, words)``: words = [{"text", "startMs", "durationMs"}, ...] 或 []
- ``set_progress_ms(ms)``: 当前播放位置, 据 words[i].startMs 计算 sung_count
- words 为空时 (无逐字数据) -> 整行始终视为"已唱"用 highlight 色
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


_ORIENTATIONS = ("horizontal", "vertical")
_DEFAULT_COLOR_BASE = QColor("#FFFFFF")
_DEFAULT_COLOR_HIGHLIGHT = QColor("#FFA200")  # 深琥珀 / QQ Music 风格暖橙
_OUTLINE_COLOR = QColor(0, 0, 0, 220)
_OUTLINE_WIDTH = 5


class DesktopLyricsWindow(QWidget):
    """无边框 + 透明 + 可锁定 + 逐字高亮的桌面歌词窗口."""

    _BASE_FLAGS = (
        Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._text = ""
        self._words: list[dict[str, Any]] = []
        self._sung_count = 0
        self._locked = True
        self._orientation = "horizontal"
        self._font = QFont("Microsoft YaHei UI", 32, QFont.Weight.Bold)
        self._color_base = QColor(_DEFAULT_COLOR_BASE)
        self._color_highlight = QColor(_DEFAULT_COLOR_HIGHLIGHT)
        self._drag_origin: QPoint | None = None

        self._apply_window_flags()
        self._set_default_geometry()

    # ------------------------------------------------------------------ 状态查询
    def is_locked(self) -> bool:
        return self._locked

    def orientation(self) -> str:
        return self._orientation

    def current_font(self) -> QFont:
        return QFont(self._font)  # 返副本防外部修改

    def colors(self) -> tuple[QColor, QColor]:
        """(未唱色, 已唱色) 副本."""
        return QColor(self._color_base), QColor(self._color_highlight)

    # ------------------------------------------------------------------ 状态修改
    def set_text(self, text: str) -> None:
        """back-compat 入口: 无逐字数据 -> 整句作为单段 (始终高亮)."""
        text = text or ""
        if text == self._text and not self._words:
            return
        self._text = text
        self._words = []
        self._sung_count = 0
        self.update()

    def set_line(self, text: str, words: list[dict[str, Any]] | None) -> None:
        """更新当前行 + 逐字时间. words 为 None / [] 时整句作为单段高亮."""
        text = text or ""
        words = list(words or [])
        if text == self._text and words == self._words:
            return
        self._text = text
        self._words = words
        self._sung_count = 0  # 新行重算; 接着会有 set_progress_ms 推上来
        self.update()

    def set_progress_ms(self, position_ms: int) -> None:
        """根据当前 ms 算出 ``sung_count``; 跨字才 update, 不每帧重绘."""
        try:
            ms = int(position_ms)
        except (TypeError, ValueError):
            return
        if not self._words:
            return
        new_count = 0
        for w in self._words:
            start = w.get("startMs", 0)
            if ms >= start:
                new_count += 1
            else:
                break  # words 已按 startMs 升序
        if new_count != self._sung_count:
            self._sung_count = new_count
            self.update()

    def set_colors(self, base: QColor, highlight: QColor) -> None:
        if not isinstance(base, QColor) or not base.isValid():
            return
        if not isinstance(highlight, QColor) or not highlight.isValid():
            return
        self._color_base = QColor(base)
        self._color_highlight = QColor(highlight)
        self.update()

    def set_locked(self, locked: bool) -> None:
        """切换锁定状态.

        锁定: ``WindowTransparentForInput`` 鼠标穿透到下层 (桌面 / 任务栏正常用).
        解锁: 去掉穿透 flag, 用户能拖动 + 右键调出菜单 + 拖角调大小.
        修 flag 必须 setWindowFlags + show 再次激活, 透明窗口不影响 (不掉内容).
        """
        if self._locked == locked:
            return
        self._locked = locked
        was_visible = self.isVisible()
        self._apply_window_flags()
        if was_visible:
            # setWindowFlags 后 Qt 会隐藏窗口, 需要重 show.
            self.show()
        self.update()

    def set_font_config(
        self,
        *,
        family: str | None = None,
        size: int | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
    ) -> None:
        """更新字体. 单个字段为 None 时保留原值."""
        font = QFont(self._font)
        if family:
            font.setFamily(family)
        if size is not None and size > 0:
            font.setPointSize(int(size))
        if bold is not None:
            font.setBold(bool(bold))
        if italic is not None:
            font.setItalic(bool(italic))
        self._font = font
        self.update()

    def set_orientation(self, orientation: str) -> None:
        """方向: ``horizontal`` 横向 (默认) / ``vertical`` 竖向 (每字独立绘制).

        非合法值时静默忽略 (保护设置文件破损 / 老版本字段)."""
        if orientation not in _ORIENTATIONS or orientation == self._orientation:
            return
        self._orientation = orientation
        # 切换方向后默认几何不再合适, 重新计算
        self._set_default_geometry()
        self.update()

    # ------------------------------------------------------------------ 内部
    def _apply_window_flags(self) -> None:
        flags = self._BASE_FLAGS
        if self._locked:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)

    def _set_default_geometry(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(900, 90)
            return
        geo = screen.availableGeometry()
        if self._orientation == "vertical":
            # 竖向: 窄列, 高度 ~70% 屏高, 默认右侧距边 80px
            width = 120
            height = max(300, int(geo.height() * 0.7))
            x = geo.x() + geo.width() - width - 80
            y = geo.y() + (geo.height() - height) // 2
        else:
            # 横向: 宽 2/3 屏, 高 90, 距底 60px
            width = max(900, geo.width() * 2 // 3)
            height = 90
            x = geo.x() + (geo.width() - width) // 2
            y = geo.y() + geo.height() - height - 60
        self.setGeometry(x, y, width, height)

    def _is_word_sung(self, word_idx: int) -> bool:
        """无 word 数据 -> 整句视为已唱; 否则按 sung_count 判定."""
        if not self._words:
            return True
        return word_idx < self._sung_count

    def _segments(self) -> list[tuple[str, bool]]:
        """把当前文本切成 (片段, 是否已唱) 列表, 用于绘制 (横向 / 竖向通用).

        无 ``words`` 数据 -> 整句一个片段, 一律已唱 (上层取高亮色绘制).
        有 ``words`` -> 按 word 切; 每 word 内部不再细分.
        """
        if not self._words:
            return [(self._text, True)] if self._text else []
        out: list[tuple[str, bool]] = []
        for i, w in enumerate(self._words):
            text = str(w.get("text", ""))
            if not text:
                continue
            out.append((text, i < self._sung_count))
        return out

    # ------------------------------------------------------------------ 鼠标 (仅解锁时)
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._locked or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._locked or self._drag_origin is None:
            super().mouseMoveEvent(event)
            return
        self.move(event.globalPosition().toPoint() - self._drag_origin)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        if not self._text:
            return

        if self._orientation == "vertical":
            self._paint_vertical(painter)
        else:
            self._paint_horizontal(painter)

    def _paint_horizontal(self, painter: QPainter) -> None:
        """横向: 按 word 切, 每段独立 path; 整句先描黑边再分段填色, 边到边对齐."""
        fm = QFontMetrics(self._font)
        segments = self._segments()
        if not segments:
            return
        # 整句宽度 = 各段宽度之和; 居中起点
        total_w = sum(fm.horizontalAdvance(seg) for seg, _ in segments)
        x0 = (self.width() - total_w) // 2
        baseline = (self.height() + fm.ascent() - fm.descent()) // 2

        # 先一次性把整句路径描边, 跨段连续 (Round join 让接缝不豁口)
        full_path = QPainterPath()
        x = float(x0)
        for seg, _ in segments:
            full_path.addText(x, float(baseline), self._font, seg)
            x += fm.horizontalAdvance(seg)
        self._draw_outline(painter, full_path)

        # 再按段填色
        x = float(x0)
        for seg, sung in segments:
            seg_path = QPainterPath()
            seg_path.addText(x, float(baseline), self._font, seg)
            self._fill_path(painter, seg_path, sung)
            x += fm.horizontalAdvance(seg)

    def _paint_vertical(self, painter: QPainter) -> None:
        """竖向: 每字独立绘制, 字色随 word 是否已唱; 描边按字单独描 (字间不连)."""
        fm = QFontMetrics(self._font)
        line_h = fm.ascent() + fm.descent() + 2
        # 展平: [(char, sung)]
        flat: list[tuple[str, bool]] = []
        for seg, sung in self._segments():
            for ch in seg:
                flat.append((ch, sung))
        if not flat:
            return
        total_h = line_h * len(flat)
        start_y = max(fm.ascent(), (self.height() - total_h) // 2 + fm.ascent())
        cx = self.width() // 2

        for i, (ch, sung) in enumerate(flat):
            char_w = fm.horizontalAdvance(ch)
            x = cx - char_w // 2
            y = start_y + i * line_h
            if y - fm.ascent() > self.height():
                break  # 超出窗口高度, 不画
            path = QPainterPath()
            path.addText(float(x), float(y), self._font, ch)
            self._draw_outline(painter, path)
            self._fill_path(painter, path, sung)

    def _draw_outline(self, painter: QPainter, path: QPainterPath) -> None:
        pen = QPen(_OUTLINE_COLOR, _OUTLINE_WIDTH)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _fill_path(self, painter: QPainter, path: QPainterPath, sung: bool) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color_highlight if sung else self._color_base)
        painter.drawPath(path)


class DesktopLyricsController(QObject):
    """连接 LyricController + SettingsController -> DesktopLyricsWindow.

    数据流:
    - ``LyricController.currentLineChanged`` -> 重读 activeIndex + lyricModel.lineAt(idx) ->
      把 (text, words) 推给窗口; 同时立即按当前 positionMs 算 sung_count.
    - ``LyricController.positionMsChanged`` -> 推 positionMs 给窗口; 窗口内部跨字才重绘.
    - ``SettingsController.settingsChanged`` -> 全量 pull 锁定 / 字体 / 方向 / 颜色.
    """

    def __init__(
        self,
        lyric_controller: Any,
        settings_controller: Any = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._lyric_controller = lyric_controller
        self._settings_controller = settings_controller
        self._window = DesktopLyricsWindow()
        self._lyric_controller.currentLineChanged.connect(self._on_line_changed)
        # positionMsChanged 是 player tick 100ms 推一次 (LyricController 透传), 量大
        # 但窗口内部 sung_count 跨字才会真正 update(), 不抖.
        position_signal = getattr(self._lyric_controller, "positionMsChanged", None)
        if position_signal is not None:
            position_signal.connect(self._on_position_changed)
        if self._settings_controller is not None:
            self._settings_controller.settingsChanged.connect(self._on_settings_changed)
            self._on_settings_changed()  # 启动期同步一次

    def show(self) -> None:
        self._window.show()
        self._sync_line()
        self._sync_position()
        logger.info("桌面歌词窗已显示")

    def hide(self) -> None:
        self._window.hide()
        logger.info("桌面歌词窗已隐藏")

    @property
    def window(self) -> DesktopLyricsWindow:
        return self._window

    def apply_settings(
        self,
        *,
        locked: bool | None = None,
        font_family: str | None = None,
        font_size: int | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        orientation: str | None = None,
        color_base: str | None = None,
        color_highlight: str | None = None,
    ) -> None:
        """从 SettingsController 推过来的批量更新; 任一字段 None 时跳过."""
        if locked is not None:
            self._window.set_locked(locked)
        if (
            font_family is not None
            or font_size is not None
            or bold is not None
            or italic is not None
        ):
            self._window.set_font_config(
                family=font_family, size=font_size, bold=bold, italic=italic
            )
        if orientation is not None:
            self._window.set_orientation(orientation)
        if color_base is not None or color_highlight is not None:
            base, hi = self._window.colors()
            if color_base is not None:
                parsed = QColor(color_base)
                if parsed.isValid():
                    base = parsed
            if color_highlight is not None:
                parsed = QColor(color_highlight)
                if parsed.isValid():
                    hi = parsed
            self._window.set_colors(base, hi)

    @Slot()
    def _on_line_changed(self) -> None:
        self._sync_line()
        self._sync_position()  # 立刻按当前 ms 算 sung_count, 不等下一 tick

    @Slot()
    def _on_position_changed(self) -> None:
        self._sync_position()

    @Slot()
    def _on_settings_changed(self) -> None:
        """SettingsController 任一字段变化都会重 emit settingsChanged; 全量拉取最简单."""
        sc = self._settings_controller
        if sc is None:
            return
        self.apply_settings(
            locked=bool(sc.desktopLyricsLocked),
            font_family=str(sc.desktopLyricsFontFamily) or None,
            font_size=int(sc.desktopLyricsFontSize),
            bold=bool(sc.desktopLyricsBold),
            italic=bool(sc.desktopLyricsItalic),
            orientation=str(sc.desktopLyricsOrientation),
            color_base=str(sc.desktopLyricsColorBase),
            color_highlight=str(sc.desktopLyricsColorHighlight),
        )

    def _sync_line(self) -> None:
        """从 LyricController 拉当前行的 (text, words). 没有 activeIndex / lyricModel
        的 fake controller 走 fallback: 仅用 currentLineText."""
        text = getattr(self._lyric_controller, "currentLineText", "") or ""
        words = self._current_words()
        self._window.set_line(text, words)

    def _sync_position(self) -> None:
        if not getattr(self._lyric_controller, "positionMs", None) and not hasattr(
            self._lyric_controller, "positionMs"
        ):
            return
        position = int(getattr(self._lyric_controller, "positionMs", 0) or 0)
        self._window.set_progress_ms(position)

    def _current_words(self) -> list[dict[str, Any]]:
        """从 ``lyricModel.lineAt(activeIndex)`` 拿 ``words`` 列表; 失败时返 []."""
        active_idx = getattr(self._lyric_controller, "activeIndex", -1)
        if active_idx is None or active_idx < 0:
            return []
        model = getattr(self._lyric_controller, "lyricModel", None)
        if model is None:
            return []
        line_at = getattr(model, "lineAt", None)
        if not callable(line_at):
            return []
        try:
            line = line_at(active_idx)
        except Exception:
            return []
        words = (line or {}).get("words", [])
        return list(words) if isinstance(words, list) else []
