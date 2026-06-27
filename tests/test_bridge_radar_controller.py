"""RadarController tests.

雷达推荐 controller 契约 (设计见 docs/plan/search-radar-recommend.md):
- 单例; 登录门槛 (未登录 -> radarRequiresLogin, 不打网络)
- 分页流: refresh 拉首页, loadNextPage 拉下一页, 跨页 mid 去重, has_more 跟随
- 不缓存 (无 persist / 无 TTL)
- 队列耗尽且 source=="radar" -> 自动续接下一页到队列 + model; 其他 source 不动
- 走真 ServiceController + PlayerController, 只 fake 最底层 service (同 home_controller 测试)
"""

from __future__ import annotations

import asyncio

from quaverq.bridge.player_controller import PlayerController
from quaverq.bridge.radar_controller import RadarController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Singer, Song, SongUrl


def _song(mid: str, name: str = "") -> Song:
    return Song(mid=mid, name=name or mid, singers=[Singer(mid="s", name="x")], duration=60)


class _FakeRadarService:
    """最底层 service mock: 按调用顺序吐 (songs, has_more) 页, 记录 page 入参."""

    def __init__(self, pages: list[tuple[list[Song], bool]]) -> None:
        self.connected = False
        self.is_authenticated = True
        self._pages = list(pages)
        self.calls: list[int] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_radar_recommend(self, *, page: int = 1) -> tuple[list[Song], bool]:
        self.calls.append(page)
        if not self._pages:
            return [], False
        return self._pages.pop(0)

    async def get_song_url(self, song: Song, *, quality_preference: str) -> SongUrl:
        return SongUrl(mid=song.mid, url=f"https://audio.example/{song.mid}.mp3")


class _BoomRadarService(_FakeRadarService):
    async def get_radar_recommend(self, *, page: int = 1) -> tuple[list[Song], bool]:
        raise RuntimeError("radar boom")


def _wire(
    service: _FakeRadarService,
) -> tuple[ServiceController, PlayerController, RadarController]:
    sc = ServiceController(service=service)  # type: ignore[arg-type]
    player = PlayerController(sc)
    radar = RadarController(sc, player_controller=player)
    return sc, player, radar


async def test_refresh_requires_login_when_not_authed():
    service = _FakeRadarService([([_song("a1")], True)])
    service.is_authenticated = False
    _, _, radar = _wire(service)

    await radar.refresh_async()

    assert radar.radarRequiresLogin is True
    assert radar.radarModel.count == 0
    assert service.calls == []  # 未登录不打网络


async def test_refresh_populates_and_tracks_has_more():
    service = _FakeRadarService([([_song("a1"), _song("a2"), _song("a3")], True)])
    _, _, radar = _wire(service)

    await radar.refresh_async()

    assert radar.radarRequiresLogin is False
    assert radar.radarModel.count == 3
    assert radar.hasMore is True
    assert service.calls == [1]


async def test_load_next_page_appends_and_dedups():
    service = _FakeRadarService(
        [
            ([_song("a1"), _song("a2")], True),
            ([_song("a2"), _song("b1"), _song("b2")], True),  # a2 跨页重复 -> 去重
        ]
    )
    _, _, radar = _wire(service)

    await radar.refresh_async()
    await radar.load_next_page_async()

    mids = [radar.radarModel.songAt(i)["mid"] for i in range(radar.radarModel.count)]
    assert mids == ["a1", "a2", "b1", "b2"]
    assert service.calls == [1, 2]


async def test_load_next_page_noop_when_no_more():
    service = _FakeRadarService([([_song("a1")], False)])
    _, _, radar = _wire(service)

    await radar.refresh_async()
    assert radar.hasMore is False

    await radar.load_next_page_async()
    assert service.calls == [1]  # 没有下一页, 不再请求
    assert radar.radarModel.count == 1


async def test_error_emits_signal_and_keeps_empty():
    service = _BoomRadarService([])
    _, _, radar = _wire(service)
    errors: list[str] = []
    radar.errorRaised.connect(errors.append)

    await radar.refresh_async()

    assert errors  # 至少一条错误
    assert radar.radarModel.count == 0


async def test_queue_exhausted_radar_extends_and_resumes():
    service = _FakeRadarService(
        [
            ([_song("a1"), _song("a2")], True),
            ([_song("b1"), _song("b2")], True),
        ]
    )
    _, player, radar = _wire(service)

    await radar.refresh_async()
    await player.play_from_model_async(radar.radarModel, 0, source="radar")
    await player.handleEndOfMedia()  # -> a2
    await player.handleEndOfMedia()  # a2 done -> exhausted -> queueExhausted("radar")

    for _ in range(5):
        await asyncio.sleep(0)
        if radar._extend_task and radar._extend_task.done():  # noqa: SLF001
            break
    if radar._extend_task is not None:  # noqa: SLF001
        await radar._extend_task  # noqa: SLF001

    mids = [radar.radarModel.songAt(i)["mid"] for i in range(radar.radarModel.count)]
    assert mids == ["a1", "a2", "b1", "b2"]
    assert player.queueModel.count == 4
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert player.currentSong["mid"] == "b1"


async def test_queue_exhausted_ignores_non_radar_source():
    service = _FakeRadarService([([_song("a1")], True)])
    _, _, radar = _wire(service)
    await radar.refresh_async()

    radar._handle_queue_exhausted("daily")  # noqa: SLF001
    assert radar._extend_task is None  # noqa: SLF001


async def test_logout_clears_stream():
    service = _FakeRadarService([([_song("a1"), _song("a2")], True)])
    sc, _, radar = _wire(service)
    await radar.refresh_async()
    assert radar.radarModel.count == 2

    service.is_authenticated = False
    radar._handle_auth_state_changed()  # noqa: SLF001

    assert radar.radarRequiresLogin is True
    assert radar.radarModel.count == 0
    assert radar.hasMore is False
