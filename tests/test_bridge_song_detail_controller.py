"""SongDetailController tests (第二档 2.1)."""

from __future__ import annotations

import asyncio

from quaverq.bridge.service_controller import ServiceController
from quaverq.bridge.song_detail_controller import SongDetailController
from quaverq.core.models import Playlist, Singer, Song


class _FakeService:
    def __init__(self) -> None:
        self.connected = False
        self.is_authenticated = True
        self.song_related_calls: list[int] = []
        self.song_related_results: dict[int, tuple[list[Song], list[Playlist]]] = {}
        self.song_related_exc: Exception | None = None
        # 用 event 拉长一次调用, 测试 race / loading
        self.gate: asyncio.Event | None = None

    async def set_credential(self, credential) -> None:
        self.is_authenticated = credential is not None

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_song_related(self, songid: int) -> tuple[list[Song], list[Playlist]]:
        self.song_related_calls.append(songid)
        if self.gate is not None:
            await self.gate.wait()
        if self.song_related_exc is not None:
            raise self.song_related_exc
        return self.song_related_results.get(songid, ([], []))


def _song_map(mid: str = "m1", song_id: int = 101, name: str = "晴天") -> dict[str, object]:
    return {
        "mid": mid,
        "id": song_id,
        "name": name,
        "singers": [{"mid": "s1", "name": "周杰伦"}],
        "albumName": "叶惠美",
        "duration": 269,
    }


async def test_open_loads_similar_and_related_and_sets_visible():
    svc = _FakeService()
    svc.song_related_results[101] = (
        [
            Song(mid="m2", id=102, name="七里香", singers=[Singer(mid="s1", name="周杰伦")]),
            Song(mid="m3", id=103, name="稻香", singers=[Singer(mid="s1", name="周杰伦")]),
        ],
        [Playlist(pid="p1", name="抖音热播", creator="A", song_count=569)],
    )
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)

    await ctrl.open_async(_song_map())

    assert svc.song_related_calls == [101]
    assert ctrl.visible is True
    assert ctrl.loading is False
    assert ctrl.errorMessage == ""
    assert ctrl.similarSongsModel.count == 2
    assert ctrl.relatedPlaylistsModel.count == 1
    assert ctrl.relatedPlaylistsModel.cardAt(0)["title"] == "抖音热播"
    assert ctrl.currentSong["mid"] == "m1"
    assert ctrl.currentSong["name"] == "晴天"


async def test_open_rejects_song_without_mid_or_id():
    svc = _FakeService()
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)
    errors: list[str] = []
    ctrl.errorRaised.connect(errors.append)

    # 缺 mid
    await ctrl.open_async({"id": 1, "name": "X"})
    assert svc.song_related_calls == []
    assert ctrl.visible is False
    assert "歌曲数据不完整" in errors[-1]

    # id=0
    errors.clear()
    await ctrl.open_async({"mid": "m1", "id": 0, "name": "X"})
    assert svc.song_related_calls == []
    assert ctrl.visible is False
    assert errors


async def test_close_keeps_models_but_hides():
    svc = _FakeService()
    svc.song_related_results[101] = (
        [Song(mid="m2", id=102, name="X")],
        [Playlist(pid="p1", name="P")],
    )
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)
    await ctrl.open_async(_song_map())
    assert ctrl.visible is True

    ctrl.close()
    assert ctrl.visible is False
    # 保留旧内容, 不闪空
    assert ctrl.similarSongsModel.count == 1
    assert ctrl.relatedPlaylistsModel.count == 1


async def test_open_handles_service_error():
    svc = _FakeService()
    svc.song_related_exc = RuntimeError("boom")
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)
    errors: list[str] = []
    ctrl.errorRaised.connect(errors.append)

    await ctrl.open_async(_song_map())

    assert ctrl.loading is False
    assert ctrl.errorMessage != ""
    assert errors


