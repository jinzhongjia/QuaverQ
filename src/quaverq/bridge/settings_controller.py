"""Persistent user settings exposed to QML."""

from __future__ import annotations

import logging
from PySide6.QtCore import QObject, Property, QSettings, Signal, Slot

from quaverq.core.cover_cache import CoverCache

logger = logging.getLogger(__name__)

_THEME_MODES = {"system", "light", "dark"}
_QUALITY_PREFERENCES = {"standard", "balanced", "high"}


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
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings or QSettings()
        self._cover_cache = cover_cache
        self._theme_mode = self._read_str("ui/themeMode", "system", _THEME_MODES)
        self._quality_preference = self._read_str(
            "playback/qualityPreference",
            "balanced",
            _QUALITY_PREFERENCES,
        )
        self._cover_cache_size_text = self._format_bytes(self._cover_cache_bytes())

    @Property(str, notify=settingsChanged)
    def themeMode(self) -> str:
        return self._theme_mode

    @Property(str, notify=settingsChanged)
    def qualityPreference(self) -> str:
        return self._quality_preference

    @Property(str, notify=cacheChanged)
    def coverCacheSizeText(self) -> str:
        return self._cover_cache_size_text

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

    @Slot()
    def refreshCoverCacheSize(self) -> None:
        self._set_cover_cache_size_text(self._format_bytes(self._cover_cache_bytes()))

    @Slot()
    def clearCoverCache(self) -> None:
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
