"""ServiceController tests."""

from __future__ import annotations

import logging

import pytest

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

    async def _get_cached_credential(self):
        return self.credential

    async def set_credential(self, credential) -> None:
        self.credential = credential
        self.is_authenticated = credential is not None

    async def get_song_url(self, song: Song, *, quality_preference: str):
        return None

    async def login_by_qrcode(self) -> bool:
        if self.on_qrcode is not None:
            self.on_qrcode(b"qr", "qq", "image/png")
        if self.on_login_status is not None:
            self.on_login_status("scan")
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


async def test_start_loads_cached_credential_when_available():
    service = _FakeAuthService()
    service.credential = object()
    controller = ServiceController(service=service)

    await controller.start()

    assert service.connected is True
    assert service.is_authenticated is True


async def test_get_song_url_requires_authenticated_service():
    service = _FakeAuthService()
    controller = ServiceController(service=service)

    with pytest.raises(RuntimeError, match="登录"):
        await controller.get_song_url(
            Song(mid="m1", name="晴天"),
            quality_preference="balanced",
        )


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
    assert statuses == ["scan", "done"]
    assert service.saved is True
    assert controller.authed is True
    assert service.on_login_status is None


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
