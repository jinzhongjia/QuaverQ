"""桌面悬浮歌词窗 —— **仅 Windows**.

类似 QQ 音乐 / 网易云的桌面歌词: 屏幕底部水平居中的大字号歌词文字, 渐变填充 + 描边,
鼠标完全穿透不影响桌面 / 任务栏 / 其他窗口的交互. 总是置顶但不抢焦点.

**Linux / macOS 故意不启用** (见 ``platform/base.py`` ``desktop_lyrics`` docstring):
Wayland 多家 compositor 下 frameless + transparent + input-passthrough 组合行为
不一致 (焦点抢占 / z-order / 透明合成怪异), 不写跨 compositor 兜底; Linux 用户走
MPRIS 接现成桌面歌词工具. 本模块本身用纯 Qt 写, 跨平台 import 不崩, 但 PAL 只在
Windows 实例化.

Qt 实现要点:
- ``Qt.FramelessWindowHint``: 无边框无装饰
- ``Qt.WindowStaysOnTopHint``: 置顶
- ``Qt.Tool``: 不在任务栏占位 / 不参与 Alt-Tab
- ``Qt.WindowTransparentForInput``: 鼠标事件穿透到下层窗口
- ``WA_TranslucentBackground``: 窗口背景透明, 只有 paint 出来的像素可见
- ``WA_ShowWithoutActivating``: show 时不抢焦点
- 绘制: ``QPainterPath.addText`` 拿文字路径, 先描边 (粗黑笔) 再填充 (黄→橙渐变 brush),
  得 QQ 音乐式的"亮黄字 + 黑描边" 效果.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class DesktopLyricsWindow(QWidget):
    """无边框 + 透明 + 鼠标穿透的桌面歌词窗口."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # 不抢键盘焦点
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._text = ""
        # 字号: 与 QQ 音乐 PC 端桌面歌词接近 (~32-40pt). Microsoft YaHei UI 支持中文+英文都好看.
        self._font = QFont("Microsoft YaHei UI", 32, QFont.Weight.Bold)

        self._set_default_geometry()

    def _set_default_geometry(self) -> None:
        """默认: 主屏水平居中, 距底部 60px (任务栏上方留余地)."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(900, 90)
            return
        geo = screen.availableGeometry()
        width = max(900, geo.width() * 2 // 3)
        height = 90
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + geo.height() - height - 60
        self.setGeometry(x, y, width, height)

    def set_text(self, text: str) -> None:
        """更新歌词文字; 没变化时跳过 (避免无意义重绘)."""
        text = text or ""
        if text == self._text:
            return
        self._text = text
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        fm = QFontMetrics(self._font)
        text_width = fm.horizontalAdvance(self._text)
        # 文字水平居中, 垂直 baseline 居中
        x = (self.width() - text_width) // 2
        y = (self.height() + fm.ascent() - fm.descent()) // 2

        # 用 QPainterPath 拿到文字路径 (描边 + 填充都基于它)
        path = QPainterPath()
        path.addText(float(x), float(y), self._font, self._text)

        # 1. 描边: 半透明黑色, 5px 宽
        outline_pen = QPen(QColor(0, 0, 0, 220), 5)
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # 2. 填充: 黄 → 橙 垂直渐变 (QQ 音乐风格)
        gradient = QLinearGradient(0.0, float(y - fm.ascent()), 0.0, float(y))
        gradient.setColorAt(0.0, QColor(255, 244, 138))
        gradient.setColorAt(1.0, QColor(255, 142, 31))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)


class DesktopLyricsController(QObject):
    """把 LyricController 的当前行实时同步到 DesktopLyricsWindow.

    持有窗口引用防 GC; 监听 ``LyricController.currentLineChanged`` 触发刷新.
    """

    def __init__(
        self,
        lyric_controller: Any,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._lyric_controller = lyric_controller
        self._window = DesktopLyricsWindow()
        self._lyric_controller.currentLineChanged.connect(self._on_line_changed)

    def show(self) -> None:
        """显示桌面歌词窗 + 同步当前行."""
        self._window.show()
        self._sync()
        logger.info("桌面歌词窗已显示")

    def hide(self) -> None:
        self._window.hide()
        logger.info("桌面歌词窗已隐藏")

    @property
    def window(self) -> DesktopLyricsWindow:
        return self._window

    @Slot()
    def _on_line_changed(self) -> None:
        self._sync()

    def _sync(self) -> None:
        text = getattr(self._lyric_controller, "currentLineText", "") or ""
        self._window.set_text(text)
