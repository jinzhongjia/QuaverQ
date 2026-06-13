"""ServiceController tests."""

from __future__ import annotations

import asyncio
import logging

import pytest

from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Album, Lyric, LyricLine, Playlist, Singer, Song, UserProfile
from quaverq.core.service import CredentialExpiredError


class _FakeService:
    def __init__(self) -> None:
        self.connected = False
        self.connect_count = 0
        self.search_calls: list[tuple[str, int, int]] = []
        self.search_pages: dict[int, list[Song]] = {
            1: [
                Song(
                    mid=f"m{i}",
                    name=f"第{i}首",
                    singers=[Singer(mid="s1", name="周杰伦")],
                    album_name="叶惠美",
                    duration=269,
                )
                for i in range(30)
            ],
            2: [
                Song(
                    mid="m31",
                    name="第31首",
                    singers=[Singer(mid="s1", name="周杰伦")],
                    album_name="叶惠美",
                    duration=269,
                )
            ],
        }

    async def connect(self) -> None:
        self.connect_count += 1
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def search_songs(
        self,
        keyword: str,
        *,
        page: int = 1,
        limit: int = 30,
    ) -> list[Song]:
        self.search_calls.append((keyword, page, limit))
        return self.search_pages.get(page, [])

    async def search_singers(self, keyword: str, *, page: int = 1, limit: int = 30) -> list[Singer]:
        return [Singer(mid="ar1", name="周杰伦", avatar_url="http://a.jpg")]

    async def search_albums(self, keyword: str, *, page: int = 1, limit: int = 30) -> list[Album]:
        return [
            Album(
                mid="al1",
                name="叶惠美",
                singers=[Singer(mid="s1", name="周杰伦")],
                song_count=10,
            )
        ]

    async def search_playlists(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Playlist]:
        return [Playlist(pid="pl1", name="华语精选", creator="DJ", song_count=50)]


class _FakeAuthService(_FakeService):
    def __init__(self) -> None:
        super().__init__()
        self.credential = None
        self.is_authenticated = False
        self.on_qrcode = None
        self.on_login_status = None
        self.saved = False
        self.login_result = True
        self.credential_path = ""
        self.expired_probe: bool | None = False

    async def _get_cached_credential(self):
        return self.credential

    async def set_credential(self, credential) -> None:
        self.credential = credential
        self.is_authenticated = credential is not None

    def set_credential_sync(self, credential) -> None:
        self.credential = credential
        self.is_authenticated = credential is not None

    def load_cached_credential_sync(self):
        return self.credential

    async def probe_login_expired(self) -> bool | None:
        return self.expired_probe

    async def get_song_url(self, song: Song, *, quality_preference: str):
        return None

    async def login_by_qrcode(self, login_type=None) -> bool:
        if self.on_qrcode is not None:
            self.on_qrcode(b"qr", "qq", "image/png")
        if self.on_login_status is not None:
            self.on_login_status("waiting")
        if self.login_result:
            await self.set_credential(object())
            if self.on_login_status is not None:
                self.on_login_status("done")
        return self.login_result

    async def save_credential(self) -> None:
        self.saved = True

    @property
    def _credential_cache_path(self) -> str:
        return self.credential_path


async def test_search_async_starts_service_and_populates_model():
    service = _FakeService()
    controller = ServiceController(service=service)

    await controller.search_async(" 周杰伦 ")

    assert service.connected is True
    assert service.search_calls == [("周杰伦", 1, 30)]
    assert controller.loading is False
    assert controller.errorMessage == ""
    assert controller.currentPage == 1
    assert controller.hasNextPage is True
    assert controller.songResults.count == 30
    assert controller.songResults.songAt(0)["name"] == "第0首"


async def test_search_async_empty_keyword_clears_results_without_network():
    service = _FakeService()
    controller = ServiceController(service=service)

    await controller.search_async("")

    assert service.connected is False
    assert service.search_calls == []
    assert controller.songResults.count == 0
    assert controller.currentPage == 0
    assert controller.hasNextPage is False


