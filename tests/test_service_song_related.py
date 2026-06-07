"""service.get_similar_songs / get_related_songlists 契约 (第二档 2.1).

接口形态来自探针:
- song.get_similar_song(songid) → GetSimilarSongResponse.song: list[SimilarSongGroup]
  每组 song: list[Song] (完整 0.6 Song pydantic, 复用 _to_song)
- song.get_related_songlist(songid) → GetRelatedSonglistResponse.songlist: list[RelatedPlaylist]
  字段 id/title/picurl/desc/songnum/listennum/creator
- 两者都是公开接口, 不需要 credential, 但凭据过期错仍需透传 (防御)
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qqmusic_api.core.exceptions import CredentialExpiredError as QQCredentialExpiredError

from quaverq.core.models import Playlist, Song
from quaverq.core.service import CredentialExpiredError, QuaverService


def _raw_song(mid: str, name: str, song_id: int) -> SimpleNamespace:
    """模拟 0.6 Song pydantic 对象."""
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


def _attach_song_mock(
    svc: QuaverService,
    *,
    similar_resp=None,
    similar_exc=None,
    related_resp=None,
    related_exc=None,
):
    """挂 svc._client.song.{get_similar_song, get_related_songlist}."""

    async def _get_similar(songid):
        if similar_exc is not None:
            raise similar_exc
        return similar_resp

    async def _get_related(songid, last=None):
        if related_exc is not None:
            raise related_exc
        return related_resp

    svc._client = SimpleNamespace(
        song=SimpleNamespace(
            get_similar_song=_get_similar,
            get_related_songlist=_get_related,
        )
    )


# ============================================================== get_similar_songs


async def test_get_similar_songs_returns_empty_when_songid_zero():
    svc = QuaverService()
    _attach_song_mock(svc, similar_resp=SimpleNamespace(song=[]))
    assert await svc.get_similar_songs(0) == []


async def test_get_similar_songs_flattens_groups():
    """多个 SimilarSongGroup 的 song 拍扁成一个列表."""
    svc = QuaverService()
    resp = SimpleNamespace(
        song=[
            SimpleNamespace(
                title_template="听「{String}」的也在听",
                title_content="周杰伦",
                song=[
                    _raw_song("m1", "晴天", 101),
                    _raw_song("m2", "七里香", 102),
                ],
            ),
            SimpleNamespace(
                title_template="另一组",
                title_content="X",
                song=[_raw_song("m3", "稻香", 103)],
            ),
        ]
    )
    _attach_song_mock(svc, similar_resp=resp)
    result = await svc.get_similar_songs(999)
    assert len(result) == 3
    assert all(isinstance(s, Song) for s in result)
    assert [s.mid for s in result] == ["m1", "m2", "m3"]
    assert result[0].name == "晴天"


async def test_get_similar_songs_dedupes_by_mid():
    """跨组同一首歌只保留一次, 保持首次出现顺序."""
    svc = QuaverService()
    resp = SimpleNamespace(
        song=[
            SimpleNamespace(
                title_template="g1",
                title_content="",
                song=[_raw_song("m1", "A", 1), _raw_song("m2", "B", 2)],
            ),
            SimpleNamespace(
                title_template="g2",
                title_content="",
                song=[_raw_song("m2", "B", 2), _raw_song("m3", "C", 3)],
            ),
        ]
    )
    _attach_song_mock(svc, similar_resp=resp)
    result = await svc.get_similar_songs(999)
    assert [s.mid for s in result] == ["m1", "m2", "m3"]


async def test_get_similar_songs_skips_songs_without_mid():
    """脏数据: 没有 mid 的歌直接跳过."""
    svc = QuaverService()
    resp = SimpleNamespace(
        song=[
            SimpleNamespace(
                title_template="g",
                title_content="",
                song=[_raw_song("", "脏数据", 0), _raw_song("m1", "正常", 1)],
            )
        ]
    )
    _attach_song_mock(svc, similar_resp=resp)
    result = await svc.get_similar_songs(999)
    assert [s.mid for s in result] == ["m1"]


async def test_get_similar_songs_raises_on_expired_credential():
    svc = QuaverService()
    _attach_song_mock(svc, similar_exc=QQCredentialExpiredError(code=1000, data={}))
    with pytest.raises(CredentialExpiredError):
        await svc.get_similar_songs(999)


async def test_get_similar_songs_returns_empty_on_generic_failure():
    svc = QuaverService()
    _attach_song_mock(svc, similar_exc=RuntimeError("network glitch"))
    assert await svc.get_similar_songs(999) == []


# ============================================================== get_related_songlists


async def test_get_related_songlists_returns_empty_when_songid_zero():
    svc = QuaverService()
    _attach_song_mock(svc, related_resp=SimpleNamespace(songlist=[], has_more=0))
    assert await svc.get_related_songlists(0) == []


async def test_get_related_songlists_parses_fields():
    svc = QuaverService()
    resp = SimpleNamespace(
        has_more=1,
        songlist=[
            SimpleNamespace(
                id=7889916404,
                dirid=1,
                title="抖音热播！站内收藏100w+华语歌",
                picurl="http://qpic/p1.jpg",
                desc="精选",
                songnum=569,
                listennum=12345,
                creator="反派大魔王",
            ),
            SimpleNamespace(
                id=9703983298,
                dirid=2,
                title="热门传唱TOP100",
                picurl="http://qpic/p2.jpg",
                desc="",
                songnum=100,
                listennum=0,
                creator="QQ音乐AI唱",
            ),
        ],
    )
    _attach_song_mock(svc, related_resp=resp)
    result = await svc.get_related_songlists(999)
    assert len(result) == 2
    assert all(isinstance(p, Playlist) for p in result)
    assert result[0].pid == "7889916404"
    assert result[0].name == "抖音热播！站内收藏100w+华语歌"
    assert result[0].cover_url == "http://qpic/p1.jpg"
    assert result[0].creator == "反派大魔王"
    assert result[0].song_count == 569
    assert result[0].play_count == 12345
    assert result[1].pid == "9703983298"


async def test_get_related_songlists_skips_items_without_id():
    svc = QuaverService()
    resp = SimpleNamespace(
        has_more=0,
        songlist=[
            SimpleNamespace(
                id=1, title="A", picurl="", desc="", songnum=1, listennum=0, creator=""
            ),
            SimpleNamespace(
                id=0, title="脏", picurl="", desc="", songnum=0, listennum=0, creator=""
            ),
        ],
    )
    _attach_song_mock(svc, related_resp=resp)
    result = await svc.get_related_songlists(999)
    assert [p.pid for p in result] == ["1"]


async def test_get_related_songlists_raises_on_expired_credential():
    svc = QuaverService()
    _attach_song_mock(svc, related_exc=QQCredentialExpiredError(code=1000, data={}))
    with pytest.raises(CredentialExpiredError):
        await svc.get_related_songlists(999)


async def test_get_related_songlists_returns_empty_on_generic_failure():
    svc = QuaverService()
    _attach_song_mock(svc, related_exc=RuntimeError("boom"))
    assert await svc.get_related_songlists(999) == []


# ============================================================== get_song_related


async def test_get_song_related_runs_both_concurrently():
    """两个调用并发, 结果合并为 (similar, related) 二元组."""
    svc = QuaverService()
    sim = SimpleNamespace(
        song=[SimpleNamespace(title_template="", title_content="", song=[_raw_song("m1", "A", 1)])]
    )
    rel = SimpleNamespace(
        has_more=0,
        songlist=[
            SimpleNamespace(
                id=42, title="P", picurl="", desc="", songnum=1, listennum=0, creator="me"
            )
        ],
    )
    _attach_song_mock(svc, similar_resp=sim, related_resp=rel)

    similar, related = await svc.get_song_related(999)
    assert len(similar) == 1
    assert similar[0].mid == "m1"
    assert len(related) == 1
    assert related[0].pid == "42"


async def test_get_song_related_returns_empty_tuple_on_zero_songid():
    svc = QuaverService()
    _attach_song_mock(
        svc,
        similar_resp=SimpleNamespace(song=[]),
        related_resp=SimpleNamespace(has_more=0, songlist=[]),
    )
    similar, related = await svc.get_song_related(0)
    assert similar == [] and related == []


async def test_get_song_related_returns_partial_when_one_side_fails():
    """一边挂掉另一边应仍正常返回 (UX: 不能因为相似挂了相关歌单也消失)."""
    svc = QuaverService()
    rel = SimpleNamespace(
        has_more=0,
        songlist=[
            SimpleNamespace(
                id=42, title="P", picurl="", desc="", songnum=1, listennum=0, creator=""
            )
        ],
    )
    _attach_song_mock(svc, similar_exc=RuntimeError("similar boom"), related_resp=rel)

    similar, related = await svc.get_song_related(999)
    assert similar == []
    assert len(related) == 1


async def test_get_song_related_propagates_credential_expired():
    """凭据过期类异常透传, 让 controller 走清缓存."""
    svc = QuaverService()
    _attach_song_mock(
        svc,
        similar_exc=QQCredentialExpiredError(code=1000, data={}),
        related_resp=SimpleNamespace(has_more=0, songlist=[]),
    )
    with pytest.raises(CredentialExpiredError):
        await svc.get_song_related(999)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
