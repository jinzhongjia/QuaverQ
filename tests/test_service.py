"""服务层测试 (qqmusic-api 0.6.1, bypass 路径).

设计:
- 0.6 Client 调用通过 mock 注入 svc._client (SimpleNamespace 模拟 client.search / album / ...)
- get_song_url 走 bypass, 测试 monkey-patch svc._try_bypass_url 替代真 HTTP
- _to_song/_to_singer/_to_album_brief/_to_playlist_brief 用 SimpleNamespace 模拟 pydantic 对象
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qqmusic_api import Credential
from qqmusic_api.core.exceptions import (
    CredentialExpiredError as QQCredentialExpiredError,
    CredentialInvalidError as QQCredentialInvalidError,
    LoginError as QQLoginError,
)

from quaverq.core.models import (
    Album,
    ArtistDetail,
    Lyric,
    Playlist,
    Singer,
    Song,
    TopList,
)
from quaverq.core.service import (
    CredentialExpiredError,
    QuaverService,
    _clean_text,
    _cover_url,
    _credential_from_dict,
    _credential_to_dict,
    is_credential_expired_error,
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


def test_is_credential_expired_error_recognizes_qqmusic_exceptions():
    assert is_credential_expired_error(
        QQCredentialExpiredError(code=1000, data={})
    )
    assert is_credential_expired_error(
        QQCredentialInvalidError("接口需要有效登录凭证")
    )
    assert is_credential_expired_error(
        QQLoginError("登录鉴权参数无效或已过期", code=104401, data={})
    )
    assert is_credential_expired_error(
        CredentialExpiredError("登录已过期，请重新登录")
    )
    assert not is_credential_expired_error(RuntimeError("ordinary API failure"))


def test_bypass_payload_detects_credential_expired_codes():
    assert QuaverService._payload_indicates_credential_expired(
        {"code": 0, "req_0": {"code": 104401, "data": {}}}
    )
    assert QuaverService._payload_indicates_credential_expired(
        {"code": 1000, "req_0": {"code": 0, "data": {}}}
    )
    assert not QuaverService._payload_indicates_credential_expired(
        {"code": 0, "req_0": {"code": 2001, "data": {}}}
    )


async def test_probe_login_expired_maps_qqmusic_expired_exception():
    class _Login:
        async def check_expired(self) -> bool:
            raise QQCredentialExpiredError(code=1000, data={})

    svc = QuaverService()
    svc._client = SimpleNamespace(login=_Login(), credential=Credential())

    assert await svc.probe_login_expired() is True


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

    async def fake_try(mid, quality, **_kwargs):
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

    async def fake_try(mid, quality, **_kwargs):
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

    async def fake_try(_mid, _q, **_kwargs):
        return None

    svc._try_bypass_url = fake_try
    assert await svc.get_song_url(Song(mid="m", name="x")) is None


async def test_get_song_url_quality_unknown_falls_back_to_balanced():
    svc = QuaverService()
    svc._ct_value = 2
    attempts: list[str] = []

    async def fake_try(mid, q, **_kwargs):
        attempts.append(q)
        return f"https://x/{q}?vkey=k"

    svc._try_bypass_url = fake_try
    await svc.get_song_url(Song(mid="m", name="x"), quality_preference="bogus")
    # balanced 首选 MP3_320
    assert attempts[0] == "MP3_320"


async def test_try_bypass_url_uses_media_mid_for_filename():
    svc = QuaverService()
    captured: dict[str, object] = {}

    async def fake_post(_module, _method, param, **_kwargs):
        captured.update(param)
        return {"midurlinfo": [{"purl": "C400m.m4a?vkey=k"}]}

    svc._bypass_post = fake_post
    url = await svc._try_bypass_url(
        "songmid",
        "MP3_128",
        media_mid="mediamid",
    )

    assert url == "https://isure.stream.qqmusic.qq.com/C400m.m4a?vkey=k"
    assert captured["songmid"] == ["songmid"]
    assert captured["filename"] == ["M500mediamidmediamid.mp3"]


async def test_try_bypass_url_uses_short_vkey_timeout():
    svc = QuaverService()
    captured: dict[str, object] = {}

    async def fake_post(_module, _method, _param, **kwargs):
        captured.update(kwargs)
        return {"midurlinfo": [{"purl": "M500m.mp3?vkey=k"}]}

    svc._bypass_post = fake_post
    await svc._try_bypass_url("m", "MP3_128")

    assert captured["timeout"] == svc._VKEY_REQUEST_TIMEOUT_SEC


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


# ============================================================== Discover / Home (P2.1)

async def test_get_recommend_playlists_maps_to_playlist():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_post(_module, _method, _param, **_kwargs):
        return {
            "List": [
                {
                    "Playlist": {
                        "basic": {
                            "tid": 8907966308,
                            "title": "国韵之潮",
                            "desc": "国风精选",
                            "cover": {"default_url": "http://x/c.jpg"},
                            "creator": {"nick": "编辑"},
                            "song_cnt": 50,
                            "play_cnt": 10000,
                        }
                    }
                }
            ]
        }

    svc._bypass_post = fake_post
    pls = await svc.get_recommend_playlists(limit=8)
    assert len(pls) == 1
    assert pls[0].pid == "8907966308"
    assert pls[0].name == "国韵之潮"
    assert pls[0].creator == "编辑"
    assert pls[0].song_count == 50


async def test_get_recommend_playlists_failure_returns_empty():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_post(_module, _method, _param, **_kwargs):
        raise RuntimeError("boom")

    svc._bypass_post = fake_post
    assert await svc.get_recommend_playlists() == []


async def test_get_recommend_playlists_uses_memo_cache():
    """同一 service 实例第二次调用直接命中内存 cache, 不打 API."""
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    call_count = [0]

    async def fake_post(_module, _method, _param, **_kwargs):
        call_count[0] += 1
        return {
            "List": [
                {
                    "Playlist": {
                        "basic": {
                            "tid": 1,
                            "title": "x",
                            "cover": {},
                            "creator": {},
                            "song_cnt": 1,
                        }
                    }
                }
            ]
        }

    svc._bypass_post = fake_post
    await svc.get_recommend_playlists()
    await svc.get_recommend_playlists()
    await svc.get_recommend_playlists()
    # 只打了一次 API, 后面两次直接 memory cache
    assert call_count[0] == 1


async def test_get_recommend_new_songs_uses_memo_cache():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    call_count = [0]

    async def fake_post(_module, _method, _param, **_kwargs):
        call_count[0] += 1
        return {"songlist": [_raw_song(mid="m", name="x")]}

    svc._bypass_post = fake_post
    await svc.get_recommend_new_songs()
    await svc.get_recommend_new_songs()
    assert call_count[0] == 1


async def test_get_daily_recommend_songs_collects_radar_pages():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    calls: list[int] = []

    async def fake_post(module, _method, param, **_kwargs):
        assert module == "music.recommend.TrackRelationServer"
        page = param["Page"]
        calls.append(page)
        start = (page - 1) * 20
        return {
            "VecSongs": [
                {"Track": _raw_song(mid=f"m{i}", name=f"每日{i}")}
                for i in range(start, start + 20)
            ],
            "HasMore": page < 2,
        }

    svc._bypass_post = fake_post

    songs = await svc.get_daily_recommend_songs(limit=30)

    assert calls == [1, 2]
    assert len(songs) == 30
    assert songs[0].name == "每日0"
    assert songs[-1].name == "每日29"


async def test_get_daily_recommend_songs_falls_back_to_guess():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_post(module, _method, _param, **_kwargs):
        if module == "music.recommend.TrackRelationServer":
            raise RuntimeError("radar unavailable")
        return {"tracks": [_raw_song(mid="g1", name="猜你喜欢")]}

    svc._bypass_post = fake_post

    songs = await svc.get_daily_recommend_songs(limit=30)

    assert len(songs) == 1
    assert songs[0].name == "猜你喜欢"


def test_clean_text_removes_br_tags():
    raw = "1. 榜单定义：xxx。<br>2. 更新频率：每日。<br>3. 排序依据：yyy。"
    out = _clean_text(raw, max_len=999)
    assert "<br>" not in out
    assert "1. 榜单定义" in out


def test_clean_text_truncates():
    raw = "abc" * 200
    out = _clean_text(raw, max_len=20)
    assert len(out) <= 21   # 20 + ellipsis
    assert out.endswith("…")


def test_clean_text_handles_empty():
    assert _clean_text(None) == ""
    assert _clean_text("") == ""


def test_clean_text_strips_em_tags():
    raw = "<em>周杰伦</em> 的歌"
    assert _clean_text(raw) == "周杰伦 的歌"


def test_clean_text_collapses_whitespace():
    raw = "line1<br><br>line2    \t  line3"
    assert _clean_text(raw) == "line1 line2 line3"


async def test_get_top_categories_flattens_groups():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_post(_module, _method, _param, **_kwargs):
        return {
            "group": [
                {
                    "groupId": 0,
                    "groupName": "巅峰榜",
                    "toplist": [
                        {
                            "topId": 135,
                            "title": "巅峰潮流榜",
                            "frontPicUrl": "http://p1",
                            "headPicUrl": "",
                            "intro": "",
                            "totalNum": 300,
                        },
                        {
                            "topId": 4,
                            "title": "飙升榜",
                            "frontPicUrl": "http://p2",
                            "headPicUrl": "",
                            "intro": "",
                            "totalNum": 200,
                        },
                    ],
                },
                {
                    "groupId": 1,
                    "groupName": "地区榜",
                    "toplist": [
                        {
                            "topId": 11,
                            "title": "内地",
                            "frontPicUrl": "",
                            "headPicUrl": "http://p3",
                            "intro": "",
                            "totalNum": 100,
                        }
                    ],
                },
            ]
        }

    svc._bypass_post = fake_post
    tops = await svc.get_top_categories()
    assert len(tops) == 3   # 扁平化全 group 的 toplist
    assert tops[0].top_id == 135
    assert tops[0].name == "巅峰潮流榜"
    assert tops[0].cover_url == "http://p1"
    assert tops[2].cover_url == "http://p3"   # head_pic_url 兜底


async def test_get_top_categories_cached():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    call_count = [0]

    async def fake_post(_module, _method, _param, **_kwargs):
        call_count[0] += 1
        return {"group": []}

    svc._bypass_post = fake_post
    await svc.get_top_categories()
    await svc.get_top_categories()
    assert call_count[0] == 1


async def test_get_top_detail_reuses_playlist_model():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_post(_module, _method, param, **_kwargs):
        assert param["topId"] == 135
        return {
            "data": {
                "topId": 135,
                "title": "巅峰潮流榜",
                "frontPicUrl": "http://p",
                "intro": "每日更新",
                "totalNum": 300,
                "listenNum": 99999,
            },
            "songInfoList": [
                _raw_song(mid="t1", name="排行第 1"),
                _raw_song(mid="t2", name="排行第 2"),
            ],
        }

    svc._bypass_post = fake_post
    p = await svc.get_top_detail(135)
    assert p.pid == "135"
    assert p.name == "巅峰潮流榜"
    assert p.cover_url == "http://p"
    assert p.song_count == 300
    assert p.play_count == 99999
    assert len(p.songs) == 2
    assert p.songs[0].name == "排行第 1"


async def test_get_top_detail_failure_returns_placeholder_playlist():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_post(_module, _method, _param, **_kwargs):
        raise RuntimeError("network")

    svc._bypass_post = fake_post
    p = await svc.get_top_detail(999)
    assert p.pid == "999"
    assert p.songs == []
    assert "不可用" in p.name


# ============================================================== P2.3 热搜 / 搜索建议


async def test_get_hot_search_extracts_queries():
    """get_hot_search 从 vec_hotkey 抽 query 字段, 排除空/重复."""
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    call_count = [0]

    async def fake_hotkey():
        call_count[0] += 1
        return {
            "vec_hotkey": [
                {"query": "玻璃 gareth.t", "title": "玻璃 Gareth.T"},
                {"query": "梓渝 凌绝顶", "title": "凌绝顶"},
                {"query": "", "title": "空查询应被跳过"},
                {"query": "玻璃 gareth.t", "title": "重复应被去重"},
            ]
        }

    svc._client = SimpleNamespace(
        search=SimpleNamespace(get_hotkey=fake_hotkey),
        credential=svc.credential,
    )
    hots = await svc.get_hot_search(limit=10)
    assert hots == ["玻璃 gareth.t", "梓渝 凌绝顶"]
    assert call_count[0] == 1


async def test_get_hot_search_cached():
    """10 分钟内存 cache, 短时间重复调用不重发请求."""
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    call_count = [0]

    async def fake_hotkey():
        call_count[0] += 1
        return {"vec_hotkey": [{"query": "a", "title": "a"}]}

    svc._client = SimpleNamespace(
        search=SimpleNamespace(get_hotkey=fake_hotkey),
        credential=svc.credential,
    )
    await svc.get_hot_search()
    await svc.get_hot_search()
    assert call_count[0] == 1


async def test_get_hot_search_failure_returns_empty():
    """get_hotkey 抛错时优雅降级返 []."""
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_hotkey():
        raise RuntimeError("net")

    svc._client = SimpleNamespace(
        search=SimpleNamespace(get_hotkey=fake_hotkey),
        credential=svc.credential,
    )
    assert await svc.get_hot_search() == []


async def test_get_search_suggest_extracts_hints():
    """complete 返回的 items 取 hint, 剥掉 <em></em> 高亮标签."""
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_complete(keyword):
        assert keyword == "周杰"
        return {
            "items": [
                {"hint": "周杰伦", "hint_hilight": "<em>周杰</em>伦"},
                {"hint": "周杰伦 七里香", "hint_hilight": "<em>周杰</em>伦 七里香"},
                {"hint": "", "hint_hilight": ""},          # 空跳过
                {"hint": "周杰伦", "hint_hilight": "重复"},  # 去重
            ]
        }

    svc._client = SimpleNamespace(
        search=SimpleNamespace(complete=fake_complete),
        credential=svc.credential,
    )
    sugs = await svc.get_search_suggest("周杰")
    assert sugs == ["周杰伦", "周杰伦 七里香"]


async def test_get_search_suggest_empty_keyword_returns_empty():
    """空 keyword 不该发请求."""
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    called = [False]

    async def fake_complete(keyword):
        called[0] = True
        return {"items": []}

    svc._client = SimpleNamespace(
        search=SimpleNamespace(complete=fake_complete),
        credential=svc.credential,
    )
    assert await svc.get_search_suggest("") == []
    assert await svc.get_search_suggest("   ") == []
    assert called[0] is False


async def test_get_search_suggest_failure_returns_empty():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_complete(keyword):
        raise RuntimeError("net")

    svc._client = SimpleNamespace(
        search=SimpleNamespace(complete=fake_complete),
        credential=svc.credential,
    )
    assert await svc.get_search_suggest("jay") == []


async def test_get_recommend_new_songs_maps_to_song():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")

    async def fake_post(_module, _method, _param, **_kwargs):
        return {
            "songlist": [
                _raw_song(mid="m1", name="新歌1"),
                _raw_song(mid="m2", name="新歌2"),
            ]
        }

    svc._bypass_post = fake_post
    songs = await svc.get_recommend_new_songs(limit=12)
    assert len(songs) == 2
    assert songs[0].name == "新歌1"
    assert songs[0].mid == "m1"


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


async def test_get_my_playlists_raises_credential_expired_from_qqmusic_error():
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k", str_musicid="1")

    async def fake_created(_uin, **_kw):
        raise QQCredentialExpiredError(code=1000, data={})

    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_created_songlist=fake_created),
        credential=svc.credential,
    )
    with pytest.raises(CredentialExpiredError):
        await svc.get_my_playlists()


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