async def test_search_async_cancels_in_flight_request_when_keyword_changes():
    class _SlowSearchService(_FakeService):
        def __init__(self) -> None:
            super().__init__()
            self.started: dict[str, asyncio.Event] = {}
            self.released: dict[str, asyncio.Event] = {}
            self.cancelled: list[str] = []
            self.cancelled_event = asyncio.Event()

        async def search_songs(
            self,
            keyword: str,
            *,
            page: int = 1,
            limit: int = 30,
        ) -> list[Song]:
            self.search_calls.append((keyword, page, limit))
            self.started.setdefault(keyword, asyncio.Event()).set()
            try:
                await self.released.setdefault(keyword, asyncio.Event()).wait()
            except asyncio.CancelledError:
                self.cancelled.append(keyword)
                self.cancelled_event.set()
                raise
            return [Song(mid=keyword, name=keyword)]

    service = _SlowSearchService()
    controller = ServiceController(service=service)

    old_started = service.started.setdefault("old", asyncio.Event())
    old_released = service.released.setdefault("old", asyncio.Event())
    new_started = service.started.setdefault("new", asyncio.Event())
    new_released = service.released.setdefault("new", asyncio.Event())

    first = asyncio.create_task(controller.search_async("old"))
    await old_started.wait()
    second = asyncio.create_task(controller.search_async("new"))
    await new_started.wait()

    try:
        await asyncio.wait_for(service.cancelled_event.wait(), timeout=1)
        new_released.set()
        await asyncio.wait_for(second, timeout=1)
        await asyncio.wait_for(first, timeout=1)
    finally:
        old_released.set()
        new_released.set()
        for task in (first, second):
            if not task.done():
                task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)

    assert service.cancelled == ["old"]
    assert controller.songResults.count == 1
    assert controller.songResults.songAt(0)["name"] == "new"
    assert controller.loading is False


async def test_search_async_ignores_stale_result_when_cancel_is_swallowed():
    class _CancellationIgnoringSearchService(_FakeService):
        def __init__(self) -> None:
            super().__init__()
            self.started: dict[str, asyncio.Event] = {}
            self.released: dict[str, asyncio.Event] = {}
            self.cancel_seen = asyncio.Event()

        async def search_songs(
            self,
            keyword: str,
            *,
            page: int = 1,
            limit: int = 30,
        ) -> list[Song]:
            self.search_calls.append((keyword, page, limit))
            self.started.setdefault(keyword, asyncio.Event()).set()
            try:
                await self.released.setdefault(keyword, asyncio.Event()).wait()
            except asyncio.CancelledError:
                self.cancel_seen.set()
                await self.released[keyword].wait()
            return [Song(mid=keyword, name=keyword)]

    service = _CancellationIgnoringSearchService()
    controller = ServiceController(service=service)

    old_started = service.started.setdefault("old", asyncio.Event())
    old_released = service.released.setdefault("old", asyncio.Event())
    new_started = service.started.setdefault("new", asyncio.Event())
    new_released = service.released.setdefault("new", asyncio.Event())

    first = asyncio.create_task(controller.search_async("old"))
    await old_started.wait()
    second = asyncio.create_task(controller.search_async("new"))
    await new_started.wait()
    try:
        await asyncio.wait_for(service.cancel_seen.wait(), timeout=1)

        new_released.set()
        await asyncio.wait_for(second, timeout=1)
        assert controller.songResults.songAt(0)["name"] == "new"

        old_released.set()
        await asyncio.wait_for(first, timeout=1)
    finally:
        old_released.set()
        new_released.set()
        for task in (first, second):
            if not task.done():
                task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)

    assert controller.songResults.count == 1
    assert controller.songResults.songAt(0)["name"] == "new"


