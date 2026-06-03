"""SettingsController tests."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from quaverq.bridge.settings_controller import SettingsController
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
