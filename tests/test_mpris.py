"""MPRIS2 单元测试.

D-Bus 实际发送在集成测试范围 (启动 session bus + playerctl 查). 这里只测:
- Song → MPRIS metadata dict 字段映射正确
- PlaybackStatus 状态转换 (None/play/pause/stop → MPRIS "Playing"/"Paused"/"Stopped")
"""

from __future__ import annotations

import pytest

from quaverq import resources
from quaverq.core.models import Singer, Song
from quaverq.core.mpris import (
    MprisCallbacks,
    _build_interfaces,
    normalize_loop_status,
    normalize_shuffle,
    normalize_status,
    song_to_metadata,
)

# ============================================================== metadata mapping


def test_song_to_metadata_basic_fields():
    s = Song(
        mid="003test",
        name="晴天",
        singers=[Singer(mid="x", name="周杰伦")],
        album_name="叶惠美",
        duration=269,
        cover_url="https://y.qq.com/.../jay.jpg",
    )
    meta = song_to_metadata(s)
    # MPRIS 规范字段
    assert meta["xesam:title"] == "晴天"
    assert meta["xesam:artist"] == ["周杰伦"]
    assert meta["xesam:album"] == "叶惠美"
    assert meta["mpris:length"] == 269 * 1_000_000  # 微秒
    assert meta["mpris:artUrl"] == "https://y.qq.com/.../jay.jpg"
    # trackid 必须是 D-Bus object path 风格
    assert meta["mpris:trackid"].startswith("/")
    assert "003test" in meta["mpris:trackid"]


def test_song_to_metadata_multi_artists():
    s = Song(
        mid="m",
        name="x",
        singers=[
            Singer(mid="a", name="周杰伦"),
            Singer(mid="b", name="Lara"),
        ],
    )
    meta = song_to_metadata(s)
    assert meta["xesam:artist"] == ["周杰伦", "Lara"]


def test_song_to_metadata_no_singers():
    s = Song(mid="m", name="x")
    meta = song_to_metadata(s)
    # 字段必须存在但为空列表 (MPRIS 协议要求 array<string>)
    assert meta["xesam:artist"] == []


def test_song_to_metadata_missing_optional_fields_safe():
    """空 cover_url / 0 duration 时也能输出合法 metadata."""
    s = Song(mid="m", name="x", singers=[], duration=0, cover_url="")
    meta = song_to_metadata(s)
    assert meta["xesam:title"] == "x"
    assert meta["mpris:length"] == 0
    # artUrl 空时不要带 (协议允许缺省)
    assert meta.get("mpris:artUrl", "") == ""


def test_song_to_metadata_sanitizes_trackid():
    """trackid 是 D-Bus path, 不允许特殊字符."""
    s = Song(mid="003w/2xz!#$@", name="x")
    meta = song_to_metadata(s)
    tid = meta["mpris:trackid"]
    # 只能含 / 和 [A-Za-z0-9_]
    for ch in tid:
        assert ch == "/" or ch == "_" or ch.isalnum()


def test_song_to_metadata_prefers_local_cover_uri():
    """有 local_cover_uri 时 artUrl 用本地 file://, 否则退到远端 cover_url."""
    s = Song(mid="m", name="x", cover_url="https://y.qq.com/cover.jpg")
    meta = song_to_metadata(s, local_cover_uri="file:///home/u/c.jpg")
    assert meta["mpris:artUrl"] == "file:///home/u/c.jpg"


def test_song_to_metadata_falls_back_to_remote_cover():
    s = Song(mid="m", name="x", cover_url="https://y.qq.com/cover.jpg")
    meta = song_to_metadata(s, local_cover_uri=None)
    assert meta["mpris:artUrl"] == "https://y.qq.com/cover.jpg"


# ============================================================== status mapping


def test_normalize_status_play():
    assert normalize_status("play") == "Playing"
    assert normalize_status("playing") == "Playing"
    assert normalize_status("PLAYING") == "Playing"


def test_normalize_status_pause():
    assert normalize_status("pause") == "Paused"
    assert normalize_status("paused") == "Paused"


def test_normalize_status_stop_default():
    assert normalize_status("stop") == "Stopped"
    assert normalize_status("stopped") == "Stopped"
    assert normalize_status(None) == "Stopped"
    assert normalize_status("xxx") == "Stopped"


def test_normalize_loop_status():
    assert normalize_loop_status("repeat_all") == "Playlist"
    assert normalize_loop_status("repeat_one") == "Track"
    assert normalize_loop_status("sequence") == "None"
    assert normalize_loop_status("shuffle") == "None"
    assert normalize_loop_status(None) == "None"


def test_normalize_shuffle():
    assert normalize_shuffle("shuffle") is True
    assert normalize_shuffle("sequence") is False
    assert normalize_shuffle("repeat_all") is False
    assert normalize_shuffle(None) is False


# ============================================================== root interface


def test_desktop_entry_names_shipped_desktop_file():
    """回归: MPRIS DesktopEntry 必须 == 安装的 `{APP_ID}.desktop` 的 basename.

    桌面环境据此找 .desktop -> 读 Icon= 解析 Now Playing 卡片的应用图标. 取值曾漂移
    (误为 "quaverq", 实际安装的是 io.github.jinzhongjia.quaverq.desktop), GNOME 找不到
    -> 卡片显示默认图标.
    """
    pytest.importorskip("dbus_next")  # 无 D-Bus 环境 (Windows) 跳过

    root_cls, _player_cls = _build_interfaces(MprisCallbacks())
    entry = root_cls().DesktopEntry  # @dbus_property 是 property 描述符, 访问即取值

    assert entry == resources.APP_ID
    assert resources.desktop_file().name == f"{entry}.desktop"
    assert resources.desktop_file().exists()