async def test_next_page_replaces_results_and_updates_pagination():
    service = _FakeService()
    controller = ServiceController(service=service)

    await controller.search_async("周杰伦")
    await controller.next_page_async()

    assert service.search_calls == [("周杰伦", 1, 30), ("周杰伦", 2, 30)]
    assert controller.currentPage == 2
    assert controller.songResults.count == 1
    assert controller.songResults.songAt(0)["name"] == "第31首"
    assert controller.hasNextPage is False


async def test_next_page_empty_keeps_current_page_and_disables_next():
    service = _FakeService()
    service.search_pages = {1: service.search_pages[1], 2: []}
    controller = ServiceController(service=service)

    await controller.search_async("周杰伦")
    await controller.next_page_async()

    assert service.search_calls == [("周杰伦", 1, 30), ("周杰伦", 2, 30)]
    assert controller.currentPage == 1
    assert controller.songResults.count == 30
    assert controller.hasNextPage is False


async def test_previous_page_replaces_results_with_previous_page():
    service = _FakeService()
    controller = ServiceController(service=service)

    await controller.search_async("周杰伦")
    await controller.next_page_async()
    await controller.previous_page_async()

    assert service.search_calls == [
        ("周杰伦", 1, 30),
        ("周杰伦", 2, 30),
        ("周杰伦", 1, 30),
    ]
    assert controller.currentPage == 1
    assert controller.songResults.count == 30
    assert controller.songResults.songAt(0)["name"] == "第0首"
    assert controller.hasNextPage is True


async def test_next_page_ignores_when_no_next_page():
    service = _FakeService()
    service.search_pages = {1: [Song(mid="m1", name="晴天")]}
    controller = ServiceController(service=service)

    await controller.search_async("周杰伦")
    await controller.next_page_async()

    assert service.search_calls == [("周杰伦", 1, 30)]
    assert controller.currentPage == 1
    assert controller.songResults.count == 1
    assert controller.hasNextPage is False


async def test_start_loads_cached_credential_when_available():
    service = _FakeAuthService()
    service.credential = object()
    controller = ServiceController(service=service)

    await controller.start()

    assert service.connected is True
    assert service.is_authenticated is True


async def test_start_logs_elapsed(caplog):
    service = _FakeAuthService()
    controller = ServiceController(service=service)

    with caplog.at_level(logging.INFO, logger="quaverq.bridge.service_controller"):
        await controller.start()

    messages = [record.getMessage() for record in caplog.records]
    assert any(message.startswith("perf service.start elapsed_ms=") for message in messages)


async def test_start_rejects_expired_cached_credential(tmp_path):
    service = _FakeAuthService()
    service.credential = object()
    service.is_authenticated = True
    service.expired_probe = True
    credential_file = tmp_path / "credential.json"
    credential_file.write_text("{}", encoding="utf-8")
    service.credential_path = str(credential_file)
    controller = ServiceController(service=service)
    expired_messages: list[str] = []
    controller.credentialExpired.connect(expired_messages.append)

    await controller.start()

    assert service.connected is True
    assert service.is_authenticated is False
    assert not credential_file.exists()
    assert expired_messages == ["登录已过期，请重新扫码"]


async def test_start_keeps_cached_credential_when_probe_unavailable():
    service = _FakeAuthService()
    service.credential = object()
    service.expired_probe = None
    controller = ServiceController(service=service)

    await controller.start()

    assert service.connected is True
    assert service.is_authenticated is True


def test_prime_credential_sync_loads_without_network():
    # 乐观登录: 同步读盘加载凭据, authed 立即生效, 不 connect / 不联网
    service = _FakeAuthService()
    service.credential = object()
    controller = ServiceController(service=service)

    loaded = controller.prime_credential_sync()

    assert loaded is True
    assert controller.authed is True
    assert service.connected is False  # 没 connect, 没联网