async def test_open_clears_models_before_load_finishes():
    """新一次 open: 旧 model 应立刻清空, 不能在 loading 时还显示上一首的数据 (避免 UX 误导)."""
    svc = _FakeService()
    svc.gate = asyncio.Event()
    svc.song_related_results[101] = (
        [Song(mid="old", id=1, name="old-similar")],
        [Playlist(pid="old", name="old-playlist")],
    )
    svc.song_related_results[202] = (
        [Song(mid="new", id=2, name="new-similar")],
        [Playlist(pid="new", name="new-playlist")],
    )
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)

    # 先把第一首加载完
    svc.gate.set()  # 一开始就放行
    await ctrl.open_async(_song_map(mid="m1", song_id=101))
    assert ctrl.similarSongsModel.count == 1
    assert ctrl.relatedPlaylistsModel.count == 1

    # 第二次 open 时把 gate 重新关上, 验证 model 在 loading 期间是空的
    svc.gate = asyncio.Event()  # 新 gate 关上
    task = asyncio.create_task(ctrl.open_async(_song_map(mid="m2", song_id=202)))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert ctrl.loading is True, "切歌瞬间应当处于 loading"
    assert ctrl.similarSongsModel.count == 0, "旧 similar 数据应在 loading 时已被清空"
    assert ctrl.relatedPlaylistsModel.count == 0, "旧 related 数据应在 loading 时已被清空"

    svc.gate.set()
    await task
    assert ctrl.similarSongsModel.count == 1
    assert ctrl.similarSongsModel.songs()[0].mid == "new"


async def test_retry_reloads_current_song():
    """retry() 应当用当前 currentSong 再次发请求."""
    svc = _FakeService()
    svc.song_related_results[101] = (
        [Song(mid="m2", id=102, name="X")],
        [Playlist(pid="p", name="P")],
    )
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)

    # 先打开一次
    await ctrl.open_async(_song_map(mid="m1", song_id=101))
    assert svc.song_related_calls == [101]

    # 然后 retry → 应再次拉同一首歌
    await ctrl.retry()
    assert svc.song_related_calls == [101, 101]


async def test_retry_does_nothing_without_current_song():
    """没 open 过就 retry 不应崩, 也不应发请求."""
    svc = _FakeService()
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)
    await ctrl.retry()
    assert svc.song_related_calls == []


async def test_error_state_keeps_models_empty_for_retry_visibility():
    """错误态下 (网络挂掉) model 是空的, dialog 该显示错误而不是空 sections."""
    svc = _FakeService()
    svc.song_related_exc = RuntimeError("boom")
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)
    await ctrl.open_async(_song_map())

    assert ctrl.loading is False
    assert ctrl.errorMessage != ""
    assert ctrl.similarSongsModel.count == 0
    assert ctrl.relatedPlaylistsModel.count == 0


async def test_open_again_supersedes_in_flight_request():
    """第二次 open 在第一次还没回来时, 应只采纳第二次结果."""
    svc = _FakeService()
    svc.gate = asyncio.Event()
    svc.song_related_results[101] = (
        [Song(mid="old", id=1, name="old-similar")],
        [Playlist(pid="old", name="old-playlist")],
    )
    svc.song_related_results[202] = (
        [Song(mid="new", id=2, name="new-similar")],
        [Playlist(pid="new", name="new-playlist")],
    )
    sc = ServiceController(service=svc)  # type: ignore[arg-type]
    ctrl = SongDetailController(sc)

    # 启动第一次 (gate 卡住)
    first = asyncio.create_task(ctrl.open_async(_song_map(mid="m1", song_id=101)))
    await asyncio.sleep(0)  # 让 first 进 gate.wait
    # 再启动第二次 (覆盖)
    second = asyncio.create_task(ctrl.open_async(_song_map(mid="m2", song_id=202)))
    await asyncio.sleep(0)
    # 放行两个调用
    svc.gate.set()
    await asyncio.gather(first, second)

    assert svc.song_related_calls == [101, 202]
    # 最终 model 应是第二次的结果
    assert ctrl.similarSongsModel.count == 1
    assert ctrl.similarSongsModel.songs()[0].mid == "new"
    assert ctrl.relatedPlaylistsModel.cardAt(0)["title"] == "new-playlist"
    assert ctrl.currentSong["mid"] == "m2"
