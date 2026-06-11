"""AppController authentication tests."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from PySide6.QtCore import QObject, Signal

from quaverq.bridge.app_controller import AppController


class _FakeServiceController(QObject):
    authStateChanged = Signal()
    credentialExpired = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.authed = False
        self.started = False
        self.login_result = True
        self.login_calls = 0
        self.logout_calls = 0
        self.last_login_type = None

    async def start(self) -> None:
        self.started = True

    async def login_by_qrcode(self, on_qrcode, on_status=None, login_type="qq") -> bool:
        self.login_calls += 1
        self.last_login_type = login_type
        on_qrcode(b"qr-bytes", login_type, "image/png")
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

    def expire(self, message: str = "登录已过期，请重新扫码") -> None:
        self.authed = False
        self.authStateChanged.emit()
        self.credentialExpired.emit(message)


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


async def test_login_by_qrcode_updates_waiting_and_scanned_messages():
    class _SlowFakeService(_FakeServiceController):
        async def login_by_qrcode(self, on_qrcode, on_status=None, login_type="qq") -> bool:
            on_qrcode(b"qr-bytes", login_type, "image/png")
            if on_status is not None:
                on_status("waiting")
                on_status("scanned")
            self.authed = False
            return False

    controller = AppController(_SlowFakeService())  # type: ignore[arg-type]
    messages: list[str] = []
    controller.loginMessageChanged.connect(lambda: messages.append(controller.loginMessage))

    await controller.login_by_qrcode_async()

    assert any("QQ" in m and "扫描二维码" in m for m in messages)
    assert any("已扫码" in m and "确认登录" in m for m in messages)


async def test_login_by_qrcode_wx_updates_waiting_and_scanned_messages():
    class _SlowFakeService(_FakeServiceController):
        async def login_by_qrcode(self, on_qrcode, on_status=None, login_type="qq") -> bool:
            on_qrcode(b"qr-bytes", login_type, "image/png")
            if on_status is not None:
                on_status("waiting")
                on_status("scanned")
            self.authed = False
            return False

    controller = AppController(_SlowFakeService())  # type: ignore[arg-type]
    messages: list[str] = []
    controller.loginMessageChanged.connect(lambda: messages.append(controller.loginMessage))

    await controller.login_by_qrcode_async(login_type="wx")

    assert any("微信" in m and "扫描二维码" in m for m in messages)
    assert any("已扫码" in m and "微信" in m for m in messages)


def test_handle_login_status_maps_qq_events_to_ui_states():
    """回归：SCAN=等待扫描→waiting；CONF=已扫待确认→scanned。不得一出二维码就 scanned。"""
    controller = AppController(_FakeServiceController())  # type: ignore[arg-type]

    controller._handle_login_status("waiting")
    assert controller.loginState == "waiting"
    assert "QQ" in controller.loginMessage
    assert "扫描二维码" in controller.loginMessage

    controller._handle_login_status("scanned")
    assert controller.loginState == "scanned"
    assert "已扫码" in controller.loginMessage

    controller._handle_login_status("done")
    assert controller.loginState == "authenticated"


async def test_login_by_qrcode_timeout_sets_retryable_state():
    class _TimeoutFakeService(_FakeServiceController):
        async def login_by_qrcode(self, on_qrcode, on_status=None, login_type="qq") -> bool:
            on_qrcode(b"qr-bytes", login_type, "image/png")
            if on_status is not None:
                on_status("timeout")
            self.authed = False
            return False

    controller = AppController(_TimeoutFakeService())  # type: ignore[arg-type]

    await controller.login_by_qrcode_async()

    assert controller.authed is False
    assert controller.loginState == "error"
    assert controller.loginMessage == "二维码已过期，请重新获取"


async def test_login_by_qrcode_refuse_sets_cancelled_reason():
    class _RefuseFakeService(_FakeServiceController):
        async def login_by_qrcode(self, on_qrcode, on_status=None, login_type="qq") -> bool:
            on_qrcode(b"qr-bytes", login_type, "image/png")
            if on_status is not None:
                on_status("refuse")
            self.authed = False
            self.authStateChanged.emit()
            return False

    controller = AppController(_RefuseFakeService())  # type: ignore[arg-type]

    await controller.login_by_qrcode_async()

    assert controller.authed is False
    assert controller.loginState == "error"
    assert controller.loginMessage == "已取消登录"


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


async def test_cancel_login_stops_polling_and_resets_state():
    cancel_event = asyncio.Event()

    class _HangingFakeService(_FakeServiceController):
        async def login_by_qrcode(self, on_qrcode, on_status=None, login_type="qq") -> bool:
            on_qrcode(b"qr-bytes", login_type, "image/png")
            if on_status is not None:
                on_status("waiting")
            await cancel_event.wait()
            return False

    controller = AppController(_HangingFakeService())  # type: ignore[arg-type]
    task = asyncio.ensure_future(controller.login_by_qrcode_async())
    await asyncio.sleep(0)

    assert controller.loggingIn is True
    assert controller.loginState == "waiting"

    controller.cancelLogin()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert controller.loggingIn is False
    assert controller.loginState == "idle"
    assert controller.loginMessage == ""
    assert controller.qrcodeDataUrl == ""
    assert task.done()


async def test_cancel_login_noop_when_not_logging_in():
    controller = AppController(_FakeServiceController())  # type: ignore[arg-type]
    controller.cancelLogin()
    assert controller.loginState == "idle"


async def test_login_by_qrcode_wx_passes_login_type_and_uses_wx_messages():
    service = _FakeServiceController()
    controller = AppController(service)  # type: ignore[arg-type]
    messages: list[str] = []
    controller.loginMessageChanged.connect(lambda: messages.append(controller.loginMessage))

    await controller.login_by_qrcode_async(login_type="wx")

    assert service.last_login_type == "wx"
    assert controller.authed is True
    assert any("微信" in m for m in messages)
    assert not any("QQ" in m for m in messages)


async def test_login_by_qrcode_qq_uses_qq_messages():
    service = _FakeServiceController()
    controller = AppController(service)  # type: ignore[arg-type]
    messages: list[str] = []
    controller.loginMessageChanged.connect(lambda: messages.append(controller.loginMessage))

    await controller.login_by_qrcode_async(login_type="qq")

    assert service.last_login_type == "qq"
    assert controller.authed is True
    assert any("QQ" in m for m in messages)


async def test_login_type_property_updates_on_login():
    service = _FakeServiceController()
    controller = AppController(service)  # type: ignore[arg-type]

    assert controller.loginType == "qq"

    await controller.login_by_qrcode_async(login_type="wx")
    assert controller.loginType == "wx"


async def test_switch_login_type_cancels_previous_and_starts_new():
    cancel_event = asyncio.Event()

    class _HangingFakeService(_FakeServiceController):
        async def login_by_qrcode(self, on_qrcode, on_status=None, login_type="qq") -> bool:
            self.last_login_type = login_type
            on_qrcode(b"qr-bytes", login_type, "image/png")
            if on_status is not None:
                on_status("waiting")
            if login_type == "qq":
                await cancel_event.wait()
                return False
            self.authed = True
            self.authStateChanged.emit()
            if on_status is not None:
                on_status("done")
            return True

    service = _HangingFakeService()
    controller = AppController(service)  # type: ignore[arg-type]

    task_qq = asyncio.ensure_future(controller.login_by_qrcode_async(login_type="qq"))
    await asyncio.sleep(0)
    assert controller.loggingIn is True
    assert controller.loginType == "qq"

    task_wx = asyncio.ensure_future(controller.login_by_qrcode_async(login_type="wx"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    with contextlib.suppress(asyncio.CancelledError):
        await task_qq
    await task_wx

    assert controller.loginType == "wx"
    assert controller.authed is True
    assert service.last_login_type == "wx"


async def test_credential_expired_updates_login_state_and_emits_signal():
    service = _FakeServiceController()
    service.authed = True
    controller = AppController(service)  # type: ignore[arg-type]
    await controller.refresh_auth_state_async()
    expired_count = 0

    def on_expired() -> None:
        nonlocal expired_count
        expired_count += 1

    controller.credExpired.connect(on_expired)

    service.expire()

    assert controller.authed is False
    assert controller.loginState == "expired"
    assert controller.loginMessage == "登录已过期，请重新扫码"
    assert expired_count == 1


def test_app_version_reads_installed_metadata():
    controller = AppController(_FakeServiceController())  # type: ignore[arg-type]
    # 本仓库以可安装包形式装进虚拟环境 ([tool.uv] package = true), 必然能读到版本
    assert controller.appVersion == "0.1.0"


def test_application_version_falls_back_when_package_missing():
    from quaverq.bridge.app_controller import application_version

    assert application_version("definitely-not-installed-pkg") == "dev"