def test_prime_credential_sync_without_credential_returns_false():
    service = _FakeAuthService()  # credential 为 None
    controller = ServiceController(service=service)

    assert controller.prime_credential_sync() is False
    assert controller.authed is False


async def test_concurrent_start_connects_only_once():
    # 乐观登录后 Sidebar 刷新与 _load_initial_state 会并发触发 start;
    # 必须只 connect 一次, 否则泄漏第二个 Client -> 退出卡死.
    service = _FakeAuthService()
    service.credential = object()
    controller = ServiceController(service=service)

    await asyncio.gather(controller.start(), controller.start(), controller.start())

    assert service.connect_count == 1


async def test_get_song_url_requires_authenticated_service():
    service = _FakeAuthService()
    controller = ServiceController(service=service)

    with pytest.raises(RuntimeError, match="登录"):
        await controller.get_song_url(
            Song(mid="m1", name="晴天"),
            quality_preference="balanced",
        )


async def test_get_song_url_converts_expired_credential_to_signal(tmp_path):
    class _ExpiredService(_FakeAuthService):
        async def get_song_url(self, song: Song, *, quality_preference: str):
            raise CredentialExpiredError("credential expired")

    service = _ExpiredService()
    service.credential = object()
    service.is_authenticated = True
    credential_file = tmp_path / "credential.json"
    credential_file.write_text("{}", encoding="utf-8")
    service.credential_path = str(credential_file)
    controller = ServiceController(service=service)
    expired_messages: list[str] = []
    controller.credentialExpired.connect(expired_messages.append)

    with pytest.raises(CredentialExpiredError):
        await controller.get_song_url(
            Song(mid="m1", name="晴天"),
            quality_preference="balanced",
        )

    assert service.is_authenticated is False
    assert not credential_file.exists()
    assert expired_messages == ["登录已过期，请重新扫码"]


async def test_login_by_qrcode_forwards_qrcode_and_saves_credential():
    service = _FakeAuthService()
    controller = ServiceController(service=service)
    qrcodes: list[tuple[bytes, str, str]] = []
    statuses: list[str] = []

    success = await controller.login_by_qrcode(
        lambda data, kind, mimetype: qrcodes.append((data, kind, mimetype)),
        statuses.append,
    )

    assert success is True
    assert qrcodes == [(b"qr", "qq", "image/png")]
    assert statuses == ["waiting", "done"]
    assert service.saved is True
    assert controller.authed is True
    assert service.on_login_status is None


async def test_default_search_type_is_songs():
    controller = ServiceController(service=_FakeAuthService())
    assert controller.searchType == "songs"


async def test_search_singers_fills_card_results_as_artist():
    controller = ServiceController(service=_FakeAuthService())
    await controller.set_search_type_async("singers")
    await controller.search_async("周杰伦")
    assert controller.searchType == "singers"
    cards = controller.cardResults.cards()
    assert len(cards) == 1
    assert cards[0]["kind"] == "artist"
    assert cards[0]["title"] == "周杰伦"
    assert controller.songResults.count == 0


async def test_search_albums_fills_card_results():
    controller = ServiceController(service=_FakeAuthService())
    await controller.set_search_type_async("albums")
    await controller.search_async("叶惠美")
    cards = controller.cardResults.cards()
    assert cards[0]["kind"] == "album"
    assert cards[0]["title"] == "叶惠美"


async def test_search_playlists_fills_card_results():
    controller = ServiceController(service=_FakeAuthService())
    await controller.set_search_type_async("playlists")
    await controller.search_async("华语")
    cards = controller.cardResults.cards()
    assert cards[0]["kind"] == "playlist"
    assert cards[0]["title"] == "华语精选"


async def test_songs_search_still_fills_song_results():
    controller = ServiceController(service=_FakeAuthService())
    await controller.search_async("x")
    assert controller.songResults.count == 30
    assert controller.cardResults.count == 0


