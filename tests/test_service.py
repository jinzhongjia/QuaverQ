"""服务层测试 (qqmusic-api 0.4.1).

覆盖 P0.1 重写后的核心契约:
- Credential dataclass 持久化往返 (兼容 v0.6 字段残留)
- _to_song 从 raw dict 提取所有字段
- search 走 search_by_type 返回 list[Song]
- get_song_url 按音质降级顺序尝试, 全失败返 None
"""

from __future__ import annotations

import pytest
from qqmusic_api import Credential
from qqmusic_api.song import SongFileType

from quaverq.core.models import Album, Playlist, Singer, Song
from quaverq.core.service import (
    QuaverService,
    _cover_url,
    _credential_from_dict,
    _credential_to_dict,
)


# ============================================================== Credential 往返

def test_credential_roundtrip_via_dict():
    cred = Credential(musicid=123, musickey="abc", str_musicid="123")
    d = _credential_to_dict(cred)
    assert d["musicid"] == 123
    assert d["musickey"] == "abc"
    cred2 = _credential_from_dict(d)
    assert cred2.musicid == 123
    assert cred2.musickey == "abc"


def test_credential_from_dict_with_v06_extra_fields():
    """credential.json 里可能残留 v0.6 字段 (musickey_create_time 等), 不应抛错."""
    d = {
        "musicid": 123,
        "musickey": "abc",
        "musickey_create_time": 1779204438,
        "key_expires_in": 259200,
        "first_login": 0,
    }
    cred = _credential_from_dict(d)
    assert cred.musicid == 123
    assert cred.musickey == "abc"
    # 多余字段进 extra_fields
    assert cred.extra_fields["musickey_create_time"] == 1779204438


def test_credential_to_dict_flattens_extra_fields():
    """保存时 extra_fields 应展开回顶层 (兼容老 json 格式)."""
    cred = Credential(musicid=1, extra_fields={"x": "y"})
    d = _credential_to_dict(cred)
    assert d["x"] == "y"
    assert "extra_fields" not in d


# ============================================================== is_authenticated

def test_is_authenticated_requires_musickey():
    svc = QuaverService()
    assert svc.is_authenticated is False

    svc.credential = Credential(musicid=123)  # 缺 musickey
    assert svc.is_authenticated is False

    svc.credential = Credential(musicid=123, musickey="key")
    assert svc.is_authenticated is True


def test_set_credential_sync_accepts_none():
    """登录过期清凭据时, 直接置 None 不抛错."""
    svc = QuaverService()
    svc.set_credential_sync(None)
    assert svc.credential is None


# ============================================================== _to_song

def _raw_song(**overrides):
    """构造 0.4.1 search_by_type 返回的 raw dict."""
    raw = {
        "mid": "003test",
        "name": "晴天",
        "singer": [
            {"mid": "0025NhlN2yWrP4", "name": "周杰伦"},
            {"mid": "002J4UUk42htjW", "name": "Lara"},
        ],
        "album": {"mid": "002fRO0N4FftzY", "name": "十一月的萧邦"},
        "file": {"media_mid": "002fRO0N4FftzY_media"},
        "pay": {"pay_play": 0},
        "interval": 215,
    }
    raw.update(overrides)
    return raw


def test_to_song_basic_fields():
    s = QuaverService._to_song(_raw_song())
    assert s.mid == "003test"
    assert s.name == "晴天"
    assert s.duration == 215
    assert s.pay_play == 0


def test_to_song_singers_extracted():
    s = QuaverService._to_song(_raw_song())
    assert s.singers == [
        Singer(mid="0025NhlN2yWrP4", name="周杰伦"),
        Singer(mid="002J4UUk42htjW", name="Lara"),
    ]
    assert s.singer_names == ["周杰伦", "Lara"]


def test_to_song_album_and_cover():
    s = QuaverService._to_song(_raw_song())
    assert s.album_mid == "002fRO0N4FftzY"
    assert s.album_name == "十一月的萧邦"
    # cover 由 album_mid 拼出
    assert "T002R300x300M000002fRO0N4FftzY.jpg" in s.cover_url


def test_to_song_media_mid_extracted():
    s = QuaverService._to_song(_raw_song())
    assert s.media_mid == "002fRO0N4FftzY_media"


def test_to_song_pay_play_from_pay_block():
    """0.4.1 raw 是 dict, pay 在子 dict 里."""
    s = QuaverService._to_song(_raw_song(pay={"pay_play": 1}))
    assert s.pay_play == 1


def test_to_song_handles_missing_optional_fields():
    s = QuaverService._to_song({"mid": "x", "name": "y"})
    assert s.singers == []
    assert s.album_mid == ""
    assert s.album_name == ""
    assert s.media_mid == ""
    assert s.cover_url == ""
    assert s.duration == 0
    assert s.pay_play == 0


def test_to_song_handles_none_subdicts():
    raw = {"mid": "x", "name": "y", "singer": None, "album": None, "file": None, "pay": None}
    s = QuaverService._to_song(raw)
    assert s.singers == []
    assert s.album_mid == ""


