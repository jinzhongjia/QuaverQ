"""服务层测试 (qqmusic-api 0.6.1, P1.1.5 bypass 路径).

设计:
- 0.6 Client 调用通过 mock 注入 svc._client (SimpleNamespace 模拟 client.search / album / ...)
- get_song_url 走 bypass, 测试 monkey-patch svc._try_bypass_url 替代真 HTTP
- _to_song/_to_singer/_to_album_brief/_to_playlist_brief 用 SimpleNamespace 模拟 pydantic 对象
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qqmusic_api import Credential

from quaverq.core.models import (
    Album,
    ArtistDetail,
    Lyric,
    Playlist,
    Singer,
    Song,
)
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


def test_credential_from_dict_ignores_unknown_fields():
    """credential.json 残留旧字段不应让 pydantic 报错."""
    d = {
        "musicid": 123,
        "musickey": "abc",
        "musickey_create_time": 1779204438,  # 不在 0.6 Credential 字段里
        "first_login": 0,
    }
    cred = _credential_from_dict(d)
    assert cred.musicid == 123
    assert cred.musickey == "abc"


# ============================================================== is_authenticated

def test_is_authenticated_requires_musickey():
    svc = QuaverService()
    assert svc.is_authenticated is False
    svc.credential = Credential(musicid=123)
    assert svc.is_authenticated is False
    svc.credential = Credential(musicid=123, musickey="key")
    assert svc.is_authenticated is True


# ============================================================== _to_song

def _raw_song(**overrides):
    """模拟 0.6 SongSearch pydantic 对象 (SimpleNamespace + 属性)."""
    raw = SimpleNamespace(
        mid="003test",
        name="晴天",
        singer=[
            SimpleNamespace(mid="0025NhlN2yWrP4", name="周杰伦"),
            SimpleNamespace(mid="002J4UUk42htjW", name="Lara"),
        ],
        album=SimpleNamespace(
            mid="002fRO0N4FftzY",
            name="十一月的萧邦",
        ),
        file=SimpleNamespace(media_mid="002fRO0N4FftzY_media"),
        pay=SimpleNamespace(pay_play=0),
        interval=215,
    )
    for k, v in overrides.items():
        setattr(raw, k, v)
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


def test_to_song_album_extracted():
    s = QuaverService._to_song(_raw_song())
    assert s.album_mid == "002fRO0N4FftzY"
    assert s.album_name == "十一月的萧邦"
    # cover 走 _cover_url 拼出
    assert "T002R300x300M000002fRO0N4FftzY.jpg" in s.cover_url


def test_to_song_media_mid_extracted():
    s = QuaverService._to_song(_raw_song())
    assert s.media_mid == "002fRO0N4FftzY_media"


def test_to_song_pay_play_from_nested_pay():
    s = QuaverService._to_song(_raw_song(pay=SimpleNamespace(pay_play=1)))
    assert s.pay_play == 1


def test_to_song_handles_missing_optional_fields():
    raw = SimpleNamespace(mid="x", name="y")
    s = QuaverService._to_song(raw)
    assert s.singers == []
    assert s.album_mid == ""
    assert s.media_mid == ""
    assert s.pay_play == 0


def test_to_song_accepts_plain_dict():
    """_to_song 不只接 pydantic, dict 也能用 (cache 反序列化复用)."""
    d = {
        "mid": "m",
        "name": "n",
        "singer": [{"mid": "s", "name": "a"}],
        "interval": 100,
    }
    s = QuaverService._to_song(d)
    assert s.mid == "m"
    assert s.singers == [Singer(mid="s", name="a")]
    assert s.duration == 100


# ============================================================== _to_singer / album / playlist

def test_to_singer_from_06_fields():
    raw = SimpleNamespace(mid="x", name="周杰伦", pic="http://avatar.jpg")
    s = QuaverService._to_singer(raw)
    assert s.mid == "x"
    assert s.name == "周杰伦"
    assert s.avatar_url == "http://avatar.jpg"


def test_to_singer_from_04_legacy_fields():
    """老 0.4 字段名 (singerMID/singerName/singerPic) 兜底."""
    raw = SimpleNamespace(singerMID="x", singerName="周杰伦", singerPic="http://a.jpg")
    s = QuaverService._to_singer(raw)
    assert s.mid == "x"
    assert s.name == "周杰伦"
    assert s.avatar_url == "http://a.jpg"


def test_to_album_brief_from_06_fields():
    raw = SimpleNamespace(
        mid="alb1",
        name="叶惠美",
        pic="http://x/album.jpg",
        time_public="2003-07-29",
        singer_list=[SimpleNamespace(mid="j", name="周杰伦")],
        song_num=12,
    )
    a = QuaverService._to_album_brief(raw)
    assert a.mid == "alb1"
    assert a.name == "叶惠美"
    assert a.publish_date == "2003-07-29"
    assert a.singers == [Singer(mid="j", name="周杰伦")]
    assert a.cover_url == "http://x/album.jpg"
    assert a.song_count == 12


def test_to_playlist_brief_from_06_fields():
    """0.6 SongListSearch 的 ID 在 'id' 字段, 不是 dirid."""
    raw = SimpleNamespace(
        id=7039749142,
        dirid=0,           # 0.6 search 经常给 0; 不可用
        title="百听不厌",
        picurl="http://x/pl.jpg",
        desc="经典",
        nickname="今晚月色很美",
        songnum=99,
        listennum=399747305,
    )
    p = QuaverService._to_playlist_brief(raw)
    assert p.pid == "7039749142"   # 用 id 而非 dirid
    assert p.name == "百听不厌"
    assert p.creator == "今晚月色很美"
    assert p.song_count == 99
    assert p.play_count == 399747305


# ============================================================== search

def _stub_client_for_search(items_song=(), items_singer=(), items_album=(), items_songlist=()):
    """构造 mock client.search.search_by_type, 按 search_type 返回不同 list."""
    from qqmusic_api.modules.search import SearchType

    async def fake_search_by_type(keyword, search_type, num, page, **kwargs):
        resp = SimpleNamespace(
            song=[], singer=[], album=[], songlist=[],
        )
        if search_type == SearchType.SONG:
            resp.song = list(items_song)
        elif search_type == SearchType.SINGER:
            resp.singer = list(items_singer)
        elif search_type == SearchType.ALBUM:
            resp.album = list(items_album)
        elif search_type == SearchType.SONGLIST:
            resp.songlist = list(items_songlist)
        return resp

    return SimpleNamespace(
        search=SimpleNamespace(search_by_type=fake_search_by_type),
        credential=None,
    )


async def test_search_songs_returns_song_list():
    svc = QuaverService()
    svc._client = _stub_client_for_search(items_song=[_raw_song(mid="m1", name="A")])
    songs = await svc.search_songs("kw")
    assert len(songs) == 1
    assert songs[0].name == "A"


async def test_search_singers_returns_singer_list():
    svc = QuaverService()
    svc._client = _stub_client_for_search(
        items_singer=[SimpleNamespace(mid="s1", name="周杰伦", pic="x.jpg")]
    )
    singers = await svc.search_singers("kw")
    assert len(singers) == 1
    assert singers[0].name == "周杰伦"


async def test_search_albums_returns_album_list():
    svc = QuaverService()
    svc._client = _stub_client_for_search(
        items_album=[
            SimpleNamespace(mid="a1", name="X", pic="", time_public="", singer_list=[], song_num=0),
        ]
    )
    albums = await svc.search_albums("kw")
    assert len(albums) == 1
    assert albums[0].name == "X"


async def test_search_playlists_returns_playlist_list():
    svc = QuaverService()
    svc._client = _stub_client_for_search(
        items_songlist=[
            SimpleNamespace(id=1, dirid=0, title="P", picurl="", desc="",
                           nickname="", songnum=5, listennum=0),
        ]
    )
    playlists = await svc.search_playlists("kw")
    assert len(playlists) == 1
    assert playlists[0].name == "P"


# ============================================================== get_song_url (bypass)

async def test_get_song_url_uses_bypass_path():
    """get_song_url 在 quality 偏好顺序中依次试 _try_bypass_url, 命中即返."""
    svc = QuaverService()
    svc._ct_value = 2

    attempts: list[str] = []

    async def fake_try(mid, quality):
        attempts.append(quality)
        if quality == "FLAC":
            return "https://x/F000m.flac?vkey=k"
        return None

    svc._try_bypass_url = fake_try
    url = await svc.get_song_url(
        Song(mid="m1", name="x"), quality_preference="high"
    )
    assert url is not None
    assert url.quality == "FLAC"
    assert attempts[0] == "FLAC"


async def test_get_song_url_walks_through_quality_until_hit():
    svc = QuaverService()
    svc._ct_value = 2

    async def fake_try(mid, quality):
        if quality == "MP3_128":
            return "https://x/M500m.mp3?vkey=k"
        return None

    svc._try_bypass_url = fake_try
    url = await svc.get_song_url(
        Song(mid="m1", name="x"), quality_preference="high"
    )
    assert url.quality == "MP3_128"


async def test_get_song_url_all_fail_returns_none():
    svc = QuaverService()
    svc._ct_value = 2

    async def fake_try(_mid, _q):
        return None

    svc._try_bypass_url = fake_try
    assert await svc.get_song_url(Song(mid="m", name="x")) is None


async def test_get_song_url_quality_unknown_falls_back_to_balanced():
    svc = QuaverService()
    svc._ct_value = 2
    attempts: list[str] = []

    async def fake_try(mid, q):
        attempts.append(q)
        return f"https://x/{q}?vkey=k"

    svc._try_bypass_url = fake_try
    await svc.get_song_url(Song(mid="m", name="x"), quality_preference="bogus")
    # balanced 首选 MP3_320
    assert attempts[0] == "MP3_320"


# ============================================================== ct 随机白名单

def test_safe_ct_values_excludes_blocklist():
    """findings 列出的风控值不应在白名单里."""
    blocklist = {1, 3, 4, 11, 18, 23, 27, 46}
    for v in QuaverService._SAFE_CT_VALUES:
        assert v not in blocklist


def test_safe_ct_values_nonempty():
    assert len(QuaverService._SAFE_CT_VALUES) > 0


async def test_connect_picks_random_ct_within_safe_pool():
    svc = QuaverService()
    await svc.connect()
    try:
        assert svc._ct_value in QuaverService._SAFE_CT_VALUES
    finally:
        await svc.disconnect()


# ============================================================== get_lyric

def _stub_lyric_response(lyric_text: str, trans_text: str = ""):
    """构造一个 fake niquests Session.post 返回值 (走 bypass)."""
    import base64

    class _FakeResp:
        def __init__(self, payload: dict):
            self._payload = payload

        def json(self):
            return self._payload

    payload = {
        "req_0": {
            "data": {
                "crypt": 0,
                "lyric": base64.b64encode(lyric_text.encode("utf-8")).decode("ascii"),
                "trans": base64.b64encode(trans_text.encode("utf-8")).decode("ascii"),
            }
        }
    }
    return _FakeResp(payload)


async def test_get_lyric_parses_lrc_bypass(monkeypatch):
    """bypass 路径: POST musicu.fcg 拿 base64 LRC, 解码 + 解析."""
    import niquests
    svc = QuaverService()
    svc._ct_value = 5
    svc.credential = Credential(musicid=1, musickey="key")

    fake_resp = _stub_lyric_response("[00:10.00]第一行\n[00:20.00]第二行")

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, *args, **kw): return fake_resp

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())

    ly = await svc.get_lyric("x")
    assert isinstance(ly, Lyric)
    assert len(ly.lines) == 2
    assert ly.lines[0].text == "第一行"


async def test_get_lyric_merges_translation_bypass(monkeypatch):
    import niquests
    svc = QuaverService()
    svc._ct_value = 5
    svc.credential = Credential(musicid=1, musickey="key")

    fake_resp = _stub_lyric_response(
        "[00:10.00]Hello", "[00:10.00]你好"
    )

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, *args, **kw): return fake_resp

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())

    ly = await svc.get_lyric("x")
    assert ly.has_translation is True
    assert ly.lines[0].text == "Hello"
    assert ly.lines[0].translation == "你好"


async def test_get_lyric_no_credential_returns_empty():
    """无登录态时优雅返回空, 不抛错."""
    svc = QuaverService()
    svc._ct_value = 5
    svc.credential = None
    ly = await svc.get_lyric("x")
    assert ly.lines == []


# ============================================================== Library APIs (P1.3)

async def test_get_my_playlists_excludes_fav_dir():
    """get_my_playlists 排除 dirid=201 (我喜欢, 独立成 Tab)."""
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k", str_musicid="1")

    async def fake_created(uin, **kw):
        return SimpleNamespace(playlists=[
            SimpleNamespace(id=2530, dirid=201, title="我喜欢", picurl="", desc="", songnum=308, listennum=0),
            SimpleNamespace(id=8899, dirid=1, title="啊浪的歌单", picurl="x", desc="", songnum=24, listennum=0),
            SimpleNamespace(id=1234, dirid=2, title="另一个", picurl="y", desc="", songnum=10, listennum=0),
        ])

    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_created_songlist=fake_created),
        credential=svc.credential,
    )
    pls = await svc.get_my_playlists()
    # 排除我喜欢
    assert len(pls) == 2
    assert all(p.name != "我喜欢" for p in pls)
    assert pls[0].name == "啊浪的歌单"
    assert pls[0].is_mine is True


async def test_get_my_playlists_no_credential_returns_empty():
    svc = QuaverService()
    svc.credential = None
    assert await svc.get_my_playlists() == []


async def test_get_followed_singers_extracts_users():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k", encrypt_uin="EUIN")

    async def fake_follow(euin, **kw):
        return SimpleNamespace(users=[
            SimpleNamespace(mid="s1", name="周杰伦", avatar_url="http://a.jpg"),
            SimpleNamespace(mid="s2", name="林俊杰", avatar_url=""),
        ])

    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_follow_singers=fake_follow),
        credential=svc.credential,
    )
    singers = await svc.get_followed_singers()
    assert len(singers) == 2
    assert singers[0].name == "周杰伦"
    assert singers[0].avatar_url == "http://a.jpg"


async def test_get_fav_albums_tolerates_lib_pydantic_error():
    """0.6.1 lib 在用户有 0 或 1 个专辑时 pydantic 校验报错, 应被 try/except 吃掉."""
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k", encrypt_uin="EUIN")

    async def fake_fav_album(euin, **kw):
        raise ValueError("pydantic validation error")

    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_fav_album=fake_fav_album),
        credential=svc.credential,
    )
    # 不抛, 返回空
    assert await svc.get_fav_albums() == []


async def test_get_fav_albums_extracts_when_available():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k", encrypt_uin="EUIN")

    async def fake_fav_album(euin, **kw):
        return SimpleNamespace(albums=[
            SimpleNamespace(
                mid="alb1", name="叶惠美",
                singer=SimpleNamespace(mid="j", name="周杰伦"),
                pic_url="http://a.jpg", time_public="2003-07-29",
                song_num=12,
            ),
        ])

    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_fav_album=fake_fav_album),
        credential=svc.credential,
    )
    albums = await svc.get_fav_albums()
    assert len(albums) == 1
    assert albums[0].name == "叶惠美"
    assert albums[0].singers[0].name == "周杰伦"


# ============================================================== 详情拉取

async def test_get_album_detail_combines_basic_info_and_songs():
    svc = QuaverService()

    async def fake_detail(value):
        return SimpleNamespace(
            album=SimpleNamespace(
                mid="alb1",
                name="叶惠美",
                time_public="2003-07-29",
                desc="经典",
                total_num=2,
            ),
            singers=[SimpleNamespace(mid="j", name="周杰伦")],
        )

    async def fake_song(value, num, page):
        return SimpleNamespace(
            song_list=[
                _raw_song(mid="t1", name="夜曲"),
                _raw_song(mid="t2", name="蓝色风暴"),
            ]
        )

    svc._client = SimpleNamespace(
        album=SimpleNamespace(get_detail=fake_detail, get_song=fake_song),
        credential=None,
    )
    a = await svc.get_album_detail("alb1")
    assert a.name == "叶惠美"
    assert a.singers == [Singer(mid="j", name="周杰伦")]
    assert a.publish_date == "2003-07-29"
    assert len(a.songs) == 2


async def test_get_playlist_detail_extracts_info_and_songs():
    """0.6.1 GetSonglistDetailResponse: info + songs + total."""
    svc = QuaverService()

    async def fake_detail(songlist_id, **kwargs):
        return SimpleNamespace(
            info=SimpleNamespace(
                id=7039749142,
                title="百听不厌",
                picurl="http://x",
                desc="经典",
                creator=SimpleNamespace(nick="今晚月色很美"),
                listennum=12345,
            ),
            songs=[
                _raw_song(mid="m1", name="A"),
                _raw_song(mid="m2", name="B"),
            ],
            total=99,
        )

    svc._client = SimpleNamespace(
        songlist=SimpleNamespace(get_detail=fake_detail),
        credential=None,
    )
    p = await svc.get_playlist_detail("7039749142")
    assert p.name == "百听不厌"
    assert p.creator == "今晚月色很美"
    assert p.song_count == 99
    assert len(p.songs) == 2


async def test_get_artist_detail_combines_info_and_hot_songs():
    svc = QuaverService()

    async def fake_info(mid):
        return SimpleNamespace(
            singer=SimpleNamespace(name="周杰伦", singer_pic="http://avatar.jpg"),
        )

    async def fake_tab_detail(mid, tab_type, page, num):
        return SimpleNamespace(
            song_tab=SimpleNamespace(
                list=[
                    _raw_song(mid="hot1", name="晴天"),
                    _raw_song(mid="hot2", name="稻香"),
                ],
            ),
        )

    svc._client = SimpleNamespace(
        singer=SimpleNamespace(get_info=fake_info, get_tab_detail=fake_tab_detail),
        credential=None,
    )
    ad = await svc.get_artist_detail("j")
    assert ad.singer.mid == "j"
    assert ad.singer.name == "周杰伦"
    assert len(ad.hot_songs) == 2
