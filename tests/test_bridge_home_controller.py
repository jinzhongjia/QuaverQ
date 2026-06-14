"""HomeController tests."""

from __future__ import annotations

import asyncio

from quaverq.bridge.home_controller import HomeController
from quaverq.bridge.player_controller import PlayerController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Playlist, Singer, Song, SongUrl, TopList


class _FakeHomeService:
    def __init__(self) -> None:
        self.connected = False
        self.is_authenticated = True
        self.daily_calls = 0

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_daily_recommend_songs(self, *, limit: int = 5) -> list[Song]:
        self.daily_calls += 1
        return [
            Song(
                mid=f"d{i}",
                name=f"每日{i}",
                singers=[Singer(mid="s1", name="周杰伦")],
                duration=200,
            )
            for i in range(limit)
        ]

    async def get_recommend_playlists(self, *, limit: int = 8) -> list[Playlist]:
        return [Playlist(pid="p1", name="今日推荐", creator="QuaverQ", song_count=30)][:limit]

    async def get_recommend_new_songs(self, *, limit: int = 12) -> list[Song]:
        return [Song(mid="n1", name="新歌", singers=[Singer(mid="s1", name="周杰伦")])][:limit]

    async def get_top_categories(
        self,
        *,
        limit_per_group: int | None = None,
    ) -> list[TopList]:
        return [TopList(top_id=4, name="流行指数榜", total_num=100)]


async def test_refresh_home_populates_discovery_models():
    service = _FakeHomeService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = HomeController(service_controller)

    await controller.refresh_home_async()

    assert service.connected is True
    assert service.daily_calls == 1
    assert controller.dailyRequiresLogin is False
    assert controller.dailyModel.count == 5
    assert controller.dailyPreviewSong["name"] == "每日0"
    assert controller.playlistModel.cardAt(0)["title"] == "今日推荐"
    assert controller.newSongModel.songAt(0)["name"] == "新歌"
    assert controller.topModel.cardAt(0)["kind"] == "top"


class _FakeHomeServiceWithExtend(_FakeHomeService):
    def __init__(self, batches: list[list[Song]]) -> None:
        super().__init__()
        self._batches = list(batches)

    async def get_daily_recommend_songs(self, *, limit: int = 5) -> list[Song]:
        self.daily_calls += 1
        if not self._batches:
            return []
        return self._batches.pop(0)

    async def get_song_url(self, song: Song, *, quality_preference: str) -> SongUrl:
        return SongUrl(mid=song.mid, url=f"https://audio.example/{song.mid}.mp3")


async def test_daily_preview_tracks_currently_playing_song_in_daily_queue():
    """播放 daily 队列时, dailyPreviewSong 跟随 currentSong 变化, 不再固定为第一首."""
    songs = [
        Song(mid=f"d{i}", name=f"每日{i}", singers=[Singer(mid="s1", name="周")], duration=120)
        for i in range(3)
    ]
    service = _FakeHomeServiceWithExtend([songs])
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player = PlayerController(service_controller)
    home = HomeController(service_controller, player_controller=player)
    await home.refresh_home_async()

    assert home.dailyPreviewSong["mid"] == "d0"  # 未播放 -> 第一首

    await player.play_from_model_async(home.dailyModel, 0, source="daily")
    assert home.dailyPreviewSong["mid"] == "d0"

    await player.next()
    assert home.dailyPreviewSong["mid"] == "d1"

    await player.next()
    assert home.dailyPreviewSong["mid"] == "d2"


async def test_daily_preview_reverts_to_first_when_playing_unrelated_queue():
    """切到非 daily 队列后, 卡片回到 dailyModel 首曲, 不再跟随播放."""
    daily = [
        Song(mid=f"d{i}", name=f"每日{i}", singers=[Singer(mid="s1", name="周")], duration=120)
        for i in range(2)
    ]
    service = _FakeHomeServiceWithExtend([daily])
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player = PlayerController(service_controller)
    home = HomeController(service_controller, player_controller=player)
    await home.refresh_home_async()

    other = [Song(mid="x1", name="别的歌", duration=120)]
    await player.play_songs_async(other, 0)  # source=""

    assert home.dailyPreviewSong["mid"] == "d0"


async def test_queue_exhausted_triggers_daily_extend_and_resumes_playback():
    """猜你喜欢 30 首播完 -> 续取下一批 -> 追加到 player 队列 + dailyModel, 自动续播."""
    batch1 = [
        Song(mid="a1", name="第一批1", singers=[Singer(mid="s", name="x")], duration=60),
        Song(mid="a2", name="第一批2", singers=[Singer(mid="s", name="x")], duration=60),
    ]
    batch2 = [
        Song(mid="b1", name="第二批1", singers=[Singer(mid="s", name="x")], duration=60),
        Song(mid="a2", name="重复", singers=[Singer(mid="s", name="x")], duration=60),  # 去重
        Song(mid="b2", name="第二批2", singers=[Singer(mid="s", name="x")], duration=60),
    ]
    service = _FakeHomeServiceWithExtend([batch1, batch2])
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player = PlayerController(service_controller)
    home = HomeController(service_controller, player_controller=player)
    await home.refresh_home_async()

    await player.play_from_model_async(home.dailyModel, 0, source="daily")
    await player.handleEndOfMedia()  # to a2
    await player.handleEndOfMedia()  # a2 done -> exhausted -> emits queueExhausted("daily")

    # 让 extend 协程完成
    for _ in range(5):
        await asyncio.sleep(0)
        if home._daily_extend_task and home._daily_extend_task.done():  # noqa: SLF001
            break
    if home._daily_extend_task is not None:  # noqa: SLF001
        await home._daily_extend_task  # noqa: SLF001

    # dailyModel 已合并 (去重 a2)
    assert home.dailyModel.count == 4
    daily_mids = [home.dailyModel.songAt(i)["mid"] for i in range(home.dailyModel.count)]
    assert daily_mids == ["a1", "a2", "b1", "b2"]
    # player 队列也增长
    assert player.queueModel.count == 4
    # 自动续播第一首新加曲
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert player.currentSong["mid"] == "b1"


async def test_daily_recommend_requires_login_but_public_sections_load():
    service = _FakeHomeService()
    service.is_authenticated = False
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = HomeController(service_controller)

    await controller.refresh_home_async()

    assert service.daily_calls == 0
    assert controller.dailyRequiresLogin is True
    assert controller.dailyModel.count == 0
    assert controller.dailyPreviewSong == {}
    assert controller.playlistModel.count == 1
    assert controller.newSongModel.count == 1
    assert controller.topModel.count == 1
