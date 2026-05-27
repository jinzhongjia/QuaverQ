"""AppController authentication tests."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from quaverq.bridge.app_controller import AppController


class _FakeServiceController(QObject):
    authStateChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.authed = False
        self.started = False
        self.login_result = True
        self.login_calls = 0
        self.logout_calls = 0

    async def start(self) -> None:
        self.started = True

    async def login_by_qrcode(self, on_qrcode, on_status=None) -> bool:
        self.login_calls += 1
        on_qrcode(b"qr-bytes", "qq", "image/png")
        if on_status is not None:
            on_status("scan")
            on_status("confirm")
        self.authed = self.login_result
        self.authStateChanged.emit()
        if on_status is not None and self.login_result:
            on_status("done")
        return self.login_result

    async def logout_async(self) -> None:
        self.logout_calls += 1
        self.authed = False
        self.authStateChanged.emit()


async def test_login_by_qrcode_exposes_qrcode_and_marks_authenticated():
    service = _FakeServiceController()
    controller = AppController(service)  # type: ignore[arg-type]
    qrcodes: list[str] = []
    controller.qrcodeChanged.connect(lambda: qrcodes.append(controller.qrcodeDataUrl))

    await controller.login_by_qrcode_async()

    assert service.login_calls == 1
    assert any(value.startswith("data:image/png;base64,") for value in qrcodes)
    assert controller.authed is True
    assert controller.loggingIn is False
    assert controller.loginState == "authenticated"
    assert controller.loginMessage == "已登录"
    assert controller.qrcodeDataUrl == ""


async def test_login_by_qrcode_failure_keeps_user_logged_out():
    service = _FakeServiceController()
    service.login_result = False
    controller = AppController(service)  # type: ignore[arg-type]

    await controller.login_by_qrcode_async()

    assert controller.authed is False
    assert controller.loggingIn is False
    assert controller.loginState == "error"
    assert controller.loginMessage == "登录未完成，请重试"


async def test_login_by_qrcode_updates_scan_and_confirm_messages():
    class _SlowFakeService(_FakeServiceController):
        async def login_by_qrcode(self, on_qrcode, on_status=None) -> bool:
            on_qrcode(b"qr-bytes", "qq", "image/png")
            if on_status is not None:
                on_status("scan")
                on_status("confirm")
            self.authed = False
            return False

    controller = AppController(_SlowFakeService())  # type: ignore[arg-type]
    messages: list[str] = []
    controller.loginMessageChanged.connect(lambda: messages.append(controller.loginMessage))

    await controller.login_by_qrcode_async()

    assert "已扫码，请在手机上确认登录" in messages
    assert "已确认，正在等待 QQ 音乐返回登录凭据" in messages


async def test_refresh_auth_state_reads_service_state():
    service = _FakeServiceController()
    service.authed = True
    controller = AppController(service)  # type: ignore[arg-type]

    await controller.refresh_auth_state_async()

    assert service.started is True
    assert controller.authed is True


async def test_logout_clears_auth_state(caplog):
    caplog.set_level(logging.INFO, logger="quaverq.bridge.app_controller")
    service = _FakeServiceController()
    service.authed = True
    controller = AppController(service)  # type: ignore[arg-type]
    await controller.refresh_auth_state_async()

    await controller.logout_async()

    assert service.logout_calls == 1
    assert controller.authed is False
    assert "logout requested" in caplog.text
    assert "logout completed" in caplog.text
