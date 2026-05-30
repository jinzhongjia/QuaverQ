"""LibraryController tests."""

from __future__ import annotations

import logging

from quaverq.bridge.library_controller import LibraryController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Album, Playlist, Singer, Song
from quaverq.core.service import CredentialExpiredError


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
        self.playlists = [Playlist(pid="p1", name="我的歌单", song_count=12)]
        self.albums = [
            Album(
                mid="a1",
                name="叶惠美",
                singers=[Singer(mid="s1", name="周杰伦")],
                song_count=11,
            )
        ]
        self.singers = [Singer(mid="ar1", name="周杰伦")]

    async def set_credential(self, credential) -> None:
        self.is_authenticated = credential is not None

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

    async def get_my_playlists(self) -> list[Playlist]:
        return self.playlists

    async def get_fav_albums(self) -> list[Album]:
        return self.albums

    async def get_followed_singers(self) -> list[Singer]:
        return self.singers


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


async def test_refresh_liked_async_logs_network_failure_without_traceback(caplog):
    service = _FakeLibraryService()

    async def fail_liked_songs(*, limit: int = 500) -> list[Song]:
        raise ConnectionError(
            "Failed to resolve 'u.y.qq.com' (Name or service not known)"
        )

    service.get_liked_songs = fail_liked_songs  # type: ignore[method-assign]
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    with caplog.at_level(logging.WARNING, logger="quaverq.bridge.library_controller"):
        await controller.refresh_liked_async()

    expected = "网络连接失败：无法解析 QQ 音乐服务域名，请检查 DNS 或网络连接"
    assert controller.errorMessage == expected
    assert errors == [expected]
    assert all(record.exc_info is None for record in caplog.records)


async def test_refresh_liked_async_expires_auth_state():
    service = _FakeLibraryService()

    async def fail_liked_songs(*, limit: int = 500) -> list[Song]:
        raise CredentialExpiredError("credential expired")

    service.get_liked_songs = fail_liked_songs  # type: ignore[method-assign]
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)
    expired_messages: list[str] = []
    service_controller.credentialExpired.connect(expired_messages.append)

    await controller.refresh_liked_async()

    assert service_controller.authed is False
    assert controller.authed is False
    assert controller.likedModel.count == 0
    assert expired_messages == ["登录已过期，请重新扫码"]


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


async def test_refresh_my_playlists_populates_card_model():
    service = _FakeLibraryService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)

    await controller.refresh_my_playlists_async()

    assert controller.playlistModel.count == 1
    assert controller.playlistModel.cardAt(0)["kind"] == "playlist"
    assert controller.playlistModel.cardAt(0)["title"] == "我的歌单"


async def test_refresh_fav_albums_populates_card_model():
    service = _FakeLibraryService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)

    await controller.refresh_fav_albums_async()

    assert controller.albumModel.count == 1
    assert controller.albumModel.cardAt(0)["kind"] == "album"
    assert controller.albumModel.cardAt(0)["subtitle"] == "周杰伦"


async def test_refresh_followed_singers_populates_card_model():
    service = _FakeLibraryService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)

    await controller.refresh_followed_singers_async()

    assert controller.artistModel.count == 1
    assert controller.artistModel.cardAt(0)["kind"] == "artist"
    assert controller.artistModel.cardAt(0)["title"] == "周杰伦"


async def test_library_card_models_clear_when_logged_out():
    service = _FakeLibraryService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = LibraryController(service_controller)

    await controller.refresh_my_playlists_async()
    await controller.refresh_fav_albums_async()
    await controller.refresh_followed_singers_async()
    service.is_authenticated = False
    service_controller.authStateChanged.emit()

    assert controller.playlistModel.count == 0
    assert controller.albumModel.count == 0
    assert controller.artistModel.count == 0
