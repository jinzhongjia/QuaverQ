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
import time
from typing import Any

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QTimer, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QHideEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


_ORIENTATIONS = ("horizontal", "vertical")
_DEFAULT_COLOR_BASE = QColor("#FFFFFF")
_DEFAULT_COLOR_HIGHLIGHT = QColor("#FFA200")  # 深琥珀 / QQ Music 风格暖橙
_OUTLINE_COLOR = QColor(0, 0, 0)  # 不透明纯黑, 收 220 alpha 让边沿更锐
_OUTLINE_WIDTH = 3  # 5px 偏粗会"吞"字形细节, 3px 与 QQ Music 参考视觉接近
# 填色 vertical gradient: 上端 = 用户色, 下端 = 微暗版, 让字有"舞台灯"立体感.
_FILL_GRADIENT_DARKEN = 115  # QColor.darker(115) = 亮度降 15%, 微妙不抢戏
_WIPE_TIMER_INTERVAL_MS = 33  # ~30 FPS 插值, 比 MediaPlayer 100ms tick 更平滑
# 插值最长外推时长: 超过此值仍没收到新 position tick -> 冻在 anchor 不再外推.
# 防止加载 / 缓冲 / 暂停态 wall-clock 自顾自把字"唱过去", 等真实 positionChanged 一来
# anchor 重置就跳回 (用户实测复现).
# MediaPlayer FFmpeg backend 正常 100ms tick 一次; 150ms 留 50ms 缓冲, 不抖.
_MAX_INTERP_DELTA_MS = 150
# 斜体常见 shear ~12°, tan(12°) ≈ 0.213. 用此值把 wipe 边沿做成平行四边形,
# 匹配 italic 字形倾斜, 避免垂直 clip 把字劈成楔形伪影 (上半字被切歪一刀).
_ITALIC_SHEAR = 0.213
# 字间距: 默认 advance 太挤 (尤其 CJK 大字号 OSD), 加 10% PercentageSpacing 让字呼吸,
# 同时与字号成比例 (避免小字号下加固定 px 导致过宽 / 大字号下不够).
_LETTER_SPACING_PERCENT = 110.0


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
        # 默认 Black (900) 比 Bold (700) 字脚更壮, OSD 大字号下"印刷"感更强;
        # family 没 Black 字重时 Qt 自动 fallback 到家族最接近的字重 (通常 Bold).
        self._font = QFont("Microsoft YaHei UI", 32, QFont.Weight.Black)
        self._font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, _LETTER_SPACING_PERCENT)
        self._color_base = QColor(_DEFAULT_COLOR_BASE)
        self._color_highlight = QColor(_DEFAULT_COLOR_HIGHLIGHT)
        self._drag_origin: QPoint | None = None

        # 平滑动画: 外部 set_progress_ms 设 anchor, 定时器 30fps 插值
        # _effective_ms() = anchor + (perf_counter - anchor_perf) * 1000
        # 当无 active wipe (无 word 正在 0<f<1) 时定时器停, 不浪费 CPU
        # _is_playing: 仅在播放中允许插值, 否则即便 ms 落在 active word 范围内, timer 也不启动 ——
        # 修启动期 / 暂停态歌没播 wipe 却自己往前跑 (wall-clock 推进) 的 bug.
        self._anchor_ms = 0
        self._anchor_perf = time.perf_counter()
        self._is_playing = False
        self._wipe_timer = QTimer(self)
        self._wipe_timer.setInterval(_WIPE_TIMER_INTERVAL_MS)
        self._wipe_timer.timeout.connect(self._on_wipe_tick)

        self._apply_window_flags()
        self._set_default_geometry()

    # ------------------------------------------------------------------ 状态查询
    def is_locked(self) -> bool:
        return self._locked

    def is_playing(self) -> bool:
        return self._is_playing

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
        self._wipe_timer.stop()
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
        self._anchor_ms = 0
        self._anchor_perf = time.perf_counter()
        self._wipe_timer.stop()
        self.update()

    def set_progress_ms(self, position_ms: int) -> None:
        """根据当前 ms 算出 ``sung_count`` + anchor; 启动 / 停 wipe 定时器."""
        try:
            ms = int(position_ms)
        except (TypeError, ValueError):
            return
        if not self._words:
            return
        # anchor 用于 wipe 插值; 每次外部 update 都重设
        self._anchor_ms = ms
        self._anchor_perf = time.perf_counter()
        # _sung_count 用 ms (binary "started count" 给 controller / 测试看)
        new_count = 0
        for w in self._words:
            start = w.get("startMs", 0)
            if ms >= start:
                new_count += 1
            else:
                break  # words 已按 startMs 升序
        self._sung_count = new_count
        self._toggle_wipe_timer()
        self.update()

    def set_playing(self, playing: bool) -> None:
        """切播放态. 暂停 / 停止时 -> 停 timer + 不再插值 (effective_ms = anchor_ms).

        修启动期 / 暂停时 wipe 自己往前跑的 bug: 之前 timer 只看 wall-clock,
        不管歌实际是否在播 -> 出现"字向前亮起接着突然回到开头"的鬼影.

        **故意不在 playing=True 时 re-anchor perf**: anchor_perf 必须与 anchor_ms
        来源同步 (上次 set_progress_ms 时刻). 强行重置 perf 会让外推从一个旧 anchor_ms
        开始计 delta, 真实 positionChanged 一到就跳回去. 由 _MAX_INTERP_DELTA_MS cap 兜底.
        """
        playing = bool(playing)
        if self._is_playing == playing:
            return
        self._is_playing = playing
        if playing:
            self._toggle_wipe_timer()
        else:
            self._wipe_timer.stop()
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

    def _effective_ms(self) -> int:
        """anchor + 插值时间. 暂停 / 停止时或 timer 不跑时 = anchor (静止状态),
        避免 wall-clock 把字"自己唱过去".

        外推有上限 ``_MAX_INTERP_DELTA_MS`` (150ms = 1.5 个 MediaPlayer tick 间隔):
        超过仍没新 position 视为 loading / buffer / 真停了, 冻在 anchor 不让字往前飞.
        """
        if not self._is_playing or not self._wipe_timer.isActive():
            return self._anchor_ms
        delta_ms = (time.perf_counter() - self._anchor_perf) * 1000.0
        if delta_ms > _MAX_INTERP_DELTA_MS:
            return self._anchor_ms
        return int(self._anchor_ms + delta_ms)

    def _word_fractions(self) -> list[tuple[str, float]]:
        """当前帧每个 word 的 (text, fill_fraction).

        无 ``words`` 数据 -> 整句作单段 fraction=1.0 (整体高亮色).
        有 ``words`` -> 每段按 ``elapsed/durationMs`` 算 0..1.
        """
        if not self._words:
            return [(self._text, 1.0)] if self._text else []
        ms = self._effective_ms()
        out: list[tuple[str, float]] = []
        for w in self._words:
            text = str(w.get("text", ""))
            if not text:
                continue
            start = int(w.get("startMs", 0))
            dur = max(1, int(w.get("durationMs", 0)))
            if ms < start:
                f = 0.0
            elif ms >= start + dur:
                f = 1.0
            else:
                f = (ms - start) / dur
            out.append((text, f))
        return out

    def _has_active_wipe(self) -> bool:
        """是否有 word 正在 0<f<1 范围 (需要定时器持续插值)."""
        if not self._words:
            return False
        ms = self._effective_ms()
        for w in self._words:
            start = int(w.get("startMs", 0))
            dur = int(w.get("durationMs", 0))
            if start <= ms < start + dur:
                return True
        return False

    def _toggle_wipe_timer(self) -> None:
        """根据当前是否有 active wipe + 是否在播放 决定 timer 起 / 停.
        - 不在播 (暂停 / 停止 / 启动期) -> 一律停, 即便 ms 落在 word 中段也不允许 timer 自驱前进
        - 隐藏 (hideEvent) 已统一停 timer, 这里不再判 isVisible() 防测试构造期假阴性
        """
        if self._is_playing and self._has_active_wipe():
            if not self._wipe_timer.isActive():
                self._wipe_timer.start()
        elif self._wipe_timer.isActive():
            self._wipe_timer.stop()

    def _on_wipe_tick(self) -> None:
        """定时器 33ms 回调: 没 active wipe / 外推超时 -> 自停; 否则重绘.

        外推超时检测: 若距 anchor_perf > cap, 说明 player 没在前进 (loading / pause /
        外部代码忘了推 position), 不再 30fps 空转浪费 CPU. 下次 set_progress_ms 触发 toggle 重启.
        """
        if not self._has_active_wipe():
            self._wipe_timer.stop()
            self.update()
            return
        delta_ms = (time.perf_counter() - self._anchor_perf) * 1000.0
        if delta_ms > _MAX_INTERP_DELTA_MS:
            self._wipe_timer.stop()
        self.update()

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

    # ------------------------------------------------------------------ 显隐
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._toggle_wipe_timer()

    def hideEvent(self, event: QHideEvent) -> None:
        # 隐藏后立刻停 timer, 不浪费 CPU 重绘看不见的内容
        self._wipe_timer.stop()
        super().hideEvent(event)

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
        """横向: 按 word 切, 整句单次描边; 每段先画 base 色, 再按 fraction 用 clipRect
        wipe 出高亮色 (QQ Music 风格"从左到右一字一字亮起")."""
        fm = QFontMetrics(self._font)
        fractions = self._word_fractions()
        if not fractions:
            return
        total_w = sum(fm.horizontalAdvance(t) for t, _ in fractions)
        x0 = (self.width() - total_w) // 2
        baseline = (self.height() + fm.ascent() - fm.descent()) // 2

        # 整句单次描边 (跨段 round join 不豁口)
        full_path = QPainterPath()
        x = float(x0)
        for text, _ in fractions:
            full_path.addText(x, float(baseline), self._font, text)
            x += fm.horizontalAdvance(text)
        self._draw_outline(painter, full_path)

        # 分段填色 + wipe
        x = float(x0)
        for text, fraction in fractions:
            word_w = fm.horizontalAdvance(text)
            word_path = QPainterPath()
            word_path.addText(x, float(baseline), self._font, text)

            # base 色铺底
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._fill_brush(highlight=False))
            painter.drawPath(word_path)

            # 高亮色 wipe (斜体时 clip 跟着 shear, 避免楔形伪影)
            if fraction > 0.0:
                painter.save()
                clip_w = max(1.0, word_w * fraction)
                clip_path = self._make_horizontal_wipe_clip(x, clip_w, float(baseline))
                painter.setClipPath(clip_path)
                painter.setBrush(self._fill_brush(highlight=True))
                painter.drawPath(word_path)
                painter.restore()

            x += word_w

    def _paint_vertical(self, painter: QPainter) -> None:
        """竖向: 按 word 切, 每 word 内多字按 fraction 自上而下 wipe.
        word 之间字符顺序排列 (新行)."""
        fm = QFontMetrics(self._font)
        line_h = fm.ascent() + fm.descent() + 2
        fractions = self._word_fractions()
        if not fractions:
            return
        total_chars = sum(len(t) for t, _ in fractions)
        if total_chars == 0:
            return
        total_h = line_h * total_chars
        start_y = max(fm.ascent(), (self.height() - total_h) // 2 + fm.ascent())
        cx = self.width() // 2

        char_idx = 0
        for text, fraction in fractions:
            # 字符 path (整个 word 一起, wipe clipRect 一次性应用)
            word_path = QPainterPath()
            first_y = start_y + char_idx * line_h
            for i, ch in enumerate(text):
                char_w = fm.horizontalAdvance(ch)
                x = cx - char_w // 2
                y = start_y + (char_idx + i) * line_h
                if y - fm.ascent() > self.height():
                    break
                word_path.addText(float(x), float(y), self._font, ch)

            # 描边 + base 色
            self._draw_outline(painter, word_path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._fill_brush(highlight=False))
            painter.drawPath(word_path)

            # 高亮 wipe (top-down)
            if fraction > 0.0:
                top_y = first_y - fm.ascent()
                word_h = line_h * len(text)
                clip_h = max(1, int(round(word_h * fraction)))
                painter.save()
                painter.setClipRect(0, top_y, self.width(), clip_h)
                painter.setBrush(self._fill_brush(highlight=True))
                painter.drawPath(word_path)
                painter.restore()

            char_idx += len(text)

    def _fill_brush(self, *, highlight: bool) -> QBrush:
        """vertical gradient brush: 顶端 = 用户色, 底端 = 微暗版.

        效果类似 QQ Music 的"舞台灯": 字体上半明下半略沉, 立体感强于纯色.
        渐变跨窗口高度而非字形 bbox -> 文字越大 / 行越靠中, 渐变越平滑.
        """
        color = self._color_highlight if highlight else self._color_base
        h = max(1, self.height())
        gradient = QLinearGradient(0.0, 0.0, 0.0, float(h))
        gradient.setColorAt(0.0, color)
        gradient.setColorAt(1.0, color.darker(_FILL_GRADIENT_DARKEN))
        return QBrush(gradient)

    def _draw_outline(self, painter: QPainter, path: QPainterPath) -> None:
        pen = QPen(_OUTLINE_COLOR, _OUTLINE_WIDTH)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _is_slanted_font(self) -> bool:
        """斜体 / 倾斜样式都需要 clip 也跟着倾斜, 否则垂直 clip 把字劈成楔形."""
        return self._font.italic() or self._font.style() == QFont.Style.StyleOblique

    def _make_horizontal_wipe_clip(
        self, x_left: float, width_px: float, baseline: float
    ) -> QPainterPath:
        """横向 wipe 的 clip 路径. 直立字体 -> 矩形; 斜体 -> 与字形 shear 匹配的平行四边形.

        斜体字形在基线上方右移 shear*Δy, 下方左移; clip 边沿必须同向 shear, 否则
        垂直切线会把字劈成楔形 (上半 / 下半各被剪掉一刀, 视觉极差).
        """
        path = QPainterPath()
        h = float(self.height())
        if not self._is_slanted_font():
            path.addRect(x_left, 0.0, width_px, h)
            return path
        # 基线到上 / 下边各 shear 一段距离;
        # 上半 (y < baseline) 右偏 (baseline - y) * shear, 下半 (y > baseline) 左偏 (y - baseline) * shear.
        top_dx = baseline * _ITALIC_SHEAR
        bot_dx = -(h - baseline) * _ITALIC_SHEAR
        path.moveTo(QPointF(x_left + top_dx, 0.0))
        path.lineTo(QPointF(x_left + width_px + top_dx, 0.0))
        path.lineTo(QPointF(x_left + width_px + bot_dx, h))
        path.lineTo(QPointF(x_left + bot_dx, h))
        path.closeSubpath()
        return path


class DesktopLyricsController(QObject):
    """连接 LyricController + SettingsController + PlayerController -> DesktopLyricsWindow.

    数据流:
    - ``LyricController.currentLineChanged`` -> 重读 activeIndex + lyricModel.lineAt(idx) ->
      把 (text, words) 推给窗口; 同时立即按当前 positionMs 算 sung_count.
    - ``LyricController.positionMsChanged`` -> 推 positionMs 给窗口; 窗口内部跨字才重绘.
    - ``PlayerController.playbackStateChanged`` -> 推 is_playing 给窗口, 控制 wipe 插值;
      不接的话会出现"暂停 / 启动期歌没播但 wipe 自己往前跑"的 bug.
    - ``SettingsController.settingsChanged`` -> 全量 pull 锁定 / 字体 / 方向 / 颜色.
    """

    def __init__(
        self,
        lyric_controller: Any,
        settings_controller: Any = None,
        player_controller: Any = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._lyric_controller = lyric_controller
        self._settings_controller = settings_controller
        self._player_controller = player_controller
        self._window = DesktopLyricsWindow()
        self._lyric_controller.currentLineChanged.connect(self._on_line_changed)
        # positionMsChanged 是 player tick 100ms 推一次 (LyricController 透传), 量大
        # 但窗口内部 sung_count 跨字才会真正 update(), 不抖.
        position_signal = getattr(self._lyric_controller, "positionMsChanged", None)
        if position_signal is not None:
            position_signal.connect(self._on_position_changed)
        if self._player_controller is not None:
            pb_signal = getattr(self._player_controller, "playbackStateChanged", None)
            if pb_signal is not None:
                pb_signal.connect(self._on_playback_state_changed)
            # 启动期同步一次当前播放态 (避免初始默认 False 与实际 "playing" 不符)
            self._on_playback_state_changed()
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
        enabled: bool | None = None,
        locked: bool | None = None,
        font_family: str | None = None,
        font_size: int | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        orientation: str | None = None,
        color_base: str | None = None,
        color_highlight: str | None = None,
    ) -> None:
        """从 SettingsController 推过来的批量更新; 任一字段 None 时跳过.

        ``enabled`` 在末尾处理: 先把样式 / 内容应到位再切换可见性,
        避免开启时先看到旧文字闪一下.
        """
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
        if enabled is not None:
            if enabled:
                self._sync_line()
                self._sync_position()
                self._window.show()
            else:
                self._window.hide()

    @Slot()
    def _on_line_changed(self) -> None:
        self._sync_line()
        self._sync_position()  # 立刻按当前 ms 算 sung_count, 不等下一 tick

    @Slot()
    def _on_position_changed(self) -> None:
        self._sync_position()

    @Slot()
    def _on_playback_state_changed(self) -> None:
        """playbackState ∈ {playing, paused, stopped, loading, ...} -> 只在 'playing' 时插值."""
        pc = self._player_controller
        if pc is None:
            return
        state = str(getattr(pc, "playbackState", "") or "")
        self._window.set_playing(state == "playing")

    @Slot()
    def _on_settings_changed(self) -> None:
        """SettingsController 任一字段变化都会重 emit settingsChanged; 全量拉取最简单."""
        sc = self._settings_controller
        if sc is None:
            return
        self.apply_settings(
            enabled=bool(sc.desktopLyricsEnabled),
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
