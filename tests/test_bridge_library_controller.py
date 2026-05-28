"""LibraryController tests."""

from __future__ import annotations

from quaverq.bridge.library_controller import LibraryController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Singer, Song


class _FakeLibraryService:
    def __init__(self) -> None:
        self.connected = False
        self.is_authenticated = True
        self.liked_songs = [
            Song(
                mid="m1",
                id=101,
                name="晴天",
                singers=[Singer(mid="s1", name="周杰伦")],
                album_name="叶惠美",
                duration=269,
            )
        ]
        self.like_calls: list[Song] = []
        self.unlike_calls: list[Song] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_liked_songs(self, *, limit: int = 500) -> list[Song]:
        return self.liked_songs[:limit]

    async def like_song(self, song: Song) -> bool:
        self.like_calls.append(song)
        self.liked_songs.insert(0, song)
        return True

    async def unlike_song(self, song: Song) -> bool:
        self.unlike_calls.append(song)
        self.liked_songs = [item for item in self.liked_songs if item.mid != song.mid]
        return True


def _song(mid: str, name: str = "七里香") -> dict[str, object]:
    return {
        "mid": mid,
        "id": 202,
        "name": name,
        "singers": [{"mid": "s1", "name": "周杰伦"}],
        "albumName": "七里香",
        "duration": 299,
    }


async def test_refresh_liked_async_populates_model_and_lookup():
    service = _FakeLibraryService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)

    await controller.refresh_liked_async()

    assert service.connected is True
    assert controller.likedCount == 1
    assert controller.likedModel.count == 1
    assert controller.likedModel.songAt(0)["name"] == "晴天"
    assert controller.isLiked("m1") is True
    assert controller.isLiked("missing") is False


async def test_toggle_like_async_adds_song_and_emits_state():
    service = _FakeLibraryService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)
    states: list[tuple[str, bool]] = []
    controller.likedChanged.connect(lambda mid, liked: states.append((mid, liked)))

    await controller.refresh_liked_async()
    await controller.toggle_like_async(_song("m2"))

    assert [song.mid for song in service.like_calls] == ["m2"]
    assert controller.isLiked("m2") is True
    assert controller.likedCount == 2
    assert controller.likedModel.songAt(0)["mid"] == "m2"
    assert states[-1] == ("m2", True)


async def test_toggle_like_async_removes_existing_song():
    service = _FakeLibraryService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)

    await controller.refresh_liked_async()
    await controller.toggle_like_async(_song("m1", "晴天"))

    assert [song.mid for song in service.unlike_calls] == ["m1"]
    assert controller.isLiked("m1") is False
    assert controller.likedCount == 0
    assert controller.likedModel.count == 0


async def test_toggle_like_async_requires_login():
    service = _FakeLibraryService()
    service.is_authenticated = False
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.toggle_like_async(_song("m2"))

    assert service.like_calls == []
    assert controller.errorMessage == "登录后才能同步喜欢"
    assert errors == ["登录后才能同步喜欢"]