def test_cover_url_empty_mid_returns_empty():
    assert _cover_url("") == ""


def test_cover_url_format():
    url = _cover_url("ALBUMMID", 300)
    assert url == "https://y.qq.com/music/photo_new/T002R300x300M000ALBUMMID.jpg"


# ============================================================== search

async def test_search_returns_song_list(monkeypatch):
    """search → 走 search.search_by_type, 返回 list[dict], _to_song 转 Song."""
    from qqmusic_api import search

    async def fake_search(**kwargs):
        assert kwargs["search_type"].name == "SONG"
        return [_raw_song(mid="m1", name="A"), _raw_song(mid="m2", name="B")]

    monkeypatch.setattr(search, "search_by_type", fake_search)

    svc = QuaverService()
    songs = await svc.search("anything")
    assert [s.mid for s in songs] == ["m1", "m2"]
    assert songs[0].singer_names == ["周杰伦", "Lara"]


async def test_search_returns_empty_when_no_results(monkeypatch):
    from qqmusic_api import search

    async def fake_search(**kwargs):
        return []

    monkeypatch.setattr(search, "search_by_type", fake_search)
    svc = QuaverService()
    assert await svc.search("nothing") == []


# ============================================================== get_song_url 降级

async def test_get_song_url_success_at_first_quality(monkeypatch):
    """FLAC 直接命中 → 返回 FLAC URL."""
    from qqmusic_api import song

    async def fake_get(*, mid, file_type, credential=None):
        if file_type == SongFileType.FLAC:
            return {mid[0]: "https://isure.qq/F000mm1.flac?vkey=abc"}
        return {mid[0]: ""}

    monkeypatch.setattr(song, "get_song_urls", fake_get)

    svc = QuaverService()
    s = Song(mid="m1", name="x", media_mid="mm1")
    url = await svc.get_song_url(s)

    assert url is not None
    assert url.quality == "FLAC"
    assert "F000mm1.flac" in url.url


async def test_get_song_url_falls_through_to_first_non_empty(monkeypatch):
    """FLAC/MP3_320 都空, MP3_128 出来 → quality=MP3_128."""
    from qqmusic_api import song

    async def fake_get(*, mid, file_type, credential=None):
        if file_type == SongFileType.MP3_128:
            return {mid[0]: "https://isure.qq/M500mm1.mp3?vkey=k"}
        return {mid[0]: ""}

    monkeypatch.setattr(song, "get_song_urls", fake_get)

    svc = QuaverService()
    s = Song(mid="m1", name="x", media_mid="mm1")
    url = await svc.get_song_url(s)

    assert url is not None
    assert url.quality == "MP3_128"


async def test_get_song_url_returns_none_when_all_qualities_empty(monkeypatch):
    """无版权 / 无 VIP → 所有音质都空 → None (controller 显示 error toast)."""
    from qqmusic_api import song

    async def fake_get(*, mid, file_type, credential=None):
        return {mid[0]: ""}

    monkeypatch.setattr(song, "get_song_urls", fake_get)

    svc = QuaverService()
    s = Song(mid="m1", name="x", media_mid="mm1")
    assert await svc.get_song_url(s) is None


async def test_get_song_url_skips_exception_and_continues(monkeypatch):
    """某个音质 API 抛错 → 跳过, 尝试下一档."""
    from qqmusic_api import song

    async def fake_get(*, mid, file_type, credential=None):
        if file_type == SongFileType.FLAC:
            raise RuntimeError("boom")
        if file_type == SongFileType.MP3_320:
            return {mid[0]: "https://isure.qq/M800mm1.mp3?vkey=k"}
        return {mid[0]: ""}

    monkeypatch.setattr(song, "get_song_urls", fake_get)

    svc = QuaverService()
    s = Song(mid="m1", name="x", media_mid="mm1")
    url = await svc.get_song_url(s)

    assert url is not None
    assert url.quality == "MP3_320"


# ============================================================== _to_singer

def test_to_singer_extracts_from_raw():
    raw = {
        "singerMID": "0025NhlN2yWrP4",
        "singerName": "周杰伦",
        "singerPic": "http://y.gtimg.cn/.../singer.jpg",
        "albumNum": 43,
    }
    s = QuaverService._to_singer(raw)
    assert s.mid == "0025NhlN2yWrP4"
    assert s.name == "周杰伦"
    assert s.avatar_url == "http://y.gtimg.cn/.../singer.jpg"


def test_to_singer_handles_missing_pic():
    s = QuaverService._to_singer({"singerMID": "x", "singerName": "y"})
    assert s.avatar_url == ""


# ============================================================== _to_album_brief

def test_to_album_brief_extracts_from_raw():
    raw = {
        "albummid": "0041WVfh2vtlJE",
        "name": "太阳之子",
        "pic": "http://y.gtimg.cn/.../album.jpg",
        "publish_date": "2026-03-25",
        "song_num": 12,
        "singer_list": [
            {"mid": "0025NhlN2yWrP4", "name": "周杰伦"},
        ],
    }
    a = QuaverService._to_album_brief(raw)
    assert a.mid == "0041WVfh2vtlJE"
    assert a.name == "太阳之子"
    assert a.singers == [Singer(mid="0025NhlN2yWrP4", name="周杰伦")]
    assert a.cover_url == "http://y.gtimg.cn/.../album.jpg"
    assert a.publish_date == "2026-03-25"
    assert a.song_count == 12


