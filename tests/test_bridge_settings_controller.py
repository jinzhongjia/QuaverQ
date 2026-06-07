"""SettingsController tests."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings

from quaverq.bridge.settings_controller import (
    _DEFAULT_COVER_MAX_BYTES,
    _LYRIC_FONT_SIZE_DEFAULT,
    _LYRIC_FONT_SIZE_MAX,
    _LYRIC_FONT_SIZE_MIN,
    SettingsController,
)
from quaverq.core.cover_cache import CoverCache


def _settings(path: Path) -> QSettings:
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.clear()
    return settings


def test_settings_controller_uses_defaults_for_missing_values(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    assert controller.themeMode == "system"
    assert controller.qualityPreference == "balanced"


def test_settings_controller_persists_values(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))

    controller.setThemeMode("dark")
    controller.setQualityPreference("high")

    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.themeMode == "dark"
    assert reloaded.qualityPreference == "high"


def test_settings_controller_rejects_invalid_values(tmp_path):
    settings = _settings(tmp_path / "settings.ini")
    settings.setValue("ui/themeMode", "sepia")
    settings.setValue("playback/qualityPreference", "lossless-plus")
    settings.sync()

    controller = SettingsController(settings=settings)

    assert controller.themeMode == "system"
    assert controller.qualityPreference == "balanced"


def test_settings_controller_reports_and_clears_cover_cache(tmp_path):
    cache = CoverCache(tmp_path / "covers")
    cache.dir.mkdir(parents=True)
    (cache.dir / "a.jpg").write_bytes(b"abc")
    controller = SettingsController(
        settings=_settings(tmp_path / "settings.ini"),
        cover_cache=cache,
    )

    assert controller.coverCacheSizeText == "3 B"
    controller.clearCoverCache()

    assert controller.coverCacheSizeText == "0 B"
    assert cache.size_bytes() == 0


# ============================================================== cover cache cap


def test_cover_cache_max_bytes_defaults(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    assert controller.coverCacheMaxBytes == _DEFAULT_COVER_MAX_BYTES


def test_set_cover_cache_max_bytes_persists(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))

    controller.setCoverCacheMaxBytes(128 * 1024 * 1024)

    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.coverCacheMaxBytes == 128 * 1024 * 1024


def test_set_cover_cache_max_bytes_applies_to_cache(tmp_path):
    cache = CoverCache(tmp_path / "covers")
    controller = SettingsController(
        settings=_settings(tmp_path / "settings.ini"),
        cover_cache=cache,
    )

    controller.setCoverCacheMaxBytes(64 * 1024 * 1024)

    assert cache.max_bytes == 64 * 1024 * 1024


def test_set_cover_cache_max_bytes_enforces_immediately(tmp_path):
    cache = CoverCache(tmp_path / "covers")
    cache.dir.mkdir(parents=True)
    old = cache.dir / "a.jpg"
    new = cache.dir / "b.jpg"
    old.write_bytes(b"aaaa")
    new.write_bytes(b"bbbb")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    controller = SettingsController(
        settings=_settings(tmp_path / "settings.ini"),
        cover_cache=cache,
    )

    controller.setCoverCacheMaxBytes(4)

    assert not old.exists()  # oldest evicted to satisfy the cap
    assert new.exists()
    assert controller.coverCacheSizeText == "4 B"  # size text refreshed


def test_cover_cache_cap_applied_on_init(tmp_path):
    settings = _settings(tmp_path / "settings.ini")
    settings.setValue("cache/coverMaxBytes", 4)
    settings.sync()
    cache = CoverCache(tmp_path / "covers")
    cache.dir.mkdir(parents=True)
    old = cache.dir / "a.jpg"
    new = cache.dir / "b.jpg"
    old.write_bytes(b"aaaa")
    new.write_bytes(b"bbbb")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))

    SettingsController(settings=settings, cover_cache=cache)

    assert cache.max_bytes == 4
    assert not old.exists()  # startup enforces a previously-unbounded cache
    assert new.exists()


def test_set_cover_cache_max_bytes_zero_is_unlimited(tmp_path):
    cache = CoverCache(tmp_path / "covers")
    cache.dir.mkdir(parents=True)
    (cache.dir / "a.jpg").write_bytes(b"aaaa")
    controller = SettingsController(
        settings=_settings(tmp_path / "settings.ini"),
        cover_cache=cache,
    )

    controller.setCoverCacheMaxBytes(0)

    assert controller.coverCacheMaxBytes == 0
    assert cache.max_bytes == 0
    assert cache.size_bytes() == 4  # nothing evicted when unlimited


def test_set_cover_cache_max_bytes_clamps_negative_to_zero(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    controller.setCoverCacheMaxBytes(-1)

    assert controller.coverCacheMaxBytes == 0


def test_invalid_stored_max_bytes_falls_back_to_default(tmp_path):
    settings = _settings(tmp_path / "settings.ini")
    settings.setValue("cache/coverMaxBytes", "not-a-number")
    settings.sync()

    controller = SettingsController(settings=settings)

    assert controller.coverCacheMaxBytes == _DEFAULT_COVER_MAX_BYTES


# ============================================================== orphan cleanup


def test_clear_cover_cache_runs_orphan_cleanup(tmp_path):
    cache = CoverCache(tmp_path / "covers")
    cache.dir.mkdir(parents=True)
    (cache.dir / "a.jpg").write_bytes(b"abc")
    calls: list[bool] = []
    controller = SettingsController(
        settings=_settings(tmp_path / "settings.ini"),
        cover_cache=cache,
        orphan_cleanup=lambda: (calls.append(True), [])[1],
    )

    controller.clearCoverCache()

    assert calls  # orphan cleanup invoked alongside the cover cache clear
    assert cache.size_bytes() == 0


def test_clear_cover_cache_without_orphan_cleanup_is_fine(tmp_path):
    cache = CoverCache(tmp_path / "covers")
    cache.dir.mkdir(parents=True)
    (cache.dir / "a.jpg").write_bytes(b"abc")
    controller = SettingsController(
        settings=_settings(tmp_path / "settings.ini"),
        cover_cache=cache,
    )

    controller.clearCoverCache()  # no orphan_cleanup -> no crash

    assert cache.size_bytes() == 0


# ============================================================== lyric font


def test_lyric_font_defaults(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    assert controller.lyricFontFamily == ""
    assert controller.lyricFontSize == _LYRIC_FONT_SIZE_DEFAULT
    assert controller.lyricFontWeight == "medium"
    assert controller.lyricFontItalic is False


def test_lyric_font_persists(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))

    controller.setLyricFontFamily("Noto Sans CJK SC")
    controller.setLyricFontSize(26)
    controller.setLyricFontWeight("bold")
    controller.setLyricFontItalic(True)

    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.lyricFontFamily == "Noto Sans CJK SC"
    assert reloaded.lyricFontSize == 26
    assert reloaded.lyricFontWeight == "bold"
    assert reloaded.lyricFontItalic is True


def test_lyric_font_size_clamps_to_range(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    controller.setLyricFontSize(_LYRIC_FONT_SIZE_MIN - 5)
    assert controller.lyricFontSize == _LYRIC_FONT_SIZE_MIN

    controller.setLyricFontSize(_LYRIC_FONT_SIZE_MAX + 10)
    assert controller.lyricFontSize == _LYRIC_FONT_SIZE_MAX


def test_lyric_font_weight_rejects_invalid(tmp_path):
    settings = _settings(tmp_path / "settings.ini")
    settings.setValue("lyrics/fontWeight", "ultra-extreme")
    settings.sync()

    controller = SettingsController(settings=settings)

    assert controller.lyricFontWeight == "medium"


def test_lyric_font_size_invalid_falls_back(tmp_path):
    settings = _settings(tmp_path / "settings.ini")
    settings.setValue("lyrics/fontSize", "huge")
    settings.sync()

    controller = SettingsController(settings=settings)

    assert controller.lyricFontSize == _LYRIC_FONT_SIZE_DEFAULT


def test_lyric_font_emits_settings_changed(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    emitted: list[int] = []
    controller.settingsChanged.connect(lambda: emitted.append(1))

    controller.setLyricFontFamily("Sans")
    controller.setLyricFontSize(24)
    controller.setLyricFontWeight("regular")
    controller.setLyricFontItalic(True)

    assert len(emitted) == 4

    controller.setLyricFontFamily("Sans")  # 重复值不再 emit
    assert len(emitted) == 4


def test_reset_lyric_font_restores_defaults(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    controller.setLyricFontFamily("Noto Serif")
    controller.setLyricFontSize(34)
    controller.setLyricFontWeight("bold")
    controller.setLyricFontItalic(True)

    controller.resetLyricFont()

    assert controller.lyricFontFamily == ""
    assert controller.lyricFontSize == _LYRIC_FONT_SIZE_DEFAULT
    assert controller.lyricFontWeight == "medium"
    assert controller.lyricFontItalic is False

    # 持久化也应被清掉
    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.lyricFontFamily == ""
    assert reloaded.lyricFontSize == _LYRIC_FONT_SIZE_DEFAULT
    assert reloaded.lyricFontWeight == "medium"
    assert reloaded.lyricFontItalic is False


def test_reset_lyric_font_emits_settings_changed_once(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    controller.setLyricFontSize(40)
    emitted: list[int] = []
    controller.settingsChanged.connect(lambda: emitted.append(1))

    controller.resetLyricFont()

    assert len(emitted) == 1  # 4 个字段一起重置只发一次信号


def test_reset_lyric_font_noop_when_already_default(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    emitted: list[int] = []
    controller.settingsChanged.connect(lambda: emitted.append(1))

    controller.resetLyricFont()

    assert emitted == []  # 全部已是默认值, 不发信号
