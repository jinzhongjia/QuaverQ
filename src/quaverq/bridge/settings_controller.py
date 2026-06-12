"""Persistent user settings exposed to QML."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot
from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication

from quaverq.core.cover_cache import CoverCache

logger = logging.getLogger(__name__)

_THEME_MODES = {"system", "light", "dark"}
_QUALITY_PREFERENCES = {"standard", "balanced", "high"}
_LYRIC_FONT_WEIGHTS = {"regular", "medium", "bold"}
_DESKTOP_LYRIC_ORIENTATIONS = {"horizontal", "vertical"}
# 桌面歌词字体大小 (默认 32, 比歌词面板大, 配大字号 OSD 风格)
_DESKTOP_LYRIC_FONT_SIZE_MIN = 14
_DESKTOP_LYRIC_FONT_SIZE_MAX = 72
_DESKTOP_LYRIC_FONT_SIZE_DEFAULT = 32
# 桌面歌词默认颜色: 未唱白色 + 已唱 QQ 音乐风格深琥珀 (饱和度高 -> 桌面背景上识别度更好).
_DESKTOP_LYRIC_COLOR_BASE_DEFAULT = "#FFFFFF"
_DESKTOP_LYRIC_COLOR_HIGHLIGHT_DEFAULT = "#FFA200"

# 封面缓存默认上限 256 MB (设为 0 表示不限). 封面多为 30–80 KB 的 jpg,
# 256 MB 可缓存数千张, 正常使用不会触及; 用户可在设置页调整或关闭.
_DEFAULT_COVER_MAX_BYTES = 256 * 1024 * 1024

# 歌词字体大小: 基准为 active 行像素值. 12 以下不可读, 48 以上溢出面板.
_LYRIC_FONT_SIZE_MIN = 12
_LYRIC_FONT_SIZE_MAX = 48
_LYRIC_FONT_SIZE_DEFAULT = 22

# 切歌淡入淡出 (issue #11): 200ms 以下听感同硬切, 2s 以上拖沓; 默认 500ms 对齐
# QQ 官方桌面端的衔接节奏. 这是音频包络时长, 与 reduceMotion (视觉动效) 无关.
_FADE_DURATION_MIN_MS = 200
_FADE_DURATION_MAX_MS = 2000
_FADE_DURATION_DEFAULT_MS = 500


def _normalize_hex_color(raw: str | None) -> str | None:
    """把任意输入归一为大写 ``#RRGGBB``; 非法 hex / 空串 / None -> 返回 ``None``.

    QColor 解析能容忍多种格式 (``red`` / ``#FFF`` / ``#FFFFFFFF`` 等), 但持久化与
    UI 显示需要稳定的 ``#RRGGBB``. 用 QColor 做 normalize 并丢 alpha.
    """
    if not raw or not isinstance(raw, str):
        return None
    color = QColor(raw)
    if not color.isValid():
        return None
    return color.name().upper()  # QColor.name() 返 "#rrggbb" 小写, 统一大写


def _collect_cjk_font_families() -> list[str]:
    """枚举系统里能渲染简体中文的字体族 (Han 字形 → 同时具备 UTF-8 / CJK 支持).
    没有 QGuiApplication (例如纯 logic 测试) 时返回空列表, 不抛."""
    if QGuiApplication.instance() is None:
        return []
    families = QFontDatabase.families(QFontDatabase.WritingSystem.SimplifiedChinese)
    return sorted({f for f in families if f and not f.startswith("@")})


class SettingsController(QObject):
    """QSettings-backed preferences and cache actions."""

    settingsChanged = Signal()
    cacheChanged = Signal()
    errorRaised = Signal(str)

    def __init__(
        self,
        *,
        settings: QSettings | None = None,
        cover_cache: CoverCache | None = None,
        orphan_cleanup: Callable[[], list[Path]] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings or QSettings()
        self._cover_cache = cover_cache
        self._orphan_cleanup = orphan_cleanup
        self._theme_mode = self._read_str("ui/themeMode", "system", _THEME_MODES)
        # 减少动效 (无障碍): Qt 6.x 没有系统级 prefers-reduced-motion 接口, 走应用级设置;
        # 灌进 Motion singleton 后各处过渡时长归零、Marquee 横滚停用
        self._reduce_motion = self._read_bool("ui/reduceMotion", False)
        self._quality_preference = self._read_str(
            "playback/qualityPreference",
            "balanced",
            _QUALITY_PREFERENCES,
        )
        self._fade_enabled = self._read_bool("playback/fadeEnabled", True)
        self._fade_duration_ms = self._read_int_clamped(
            "playback/fadeDurationMs",
            _FADE_DURATION_DEFAULT_MS,
            _FADE_DURATION_MIN_MS,
            _FADE_DURATION_MAX_MS,
        )
        # 输出设备: id 为 base64 编码的 QAudioDevice.id() 字节串, 空 = 跟随系统默认;
        # label 是选择时的设备显示名快照, 设备断开时设置页占位 "xxx (已断开)" 用
        self._audio_output_device_id = str(
            self._settings.value("playback/audioOutputDeviceId", "") or ""
        )
        self._audio_output_device_label = str(
            self._settings.value("playback/audioOutputDeviceLabel", "") or ""
        )
        if not self._audio_output_device_id:
            self._audio_output_device_label = ""
        self._cover_cache_max_bytes = self._read_int(
            "cache/coverMaxBytes",
            _DEFAULT_COVER_MAX_BYTES,
        )
        if self._cover_cache is not None:
            try:
                # 启动时把上限推给缓存并淘汰一次, 处理上个不限版本遗留的超量缓存.
                self._cover_cache.set_max_bytes(self._cover_cache_max_bytes)
            except Exception:
                logger.exception("apply cover cache cap on init failed")
        self._cover_cache_size_text = self._format_bytes(self._cover_cache_bytes())
        self._lyric_font_family = str(self._settings.value("lyrics/fontFamily", "") or "")
        self._lyric_font_size = self._read_int_clamped(
            "lyrics/fontSize",
            _LYRIC_FONT_SIZE_DEFAULT,
            _LYRIC_FONT_SIZE_MIN,
            _LYRIC_FONT_SIZE_MAX,
        )
        self._lyric_font_weight = self._read_str(
            "lyrics/fontWeight",
            "medium",
            _LYRIC_FONT_WEIGHTS,
        )
        self._lyric_font_italic = self._read_bool("lyrics/italic", False)
        self._available_lyric_fonts: list[str] | None = None

        # 桌面悬浮歌词 (Windows-only feature; 字段持久化跨平台无伤大雅, 反正非 Windows
        # 不会实例化 DesktopLyricsController, 这些值就不会被读到).
        self._desktop_lyrics_enabled = self._read_bool("desktopLyrics/enabled", True)
        self._desktop_lyrics_locked = self._read_bool("desktopLyrics/locked", True)
        self._desktop_lyrics_font_family = str(
            self._settings.value("desktopLyrics/fontFamily", "") or ""
        )
        self._desktop_lyrics_font_size = self._read_int_clamped(
            "desktopLyrics/fontSize",
            _DESKTOP_LYRIC_FONT_SIZE_DEFAULT,
            _DESKTOP_LYRIC_FONT_SIZE_MIN,
            _DESKTOP_LYRIC_FONT_SIZE_MAX,
        )
        self._desktop_lyrics_bold = self._read_bool("desktopLyrics/bold", True)
        self._desktop_lyrics_italic = self._read_bool("desktopLyrics/italic", False)
        self._desktop_lyrics_orientation = self._read_str(
            "desktopLyrics/orientation",
            "horizontal",
            _DESKTOP_LYRIC_ORIENTATIONS,
        )
        self._desktop_lyrics_color_base = self._read_color(
            "desktopLyrics/colorBase",
            _DESKTOP_LYRIC_COLOR_BASE_DEFAULT,
        )
        self._desktop_lyrics_color_highlight = self._read_color(
            "desktopLyrics/colorHighlight",
            _DESKTOP_LYRIC_COLOR_HIGHLIGHT_DEFAULT,
        )

    @Property(str, notify=settingsChanged)
    def themeMode(self) -> str:
        return self._theme_mode

    @Property(bool, notify=settingsChanged)
    def reduceMotion(self) -> bool:
        return self._reduce_motion

    @Property(str, notify=settingsChanged)
    def qualityPreference(self) -> str:
        return self._quality_preference

    @Property(bool, notify=settingsChanged)
    def fadeEnabled(self) -> bool:
        """切歌淡入淡出总开关; 关闭后播放行为与无 fade 的旧实现完全一致."""
        return self._fade_enabled

    @Property(int, notify=settingsChanged)
    def fadeDurationMs(self) -> int:
        return self._fade_duration_ms

    @Property(str, notify=settingsChanged)
    def audioOutputDeviceId(self) -> str:
        """所选输出设备 id (base64 编码字节串); 空串 = 跟随系统默认."""
        return self._audio_output_device_id

    @Property(str, notify=settingsChanged)
    def audioOutputDeviceLabel(self) -> str:
        """所选输出设备的显示名快照; 跟随系统默认时恒为空串."""
        return self._audio_output_device_label

    @Property(str, notify=cacheChanged)
    def coverCacheSizeText(self) -> str:
        return self._cover_cache_size_text

    @Property(int, notify=cacheChanged)
    def coverCacheMaxBytes(self) -> int:
        """Current cover cache cap in bytes; 0 means unlimited."""
        return self._cover_cache_max_bytes

    @Property(str, notify=settingsChanged)
    def lyricFontFamily(self) -> str:
        return self._lyric_font_family

    @Property(int, notify=settingsChanged)
    def lyricFontSize(self) -> int:
        return self._lyric_font_size

    @Property(str, notify=settingsChanged)
    def lyricFontWeight(self) -> str:
        return self._lyric_font_weight

    @Property(bool, notify=settingsChanged)
    def lyricFontItalic(self) -> bool:
        return self._lyric_font_italic

    # ------------------------------------------------------------------ 桌面悬浮歌词 (Windows-only)

    @Property(bool, notify=settingsChanged)
    def desktopLyricsEnabled(self) -> bool:
        """是否启用桌面悬浮歌词. False -> Controller 立即隐藏窗口, 不动其他字段."""
        return self._desktop_lyrics_enabled

    @Property(bool, notify=settingsChanged)
    def desktopLyricsLocked(self) -> bool:
        return self._desktop_lyrics_locked

    @Property(str, notify=settingsChanged)
    def desktopLyricsFontFamily(self) -> str:
        return self._desktop_lyrics_font_family

    @Property(int, notify=settingsChanged)
    def desktopLyricsFontSize(self) -> int:
        return self._desktop_lyrics_font_size

    @Property(bool, notify=settingsChanged)
    def desktopLyricsBold(self) -> bool:
        return self._desktop_lyrics_bold

    @Property(bool, notify=settingsChanged)
    def desktopLyricsItalic(self) -> bool:
        return self._desktop_lyrics_italic

    @Property(str, notify=settingsChanged)
    def desktopLyricsOrientation(self) -> str:
        return self._desktop_lyrics_orientation

    @Property(str, notify=settingsChanged)
    def desktopLyricsColorBase(self) -> str:
        """未唱字色 (#RRGGBB hex 大写)."""
        return self._desktop_lyrics_color_base

    @Property(str, notify=settingsChanged)
    def desktopLyricsColorHighlight(self) -> str:
        """已唱字色 (#RRGGBB hex 大写)."""
        return self._desktop_lyrics_color_highlight

    @Property("QStringList", constant=True)
    def availableLyricFonts(self) -> list[str]:
        """系统中支持 CJK / UTF-8 的字体族; 首次访问时枚举并缓存."""
        if self._available_lyric_fonts is None:
            self._available_lyric_fonts = _collect_cjk_font_families()
        return self._available_lyric_fonts

    @Slot(str)
    def setThemeMode(self, mode: str) -> None:
        value = mode if mode in _THEME_MODES else "system"
        if self._theme_mode == value:
            return
        self._theme_mode = value
        self._settings.setValue("ui/themeMode", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(bool)
    def setReduceMotion(self, reduce: bool) -> None:
        value = bool(reduce)
        if self._reduce_motion == value:
            return
        self._reduce_motion = value
        self._settings.setValue("ui/reduceMotion", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(str)
    def setQualityPreference(self, preference: str) -> None:
        value = preference if preference in _QUALITY_PREFERENCES else "balanced"
        if self._quality_preference == value:
            return
        self._quality_preference = value
        self._settings.setValue("playback/qualityPreference", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(bool)
    def setFadeEnabled(self, enabled: bool) -> None:
        value = bool(enabled)
        if self._fade_enabled == value:
            return
        self._fade_enabled = value
        self._settings.setValue("playback/fadeEnabled", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(int)
    def setFadeDurationMs(self, duration_ms: int) -> None:
        try:
            value = int(duration_ms)
        except (TypeError, ValueError):
            return
        value = max(_FADE_DURATION_MIN_MS, min(_FADE_DURATION_MAX_MS, value))
        if self._fade_duration_ms == value:
            return
        self._fade_duration_ms = value
        self._settings.setValue("playback/fadeDurationMs", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(str, str)
    def setAudioOutputDevice(self, device_id: str, label: str) -> None:
        """选择输出设备: id 为 base64 字符串 (空 = 跟随系统默认), label 为设备显示名."""
        id_value = str(device_id or "").strip()
        label_value = str(label or "").strip() if id_value else ""
        if (self._audio_output_device_id, self._audio_output_device_label) == (
            id_value,
            label_value,
        ):
            return
        self._audio_output_device_id = id_value
        self._audio_output_device_label = label_value
        self._settings.setValue("playback/audioOutputDeviceId", id_value)
        self._settings.setValue("playback/audioOutputDeviceLabel", label_value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(int)
    def setCoverCacheMaxBytes(self, max_bytes: int) -> None:
        value = max(0, int(max_bytes))
        if value == self._cover_cache_max_bytes:
            return
        self._cover_cache_max_bytes = value
        self._settings.setValue("cache/coverMaxBytes", value)
        self._settings.sync()
        if self._cover_cache is not None:
            try:
                self._cover_cache.set_max_bytes(value)
            except Exception as exc:
                logger.exception("apply cover cache cap failed")
                self.errorRaised.emit(f"应用缓存上限失败：{exc}")
        self._set_cover_cache_size_text(self._format_bytes(self._cover_cache_bytes()))
        self.cacheChanged.emit()

    @Slot(str)
    def setLyricFontFamily(self, family: str) -> None:
        value = str(family or "").strip()
        if self._lyric_font_family == value:
            return
        self._lyric_font_family = value
        self._settings.setValue("lyrics/fontFamily", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(int)
    def setLyricFontSize(self, size: int) -> None:
        try:
            value = int(size)
        except (TypeError, ValueError):
            return
        value = max(_LYRIC_FONT_SIZE_MIN, min(_LYRIC_FONT_SIZE_MAX, value))
        if self._lyric_font_size == value:
            return
        self._lyric_font_size = value
        self._settings.setValue("lyrics/fontSize", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(str)
    def setLyricFontWeight(self, weight: str) -> None:
        value = weight if weight in _LYRIC_FONT_WEIGHTS else "medium"
        if self._lyric_font_weight == value:
            return
        self._lyric_font_weight = value
        self._settings.setValue("lyrics/fontWeight", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(bool)
    def setLyricFontItalic(self, italic: bool) -> None:
        value = bool(italic)
        if self._lyric_font_italic == value:
            return
        self._lyric_font_italic = value
        self._settings.setValue("lyrics/italic", value)
        self._settings.sync()
        self.settingsChanged.emit()

    # ------------------------------------------------------------------ 桌面悬浮歌词 setters

    @Slot(bool)
    def setDesktopLyricsEnabled(self, enabled: bool) -> None:
        value = bool(enabled)
        if self._desktop_lyrics_enabled == value:
            return
        self._desktop_lyrics_enabled = value
        self._settings.setValue("desktopLyrics/enabled", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(bool)
    def setDesktopLyricsLocked(self, locked: bool) -> None:
        value = bool(locked)
        if self._desktop_lyrics_locked == value:
            return
        self._desktop_lyrics_locked = value
        self._settings.setValue("desktopLyrics/locked", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(str)
    def setDesktopLyricsFontFamily(self, family: str) -> None:
        value = str(family or "").strip()
        if self._desktop_lyrics_font_family == value:
            return
        self._desktop_lyrics_font_family = value
        self._settings.setValue("desktopLyrics/fontFamily", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(int)
    def setDesktopLyricsFontSize(self, size: int) -> None:
        try:
            value = int(size)
        except (TypeError, ValueError):
            return
        value = max(_DESKTOP_LYRIC_FONT_SIZE_MIN, min(_DESKTOP_LYRIC_FONT_SIZE_MAX, value))
        if self._desktop_lyrics_font_size == value:
            return
        self._desktop_lyrics_font_size = value
        self._settings.setValue("desktopLyrics/fontSize", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(bool)
    def setDesktopLyricsBold(self, bold: bool) -> None:
        value = bool(bold)
        if self._desktop_lyrics_bold == value:
            return
        self._desktop_lyrics_bold = value
        self._settings.setValue("desktopLyrics/bold", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(bool)
    def setDesktopLyricsItalic(self, italic: bool) -> None:
        value = bool(italic)
        if self._desktop_lyrics_italic == value:
            return
        self._desktop_lyrics_italic = value
        self._settings.setValue("desktopLyrics/italic", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(str)
    def setDesktopLyricsOrientation(self, orientation: str) -> None:
        value = orientation if orientation in _DESKTOP_LYRIC_ORIENTATIONS else "horizontal"
        if self._desktop_lyrics_orientation == value:
            return
        self._desktop_lyrics_orientation = value
        self._settings.setValue("desktopLyrics/orientation", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(str)
    def setDesktopLyricsColorBase(self, color: str) -> None:
        value = _normalize_hex_color(color)
        if value is None or self._desktop_lyrics_color_base == value:
            return
        self._desktop_lyrics_color_base = value
        self._settings.setValue("desktopLyrics/colorBase", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(str)
    def setDesktopLyricsColorHighlight(self, color: str) -> None:
        value = _normalize_hex_color(color)
        if value is None or self._desktop_lyrics_color_highlight == value:
            return
        self._desktop_lyrics_color_highlight = value
        self._settings.setValue("desktopLyrics/colorHighlight", value)
        self._settings.sync()
        self.settingsChanged.emit()

    @Slot(str, result=str)
    def pickDesktopLyricsColor(self, role: str) -> str:
        """打开 QColorDialog 让用户选颜色, 选定后通过对应 setter 应用 + 返回 hex.

        role: ``base`` (未唱) / ``highlight`` (已唱). 用户取消 -> 返空串, 不动状态.
        QColorDialog 是 QtWidgets 模态对话框, 已有 QApplication, 不阻塞 Qt 事件循环
        (内部自跑 nested loop).
        """
        from PySide6.QtWidgets import QColorDialog

        if role == "base":
            initial = self._desktop_lyrics_color_base
        elif role == "highlight":
            initial = self._desktop_lyrics_color_highlight
        else:
            return ""
        chosen = QColorDialog.getColor(QColor(initial), None, "选择颜色")
        if not chosen.isValid():
            return ""
        hex_value = chosen.name().upper()  # QColor.name() -> "#rrggbb" 小写
        if role == "base":
            self.setDesktopLyricsColorBase(hex_value)
        else:
            self.setDesktopLyricsColorHighlight(hex_value)
        return hex_value

    @Slot()
    def resetDesktopLyrics(self) -> None:
        """字体 / 字号 / 粗体 / 斜体 / 方向 / 颜色 -> 默认. 启用 / 锁定状态不动 (用户偏好独立)."""
        changed = False
        if self._desktop_lyrics_font_family != "":
            self._desktop_lyrics_font_family = ""
            self._settings.setValue("desktopLyrics/fontFamily", "")
            changed = True
        if self._desktop_lyrics_font_size != _DESKTOP_LYRIC_FONT_SIZE_DEFAULT:
            self._desktop_lyrics_font_size = _DESKTOP_LYRIC_FONT_SIZE_DEFAULT
            self._settings.setValue("desktopLyrics/fontSize", _DESKTOP_LYRIC_FONT_SIZE_DEFAULT)
            changed = True
        if self._desktop_lyrics_bold is not True:
            self._desktop_lyrics_bold = True
            self._settings.setValue("desktopLyrics/bold", True)
            changed = True
        if self._desktop_lyrics_italic is not False:
            self._desktop_lyrics_italic = False
            self._settings.setValue("desktopLyrics/italic", False)
            changed = True
        if self._desktop_lyrics_orientation != "horizontal":
            self._desktop_lyrics_orientation = "horizontal"
            self._settings.setValue("desktopLyrics/orientation", "horizontal")
            changed = True
        if self._desktop_lyrics_color_base != _DESKTOP_LYRIC_COLOR_BASE_DEFAULT:
            self._desktop_lyrics_color_base = _DESKTOP_LYRIC_COLOR_BASE_DEFAULT
            self._settings.setValue("desktopLyrics/colorBase", _DESKTOP_LYRIC_COLOR_BASE_DEFAULT)
            changed = True
        if self._desktop_lyrics_color_highlight != _DESKTOP_LYRIC_COLOR_HIGHLIGHT_DEFAULT:
            self._desktop_lyrics_color_highlight = _DESKTOP_LYRIC_COLOR_HIGHLIGHT_DEFAULT
            self._settings.setValue(
                "desktopLyrics/colorHighlight", _DESKTOP_LYRIC_COLOR_HIGHLIGHT_DEFAULT
            )
            changed = True
        if changed:
            self._settings.sync()
            self.settingsChanged.emit()

    @Slot()
    def resetLyricFont(self) -> None:
        """把 4 个歌词字体字段全部恢复到默认值, 仅在确有变化时统一发一次 settingsChanged."""
        changed = False
        if self._lyric_font_family != "":
            self._lyric_font_family = ""
            self._settings.setValue("lyrics/fontFamily", "")
            changed = True
        if self._lyric_font_size != _LYRIC_FONT_SIZE_DEFAULT:
            self._lyric_font_size = _LYRIC_FONT_SIZE_DEFAULT
            self._settings.setValue("lyrics/fontSize", _LYRIC_FONT_SIZE_DEFAULT)
            changed = True
        if self._lyric_font_weight != "medium":
            self._lyric_font_weight = "medium"
            self._settings.setValue("lyrics/fontWeight", "medium")
            changed = True
        if self._lyric_font_italic is not False:
            self._lyric_font_italic = False
            self._settings.setValue("lyrics/italic", False)
            changed = True
        if changed:
            self._settings.sync()
            self.settingsChanged.emit()

    @Slot()
    def refreshCoverCacheSize(self) -> None:
        self._set_cover_cache_size_text(self._format_bytes(self._cover_cache_bytes()))

    @Slot()
    def clearCoverCache(self) -> None:
        self._run_orphan_cleanup()
        if self._cover_cache is None:
            self._set_cover_cache_size_text(self._format_bytes(0))
            return
        try:
            removed = self._cover_cache.clear()
        except Exception as exc:
            logger.exception("clear cover cache failed")
            message = f"清理封面缓存失败：{exc}"
            self.errorRaised.emit(message)
            return
        logger.info("cleared cover cache: %s", self._format_bytes(removed))
        self._set_cover_cache_size_text(self._format_bytes(self._cover_cache_bytes()))

    def _run_orphan_cleanup(self) -> None:
        if self._orphan_cleanup is None:
            return
        try:
            removed = self._orphan_cleanup()
        except Exception:
            logger.exception("orphan cache cleanup failed")
            return
        if removed:
            logger.info(
                "removed orphan caches: %s",
                ", ".join(str(path) for path in removed),
            )

    def _cover_cache_bytes(self) -> int:
        if self._cover_cache is None:
            return 0
        try:
            return self._cover_cache.size_bytes()
        except Exception as exc:
            logger.warning("cover cache size failed: %s", exc)
            return 0

    def _set_cover_cache_size_text(self, value: str) -> None:
        if self._cover_cache_size_text == value:
            return
        self._cover_cache_size_text = value
        self.cacheChanged.emit()

    def _read_str(
        self,
        key: str,
        default: str,
        allowed: set[str],
    ) -> str:
        value = str(self._settings.value(key, default) or default)
        if value not in allowed:
            self._settings.setValue(key, default)
            self._settings.sync()
            return default
        return value

    def _read_int(self, key: str, default: int) -> int:
        try:
            value = int(self._settings.value(key, default))
        except (TypeError, ValueError):
            return default
        return value if value >= 0 else default

    def _read_int_clamped(self, key: str, default: int, lo: int, hi: int) -> int:
        try:
            value = int(self._settings.value(key, default))
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, value))

    def _read_color(self, key: str, default: str) -> str:
        raw = self._settings.value(key, default)
        normalized = _normalize_hex_color(raw if isinstance(raw, str) else default)
        return normalized or default

    def _read_bool(self, key: str, default: bool) -> bool:
        raw = self._settings.value(key, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw)

    @staticmethod
    def _format_bytes(size: int) -> str:
        size = max(0, int(size))
        if size < 1024:
            return f"{size} B"
        units = ("KB", "MB", "GB")
        value = float(size)
        for unit in units:
            value /= 1024.0
            if value < 1024.0 or unit == units[-1]:
                return f"{value:.1f} {unit}"
        return f"{value:.1f} GB"
