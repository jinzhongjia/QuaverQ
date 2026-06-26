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

import bisect
import logging
import time
from typing import Any, NamedTuple

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, Qt, QTimer, Signal, Slot
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
    QResizeEvent,
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
_VERTICAL_CHAR_GAP_RATIO = 0.25
# wipe clip 纵向裕量: 值不重要, 只要大于文字实际高度就行
_CLIP_MARGIN = 2000.0
_TRANS_SIZE_RATIO = 0.6
_VTRANS_SIZE_RATIO = 0.75  # 竖排翻译字号比例 (竖排本身字不大, 0.6 太小)
_TRANS_OUTLINE_WIDTH = 2
_TRANS_GAP = 6
_VCOL_GAP = 12  # 竖排双列间距 (歌词右列 + 翻译左列)
_SCROLL_EDGE_PADDING = 8  # 超长歌词滚动到首尾时给描边/抗锯齿留一点余量


def _is_vertical_char(c: str) -> bool:
    """竖排中应直立堆叠的字符: CJK 表意字 / 假名 / 谚文 / 全角标点."""
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


def _segment_for_vertical(text: str) -> list[tuple[str, bool]]:
    """将文本拆分为 (段文字, 是否直立竖排) 对, 用于竖向块布局.

    竖排只有一条规则 (无脑化, 消除各类边界 case):
    - CJK 表意字 / 假名 / 谚文 / 全角标点 → True (正立逐字堆叠)
    - 其余一切 (拉丁 / 数字 / ASCII 标点 / 空格) → False, 整段连续作为一个块旋转 90°

    非竖排段去首尾空白; 全空白段 (如 CJK 之间的孤立空格) 丢弃.
    """
    if not text:
        return []
    raw: list[tuple[str, bool]] = []
    buf = text[0]
    buf_vert = _is_vertical_char(text[0])
    for c in text[1:]:
        vert = _is_vertical_char(c)
        if vert == buf_vert:
            buf += c
        else:
            raw.append((buf, buf_vert))
            buf = c
            buf_vert = vert
    raw.append((buf, buf_vert))
    result: list[tuple[str, bool]] = []
    for seg_text, is_vert in raw:
        if is_vert:
            result.append((seg_text, True))
        else:
            stripped = seg_text.strip()
            if stripped:
                result.append((stripped, False))
    return result


def _normalize_path_x(path: QPainterPath, outline_width: int) -> tuple[QPainterPath, float]:
    """把横向路径 X bbox 归一到 [pad, pad+width], 供旋转成竖向块时计高."""
    bounds = path.boundingRect()
    pad = max(1.0, float(outline_width))
    normalized = QPainterPath(path)
    normalized.translate(-bounds.left() + pad, 0.0)
    return normalized, float(bounds.width() + pad * 2.0)


class _WordInfo(NamedTuple):
    """预处理后的逐字信息, 消除热路径 dict.get() 开销."""

    text: str
    start_ms: int
    duration_ms: int
    end_ms: int


class _VBlock(NamedTuple):
    """竖向布局中的一个视觉块 (CJK 正立堆叠块 / 非 CJK 旋转块)."""

    path: QPainterPath
    v_height: float
    rotated: bool
    content_h: float


class _HorizontalLayout(NamedTuple):
    """横排绘制布局, 坐标为 widget 像素; scale 固定 1, 超长靠原点滚动."""

    scale: float
    main_x: float
    baseline: float
    baseline_local: float
    viewport_h: float
    trans_x: float
    trans_baseline: float


class _VerticalColumnLayout(NamedTuple):
    """竖排绘制布局, 坐标为 widget 像素; scale 固定 1, 超长靠原点滚动."""

    scale: float
    main_cx: float
    trans_cx: float
    main_start_y: float
    trans_start_y: float
    main_h: float
    trans_h: float
    main_ascent: float
    trans_ascent: float
    content_h: float


def _make_word_infos(words: list[dict[str, Any]]) -> list[_WordInfo]:
    return [
        _WordInfo(
            text=str(w.get("text", "")),
            start_ms=int(w.get("startMs", 0)),
            duration_ms=max(0, int(w.get("durationMs", 0))),
            end_ms=int(w.get("startMs", 0)) + max(0, int(w.get("durationMs", 0))),
        )
        for w in words
    ]


