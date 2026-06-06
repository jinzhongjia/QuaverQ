"""Persistent user settings exposed to QML."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot

from quaverq.core.cover_cache import CoverCache

logger = logging.getLogger(__name__)

_THEME_MODES = {"system", "light", "dark"}
_QUALITY_PREFERENCES = {"standard", "balanced", "high"}

# 封面缓存默认上限 256 MB (设为 0 表示不限). 封面多为 30–80 KB 的 jpg,
# 256 MB 可缓存数千张, 正常使用不会触及; 用户可在设置页调整或关闭.
_DEFAULT_COVER_MAX_BYTES = 256 * 1024 * 1024


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
