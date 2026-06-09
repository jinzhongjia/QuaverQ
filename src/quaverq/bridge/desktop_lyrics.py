"""桌面悬浮歌词窗 —— **仅 Windows**.

类似 QQ 音乐 / 网易云的桌面歌词: 大字号歌词文字, 渐变填充 + 描边, 鼠标完全穿透,
总是置顶但不抢焦点. 用户可以:
- 解锁后拖动调整位置
- 调字体 / 字号 / 粗细 / 斜体
- 切换横向 / 竖向显示

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
- 绘制: ``QPainterPath.addText`` 拿文字路径, 先描边再渐变填充, 得 QQ 音乐风格
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


_ORIENTATIONS = ("horizontal", "vertical")


class DesktopLyricsWindow(QWidget):
    """无边框 + 透明 + 可锁定的桌面歌词窗口."""

    _BASE_FLAGS = (
        Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._text = ""
        self._locked = True
        self._orientation = "horizontal"
        self._font = QFont("Microsoft YaHei UI", 32, QFont.Weight.Bold)
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

    # ------------------------------------------------------------------ 状态修改
    def set_text(self, text: str) -> None:
        text = text or ""
        if text == self._text:
            return
        self._text = text
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
        fm = QFontMetrics(self._font)
        text_width = fm.horizontalAdvance(self._text)
        x = (self.width() - text_width) // 2
        y = (self.height() + fm.ascent() - fm.descent()) // 2

        path = QPainterPath()
        path.addText(float(x), float(y), self._font, self._text)
        self._stroke_and_fill(painter, path, y - fm.ascent(), y)

    def _paint_vertical(self, painter: QPainter) -> None:
        """竖向: 每字独立 path, y 递增, x 居中. CJK 看起来自然, ASCII 也能用."""
        fm = QFontMetrics(self._font)
        # 行高 = ascent + descent + 一点点 leading
        line_h = fm.ascent() + fm.descent() + 2
        total_h = line_h * len(self._text)
        start_y = max(fm.ascent(), (self.height() - total_h) // 2 + fm.ascent())
        cx = self.width() // 2

        for i, ch in enumerate(self._text):
            char_w = fm.horizontalAdvance(ch)
            x = cx - char_w // 2
            y = start_y + i * line_h
            if y - fm.ascent() > self.height():
                break  # 超出窗口高度, 不画
            path = QPainterPath()
            path.addText(float(x), float(y), self._font, ch)
            self._stroke_and_fill(painter, path, y - fm.ascent(), y)

    def _stroke_and_fill(
        self,
        painter: QPainter,
        path: QPainterPath,
        gradient_top: int,
        gradient_bottom: int,
    ) -> None:
        # 描边
        outline_pen = QPen(QColor(0, 0, 0, 220), 5)
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # 渐变填充 黄 → 橙
        gradient = QLinearGradient(0.0, float(gradient_top), 0.0, float(gradient_bottom))
        gradient.setColorAt(0.0, QColor(255, 244, 138))
        gradient.setColorAt(1.0, QColor(255, 142, 31))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)


class DesktopLyricsController(QObject):
    """连接 LyricController + SettingsController -> DesktopLyricsWindow.

    - 监听 ``LyricController.currentLineChanged`` 实时更新文字
    - 监听 ``SettingsController.settingsChanged`` 同步锁定 / 字体 / 方向
    - 启动时一次性 pull 当前设置 (避免 SettingsController 在窗口创建前已 emit 完)
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
        if self._settings_controller is not None:
            self._settings_controller.settingsChanged.connect(self._on_settings_changed)
            self._on_settings_changed()  # 启动期同步一次

    def show(self) -> None:
        self._window.show()
        self._sync()
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

    @Slot()
    def _on_line_changed(self) -> None:
        self._sync()

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
        )

    def _sync(self) -> None:
        text = getattr(self._lyric_controller, "currentLineText", "") or ""
        self._window.set_text(text)
