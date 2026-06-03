"""Application-level QObject exposed to QML."""

from __future__ import annotations

import base64
import logging

from PySide6.QtCore import QObject, Property, Signal, Slot
from qasync import asyncSlot

from .service_controller import ServiceController

logger = logging.getLogger(__name__)


class AppController(QObject):
    """Application state and authentication controller exposed to QML."""

    authedChanged = Signal()
    authChanged = Signal(bool, str)
    credExpired = Signal()
    darkModeChanged = Signal()
    loggingInChanged = Signal()
    qrcodeChanged = Signal()
    loginStateChanged = Signal()
    loginMessageChanged = Signal()
    errorRaised = Signal(str)

    def __init__(
        self,
        service_controller: ServiceController | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._authed = False
        self._dark_mode = False
        self._logging_in = False
        self._qrcode_data_url = ""
        self._qrcode_kind = ""
        self._login_state = "idle"
        self._login_message = ""

        if self._service_controller is not None:
            self._service_controller.authStateChanged.connect(self._sync_auth_state)
            credential_expired = getattr(
                self._service_controller,
                "credentialExpired",
                None,
            )
            if credential_expired is not None:
                credential_expired.connect(self._handle_credential_expired)

    @Property(bool, notify=authedChanged)
    def authed(self) -> bool:
        return self._authed

    @Property(bool, notify=darkModeChanged)
    def darkMode(self) -> bool:
        return self._dark_mode

    @Property(bool, notify=loggingInChanged)
    def loggingIn(self) -> bool:
        return self._logging_in

    @Property(str, notify=qrcodeChanged)
    def qrcodeDataUrl(self) -> str:
        return self._qrcode_data_url

    @Property(str, notify=qrcodeChanged)
    def qrcodeKind(self) -> str:
        return self._qrcode_kind

    @Property(str, notify=loginStateChanged)
    def loginState(self) -> str:
        return self._login_state

    @Property(str, notify=loginMessageChanged)
    def loginMessage(self) -> str:
        return self._login_message

    @asyncSlot()
    async def loginByQrCode(self) -> None:
        await self.login_by_qrcode_async()

    async def login_by_qrcode_async(self) -> None:
        if self._logging_in:
            return
        if self._service_controller is None:
            self._set_login_error("登录服务未初始化")
            return

        self._set_logging_in(True)
        self._set_qrcode("", "")
        self._set_login_state("loading")
        self._set_login_message("正在获取二维码")
        try:
            success = await self._service_controller.login_by_qrcode(
                self._handle_qrcode,
                self._handle_login_status,
            )
        except Exception as exc:
            logger.exception("QR login failed")
            self._set_authed(False, "error")
            self._set_login_error(str(exc) or exc.__class__.__name__)
            return
        finally:
            self._set_logging_in(False)

        if success:
            self._set_authed(True, "login")
            self._set_login_state("authenticated")
            self._set_login_message("已登录")
            self._set_qrcode("", "")
        else:
            had_terminal_state = self._login_state in {"error", "expired"}
            self._set_authed(False, "cancelled")
            if not had_terminal_state:
                self._set_login_state("error")
                self._set_login_message("登录未完成，请重试")
            elif not self._login_message:
                self._set_login_message("登录未完成，请重试")

    async def refresh_auth_state_async(self) -> None:
        if self._service_controller is None:
            return
        await self._service_controller.start()
        self._sync_auth_state()

    @asyncSlot()
    async def logout(self) -> None:
        await self.logout_async()

    async def logout_async(self) -> None:
        if not self._authed:
            logger.info("logout skipped: user is already logged out")
            return
        logger.info("logout requested")
        if self._service_controller is not None:
            await self._service_controller.logout_async()
        self._set_authed(False, "logout")
        self._set_login_state("idle")
        self._set_login_message("")
        self._set_qrcode("", "")
        logger.info("logout completed")

    def _handle_qrcode(self, data: bytes, kind: str, mimetype: str) -> None:
        encoded = base64.b64encode(data).decode("ascii")
        self._set_qrcode(
            f"data:{mimetype or 'image/png'};base64,{encoded}",
            kind,
        )
        self._set_login_state("waiting")
        self._set_login_message("请使用 QQ 音乐扫描二维码并确认登录")

    def _handle_login_status(self, status: str) -> None:
        if status in ("qrcode", "waiting"):
            self._set_login_state("waiting")
            self._set_login_message("请使用 QQ 音乐扫描二维码并确认登录")
        elif status == "scanned":
            self._set_login_state("scanned")
            self._set_login_message("已扫码，请在手机上确认登录")
        elif status == "confirm":
            self._set_login_state("confirming")
            self._set_login_message("已确认，正在等待 QQ 音乐返回登录凭据")
        elif status == "timeout":
            self._set_login_state("error")
            self._set_login_message("二维码已过期，请重新获取")
        elif status == "refuse":
            self._set_login_state("error")
            self._set_login_message("已取消登录")
        elif status == "done":
            self._set_login_state("authenticated")
            self._set_login_message("已登录")
        elif status == "expired":
            self._set_login_state("expired")
            self._set_login_message("登录已过期，请重新扫码")

    @Slot()
    def _sync_auth_state(self) -> None:
        if self._service_controller is None:
            return
        self._set_authed(self._service_controller.authed, "cached")

    @Slot(str)
    def _handle_credential_expired(self, message: str) -> None:
        text = message or "登录已过期，请重新扫码"
        self._set_authed(False, "expired")
        self._set_logging_in(False)
        self._set_qrcode("", "")
        self._set_login_state("expired")
        self._set_login_message(text)
        self.credExpired.emit()

    def _set_authed(self, value: bool, reason: str) -> None:
        if self._authed == value:
            return
        self._authed = value
        self.authedChanged.emit()
        self.authChanged.emit(value, reason)

    def _set_logging_in(self, value: bool) -> None:
        if self._logging_in == value:
            return
        self._logging_in = value
        self.loggingInChanged.emit()

    def _set_qrcode(self, data_url: str, kind: str) -> None:
        if self._qrcode_data_url == data_url and self._qrcode_kind == kind:
            return
        self._qrcode_data_url = data_url
        self._qrcode_kind = kind
        self.qrcodeChanged.emit()

    def _set_login_state(self, value: str) -> None:
        if self._login_state == value:
            return
        self._login_state = value
        self.loginStateChanged.emit()

    def _set_login_message(self, value: str) -> None:
        if self._login_message == value:
            return
        self._login_message = value
        self.loginMessageChanged.emit()

    def _set_login_error(self, message: str) -> None:
        text = f"登录失败：{message}" if message else "登录失败"
        self._set_login_state("error")
        self._set_login_message(text)
        self.errorRaised.emit(text)
