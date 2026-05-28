"""HomeController tests."""

from __future__ import annotations

from quaverq.bridge.home_controller import HomeController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Playlist, Singer, Song, TopList


class _FakeHomeService:
    def __init__(self) -> None:
        self.connected = False
        self.is_authenticated = True
        self.daily_calls = 0

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_daily_recommend_songs(self, *, limit: int = 30) -> list[Song]:
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
        return [
            Playlist(pid="p1", name="今日推荐", creator="QuaverQ", song_count=30)
        ][:limit]

    async def get_recommend_new_songs(self, *, limit: int = 12) -> list[Song]:
        return [
            Song(mid="n1", name="新歌", singers=[Singer(mid="s1", name="周杰伦")])
        ][:limit]

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
    assert controller.dailyModel.count == 30
    assert controller.dailyPreviewSong["name"] == "每日0"
    assert controller.playlistModel.cardAt(0)["title"] == "今日推荐"
    assert controller.newSongModel.songAt(0)["name"] == "新歌"
    assert controller.topModel.cardAt(0)["kind"] == "top"


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