def test_to_album_brief_falls_back_to_cover_url_helper_when_no_pic():
    a = QuaverService._to_album_brief(
        {"albummid": "MID", "name": "x", "pic": ""}
    )
    assert "T002R300x300M000MID.jpg" in a.cover_url


def test_to_album_brief_handles_missing_singer_list():
    a = QuaverService._to_album_brief({"albummid": "x", "name": "y"})
    assert a.singers == []


# ============================================================== _to_playlist_brief

def test_to_playlist_brief_extracts_from_raw():
    raw = {
        "dissid": "7039749142",
        "dissname": "百听不厌",
        "description": "99首 4.0亿次播放",
        "nickname": "今晚月色很美",
        "logo": "http://qpic.y.qq.com/.../pl.jpg",
        "listennum": 399747305,
        "songnum": 99,
    }
    p = QuaverService._to_playlist_brief(raw)
    assert p.pid == "7039749142"
    assert p.name == "百听不厌"
    assert p.description == "99首 4.0亿次播放"
    assert p.creator == "今晚月色很美"
    assert p.cover_url == "http://qpic.y.qq.com/.../pl.jpg"
    assert p.play_count == 399747305
    assert p.song_count == 99
    assert p.is_mine is False


def test_to_playlist_brief_stringifies_dissid_when_numeric():
    p = QuaverService._to_playlist_brief({"dissid": 12345, "dissname": "x"})
    assert p.pid == "12345"


# ============================================================== search by kind (4 类型)

async def test_search_songs_calls_search_by_type_with_song(monkeypatch):
    from qqmusic_api import search
    from qqmusic_api.search import SearchType

    captured = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return [_raw_song(mid="m1", name="A")]

    monkeypatch.setattr(search, "search_by_type", fake_search)
    svc = QuaverService()
    results = await svc.search_songs("kw")

    assert captured["search_type"] == SearchType.SONG
    assert captured["highlight"] is False  # 不要 <em> 标签
    assert len(results) == 1
    assert isinstance(results[0], Song)


async def test_search_singers_returns_singer_list(monkeypatch):
    from qqmusic_api import search
    from qqmusic_api.search import SearchType

    captured = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return [{"singerMID": "s1", "singerName": "A"}]

    monkeypatch.setattr(search, "search_by_type", fake_search)
    svc = QuaverService()
    results = await svc.search_singers("kw")

    assert captured["search_type"] == SearchType.SINGER
    assert len(results) == 1
    assert isinstance(results[0], Singer)
    assert results[0].name == "A"


async def test_search_albums_returns_album_list(monkeypatch):
    from qqmusic_api import search
    from qqmusic_api.search import SearchType

    captured = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return [{"albummid": "a1", "name": "Album X", "singer_list": []}]

    monkeypatch.setattr(search, "search_by_type", fake_search)
    svc = QuaverService()
    results = await svc.search_albums("kw")

    assert captured["search_type"] == SearchType.ALBUM
    assert len(results) == 1
    assert isinstance(results[0], Album)
    assert results[0].name == "Album X"


async def test_search_playlists_returns_playlist_list(monkeypatch):
    from qqmusic_api import search
    from qqmusic_api.search import SearchType

    captured = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return [{"dissid": "1", "dissname": "P", "songnum": 5}]

    monkeypatch.setattr(search, "search_by_type", fake_search)
    svc = QuaverService()
    results = await svc.search_playlists("kw")

    assert captured["search_type"] == SearchType.SONGLIST
    assert len(results) == 1
    assert isinstance(results[0], Playlist)
    assert results[0].name == "P"


async def test_search_legacy_alias_still_returns_songs(monkeypatch):
    """旧 search() 接口保留, 别处调用不回归."""
    from qqmusic_api import search

    async def fake_search(**kwargs):
        return [_raw_song(mid="m1", name="A")]

    monkeypatch.setattr(search, "search_by_type", fake_search)
    svc = QuaverService()
    results = await svc.search("kw")
    assert all(isinstance(r, Song) for r in results)


# ============================================================== get_song_url 凭据传递 (原 P0.1 测试, 保留)

async def test_get_song_url_passes_credential_through(monkeypatch):
    """credential 必须传给底层 API, 否则服务端不下发 VIP 内容."""
    from qqmusic_api import song

    captured = {}

    async def fake_get(*, mid, file_type, credential=None):
        captured["credential"] = credential
        return {mid[0]: "https://isure.qq/x.mp3?vkey=k"}

    monkeypatch.setattr(song, "get_song_urls", fake_get)

    svc = QuaverService()
    svc.credential = Credential(musicid=123, musickey="key")
    await svc.get_song_url(Song(mid="m1", name="x"))

    assert captured["credential"] is svc.credential
    assert captured["credential"].musicid == 123
