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

from quaverq.core.models import Album, ArtistDetail, Lyric, Playlist, Singer, Song
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
    """FLAC 直接命中 → 返回 FLAC URL (在 high 偏好档下)."""
    from qqmusic_api import song

    async def fake_get(*, mid, file_type, credential=None):
        if file_type == SongFileType.FLAC:
            return {mid[0]: "https://isure.qq/F000mm1.flac?vkey=abc"}
        return {mid[0]: ""}

    monkeypatch.setattr(song, "get_song_urls", fake_get)

    svc = QuaverService()
    s = Song(mid="m1", name="x", media_mid="mm1")
    url = await svc.get_song_url(s, quality_preference="high")

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


# ============================================================== 详情拉取 (P0.3)

async def test_get_album_detail_combines_basic_info_and_songs(monkeypatch):
    """album.get_detail (元信息) + album.get_song (歌曲列表) 组合成完整 Album."""
    from qqmusic_api import album

    async def fake_detail(value, **_kw):
        assert value == "ALBUM_MID"
        return {
            "basicInfo": {
                "albumMid": "ALBUM_MID",
                "albumName": "十一月的萧邦",
                "publishDate": "2005-11-01",
                "desc": "周杰伦第六张专辑",
                "total_song_num": 12,
            },
            "singer": {
                "singerList": [
                    {"mid": "JAY_MID", "name": "周杰伦"},
                ],
            },
        }

    async def fake_song(value, num, page, **_kw):
        assert value == "ALBUM_MID"
        return [_raw_song(mid="t1", name="夜曲"), _raw_song(mid="t2", name="蓝色风暴")]

    monkeypatch.setattr(album, "get_detail", fake_detail)
    monkeypatch.setattr(album, "get_song", fake_song)

    svc = QuaverService()
    a = await svc.get_album_detail("ALBUM_MID")

    assert a.mid == "ALBUM_MID"
    assert a.name == "十一月的萧邦"
    assert a.publish_date == "2005-11-01"
    assert a.description == "周杰伦第六张专辑"
    assert a.song_count == 12
    assert a.singers == [Singer(mid="JAY_MID", name="周杰伦")]
    assert len(a.songs) == 2
    assert [s.mid for s in a.songs] == ["t1", "t2"]


async def test_get_playlist_detail_parses_dirinfo_and_songlist(monkeypatch):
    """songlist.get_detail 返回 dirinfo + songlist; 应映射到 Playlist + songs."""
    from qqmusic_api import songlist as sl_module

    async def fake_detail(songlist_id, **kwargs):
        assert songlist_id == 7039749142
        return {
            "dirinfo": {
                "dirid": 7039749142,
                "title": "百听不厌的周杰伦",
                "picurl": "https://qpic.y.qq.com/.../pl.jpg",
                "desc": "杰伦经典",
                "creator": {"nick": "今晚月色很美"},
                "songnum": 99,
                "listennum": 399747305,
            },
            "songlist": [
                _raw_song(mid="m1", name="Hi 1"),
                _raw_song(mid="m2", name="Hi 2"),
            ],
        }

    monkeypatch.setattr(sl_module, "get_detail", fake_detail)

    svc = QuaverService()
    p = await svc.get_playlist_detail("7039749142")

    assert p.pid == "7039749142"
    assert p.name == "百听不厌的周杰伦"
    assert p.creator == "今晚月色很美"
    assert p.description == "杰伦经典"
    assert p.song_count == 99
    assert p.play_count == 399747305
    assert p.cover_url == "https://qpic.y.qq.com/.../pl.jpg"
    assert [s.mid for s in p.songs] == ["m1", "m2"]


async def test_get_playlist_detail_accepts_str_pid_with_digits(monkeypatch):
    """pid 是字符串 (来自搜索); 内部要转 int 给 0.4.1 API."""
    from qqmusic_api import songlist as sl_module
    captured = {}

    async def fake_detail(songlist_id, **kwargs):
        captured["songlist_id"] = songlist_id
        return {"dirinfo": {"title": "t"}, "songlist": []}

    monkeypatch.setattr(sl_module, "get_detail", fake_detail)
    svc = QuaverService()
    await svc.get_playlist_detail("12345")
    assert captured["songlist_id"] == 12345


async def test_get_artist_detail_combines_info_and_hot_songs(monkeypatch):
    """singer.get_info + singer.get_songs(SONG) 组合成 ArtistDetail."""
    from qqmusic_api import singer as singer_module

    async def fake_info(mid, **_kw):
        assert mid == "JAY_MID"
        return {
            "Info": {
                "Name": "周杰伦",
                "Pic": "https://y.qq.com/.../jay.jpg",
            }
        }

    async def fake_tab_detail(mid, tab_type, page, num, **_kw):
        assert mid == "JAY_MID"
        return [_raw_song(mid="hot1", name="晴天"), _raw_song(mid="hot2", name="稻香")]

    monkeypatch.setattr(singer_module, "get_info", fake_info)
    monkeypatch.setattr(singer_module, "get_tab_detail", fake_tab_detail)

    svc = QuaverService()
    ad = await svc.get_artist_detail("JAY_MID")

    assert isinstance(ad, ArtistDetail)
    assert ad.singer.mid == "JAY_MID"
    assert ad.singer.name == "周杰伦"
    assert ad.singer.avatar_url == "https://y.qq.com/.../jay.jpg"
    assert [s.mid for s in ad.hot_songs] == ["hot1", "hot2"]


