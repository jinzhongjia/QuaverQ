"""service.get_similar_singers / get_singer_songs / get_singer_albums 契约 (第二档 2.2).

接口形态来自探针:
- singer.get_similar(mid, number) → SimilarSingerResponse.singerlist: list[SimilarSinger]
  字段 mid/name/id/singer_pic
- singer.get_songs_list(mid, num, page) → SingerSongListResponse.song_list: list[Song]
  完整 Song pydantic, 复用 _to_song; 服务端 total_num 表示总数
- singer.get_album_list(mid, num, page) → SingerAlbumListResponse.album_list: list[AlbumBrief]
  AlbumBrief 字段: mid/name/subtitle/time_public/total_num/album_type/singer_name(单字符串)/tags
  没有 publish_date / songnum, 用 time_public / total_num 别名; 无封面 URL → 用 _cover_url
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qqmusic_api.core.exceptions import CredentialExpiredError as QQCredentialExpiredError

from quaverq.core.models import Album, Singer, Song
from quaverq.core.service import CredentialExpiredError, QuaverService


def _raw_song(mid: str, name: str, song_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        mid=mid,
        id=song_id,
        name=name,
        singer=[SimpleNamespace(mid="s1", name="周杰伦")],
        album=SimpleNamespace(mid="a1", name="叶惠美"),
        file=SimpleNamespace(media_mid=f"{mid}_media"),
        pay=SimpleNamespace(pay_play=0),
        interval=215,
    )


def _attach_singer_mock(
    svc: QuaverService,
    *,
    similar_resp=None,
    similar_exc=None,
    songs_resp=None,
    songs_exc=None,
    albums_resp=None,
    albums_exc=None,
):
    """挂 svc._client.singer.{get_similar, get_songs_list, get_album_list}."""

    async def _get_similar(mid, number=10):
        if similar_exc is not None:
            raise similar_exc
        return similar_resp

    async def _get_songs(mid, num=10, page=1):
        if songs_exc is not None:
            raise songs_exc
        return songs_resp

    async def _get_albums(mid, num=10, page=1):
        if albums_exc is not None:
            raise albums_exc
        return albums_resp

    svc._client = SimpleNamespace(
        singer=SimpleNamespace(
            get_similar=_get_similar,
            get_songs_list=_get_songs,
            get_album_list=_get_albums,
        )
    )


# ============================================================== get_similar_singers


async def test_get_similar_singers_empty_when_mid_empty():
    svc = QuaverService()
    _attach_singer_mock(svc, similar_resp=SimpleNamespace(singerlist=[]))
    assert await svc.get_similar_singers("") == []


async def test_get_similar_singers_parses_fields():
    svc = QuaverService()
    resp = SimpleNamespace(
        singerlist=[
            SimpleNamespace(
                mid="0010PLKl2Wgolz",
                name="F.I.R.飞儿乐团",
                id=245,
                singer_pic="http://qpic/p1.jpg",
            ),
            SimpleNamespace(
                mid="001JDzPT3JdvqK",
                name="王力宏",
                id=265,
                singer_pic="http://qpic/p2.jpg",
            ),
        ]
    )
    _attach_singer_mock(svc, similar_resp=resp)
    result = await svc.get_similar_singers("000")
    assert len(result) == 2
    assert all(isinstance(s, Singer) for s in result)
    assert result[0].mid == "0010PLKl2Wgolz"
    assert result[0].name == "F.I.R.飞儿乐团"
    assert result[0].avatar_url == "http://qpic/p1.jpg"


async def test_get_similar_singers_skips_items_without_mid():
    svc = QuaverService()
    resp = SimpleNamespace(
        singerlist=[
            SimpleNamespace(mid="m1", name="A", id=1, singer_pic=""),
            SimpleNamespace(mid="", name="脏", id=0, singer_pic=""),
        ]
    )
    _attach_singer_mock(svc, similar_resp=resp)
    result = await svc.get_similar_singers("000")
    assert [s.mid for s in result] == ["m1"]


async def test_get_similar_singers_raises_on_expired():
    svc = QuaverService()
    _attach_singer_mock(svc, similar_exc=QQCredentialExpiredError(code=1000, data={}))
    with pytest.raises(CredentialExpiredError):
        await svc.get_similar_singers("000")


async def test_get_similar_singers_returns_empty_on_generic_failure():
    svc = QuaverService()
    _attach_singer_mock(svc, similar_exc=RuntimeError("boom"))
    assert await svc.get_similar_singers("000") == []


# ============================================================== get_singer_songs


async def test_get_singer_songs_empty_when_mid_empty():
    svc = QuaverService()
    _attach_singer_mock(svc, songs_resp=SimpleNamespace(song_list=[], total_num=0))
    assert await svc.get_singer_songs("") == []


async def test_get_singer_songs_parses_via_to_song():
    svc = QuaverService()
    resp = SimpleNamespace(
        total_num=1012,
        song_list=[
            _raw_song("m1", "晴天", 97773),
            _raw_song("m2", "搁浅", 102065750),
        ],
    )
    _attach_singer_mock(svc, songs_resp=resp)
    result = await svc.get_singer_songs("000")
    assert len(result) == 2
    assert all(isinstance(s, Song) for s in result)
    assert [s.mid for s in result] == ["m1", "m2"]
    assert result[0].name == "晴天"


async def test_get_singer_songs_passes_page_and_limit():
    svc = QuaverService()
    captured: dict[str, int] = {}

    async def _get_songs(mid, num=10, page=1):
        captured["num"] = num
        captured["page"] = page
        captured["mid"] = mid
        return SimpleNamespace(song_list=[], total_num=0)

    svc._client = SimpleNamespace(singer=SimpleNamespace(get_songs_list=_get_songs))
    await svc.get_singer_songs("ABC123", limit=80, page=3)
    assert captured == {"num": 80, "page": 3, "mid": "ABC123"}


async def test_get_singer_songs_raises_on_expired():
    svc = QuaverService()
    _attach_singer_mock(svc, songs_exc=QQCredentialExpiredError(code=1000, data={}))
    with pytest.raises(CredentialExpiredError):
        await svc.get_singer_songs("000")


# ============================================================== get_singer_albums


async def test_get_singer_albums_empty_when_mid_empty():
    svc = QuaverService()
    _attach_singer_mock(svc, albums_resp=SimpleNamespace(album_list=[], total=0))
    assert await svc.get_singer_albums("") == []


async def test_get_singer_albums_parses_album_brief_fields():
    """AlbumBrief 用 total_num (不是 songnum), time_public (不是 publish_date), singer_name (单字符串)."""
    svc = QuaverService()
    resp = SimpleNamespace(
        total=43,
        album_list=[
            SimpleNamespace(
                mid="003RMaRI1iFoYd",
                name="周杰伦的床边故事",
                subtitle="",
                time_public="2016-06-24",
                total_num=10,
                album_type="正式",
                singer_name="周杰伦",
                tags=[],
            ),
            SimpleNamespace(
                mid="002eFUFm2XYZ7z",
                name="我很忙",
                subtitle="",
                time_public="2007-11-02",
                total_num=11,
                album_type="正式",
                singer_name="周杰伦",
                tags=[],
            ),
        ],
    )
    _attach_singer_mock(svc, albums_resp=resp)
    result = await svc.get_singer_albums("000")
    assert len(result) == 2
    assert all(isinstance(a, Album) for a in result)
    assert result[0].mid == "003RMaRI1iFoYd"
    assert result[0].name == "周杰伦的床边故事"
    assert result[0].publish_date == "2016-06-24"
    assert result[0].song_count == 10
    # singer_name 单字符串 → 包成 [Singer(name=...)]
    assert len(result[0].singers) == 1
    assert result[0].singers[0].name == "周杰伦"
    # 没有封面字段 → 用 _cover_url(mid, 300) 自拼
    assert "003RMaRI1iFoYd" in result[0].cover_url
    assert result[0].cover_url.startswith("https://y.qq.com/music/photo_new/")


async def test_get_singer_albums_skips_items_without_mid():
    svc = QuaverService()
    resp = SimpleNamespace(
        total=2,
        album_list=[
            SimpleNamespace(
                mid="a1",
                name="A",
                time_public="",
                total_num=1,
                singer_name="X",
                tags=[],
                subtitle="",
                album_type="",
            ),
            SimpleNamespace(
                mid="",
                name="脏",
                time_public="",
                total_num=0,
                singer_name="",
                tags=[],
                subtitle="",
                album_type="",
            ),
        ],
    )
    _attach_singer_mock(svc, albums_resp=resp)
    result = await svc.get_singer_albums("000")
    assert [a.mid for a in result] == ["a1"]


async def test_get_singer_albums_passes_page_and_limit():
    svc = QuaverService()
    captured: dict[str, int] = {}

    async def _get_albums(mid, num=10, page=1):
        captured["num"] = num
        captured["page"] = page
        return SimpleNamespace(album_list=[], total=0)

    svc._client = SimpleNamespace(singer=SimpleNamespace(get_album_list=_get_albums))
    await svc.get_singer_albums("000", limit=50, page=2)
    assert captured == {"num": 50, "page": 2}


async def test_get_singer_albums_raises_on_expired():
    svc = QuaverService()
    _attach_singer_mock(svc, albums_exc=QQCredentialExpiredError(code=1000, data={}))
    with pytest.raises(CredentialExpiredError):
        await svc.get_singer_albums("000")


async def test_get_singer_albums_returns_empty_on_generic_failure():
    svc = QuaverService()
    _attach_singer_mock(svc, albums_exc=RuntimeError("boom"))
    assert await svc.get_singer_albums("000") == []