async def test_set_search_type_reruns_with_current_keyword():
    controller = ServiceController(service=_FakeAuthService())
    await controller.search_async("周杰伦")
    assert controller.songResults.count == 30
    await controller.set_search_type_async("singers")
    assert controller.cardResults.count == 1
    assert controller.songResults.count == 0


async def test_invalid_search_type_falls_back_to_songs():
    controller = ServiceController(service=_FakeAuthService())
    await controller.set_search_type_async("bogus")
    assert controller.searchType == "songs"


async def test_logout_async_clears_credential_cache(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="quaverq.bridge.service_controller")
    service = _FakeAuthService()
    service.credential = object()
    service.is_authenticated = True
    credential_file = tmp_path / "credential.json"
    credential_file.write_text("{}", encoding="utf-8")
    service.credential_path = str(credential_file)
    controller = ServiceController(service=service)

    await controller.logout_async()

    assert service.is_authenticated is False
    assert not credential_file.exists()
    assert "cleared QQ Music credential from memory" in caplog.text
    assert "removed cached QQ Music credential" in caplog.text


async def test_get_user_profile_passes_through_service():
    class _ProfileService(_FakeAuthService):
        async def get_user_profile(self):
            return UserProfile(nickname="鹿鸣", vip_kind="hugevip")

    controller = ServiceController(service=_ProfileService())

    profile = await controller.get_user_profile()

    assert profile.nickname == "鹿鸣"
    assert profile.vip_kind == "hugevip"


async def test_get_user_profile_converts_expired_credential_to_signal(tmp_path):
    class _ExpiredProfileService(_FakeAuthService):
        async def get_user_profile(self):
            raise CredentialExpiredError("credential expired")

    service = _ExpiredProfileService()
    service.credential = object()
    service.is_authenticated = True
    credential_file = tmp_path / "credential.json"
    credential_file.write_text("{}", encoding="utf-8")
    service.credential_path = str(credential_file)
    controller = ServiceController(service=service)
    expired_messages: list[str] = []
    controller.credentialExpired.connect(expired_messages.append)

    with pytest.raises(CredentialExpiredError):
        await controller.get_user_profile()

    assert expired_messages == ["登录已过期，请重新扫码"]


async def test_get_lyric_deduplicates_inflight_and_reuses_memory_cache():
    class _SlowLyricService(_FakeAuthService):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[tuple[str, bool]] = []
            self.release = asyncio.Event()

        async def get_lyric(self, mid: str, *, with_translation: bool = True) -> Lyric:
            self.calls.append((mid, with_translation))
            await self.release.wait()
            return Lyric(mid=mid, lines=[LyricLine(timestamp_ms=0, text=f"{mid}-line")])

    service = _SlowLyricService()
    controller = ServiceController(service=service)

    first = asyncio.create_task(controller.get_lyric("m1", with_translation=True))
    second = asyncio.create_task(controller.get_lyric("m1", with_translation=True))
    for _ in range(10):
        if service.calls:
            break
        await asyncio.sleep(0)

    assert service.calls == [("m1", True)]

    service.release.set()
    lyric_a, lyric_b = await asyncio.gather(first, second)
    lyric_c = await controller.get_lyric("m1", with_translation=True)

    assert lyric_a == lyric_b == lyric_c
    assert service.calls == [("m1", True)]


async def test_get_lyric_does_not_cache_failures():
    class _FlakyLyricService(_FakeAuthService):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def get_lyric(self, mid: str, *, with_translation: bool = True) -> Lyric:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary")
            return Lyric(mid=mid, lines=[LyricLine(timestamp_ms=0, text="ok")])

    service = _FlakyLyricService()
    controller = ServiceController(service=service)

    with pytest.raises(RuntimeError, match="temporary"):
        await controller.get_lyric("m1", with_translation=True)

    lyric = await controller.get_lyric("m1", with_translation=True)

    assert lyric.lines[0].text == "ok"
    assert service.calls == 2
