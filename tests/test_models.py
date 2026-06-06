"""模型基础测试 — 字段默认值, 派生 property."""

from __future__ import annotations

from quaverq.core.models import (
    Album,
    Lyric,
    LyricLine,
    Playlist,
    Singer,
    Song,
    SongUrl,
)

# ---------------------------------------------------------------------- Song


def test_song_minimal_fields():
    s = Song(mid="abc", name="Hello")
    assert s.mid == "abc"
    assert s.name == "Hello"
    assert s.singers == []
    assert s.album_mid == ""
    assert s.album_name == ""
    assert s.cover_url == ""
    assert s.duration == 0
    assert s.pay_play == 0
    assert s.file_qualities == set()
    assert s.media_mid == ""


def test_song_singer_names_derives_from_singers():
    s = Song(
        mid="abc",
        name="七里香",
        singers=[
            Singer(mid="0025NhlN2yWrP4", name="周杰伦"),
            Singer(mid="002J4UUk42htjW", name="Lara"),
        ],
    )
    assert s.singer_names == ["周杰伦", "Lara"]


def test_song_singer_names_empty_when_no_singers():
    s = Song(mid="abc", name="Hello")
    assert s.singer_names == []


# --------------------------------------------------------------------- Album


def test_album_singer_name_derives_from_first_singer():
    a = Album(
        mid="album1",
        name="十一月的萧邦",
        singers=[Singer(mid="x", name="周杰伦")],
    )
    assert a.singer_name == "周杰伦"


def test_album_singer_name_empty_when_no_singers():
    a = Album(mid="album1", name="Untitled")
    assert a.singer_name == ""


def test_album_defaults():
    a = Album(mid="x", name="x")
    assert a.cover_url == ""
    assert a.publish_date == ""
    assert a.description == ""
    assert a.song_count == 0
    assert a.songs == []


# ------------------------------------------------------------------ Playlist


def test_playlist_defaults():
    p = Playlist(pid="1", name="我的歌单")
    assert p.creator == ""
    assert p.play_count == 0
    assert p.is_mine is False
    assert p.song_count == 0
    assert p.songs == []


# -------------------------------------------------------------------- SongUrl


def test_song_url_minimal():
    u = SongUrl(mid="x", url="https://example.com/a.mp3")
    assert u.quality == ""
    assert u.expires_at == 0
    assert u.size == 0


# ----------------------------------------------------------------------- Lyric


def test_lyric_defaults():
    ly = Lyric(mid="x")
    assert ly.lines == []
    assert ly.has_translation is False
    assert ly.has_romanji is False


def test_lyric_line_translation_optional():
    line = LyricLine(timestamp_ms=1000, text="hello")
    assert line.translation == ""
