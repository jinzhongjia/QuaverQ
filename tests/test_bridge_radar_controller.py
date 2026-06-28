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
from types import SimpleNamespace

from quaverq.bridge.player_controller import PlayerController
from quaverq.bridge.radar_controller import RadarController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Singer, Song, SongUrl


def _song(mid: str, name: str = "") -> Song:
    return Song(mid=mid, name=name or mid, singers=[Singer(mid="s", name="x")], duration=60)


class _FakeRadarService:
    """最底层 service mock: 按调用顺序吐 (songs, has_more) 页, 记录 page 入参."""

    def __init__(self, pages: list[tuple[list[Song], bool]], *, musicid: str = "111") -> None:
        self.connected = False
        self.is_authenticated = True
        self.musicid = musicid  # 改它即模拟切换账号 (ServiceController.account_key 据此哈希)
        self._pages = list(pages)
        self.calls: list[int] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    def _effective_credential(self):
        if not self.is_authenticated:
            return None
        return SimpleNamespace(musicid=self.musicid)

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


class _GatedRadarService(_FakeRadarService):
    """可阻塞指定页的请求, 用于构造并发 / 迟到响应竞态."""

    def __init__(self, pages: list[tuple[list[Song], bool]], *, gate_page: int) -> None:
        super().__init__(pages)
        self._gate_page = gate_page
        self.gate = asyncio.Event()

    async def get_radar_recommend(self, *, page: int = 1) -> tuple[list[Song], bool]:
        self.calls.append(page)
        if page == self._gate_page:
            await self.gate.wait()
        if not self._pages:
            return [], False
        return self._pages.pop(0)


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


async def test_concurrent_next_page_and_extend_share_one_request():
    """滚动加载下一页与队列耗尽续接并发: 应合并成一次请求, 两者拿到同一批结果.

    回归 (PR #35 review): 旧实现里 extend 撞上 _loading=True 会拿到空列表 ->
    队列不续接 -> 自动续播静默失败.
    """
    service = _GatedRadarService(
        [([_song("a1"), _song("a2")], True), ([_song("b1"), _song("b2")], True)],
        gate_page=2,
    )
    _, player, radar = _wire(service)
    await radar.refresh_async()
    await player.play_from_model_async(radar.radarModel, 0, source="radar")

    t_scroll = asyncio.create_task(radar.load_next_page_async())
    await asyncio.sleep(0)  # 让滚动加载进入 page 2 的 gate 等待
    t_extend = asyncio.create_task(radar._extend_async())  # noqa: SLF001
    await asyncio.sleep(0)  # 让 extend 进入 await(合并到滚动任务)
    service.gate.set()

    fresh_scroll = await t_scroll
    added_extend = await t_extend

    assert [s.mid for s in fresh_scroll] == ["b1", "b2"]
    assert [s.mid for s in added_extend] == ["b1", "b2"]
    assert service.calls.count(2) == 1  # 合并: page 2 只请求一次
    assert player.queueModel.count == 4  # 队列被续接, 不再静默失败


async def test_late_response_after_logout_is_discarded():
    """refresh 在途时用户登出: 迟到的响应不得污染已清空的 model (竞态保护).

    回归 (PR #35 review).
    """
    service = _GatedRadarService([([_song("a1"), _song("a2")], True)], gate_page=1)
    _, _, radar = _wire(service)

    t = asyncio.create_task(radar.refresh_async())
    await asyncio.sleep(0)  # refresh 进入 page 1 的 gate 等待
    service.is_authenticated = False
    radar._handle_auth_state_changed()  # noqa: SLF001 -> 登出, 清空 model
    service.gate.set()
    await t  # 迟到响应返回

    assert radar.radarModel.count == 0  # 被丢弃, 未 repopulate
    assert radar.radarRequiresLogin is True


async def test_late_response_after_account_switch_is_discarded():
    """账号 A 的 refresh 在途时切到账号 B (authed->authed): A 的结果不得填进 B 的 model.

    回归 (PR #35 review 边角): 仅靠 authed 重查挡不住换号, 需 account_key 代际校验.
    """
    service = _GatedRadarService([([_song("a1"), _song("a2")], True)], gate_page=1)
    service.musicid = "AAA"
    _, _, radar = _wire(service)

    t = asyncio.create_task(radar.refresh_async())
    await asyncio.sleep(0)  # 账号 A 的 refresh 进入 gate
    service.musicid = "BBB"  # 切到账号 B, 仍登录
    service.gate.set()
    await t  # A 的迟到响应返回

    assert radar.radarModel.count == 0  # account_key 不匹配 -> 丢弃, 不污染 B


async def test_account_switch_via_auth_handler_resets_and_reloads():
    """切号事件 (authStateChanged, authed->authed): 立即清旧账号流并自动重载新账号."""
    service = _FakeRadarService(
        [([_song("a1")], True), ([_song("b1"), _song("b2")], True)], musicid="AAA"
    )
    _, _, radar = _wire(service)
    await radar.refresh_async()  # 账号 A: [a1]
    assert radar.radarModel.count == 1

    service.musicid = "BBB"  # 切账号
    radar._handle_auth_state_changed()  # noqa: SLF001 -> 同步清旧流 + 调度新 refresh
    assert radar.radarModel.count == 0  # A 的内容立即清掉

    for _ in range(5):
        await asyncio.sleep(0)
        if radar._refresh_task and radar._refresh_task.done():  # noqa: SLF001
            break
    if radar._refresh_task is not None:  # noqa: SLF001
        await radar._refresh_task  # noqa: SLF001

    mids = [radar.radarModel.songAt(i)["mid"] for i in range(radar.radarModel.count)]
    assert mids == ["b1", "b2"]  # 自动加载了账号 B 的推荐
