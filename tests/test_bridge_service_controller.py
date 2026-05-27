"""ServiceController tests."""

from __future__ import annotations

from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Singer, Song


class _FakeService:
    def __init__(self) -> None:
        self.connected = False
        self.search_calls: list[tuple[str, int]] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def search_songs(self, keyword: str, *, limit: int = 30) -> list[Song]:
        self.search_calls.append((keyword, limit))
        return [
            Song(
                mid="m1",
                name="晴天",
                singers=[Singer(mid="s1", name="周杰伦")],
                album_name="叶惠美",
                duration=269,
            )
        ]


async def test_search_async_starts_service_and_populates_model():
    service = _FakeService()
    controller = ServiceController(service=service)

    await controller.search_async(" 周杰伦 ")

    assert service.connected is True
    assert service.search_calls == [("周杰伦", 30)]
    assert controller.loading is False
    assert controller.errorMessage == ""
    assert controller.songResults.count == 1
    assert controller.songResults.songAt(0)["name"] == "晴天"


async def test_search_async_empty_keyword_clears_results_without_network():
    service = _FakeService()
    controller = ServiceController(service=service)

    await controller.search_async("")

    assert service.connected is False
    assert service.search_calls == []
    assert controller.songResults.count == 0
