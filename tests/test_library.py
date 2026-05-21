"""Library (P1.2) 测试 — 本地 cache 即写 + 远端容错 sync."""

from __future__ import annotations

from pathlib import Path

import pytest

from quaverq.core.cache import Cache
from quaverq.core.library import Library
from quaverq.core.models import Singer, Song


class _FakeService:
    """模拟 QuaverService 的 like/unlike/get_liked_songs."""

    def __init__(self):
        self.remote: list[Song] = []
        self.calls: list[tuple[str, str]] = []  # (op, mid)
        self.like_should_fail = False
        self.get_liked_should_fail = False

    async def like_song(self, song: Song) -> bool:
        self.calls.append(("like", song.mid))
        if self.like_should_fail:
            return False
        self.remote.append(song)
        return True

    async def unlike_song(self, song: Song) -> bool:
        self.calls.append(("unlike", song.mid))
        self.remote = [s for s in self.remote if s.mid != song.mid]
        return True

    async def get_liked_songs(self, *, limit: int = 500) -> list[Song]:
        if self.get_liked_should_fail:
            raise RuntimeError("network")
        return list(self.remote)


@pytest.fixture
def lib(tmp_path: Path) -> Library:
    cache = Cache(tmp_path / "lib.db")
    cache.open()
    svc = _FakeService()
    return Library(cache=cache, service=svc)


# ============================================================== local-only

def test_is_liked_initially_false(lib: Library):
    assert lib.is_liked("nope") is False


def test_list_liked_initially_empty(lib: Library):
    assert lib.list_liked() == []


# ============================================================== like/unlike

async def test_like_writes_local_immediately(lib: Library):
    s = Song(mid="m1", name="晴天", id=97773)
    await lib.like(s)
    # UI 秒级查询要看到
    assert lib.is_liked("m1") is True
    # 远端被调
    assert ("like", "m1") in lib.service.calls


async def test_unlike_removes_local_immediately(lib: Library):
    s = Song(mid="m1", name="x", id=1)
    await lib.like(s)
    await lib.unlike(s)
    assert lib.is_liked("m1") is False
    assert ("unlike", "m1") in lib.service.calls


async def test_like_keeps_local_even_if_remote_fails(lib: Library):
    """远端失败不回滚本地 (用户态优先)."""
    lib.service.like_should_fail = True
    s = Song(mid="m1", name="x", id=1)
    await lib.like(s)
    assert lib.is_liked("m1") is True


async def test_toggle_like_flips_state(lib: Library):
    s = Song(mid="m1", name="x", id=1)
    new = await lib.toggle_like(s)
    assert new is True
    assert lib.is_liked("m1") is True

    new = await lib.toggle_like(s)
    assert new is False
    assert lib.is_liked("m1") is False


# ============================================================== sync_from_remote

async def test_sync_from_remote_replaces_local(lib: Library):
    # 本地有旧的
    await lib.like(Song(mid="old", name="old"))
    # 远端有新的
    lib.service.remote = [
        Song(mid="r1", name="r1"),
        Song(mid="r2", name="r2"),
    ]
    n = await lib.sync_from_remote()
    assert n == 2
    assert lib.is_liked("old") is False  # 旧的被覆盖
    assert lib.is_liked("r1") is True
    assert lib.is_liked("r2") is True


async def test_sync_from_remote_failure_is_tolerated(lib: Library):
    """远端拉失败不抛, 不改本地."""
    await lib.like(Song(mid="kept", name="x"))
    lib.service.get_liked_should_fail = True
    n = await lib.sync_from_remote()
    assert n == 0
    assert lib.is_liked("kept") is True  # 没被清


async def test_list_liked_after_sync(lib: Library):
    lib.service.remote = [
        Song(mid="a", name="A", singers=[Singer(mid="s", name="周杰伦")]),
        Song(mid="b", name="B"),
    ]
    await lib.sync_from_remote()
    liked = lib.list_liked()
    assert {s.mid for s in liked} == {"a", "b"}
    a = next(s for s in liked if s.mid == "a")
    assert a.singers[0].name == "周杰伦"
