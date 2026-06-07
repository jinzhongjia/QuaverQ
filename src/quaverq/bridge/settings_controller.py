"""Persistent user settings exposed to QML."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication

from quaverq.core.cover_cache import CoverCache

logger = logging.getLogger(__name__)

_THEME_MODES = {"system", "light", "dark"}
_QUALITY_PREFERENCES = {"standard", "balanced", "high"}
_LYRIC_FONT_WEIGHTS = {"regular", "medium", "bold"}

# 封面缓存默认上限 256 MB (设为 0 表示不限). 封面多为 30–80 KB 的 jpg,
# 256 MB 可缓存数千张, 正常使用不会触及; 用户可在设置页调整或关闭.
_DEFAULT_COVER_MAX_BYTES = 256 * 1024 * 1024

# 歌词字体大小: 基准为 active 行像素值. 12 以下不可读, 48 以上溢出面板.
_LYRIC_FONT_SIZE_MIN = 12
_LYRIC_FONT_SIZE_MAX = 48
_LYRIC_FONT_SIZE_DEFAULT = 22


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
        self._quality_preference = self._read_str(
            "playback/qualityPreference",
            "balanced",
            _QUALITY_PREFERENCES,
        )
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

    @Property(str, notify=settingsChanged)
    def themeMode(self) -> str:
        return self._theme_mode

    @Property(str, notify=settingsChanged)
    def qualityPreference(self) -> str:
        return self._quality_preference

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

    @Slot(str)
    def setQualityPreference(self, preference: str) -> None:
        value = preference if preference in _QUALITY_PREFERENCES else "balanced"
        if self._quality_preference == value:
            return
        self._quality_preference = value
        self._settings.setValue("playback/qualityPreference", value)
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
