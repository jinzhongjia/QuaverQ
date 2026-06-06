"""SettingsController tests."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings

from quaverq.bridge.settings_controller import (
    _DEFAULT_COVER_MAX_BYTES,
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
