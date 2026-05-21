"""SQLite cache 层单元测试.

覆盖:
- schema 创建 + 表存在
- song/album/playlist/artist 写穿 + 命中
- TTL: 过期返 None
- 嵌套 dataclass (Song.singers, Album.songs, ArtistDetail.hot_songs) 往返
- 多次写 = upsert (主键冲突替换)
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from quaverq.core.cache import Cache
from quaverq.core.models import Album, ArtistDetail, Playlist, Singer, Song


@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    c = Cache(tmp_path / "cache.db")
    c.open()
    yield c
    c.close()


# ============================================================== schema

def test_open_creates_db_file(tmp_path: Path):
    db = tmp_path / "x.db"
    c = Cache(db)
    c.open()
    try:
        assert db.exists()
        # 关键表存在
        tables = c.list_tables()
        assert "song_meta" in tables
        assert "album_meta" in tables
        assert "playlist_meta" in tables
        assert "artist_meta" in tables
    finally:
        c.close()


def test_open_idempotent(tmp_path: Path):
    """重复打开 (含已存在 schema) 不抛错."""
    db = tmp_path / "y.db"
    c1 = Cache(db); c1.open(); c1.close()
    c2 = Cache(db); c2.open(); c2.close()


# ============================================================== Song

def test_song_roundtrip(cache: Cache):
    s = Song(
        mid="m1", name="晴天",
        singers=[Singer(mid="j", name="周杰伦")],
        album_mid="alb", album_name="叶惠美",
        duration=269, pay_play=0, media_mid="mm1",
        cover_url="http://x/c.jpg",
    )
    cache.put_song(s)
    got = cache.get_song("m1")
    assert got is not None
    assert got.mid == "m1"
    assert got.name == "晴天"
    assert got.singers == [Singer(mid="j", name="周杰伦")]
    assert got.album_name == "叶惠美"
    assert got.duration == 269
    assert got.media_mid == "mm1"


def test_song_miss_returns_none(cache: Cache):
    assert cache.get_song("nope") is None


def test_song_ttl_expired_returns_none(cache: Cache):
    s = Song(mid="m1", name="x")
    cache.put_song(s)
    # 立即查命中
    assert cache.get_song("m1", ttl_sec=10) is not None
    # 用 ttl=0 立即过期
    assert cache.get_song("m1", ttl_sec=0) is None


def test_song_upsert_replaces_existing(cache: Cache):
    s1 = Song(mid="m1", name="old")
    s2 = Song(mid="m1", name="new")
    cache.put_song(s1)
    cache.put_song(s2)
    got = cache.get_song("m1")
    assert got.name == "new"


# ============================================================== Album

def test_album_with_songs_roundtrip(cache: Cache):
    a = Album(
        mid="alb1",
        name="叶惠美",
        singers=[Singer(mid="j", name="周杰伦")],
        publish_date="2003-07-29",
        description="第四张专辑",
        song_count=2,
        songs=[
            Song(mid="t1", name="以父之名", singers=[Singer(mid="j", name="周杰伦")]),
            Song(mid="t2", name="晴天", singers=[Singer(mid="j", name="周杰伦")]),
        ],
        cover_url="http://x/c.jpg",
    )
    cache.put_album(a)
    got = cache.get_album("alb1")
    assert got is not None
    assert got.name == "叶惠美"
    assert got.song_count == 2
    assert len(got.songs) == 2
    assert got.songs[0].name == "以父之名"
    assert got.songs[0].singers[0].name == "周杰伦"
    assert got.publish_date == "2003-07-29"


def test_album_ttl_expired(cache: Cache):
    cache.put_album(Album(mid="x", name="x"))
    assert cache.get_album("x", ttl_sec=0) is None


# ============================================================== Playlist

def test_playlist_with_songs_roundtrip(cache: Cache):
    p = Playlist(
        pid="pl1", name="周杰伦精选",
        cover_url="http://x", description="经典",
        creator="今晚月色很美", song_count=2,
        play_count=12345,
        songs=[
            Song(mid="t1", name="A"),
            Song(mid="t2", name="B"),
        ],
        is_mine=False,
    )
    cache.put_playlist(p)
    got = cache.get_playlist("pl1")
    assert got is not None
    assert got.name == "周杰伦精选"
    assert got.creator == "今晚月色很美"
    assert got.play_count == 12345
    assert [s.name for s in got.songs] == ["A", "B"]


# ============================================================== ArtistDetail

def test_artist_detail_with_hot_songs_roundtrip(cache: Cache):
    ad = ArtistDetail(
        singer=Singer(mid="j", name="周杰伦", avatar_url="http://x/avatar"),
        description="华语流行歌手",
        hot_songs=[
            Song(mid="h1", name="晴天"),
            Song(mid="h2", name="稻香"),
        ],
        albums=[],
    )
    cache.put_artist(ad)
    got = cache.get_artist("j")
    assert got is not None
    assert got.singer.name == "周杰伦"
    assert got.singer.avatar_url == "http://x/avatar"
    assert [s.name for s in got.hot_songs] == ["晴天", "稻香"]


# ============================================================== invalidation

def test_invalidate_removes_entry(cache: Cache):
    cache.put_song(Song(mid="m1", name="x"))
    cache.invalidate_song("m1")
    assert cache.get_song("m1") is None


# ============================================================== thread safety

# ============================================================== liked_song (P1.2)

def test_is_liked_empty_returns_false(cache: Cache):
    assert cache.is_liked("nope") is False


def test_put_liked_and_is_liked(cache: Cache):
    s = Song(mid="m1", name="晴天", id=97773)
    cache.put_liked(s)
    assert cache.is_liked("m1") is True
    assert cache.is_liked("other") is False


def test_remove_liked(cache: Cache):
    cache.put_liked(Song(mid="m1", name="x"))
    cache.remove_liked("m1")
    assert cache.is_liked("m1") is False


def test_list_liked_returns_all(cache: Cache):
    cache.put_liked(Song(mid="m1", name="A", singers=[Singer(mid="s", name="周杰伦")]))
    cache.put_liked(Song(mid="m2", name="B"))
    liked = cache.list_liked()
    assert {s.mid for s in liked} == {"m1", "m2"}
    # 数据完整 (含 singers 嵌套)
    m1 = next(s for s in liked if s.mid == "m1")
    assert m1.singers == [Singer(mid="s", name="周杰伦")]


def test_replace_liked_bulk(cache: Cache):
    """远端 sync 走 bulk replace 而非逐条 put."""
    cache.put_liked(Song(mid="old1", name="x"))
    cache.put_liked(Song(mid="old2", name="y"))
    cache.replace_liked([
        Song(mid="new1", name="a"),
        Song(mid="new2", name="b"),
    ])
    assert cache.is_liked("old1") is False
    assert cache.is_liked("old2") is False
    assert cache.is_liked("new1") is True
    assert cache.is_liked("new2") is True


def test_put_liked_idempotent(cache: Cache):
    """重复 put 同一 mid 不抛错."""
    s = Song(mid="m", name="x")
    cache.put_liked(s)
    cache.put_liked(s)
    assert cache.is_liked("m") is True


def test_cache_works_across_threads(tmp_path: Path):
    """主线程 open, 后台线程读写, 不抛 ProgrammingError (跨线程回归)."""
    import threading

    db = tmp_path / "thread.db"
    c = Cache(db)
    c.open()
    try:
        # 主线程写
        c.put_song(Song(mid="t1", name="main thread"))

        errors: list[BaseException] = []
        results: list[Song | None] = []

        def _bg():
            try:
                got = c.get_song("t1")
                results.append(got)
                c.put_song(Song(mid="t2", name="bg thread"))
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        t = threading.Thread(target=_bg)
        t.start()
        t.join(timeout=2)

        assert errors == [], f"跨线程访问抛错: {errors}"
        assert results[0] is not None
        assert results[0].name == "main thread"
        # 主线程读 bg 写的
        assert c.get_song("t2") is not None
    finally:
        c.close()
