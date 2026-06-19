"""SettingsController tests."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings

from quaverq.bridge.settings_controller import (
    _DEFAULT_COVER_MAX_BYTES,
    _FADE_DURATION_DEFAULT_MS,
    _FADE_DURATION_MAX_MS,
    _FADE_DURATION_MIN_MS,
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


# ============================================================== audio output device


def test_audio_output_device_defaults_to_follow_system(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    assert controller.audioOutputDeviceId == ""
    assert controller.audioOutputDeviceLabel == ""


def test_set_audio_output_device_persists(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))

    controller.setAudioOutputDevice("c2luay1hbHNh", "USB 耳机")

    assert controller.audioOutputDeviceId == "c2luay1hbHNh"
    assert controller.audioOutputDeviceLabel == "USB 耳机"
    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.audioOutputDeviceId == "c2luay1hbHNh"
    assert reloaded.audioOutputDeviceLabel == "USB 耳机"


def test_set_audio_output_device_emits_once_and_skips_same_value(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    seen = []
    controller.settingsChanged.connect(lambda: seen.append(1))

    controller.setAudioOutputDevice("abc", "Speaker")
    controller.setAudioOutputDevice("abc", "Speaker")

    assert len(seen) == 1


def test_set_audio_output_device_label_only_change_emits(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    controller.setAudioOutputDevice("abc", "Speaker")
    seen = []
    controller.settingsChanged.connect(lambda: seen.append(1))

    controller.setAudioOutputDevice("abc", "Speaker (HDMI)")

    assert len(seen) == 1
    assert controller.audioOutputDeviceLabel == "Speaker (HDMI)"


def test_set_audio_output_device_back_to_default_clears_label(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    controller.setAudioOutputDevice("abc", "Speaker")

    controller.setAudioOutputDevice("", "残留名字不应保存")

    assert controller.audioOutputDeviceId == ""
    assert controller.audioOutputDeviceLabel == ""
    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.audioOutputDeviceId == ""
    assert reloaded.audioOutputDeviceLabel == ""


def test_set_audio_output_device_normalizes_none(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    controller.setAudioOutputDevice("abc", "Speaker")

    controller.setAudioOutputDevice(None, None)

    assert controller.audioOutputDeviceId == ""
    assert controller.audioOutputDeviceLabel == ""


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


def test_clear_cover_cache_clears_cover_files(tmp_path):
    cache = CoverCache(tmp_path / "covers")
    cache.dir.mkdir(parents=True)
    (cache.dir / "a.jpg").write_bytes(b"abc")
    controller = SettingsController(
        settings=_settings(tmp_path / "settings.ini"),
        cover_cache=cache,
    )

    controller.clearCoverCache()

    assert cache.size_bytes() == 0


# ============================================================== lyric font


def test_lyric_font_defaults(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    assert controller.lyricFontFamily == ""
    assert controller.lyricFontSize == _LYRIC_FONT_SIZE_DEFAULT
    assert controller.lyricFontWeight == "medium"
    assert controller.lyricFontItalic is False


def test_lyric_translation_visibility_defaults_on(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    assert controller.lyricTranslationVisible is True


def test_lyric_translation_visibility_persists_and_emits_once(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    emitted: list[bool] = []
    controller.settingsChanged.connect(lambda: emitted.append(controller.lyricTranslationVisible))

    controller.setLyricTranslationVisible(False)
    controller.setLyricTranslationVisible(False)

    assert emitted == [False]
    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.lyricTranslationVisible is False


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


# ============================================================== 桌面悬浮歌词 (Windows-only)


def test_desktop_lyrics_defaults(tmp_path):
    """默认: 锁定 / 字体家族空 (Window 端用 Microsoft YaHei UI 默认) / 32 size / bold / 不斜体 / 横向."""
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    assert controller.desktopLyricsLocked is True
    assert controller.desktopLyricsFontFamily == ""
    assert controller.desktopLyricsFontSize == 32
    assert controller.desktopLyricsBold is True
    assert controller.desktopLyricsItalic is False
    assert controller.desktopLyricsOrientation == "horizontal"


def test_desktop_lyrics_setters_persist(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    controller.setDesktopLyricsLocked(False)
    controller.setDesktopLyricsFontFamily("SimHei")
    controller.setDesktopLyricsFontSize(40)
    controller.setDesktopLyricsBold(False)
    controller.setDesktopLyricsItalic(True)
    controller.setDesktopLyricsOrientation("vertical")

    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.desktopLyricsLocked is False
    assert reloaded.desktopLyricsFontFamily == "SimHei"
    assert reloaded.desktopLyricsFontSize == 40
    assert reloaded.desktopLyricsBold is False
    assert reloaded.desktopLyricsItalic is True
    assert reloaded.desktopLyricsOrientation == "vertical"


def test_desktop_lyrics_font_size_clamped(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    controller.setDesktopLyricsFontSize(1000)
    assert controller.desktopLyricsFontSize == 72
    controller.setDesktopLyricsFontSize(-5)
    assert controller.desktopLyricsFontSize == 14


def test_desktop_lyrics_orientation_rejects_invalid(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    controller.setDesktopLyricsOrientation("diagonal")
    assert controller.desktopLyricsOrientation == "horizontal"


def test_desktop_lyrics_setters_no_redundant_signal(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    emitted: list[int] = []
    controller.settingsChanged.connect(lambda: emitted.append(1))

    controller.setDesktopLyricsLocked(True)
    controller.setDesktopLyricsOrientation("horizontal")
    assert emitted == []

    controller.setDesktopLyricsLocked(False)
    assert len(emitted) == 1


def test_desktop_lyrics_color_defaults(tmp_path):
    """默认: 未唱白色 + 已唱 QQ 风格暖黄 (#FFA200)."""
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    assert controller.desktopLyricsColorBase == "#FFFFFF"
    assert controller.desktopLyricsColorHighlight == "#FFA200"


def test_desktop_lyrics_color_setters_persist(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    controller.setDesktopLyricsColorBase("#aabbcc")
    # Qt 接受 #AARRGGBB (alpha-first), 这里 #11223344 = alpha=0x11/R=22/G=33/B=44, 存为 #223344
    controller.setDesktopLyricsColorHighlight("#11223344")

    # 统一大写存 + 不含 alpha 段 (颜色对比下 alpha 没意义, 解析后只保留 #RRGGBB)
    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.desktopLyricsColorBase == "#AABBCC"
    assert reloaded.desktopLyricsColorHighlight == "#223344"


def test_desktop_lyrics_color_rejects_invalid(tmp_path):
    """非 hex / 错长度 / 含字母不 valid -> 静默忽略, 保留旧值."""
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    controller.setDesktopLyricsColorBase("not-a-color")
    assert controller.desktopLyricsColorBase == "#FFFFFF"
    controller.setDesktopLyricsColorHighlight("#xyz")
    assert controller.desktopLyricsColorHighlight == "#FFA200"
    controller.setDesktopLyricsColorBase("")
    assert controller.desktopLyricsColorBase == "#FFFFFF"


def test_reset_desktop_lyrics(tmp_path):
    """重置: 字体 / 字号 / 粗体 / 斜体 / 方向 / 颜色全部回默认; 锁定 / 启用状态不动 (用户偏好独立)."""
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    controller.setDesktopLyricsEnabled(False)
    controller.setDesktopLyricsLocked(False)
    controller.setDesktopLyricsFontFamily("SimHei")
    controller.setDesktopLyricsFontSize(48)
    controller.setDesktopLyricsBold(False)
    controller.setDesktopLyricsItalic(True)
    controller.setDesktopLyricsOrientation("vertical")
    controller.setDesktopLyricsColorBase("#000000")
    controller.setDesktopLyricsColorHighlight("#FF0000")

    controller.resetDesktopLyrics()

    assert controller.desktopLyricsEnabled is False  # 启用不动
    assert controller.desktopLyricsLocked is False  # 锁定不动
    assert controller.desktopLyricsFontFamily == ""
    assert controller.desktopLyricsFontSize == 32
    assert controller.desktopLyricsBold is True
    assert controller.desktopLyricsItalic is False
    assert controller.desktopLyricsOrientation == "horizontal"
    assert controller.desktopLyricsColorBase == "#FFFFFF"
    assert controller.desktopLyricsColorHighlight == "#FFA200"


def test_desktop_lyrics_enabled_default(tmp_path):
    """默认启用 (用户主动关才关). 默认 True 配合"装即用"."""
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    assert controller.desktopLyricsEnabled is True


def test_desktop_lyrics_enabled_setter_persist(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    controller.setDesktopLyricsEnabled(False)
    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.desktopLyricsEnabled is False


def test_desktop_lyrics_enabled_setter_signal(tmp_path):
    """变化才 emit; 重复 set 同值不 emit."""
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    emitted: list[int] = []
    controller.settingsChanged.connect(lambda: emitted.append(1))

    controller.setDesktopLyricsEnabled(True)  # 同默认值
    assert emitted == []

    controller.setDesktopLyricsEnabled(False)
    assert len(emitted) == 1


def test_reduce_motion_defaults_off(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    assert controller.reduceMotion is False


def test_reduce_motion_persists(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    events: list[bool] = []
    controller.settingsChanged.connect(lambda: events.append(controller.reduceMotion))

    controller.setReduceMotion(True)
    assert controller.reduceMotion is True
    assert events == [True]

    # 同值幂等: 不重复落盘 / 不重复发信号
    controller.setReduceMotion(True)
    assert events == [True]

    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.reduceMotion is True


# ============================================================== download settings


def test_download_settings_defaults(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    assert controller.downloadQuality == "balanced"
    assert controller.downloadWithLyric is True
    assert controller.downloadWithCover is True
    # 默认目录: <系统音乐目录>/QuaverQ (QStandardPaths 解析, 非空)
    assert controller.downloadDirectory
    assert Path(controller.downloadDirectory).name == "QuaverQ"


def test_download_settings_persist(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))

    controller.setDownloadQuality("high")
    controller.setDownloadDirectory(str(tmp_path / "music"))
    controller.setDownloadWithLyric(False)
    controller.setDownloadWithCover(False)

    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.downloadQuality == "high"
    assert reloaded.downloadDirectory == str(tmp_path / "music")
    assert reloaded.downloadWithLyric is False
    assert reloaded.downloadWithCover is False


def test_download_quality_rejects_invalid(tmp_path):
    settings = _settings(tmp_path / "settings.ini")
    settings.setValue("download/quality", "master-plus")
    settings.sync()

    controller = SettingsController(settings=settings)
    assert controller.downloadQuality == "balanced"

    controller.setDownloadQuality("nonsense")
    assert controller.downloadQuality == "balanced"


def test_download_embed_tags_defaults_on_and_persists(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))
    assert controller.downloadEmbedTags is True

    controller.setDownloadEmbedTags(False)
    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.downloadEmbedTags is False


def test_download_quality_accepts_master_tier(tmp_path):
    # 下载比播放多一档 "master" (臻品母带); 播放音质仍只有三档
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    controller.setDownloadQuality("master")
    assert controller.downloadQuality == "master"

    controller.setQualityPreference("master")  # 播放侧不认, 回退默认
    assert controller.qualityPreference == "balanced"


def test_download_directory_ignores_blank(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    before = controller.downloadDirectory

    controller.setDownloadDirectory("   ")
    assert controller.downloadDirectory == before


def test_download_directory_strips_file_url_prefix(tmp_path):
    # QML FolderDialog 返回 file:// URL, setter 需归一为本地路径
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    controller.setDownloadDirectory(f"file://{tmp_path}/music")
    assert controller.downloadDirectory == str(tmp_path / "music")


def test_download_settings_emit_signal_once(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    emitted: list[int] = []
    controller.settingsChanged.connect(lambda: emitted.append(1))

    controller.setDownloadQuality("high")
    assert len(emitted) == 1
    controller.setDownloadQuality("high")  # 同值幂等
    assert len(emitted) == 1


# ------------------------------------------------------------------ 淡入淡出 (issue #11 Stage C1)


def test_fade_defaults(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    assert controller.fadeEnabled is True
    assert controller.fadeDurationMs == _FADE_DURATION_DEFAULT_MS


def test_fade_settings_persist(tmp_path):
    path = tmp_path / "settings.ini"
    controller = SettingsController(settings=_settings(path))

    controller.setFadeEnabled(False)
    controller.setFadeDurationMs(1200)

    reloaded = SettingsController(settings=QSettings(str(path), QSettings.Format.IniFormat))
    assert reloaded.fadeEnabled is False
    assert reloaded.fadeDurationMs == 1200


def test_fade_duration_clamped_to_range(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))

    controller.setFadeDurationMs(50)
    assert controller.fadeDurationMs == _FADE_DURATION_MIN_MS
    controller.setFadeDurationMs(99999)
    assert controller.fadeDurationMs == _FADE_DURATION_MAX_MS


def test_fade_duration_garbage_persisted_value_falls_back(tmp_path):
    settings = _settings(tmp_path / "settings.ini")
    settings.setValue("playback/fadeDurationMs", "not-a-number")
    settings.sync()

    controller = SettingsController(settings=settings)
    assert controller.fadeDurationMs == _FADE_DURATION_DEFAULT_MS


def test_fade_setters_skip_signal_on_same_value(tmp_path):
    controller = SettingsController(settings=_settings(tmp_path / "settings.ini"))
    events: list[bool] = []
    controller.settingsChanged.connect(lambda: events.append(True))

    controller.setFadeEnabled(True)  # 与默认同值 -> 不发信号
    controller.setFadeDurationMs(_FADE_DURATION_DEFAULT_MS)
    assert events == []

    controller.setFadeEnabled(False)
    controller.setFadeDurationMs(800)
    assert len(events) == 2