async def test_get_artist_detail_resilient_to_missing_info(monkeypatch):
    """singer.get_info 可能返回空 Info 字段, 用 mid 做 fallback name 也行."""
    from qqmusic_api import singer as singer_module

    async def fake_info(_mid, **_kw):
        return {}

    async def fake_tab_detail(_mid, tab_type, page, num, **_kw):
        return []

    monkeypatch.setattr(singer_module, "get_info", fake_info)
    monkeypatch.setattr(singer_module, "get_tab_detail", fake_tab_detail)

    svc = QuaverService()
    ad = await svc.get_artist_detail("MID_X")
    assert ad.singer.mid == "MID_X"
    assert ad.hot_songs == []


# ============================================================== get_lyric (P0.5)

async def test_get_lyric_parses_lrc_text(monkeypatch):
    from qqmusic_api import lyric as lyric_module

    async def fake_get_lyric(value, **_kw):
        assert value == "MID_X"
        return {
            "lyric": "[00:10.00]第一行\n[00:20.50]第二行",
            "trans": "",
            "roma": "",
        }

    monkeypatch.setattr(lyric_module, "get_lyric", fake_get_lyric)

    svc = QuaverService()
    ly = await svc.get_lyric("MID_X")
    assert isinstance(ly, Lyric)
    assert ly.mid == "MID_X"
    assert ly.has_translation is False
    assert len(ly.lines) == 2
    assert ly.lines[0].timestamp_ms == 10000
    assert ly.lines[0].text == "第一行"


async def test_get_lyric_merges_translation_by_timestamp(monkeypatch):
    from qqmusic_api import lyric as lyric_module

    async def fake_get_lyric(value, **_kw):
        return {
            "lyric": "[00:10.00]Hello\n[00:20.00]World",
            "trans": "[00:10.00]你好\n[00:20.00]世界",
            "roma": "",
        }

    monkeypatch.setattr(lyric_module, "get_lyric", fake_get_lyric)
    svc = QuaverService()
    ly = await svc.get_lyric("M")
    assert ly.has_translation is True
    assert ly.lines[0].text == "Hello"
    assert ly.lines[0].translation == "你好"
    assert ly.lines[1].translation == "世界"


async def test_get_lyric_handles_empty_response(monkeypatch):
    from qqmusic_api import lyric as lyric_module

    async def fake_get_lyric(_value, **_kw):
        return {"lyric": "", "trans": "", "roma": ""}

    monkeypatch.setattr(lyric_module, "get_lyric", fake_get_lyric)
    svc = QuaverService()
    ly = await svc.get_lyric("M")
    assert ly.lines == []
    assert ly.has_translation is False


# ============================================================== get_song_url 凭据传递 (原 P0.1 测试, 保留)

async def test_get_song_url_respects_quality_preference_high(monkeypatch):
    """quality='high' 顺序: FLAC → MP3_320 → OGG_192 → MP3_128."""
    from qqmusic_api import song

    attempts: list[str] = []

    async def fake_get(*, mid, file_type, credential=None):
        attempts.append(file_type.name)
        # 只有 FLAC 通
        if file_type.name == "FLAC":
            return {mid[0]: "https://x/F000.flac?vkey=k"}
        return {mid[0]: ""}

    monkeypatch.setattr(song, "get_song_urls", fake_get)
    svc = QuaverService()
    url = await svc.get_song_url(Song(mid="m1", name="x"), quality_preference="high")
    assert attempts[0] == "FLAC"
    assert url.quality == "FLAC"


async def test_get_song_url_respects_quality_preference_standard(monkeypatch):
    """quality='standard' 顺序: MP3_128 优先."""
    from qqmusic_api import song

    attempts: list[str] = []

    async def fake_get(*, mid, file_type, credential=None):
        attempts.append(file_type.name)
        return {mid[0]: "https://x/x.mp3?vkey=k"}

    monkeypatch.setattr(song, "get_song_urls", fake_get)
    svc = QuaverService()
    await svc.get_song_url(Song(mid="m1", name="x"), quality_preference="standard")
    assert attempts[0] == "MP3_128"


async def test_get_song_url_quality_unknown_falls_back_to_balanced(monkeypatch):
    from qqmusic_api import song

    attempts: list[str] = []

    async def fake_get(*, mid, file_type, credential=None):
        attempts.append(file_type.name)
        return {mid[0]: "https://x/x.mp3?vkey=k"}

    monkeypatch.setattr(song, "get_song_urls", fake_get)
    svc = QuaverService()
    await svc.get_song_url(Song(mid="m1", name="x"), quality_preference="不存在的档位")
    # balanced 首选 MP3_320
    assert attempts[0] == "MP3_320"


async def test_get_song_url_returns_actual_quality_after_downgrade(monkeypatch):
    """偏好 high 但 FLAC/MP3_320 都拿不到, 只 MP3_128 通 → quality='MP3_128' (用于 toast 显示)."""
    from qqmusic_api import song

    async def fake_get(*, mid, file_type, credential=None):
        if file_type.name == "MP3_128":
            return {mid[0]: "https://x/M500.mp3?vkey=k"}
        return {mid[0]: ""}

    monkeypatch.setattr(song, "get_song_urls", fake_get)
    svc = QuaverService()
    url = await svc.get_song_url(Song(mid="m1", name="x"), quality_preference="high")
    assert url.quality == "MP3_128"


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