class DesktopLyricsWindow(QWidget):
    """无边框 + 透明 + 可锁定 + 逐字高亮的桌面歌词窗口."""

    _BASE_FLAGS = (
        Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
    )

    # 用户拖动结束后发: (orientation, x, y, w, h). Controller 接住写入 SettingsController.
    geometryEdited = Signal(str, int, int, int, int)

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
        # 被拖动后记住的位置 (横 / 竖各一份); None = 该方向尚无记忆, 用默认几何.
        self._saved_geometries: dict[str, QRect | None] = {
            "horizontal": None,
            "vertical": None,
        }

        # 预处理: 消除热路径 dict.get / int() 开销
        self._word_infos: list[_WordInfo] = []
        self._word_starts: list[int] = []
        self._display_words: list[_WordInfo] = []

        # 平滑动画: 外部 set_progress_ms 设 anchor, 定时器 30fps 插值
        self._anchor_ms = 0
        self._anchor_perf = time.perf_counter()
        self._is_playing = False
        self._wipe_timer = QTimer(self)
        self._wipe_timer.setInterval(_WIPE_TIMER_INTERVAL_MS)
        self._wipe_timer.timeout.connect(self._on_wipe_tick)

        # ---- 绘制缓存 ----
        # 路径缓存: text/font/orientation 变化时重建, paintEvent 只 drawPath
        self._cached_fm: QFontMetrics | None = None
        # 横向
        self._h_outline_path = QPainterPath()
        self._h_word_paths: list[QPainterPath] = []
        self._h_word_xs: list[float] = []
        self._h_word_widths: list[float] = []
        self._h_total_w: float = 0.0
        # 竖向: CJK 正立逐字堆叠 + 非 CJK 段整段旋转 90°, 统一块模型
        self._v_line_h: float = 0.0
        self._v_word_blocks: list[list[_VBlock]] = []
        self._v_word_v_heights: list[float] = []
        self._v_total_v_height: float = 0.0
        self._v_trans_blocks: list[_VBlock] = []
        self._v_trans_v_height: float = 0.0
        # 翻译
        self._translation = ""
        self._has_trans = False
        self._line_start_ms: int | None = None
        self._line_end_ms: int | None = None
        self._trans_outline_pen = QPen(_OUTLINE_COLOR, _TRANS_OUTLINE_WIDTH)
        self._trans_outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._trans_outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self._trans_font = QFont(self._font)
        self._trans_fm: QFontMetrics | None = None
        self._trans_path = QPainterPath()
        self._trans_total_w: float = 0.0
        # 画刷缓存: color/height 变化时重建
        self._cached_brush_base: QBrush | None = None
        self._cached_brush_highlight: QBrush | None = None
        self._brush_cache_height: int = -1
        # 描边画笔: 常量, 构建一次
        self._outline_pen = QPen(_OUTLINE_COLOR, _OUTLINE_WIDTH)
        self._outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        self._apply_window_flags()
        self._apply_geometry_for_current()

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
        if text == self._text and not self._words and not self._translation:
            return
        self._text = text
        self._translation = ""
        self._words = []
        self._word_infos = []
        self._word_starts = []
        self._line_start_ms = None
        self._line_end_ms = None
        self._sung_count = 0
        self._wipe_timer.stop()
        self._rebuild_paint_cache()
        self.update()

    def set_line(
        self,
        text: str,
        words: list[dict[str, Any]] | None,
        translation: str = "",
        *,
        line_start_ms: int | None = None,
        line_end_ms: int | None = None,
    ) -> None:
        """更新当前行 + 逐字时间 + 翻译. words 为 None / [] 时整句作为单段高亮."""
        text = text or ""
        words = list(words or [])
        translation = translation or ""
        try:
            line_start = None if line_start_ms is None else int(line_start_ms)
            line_end = None if line_end_ms is None else int(line_end_ms)
        except (TypeError, ValueError):
            line_start = None
            line_end = None
        if (
            text == self._text
            and words == self._words
            and translation == self._translation
            and line_start == self._line_start_ms
            and line_end == self._line_end_ms
        ):
            return
        self._text = text
        self._translation = translation
        self._line_start_ms = line_start
        self._line_end_ms = line_end
        self._words = words
        self._word_infos = _make_word_infos(words)
        self._word_starts = [w.start_ms for w in self._word_infos]
        self._sung_count = 0  # 新行重算; 接着会有 set_progress_ms 推上来
        self._anchor_ms = 0
        self._anchor_perf = time.perf_counter()
        self._wipe_timer.stop()
        self._rebuild_paint_cache()
        self.update()

    def set_progress_ms(self, position_ms: int) -> None:
        """根据当前 ms 算出 ``sung_count`` + anchor; 启动 / 停 wipe 定时器."""
        try:
            ms = int(position_ms)
        except (TypeError, ValueError):
            return
        old_anchor = self._anchor_ms
        self._anchor_ms = ms
        self._anchor_perf = time.perf_counter()
        if not self._word_infos:
            if self._has_line_timing() and old_anchor != ms:
                self.update()
            return
        old_count = self._sung_count
        self._sung_count = bisect.bisect_right(self._word_starts, ms)
        self._toggle_wipe_timer()
        if self._sung_count != old_count or self._wipe_timer.isActive():
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
        self._brush_cache_height = -1
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
        # setWindowFlags 在部分平台 (Windows) 会复位窗口位置, 先存当前几何, 之后恢复,
        # 否则锁 / 解锁一下就把用户拖好的位置丢了.
        saved_geo = self.geometry()
        self._apply_window_flags()
        if was_visible:
            # setWindowFlags 后 Qt 会隐藏窗口, 需要重 show.
            self.show()
        self.setGeometry(saved_geo)
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
        self._rebuild_paint_cache()
        self.update()

    def set_orientation(self, orientation: str) -> None:
        """方向: ``horizontal`` 横向 (默认) / ``vertical`` 竖向.

        竖向统一块模型: CJK (含全角标点) 正立逐字堆叠, 非 CJK 段整段旋转 90°.
        非合法值时静默忽略 (保护设置文件破损 / 老版本字段)."""
        if orientation not in _ORIENTATIONS or orientation == self._orientation:
            return
        self._orientation = orientation
        # 切换方向后沿用该方向已记忆的位置, 没有才回默认几何 (横竖默认差异大).
        self._apply_geometry_for_current()
        self._rebuild_paint_cache()
        self.update()

    # ------------------------------------------------------------------ 缓存
    def _rebuild_paint_cache(self) -> None:
        """重建文字路径 + 测量缓存. set_line/set_text/set_font_config/set_orientation 调用."""
        fm = QFontMetrics(self._font)
        self._cached_fm = fm

        if self._word_infos:
            self._display_words = [w for w in self._word_infos if w.text]
        elif self._text:
            self._display_words = [_WordInfo(self._text, 0, 0, 0)]
        else:
            self._display_words = []

        if self._translation:
            trans_font = QFont(self._font)
            ratio = _VTRANS_SIZE_RATIO if self._orientation == "vertical" else _TRANS_SIZE_RATIO
            trans_font.setPointSize(max(12, int(self._font.pointSize() * ratio)))
            trans_font.setWeight(QFont.Weight.Bold)
            self._trans_fm = QFontMetrics(trans_font)
            self._trans_font = trans_font

        if self._orientation == "vertical":
            self._build_vertical_cache(fm)
            self._build_trans_vertical_cache()
        else:
            self._build_horizontal_cache(fm)
            self._build_trans_horizontal_cache()

        if self._orientation == "vertical":
            self._has_trans = bool(self._translation) and self._v_trans_v_height > 0
        else:
            self._has_trans = bool(self._translation) and self._trans_total_w > 0

    def _build_horizontal_cache(self, fm: QFontMetrics) -> None:
        outline = QPainterPath()
        paths: list[QPainterPath] = []
        xs: list[float] = []
        widths: list[float] = []
        x = 0.0
        for w in self._display_words:
            word_w = fm.horizontalAdvance(w.text)
            path = QPainterPath()
            path.addText(x, 0.0, self._font, w.text)
            outline.addPath(path)
            paths.append(path)
            xs.append(x)
            widths.append(float(word_w))
            x += word_w
        self._h_outline_path = outline
        self._h_word_paths = paths
        self._h_word_xs = xs
        self._h_word_widths = widths
        self._h_total_w = x

    def _build_vertical_cache(self, fm: QFontMetrics) -> None:
        """竖向统一块模型: 每个 display word 拆成 CJK 正立块 + 非 CJK 旋转块."""
        char_h = fm.ascent() + fm.descent()
        line_h = char_h + max(4, int(char_h * _VERTICAL_CHAR_GAP_RATIO))
        self._v_line_h = float(line_h)
        self._build_vertical_blocks(fm, line_h, char_h)

    def _build_vertical_blocks(self, fm: QFontMetrics, line_h: int, char_h: int) -> None:
        gap = line_h - char_h
        word_blocks: list[list[_VBlock]] = []
        word_heights: list[float] = []
        total_h = 0.0
        for w in self._display_words:
            segments = _segment_for_vertical(w.text)
            blocks: list[_VBlock] = []
            word_h = 0.0
            for seg_text, is_vert in segments:
                if is_vert:
                    path = QPainterPath()
                    for i, ch in enumerate(seg_text):
                        cw = fm.horizontalAdvance(ch)
                        path.addText(-cw / 2.0, float(i * line_h), self._font, ch)
                    v_h = float(len(seg_text) * line_h)
                    blocks.append(_VBlock(path=path, v_height=v_h, rotated=False, content_h=v_h))
                else:
                    path = QPainterPath()
                    path.addText(0.0, 0.0, self._font, seg_text)
                    path, visual_w = _normalize_path_x(path, _OUTLINE_WIDTH)
                    v_h = visual_w + gap
                    blocks.append(
                        _VBlock(path=path, v_height=v_h, rotated=True, content_h=visual_w)
                    )
                word_h += v_h
            word_blocks.append(blocks)
            word_heights.append(word_h)
            total_h += word_h
        self._v_word_blocks = word_blocks
        self._v_word_v_heights = word_heights
        self._v_total_v_height = total_h

    def _build_trans_horizontal_cache(self) -> None:
        if not self._translation or not self._trans_fm:
            self._trans_path = QPainterPath()
            self._trans_total_w = 0.0
            return
        path = QPainterPath()
        path.addText(0, 0, self._trans_font, self._translation)
        self._trans_path = path
        self._trans_total_w = float(self._trans_fm.horizontalAdvance(self._translation))

    def _build_trans_vertical_cache(self) -> None:
        if not self._translation or not self._trans_fm:
            self._v_trans_blocks = []
            self._v_trans_v_height = 0.0
            return
        self._build_trans_mixed_vertical_cache(self._trans_fm)

    def _build_trans_mixed_vertical_cache(self, tfm: QFontMetrics) -> None:
        char_h = tfm.ascent() + tfm.descent()
        line_h = char_h + max(3, int(char_h * _VERTICAL_CHAR_GAP_RATIO))
        gap = line_h - char_h
        blocks: list[_VBlock] = []
        total_h = 0.0
        for seg_text, is_vert in _segment_for_vertical(self._translation):
            if is_vert:
                path = QPainterPath()
                for i, ch in enumerate(seg_text):
                    cw = tfm.horizontalAdvance(ch)
                    path.addText(-cw / 2.0, float(i * line_h), self._trans_font, ch)
                v_h = float(len(seg_text) * line_h)
                blocks.append(_VBlock(path=path, v_height=v_h, rotated=False, content_h=v_h))
            else:
                path = QPainterPath()
                path.addText(0.0, 0.0, self._trans_font, seg_text)
                path, visual_w = _normalize_path_x(path, _TRANS_OUTLINE_WIDTH)
                v_h = visual_w + gap
                blocks.append(_VBlock(path=path, v_height=v_h, rotated=True, content_h=visual_w))
            total_h += v_h
        self._v_trans_blocks = blocks
        self._v_trans_v_height = total_h

    def _ensure_brush_cache(self) -> None:
        h = max(1, self.height())
        if h == self._brush_cache_height:
            return
        self._brush_cache_height = h
        for color, attr in (
            (self._color_base, "_cached_brush_base"),
            (self._color_highlight, "_cached_brush_highlight"),
        ):
            gradient = QLinearGradient(0.0, 0.0, 0.0, float(h))
            gradient.setColorAt(0.0, color)
            gradient.setColorAt(1.0, color.darker(_FILL_GRADIENT_DARKEN))
            setattr(self, attr, QBrush(gradient))

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
            # 竖向: 双列 (歌词右 + 翻译左), 高度 ~70% 屏高, 默认右侧距边 80px
            width = 200
            height = max(300, int(geo.height() * 0.7))
            x = geo.x() + geo.width() - width - 80
            y = geo.y() + (geo.height() - height) // 2
        else:
            # 横向: 宽 2/3 屏, 高 130 (容纳主歌词 + 翻译行), 距底 60px
            width = min(geo.width(), max(900, geo.width() * 2 // 3))
            height = 130
            x = geo.x() + (geo.width() - width) // 2
            y = geo.y() + geo.height() - height - 60
        self.setGeometry(x, y, width, height)

    def set_saved_geometries(self, horizontal: QRect | None, vertical: QRect | None) -> None:
        """Controller 推入横 / 竖两方向记忆的位置, 并按当前方向立即应用 (没有则默认)."""
        self._saved_geometries["horizontal"] = QRect(horizontal) if horizontal is not None else None
        self._saved_geometries["vertical"] = QRect(vertical) if vertical is not None else None
        self._apply_geometry_for_current()

    def _apply_geometry_for_current(self) -> None:
        """有当前方向的有效记忆位置 (clamp 到屏内) 则用它, 否则回默认几何."""
        saved = self._saved_geometries.get(self._orientation)
        if saved is not None:
            clamped = self._clamp_geometry(saved)
            if clamped is not None:
                self.setGeometry(clamped)
                return
        self._set_default_geometry()

    @staticmethod
    def _clamp_geometry(rect: QRect) -> QRect | None:
        """把记忆的几何夹到与之相交最多的屏幕可用区内; 完全离屏 / 无屏 / 尺寸非法 -> None.

        防止换显示器 / 拔副屏后窗口定位到看不见的地方; 返回 None 让调用方回退默认位置.
        """
        if rect.width() <= 0 or rect.height() <= 0:
            return None
        screens = QGuiApplication.screens()
        if not screens:
            return None
        best = None
        best_area = 0
        for screen in screens:
            inter = screen.availableGeometry().intersected(rect)
            area = inter.width() * inter.height()
            if area > best_area:
                best_area = area
                best = screen
        if best is None or best_area <= 0:
            return None
        avail = best.availableGeometry()
        w = min(rect.width(), avail.width())
        h = min(rect.height(), avail.height())
        x = min(max(rect.x(), avail.x()), avail.x() + avail.width() - w)
        y = min(max(rect.y(), avail.y()), avail.y() + avail.height() - h)
        return QRect(x, y, w, h)

    def _persist_current_geometry(self) -> None:
        """拖动结束后把当前几何记到当前方向并发信号给 Controller 落盘."""
        rect = self.geometry()
        self._saved_geometries[self._orientation] = QRect(rect)
        logger.info(
            "桌面歌词位置记住: %s %d,%d %dx%d",
            self._orientation,
            rect.x(),
            rect.y(),
            rect.width(),
            rect.height(),
        )
        self.geometryEdited.emit(self._orientation, rect.x(), rect.y(), rect.width(), rect.height())

    @staticmethod
    def _scroll_origin(content_len: float, focus_pos: float, viewport_len: float) -> float:
        if content_len <= viewport_len:
            return (viewport_len - content_len) / 2.0
        padding = min(float(_SCROLL_EDGE_PADDING), viewport_len / 4.0)
        target = viewport_len / 2.0 - focus_pos
        min_origin = viewport_len - content_len - padding
        max_origin = padding
        return min(max(target, min_origin), max_origin)

    def _active_display_word_index(self, ms: int) -> int:
        if not self._display_words:
            return -1
        idx = 0
        for i, word in enumerate(self._display_words):
            if ms >= word.start_ms:
                idx = i
            else:
                break
        return idx

    @staticmethod
    def _clamp_pos(value: float, upper: float) -> float:
        return min(max(0.0, value), max(0.0, upper))

    def _has_line_timing(self) -> bool:
        return (
            self._line_start_ms is not None
            and self._line_end_ms is not None
            and self._line_end_ms > self._line_start_ms
        )

    def _line_fraction(self, ms: int) -> float | None:
        if not self._has_line_timing():
            return None
        start = self._line_start_ms
        end = self._line_end_ms
        if ms <= start:
            return 0.0
        if ms >= end:
            return 1.0
        return (ms - start) / (end - start)

    def _horizontal_focus_x(self) -> float:
        if self._h_total_w <= 0:
            return 0.0
        if not self._word_infos or not self._display_words:
            fraction = self._line_fraction(self._effective_ms())
            return self._h_total_w * fraction if fraction is not None else self._h_total_w / 2.0
        ms = self._effective_ms()
        idx = self._active_display_word_index(ms)
        if idx < 0:
            return 0.0
        word = self._display_words[idx]
        fraction = self._fraction_at(word, ms)
        focus = self._h_word_xs[idx] + self._h_word_widths[idx] * fraction
        return self._clamp_pos(focus, self._h_total_w)

    def _vertical_focus_y(self) -> float:
        main_h = self._vertical_main_height()
        if main_h <= 0:
            return 0.0
        if not self._word_infos or not self._display_words:
            fraction = self._line_fraction(self._effective_ms())
            return main_h * fraction if fraction is not None else main_h / 2.0
        ms = self._effective_ms()
        idx = self._active_display_word_index(ms)
        if idx < 0:
            return 0.0
        word = self._display_words[idx]
        fraction = self._fraction_at(word, ms)
        focus = sum(self._v_word_v_heights[:idx]) + self._v_word_v_heights[idx] * fraction
        return self._clamp_pos(focus, main_h)

    def _horizontal_layout(self) -> _HorizontalLayout:
        fm = self._cached_fm
        if fm is None:
            return _HorizontalLayout(1.0, 0.0, 0.0, 0.0, float(self.height()), 0.0, 0.0)

        has_trans = self._has_trans and self._trans_fm is not None
        main_h = float(fm.ascent() + fm.descent())
        trans_h = 0.0
        trans_ascent = 0.0
        if has_trans:
            trans_h = float(self._trans_fm.ascent() + self._trans_fm.descent())
            trans_ascent = float(self._trans_fm.ascent())
        total_h = main_h + (_TRANS_GAP + trans_h if has_trans else 0.0)
        scale = 1.0
        focus_x = self._horizontal_focus_x()
        top = (self.height() - total_h) / 2.0
        baseline = top + fm.ascent()
        main_x = self._scroll_origin(self._h_total_w, focus_x, float(self.width()))
        trans_x = 0.0
        trans_baseline = 0.0
        if has_trans:
            ratio = focus_x / self._h_total_w if self._h_total_w > 0 else 0.5
            trans_focus = self._trans_total_w * ratio
            trans_x = self._scroll_origin(self._trans_total_w, trans_focus, float(self.width()))
            trans_baseline = top + main_h + _TRANS_GAP + trans_ascent
        baseline_local = baseline
        viewport_h = float(self.height())
        return _HorizontalLayout(
            scale=scale,
            main_x=main_x,
            baseline=baseline,
            baseline_local=baseline_local,
            viewport_h=viewport_h,
            trans_x=trans_x,
            trans_baseline=trans_baseline,
        )

    def _vertical_main_height(self) -> float:
        return self._v_total_v_height

    def _vertical_column_layout(self) -> _VerticalColumnLayout:
        fm = self._cached_fm
        if fm is None:
            return _VerticalColumnLayout(
                1.0,
                self.width() / 2.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            )

        has_trans = self._has_trans and self._trans_fm is not None
        main_h = float(self._vertical_main_height())
        trans_h = float(self._v_trans_v_height if has_trans else 0.0)
        main_ascent = float(fm.ascent())
        trans_ascent = float(self._trans_fm.ascent() if has_trans else 0.0)
        content_h = max(main_h, trans_h, 1.0)

        main_w = float(fm.ascent() + fm.descent())
        if has_trans:
            trans_w = float(self._trans_fm.ascent() + self._trans_fm.descent())
            content_w = main_w + _VCOL_GAP + trans_w
        else:
            trans_w = 0.0
            content_w = main_w
        scale = 1.0

        left_edge = max(0.0, (self.width() - content_w) / 2.0)
        if has_trans:
            trans_cx = left_edge + trans_w / 2.0
            main_cx = left_edge + trans_w + _VCOL_GAP + main_w / 2.0
        else:
            main_cx = self.width() / 2.0
            trans_cx = 0.0

        focus_y = self._vertical_focus_y()
        main_top = self._scroll_origin(main_h, focus_y, float(self.height()))
        ratio = focus_y / main_h if main_h > 0 else 0.5
        if has_trans:
            trans_focus = trans_h * ratio
            trans_top = self._scroll_origin(trans_h, trans_focus, float(self.height()))
        else:
            trans_top = 0.0
        main_start_y = main_top + main_ascent
        trans_start_y = trans_top + trans_ascent if has_trans else 0.0

        return _VerticalColumnLayout(
            scale=scale,
            main_cx=main_cx,
            trans_cx=trans_cx,
            main_start_y=main_start_y,
            trans_start_y=trans_start_y,
            main_h=main_h,
            trans_h=trans_h,
            main_ascent=main_ascent,
            trans_ascent=trans_ascent,
            content_h=content_h,
        )

    def _is_word_sung(self, word_idx: int) -> bool:
        """无 word 数据 -> 整句视为已唱; 否则按 sung_count 判定."""
        if not self._word_infos:
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

    @staticmethod
    def _fraction_at(w: _WordInfo, ms: int) -> float:
        if ms < w.start_ms:
            return 0.0
        if w.duration_ms <= 0 or ms >= w.end_ms:
            return 1.0
        return (ms - w.start_ms) / w.duration_ms

    def _word_fractions(self) -> list[tuple[str, float]]:
        """当前帧每个 word 的 (text, fill_fraction).

        无 ``words`` 数据 -> 整句作单段 fraction=1.0 (整体高亮色).
        有 ``words`` -> 每段按 ``elapsed/durationMs`` 算 0..1.
        """
        if not self._word_infos:
            return [(self._text, 1.0)] if self._text else []
        ms = self._effective_ms()
        return [(w.text, self._fraction_at(w, ms)) for w in self._display_words]

    def _has_active_wipe(self) -> bool:
        """是否有 word 正在 0<f<1 范围 (需要定时器持续插值)."""
        if not self._word_infos:
            return False
        ms = self._effective_ms()
        for w in self._word_infos:
            if w.start_ms > ms:
                break
            if ms < w.end_ms:
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
            was_dragging = self._drag_origin is not None
            self._drag_origin = None
            if was_dragging:
                self._persist_current_geometry()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ 显隐 + resize
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # 某些平台 (Windows) 在 show() / setWindowFlags 后会把 frameless 窗口移回默认位置,
        # 仅在 show() 之前 setGeometry 不够稳. 显示时再落实一次记忆位置, 防止重启 / 切显隐
        # 后窗口回到原处 (无记忆位置时即默认几何, 行为不变).
        self._apply_geometry_for_current()
        self._toggle_wipe_timer()

    def hideEvent(self, event: QHideEvent) -> None:
        # 隐藏后立刻停 timer, 不浪费 CPU 重绘看不见的内容
        self._wipe_timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if event.oldSize().height() != event.size().height():
            self._brush_cache_height = -1

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, _event: QPaintEvent) -> None:
        if not self._text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        self._ensure_brush_cache()

        if self._orientation == "vertical":
            self._paint_vertical(painter)
        else:
            self._paint_horizontal(painter)

    def _paint_horizontal(self, painter: QPainter) -> None:
        """横向: 缓存路径 + 逐字 wipe clip + 翻译."""
        if not self._display_words or not self._cached_fm:
            return
        layout = self._horizontal_layout()
        has_trans = self._has_trans

        ms = self._effective_ms()
        base_brush = self._cached_brush_base
        hi_brush = self._cached_brush_highlight
        nopen = Qt.PenStyle.NoPen

        painter.save()
        painter.translate(layout.main_x, layout.baseline)
        painter.scale(layout.scale, layout.scale)

        painter.setPen(self._outline_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._h_outline_path)

        for i, w in enumerate(self._display_words):
            word_path = self._h_word_paths[i]
            fraction = self._fraction_at(w, ms) if self._word_infos else 1.0

            painter.setPen(nopen)
            painter.setBrush(base_brush)
            painter.drawPath(word_path)

            if fraction > 0.0:
                word_x = self._h_word_xs[i]
                word_w = self._h_word_widths[i]
                clip_w = max(1.0, word_w * fraction)
                painter.save()
                clip_path = self._make_horizontal_wipe_clip(
                    word_x,
                    clip_w,
                    layout.baseline_local,
                    layout.viewport_h,
                )
                painter.setClipPath(clip_path)
                painter.setBrush(hi_brush)
                painter.drawPath(word_path)
                painter.restore()
        painter.restore()

        if has_trans:
            painter.save()
            painter.translate(layout.trans_x, layout.trans_baseline)
            painter.scale(layout.scale, layout.scale)
            painter.setPen(self._trans_outline_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._trans_path)
            painter.setPen(nopen)
            painter.setBrush(base_brush)
            painter.drawPath(self._trans_path)
            painter.restore()

    def _vcol_positions(self) -> tuple[float, float]:
        """竖排双列中心 X: (main_cx, trans_cx). 歌词右列, 翻译左列."""
        layout = self._vertical_column_layout()
        return layout.main_cx, layout.trans_cx

    def _paint_trans_vertical_blocks(
        self, painter: QPainter, layout: _VerticalColumnLayout
    ) -> None:
        trans_fm = self._trans_fm
        trans_baseline = (trans_fm.ascent() - trans_fm.descent()) / 2.0
        scale = layout.scale
        base_brush = self._cached_brush_base
        nopen = Qt.PenStyle.NoPen
        block_y = layout.trans_start_y
        for blk in self._v_trans_blocks:
            if blk.rotated:
                painter.save()
                painter.translate(layout.trans_cx, block_y + blk.content_h * scale / 2.0)
                painter.scale(scale, scale)
                painter.rotate(90)
                painter.translate(-blk.content_h / 2.0, trans_baseline)
                painter.setPen(self._trans_outline_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(blk.path)
                painter.setPen(nopen)
                painter.setBrush(base_brush)
                painter.drawPath(blk.path)
                painter.restore()
            else:
                painter.save()
                painter.translate(layout.trans_cx, block_y)
                painter.scale(scale, scale)
                painter.setPen(self._trans_outline_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(blk.path)
                painter.setPen(nopen)
                painter.setBrush(base_brush)
                painter.drawPath(blk.path)
                painter.restore()
            block_y += blk.v_height * scale

    def _paint_vertical(self, painter: QPainter) -> None:
        """竖向统一块模型: CJK 正立逐字堆叠 + 非 CJK 段整段旋转 90°, 翻译左列."""
        if not self._display_words or not self._cached_fm:
            return
        fm = self._cached_fm
        baseline_off = (fm.ascent() - fm.descent()) / 2.0

        layout = self._vertical_column_layout()
        has_trans = self._has_trans

        ms = self._effective_ms()
        base_brush = self._cached_brush_base
        hi_brush = self._cached_brush_highlight
        nopen = Qt.PenStyle.NoPen
        scale = layout.scale

        word_y = layout.main_start_y
        for i, w in enumerate(self._display_words):
            blocks = self._v_word_blocks[i]
            word_h = self._v_word_v_heights[i]
            fraction = self._fraction_at(w, ms) if self._word_infos else 1.0

            block_y = word_y
            for blk in blocks:
                if blk.rotated:
                    painter.save()
                    painter.translate(layout.main_cx, block_y + blk.content_h * scale / 2.0)
                    painter.scale(scale, scale)
                    painter.rotate(90)
                    painter.translate(-blk.content_h / 2.0, baseline_off)
                    painter.setPen(self._outline_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(blk.path)
                    painter.setPen(nopen)
                    painter.setBrush(base_brush)
                    painter.drawPath(blk.path)
                    painter.restore()
                else:
                    painter.save()
                    painter.translate(layout.main_cx, block_y)
                    painter.scale(scale, scale)
                    painter.setPen(self._outline_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(blk.path)
                    painter.setPen(nopen)
                    painter.setBrush(base_brush)
                    painter.drawPath(blk.path)
                    painter.restore()
                block_y += blk.v_height * scale

            if fraction > 0.0:
                clip_total = (word_h + fm.ascent()) * scale
                clip_h = max(1, int(round(clip_total * fraction)))
                painter.save()
                painter.setClipRect(
                    0,
                    int(word_y - fm.ascent() * scale),
                    self.width(),
                    clip_h,
                )
                block_y = word_y
                for blk in blocks:
                    if blk.rotated:
                        painter.save()
                        painter.translate(
                            layout.main_cx,
                            block_y + blk.content_h * scale / 2.0,
                        )
                        painter.scale(scale, scale)
                        painter.rotate(90)
                        painter.translate(-blk.content_h / 2.0, baseline_off)
                        painter.setPen(nopen)
                        painter.setBrush(hi_brush)
                        painter.drawPath(blk.path)
                        painter.restore()
                    else:
                        painter.save()
                        painter.translate(layout.main_cx, block_y)
                        painter.scale(scale, scale)
                        painter.setPen(nopen)
                        painter.setBrush(hi_brush)
                        painter.drawPath(blk.path)
                        painter.restore()
                    block_y += blk.v_height * scale
                painter.restore()

            word_y += word_h * scale

        if has_trans:
            self._paint_trans_vertical_blocks(painter, layout)

    def _is_slanted_font(self) -> bool:
        """斜体 / 倾斜样式都需要 clip 也跟着倾斜, 否则垂直 clip 把字劈成楔形."""
        return self._font.italic() or self._font.style() == QFont.Style.StyleOblique

    def _make_horizontal_wipe_clip(
        self,
        x_left: float,
        width_px: float,
        baseline: float,
        viewport_height: float | None = None,
    ) -> QPainterPath:
        """横向 wipe 的 clip 路径. 直立字体 -> 矩形; 斜体 -> 与字形 shear 匹配的平行四边形.

        斜体字形在基线上方右移 shear*Δy, 下方左移; clip 边沿必须同向 shear, 否则
        垂直切线会把字劈成楔形 (上半 / 下半各被剪掉一刀, 视觉极差).

        坐标系: painter 已 translate 到 (x0, baseline), 路径以 (0,0) 为文字原点.
        clip 必须覆盖 widget 全高, 用 y=[-baseline, h-baseline] (translate 后).
        """
        path = QPainterPath()
        h = float(self.height()) if viewport_height is None else float(viewport_height)
        if not self._is_slanted_font():
            path.addRect(x_left, -baseline, width_px, h)
            return path
        top_dx = baseline * _ITALIC_SHEAR
        bot_dx = -(h - baseline) * _ITALIC_SHEAR
        path.moveTo(QPointF(x_left + top_dx, -baseline))
        path.lineTo(QPointF(x_left + width_px + top_dx, -baseline))
        path.lineTo(QPointF(x_left + width_px + bot_dx, h - baseline))
        path.lineTo(QPointF(x_left + bot_dx, h - baseline))
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
        self._window.geometryEdited.connect(self._on_window_geometry_edited)
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

    @Slot(str, int, int, int, int)
    def _on_window_geometry_edited(self, orientation: str, x: int, y: int, w: int, h: int) -> None:
        """窗口被拖动后回写位置到 SettingsController (单向, 不再触发 settingsChanged)."""
        sc = self._settings_controller
        if sc is None:
            return
        setter = getattr(sc, "setDesktopLyricsGeometry", None)
        if callable(setter):
            setter(orientation, int(x), int(y), int(w), int(h))

    @staticmethod
    def _parse_geometry(value: str) -> QRect | None:
        """把 ``"x,y,w,h"`` 串解析回 QRect; 空 / 非法 -> None."""
        if not value:
            return None
        parts = str(value).split(",")
        if len(parts) != 4:
            return None
        try:
            x, y, w, h = (int(p) for p in parts)
        except (TypeError, ValueError):
            return None
        if w <= 0 or h <= 0:
            return None
        return QRect(x, y, w, h)

    @Slot()
    def _on_settings_changed(self) -> None:
        """SettingsController 任一字段变化都会重 emit settingsChanged; 全量拉取最简单."""
        sc = self._settings_controller
        if sc is None:
            return
        # 先把记忆位置推给窗口 (apply_settings 里的 set_orientation 会据此定位).
        self._window.set_saved_geometries(
            self._parse_geometry(str(getattr(sc, "desktopLyricsGeometryHorizontal", "") or "")),
            self._parse_geometry(str(getattr(sc, "desktopLyricsGeometryVertical", "") or "")),
        )
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
        """从 LyricController 拉当前行的 (text, words, translation)."""
        text = getattr(self._lyric_controller, "currentLineText", "") or ""
        words = self._current_words()
        translation = getattr(self._lyric_controller, "currentLineTranslation", "") or ""
        line_start_ms, line_end_ms = self._current_line_timing()
        self._window.set_line(
            text,
            words,
            translation=translation,
            line_start_ms=line_start_ms,
            line_end_ms=line_end_ms,
        )

    def _sync_position(self) -> None:
        if not getattr(self._lyric_controller, "positionMs", None) and not hasattr(
            self._lyric_controller, "positionMs"
        ):
            return
        position = int(getattr(self._lyric_controller, "positionMs", 0) or 0)
        self._window.set_progress_ms(position)

    def _current_words(self) -> list[dict[str, Any]]:
        """从 ``lyricModel.lineAt(activeIndex)`` 拿 ``words`` 列表; 失败时返 []."""
        line = self._current_line_map()
        words = (line or {}).get("words", [])
        return list(words) if isinstance(words, list) else []

    def _current_line_timing(self) -> tuple[int | None, int | None]:
        active_idx = getattr(self._lyric_controller, "activeIndex", -1)
        if active_idx is None or active_idx < 0:
            return None, None
        line = self._current_line_map()
        if not line:
            return None, None
        try:
            start = int(line.get("timestampMs"))
        except (TypeError, ValueError):
            return None, None
        next_line = self._line_map_at(active_idx + 1)
        try:
            end = int(next_line.get("timestampMs")) if next_line else None
        except (TypeError, ValueError):
            end = None
        if end is not None and end <= start:
            end = None
        return start, end

    def _current_line_map(self) -> dict[str, Any]:
        active_idx = getattr(self._lyric_controller, "activeIndex", -1)
        return self._line_map_at(active_idx)

    def _line_map_at(self, idx: int) -> dict[str, Any]:
        if idx is None or idx < 0:
            return {}
        model = getattr(self._lyric_controller, "lyricModel", None)
        if model is None:
            return {}
        line_at = getattr(model, "lineAt", None)
        if not callable(line_at):
            return {}
        try:
            line = line_at(idx)
        except Exception:
            return {}
        return line if isinstance(line, dict) else {}
