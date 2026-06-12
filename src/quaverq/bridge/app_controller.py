"""Application-level QObject exposed to QML."""

from __future__ import annotations

import asyncio
import base64
import logging
from importlib import metadata

from PySide6.QtCore import Property, QObject, Signal, Slot
from qasync import asyncSlot

from quaverq.core.home_cache import HomeCache
from quaverq.core.models import UserProfile

from .service_controller import ServiceController

logger = logging.getLogger(__name__)


def application_version(package: str = "quaverq") -> str:
    """已安装包的版本号; 源码直跑等读不到元数据的场景回退 "dev"."""
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "dev"


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
    loginTypeChanged = Signal()
    profileChanged = Signal()
    errorRaised = Signal(str)

    _LOGIN_TYPE_LABELS: dict[str, str] = {
        "qq": "QQ",
        "wx": "微信",
    }

    def __init__(
        self,
        service_controller: ServiceController | None = None,
        home_cache: HomeCache | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._home_cache = home_cache
        self._authed = False
        self._dark_mode = False
        self._logging_in = False
        self._login_task: asyncio.Task[None] | None = None
        self._qrcode_data_url = ""
        self._qrcode_kind = ""
        self._login_state = "idle"
        self._login_message = ""
        self._login_type = "qq"
        self._profile: UserProfile | None = None
        self._profile_task: asyncio.Task[None] | None = None

        if self._service_controller is not None:
            self._service_controller.authStateChanged.connect(self._sync_auth_state)
            credential_expired = getattr(
                self._service_controller,
                "credentialExpired",
                None,
            )
            if credential_expired is not None:
                credential_expired.connect(self._handle_credential_expired)

    @Property(str, constant=True)
    def appVersion(self) -> str:
        return application_version()

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

    @Property(str, notify=loginTypeChanged)
    def loginType(self) -> str:
        return self._login_type

    @Property(str, notify=profileChanged)
    def nickname(self) -> str:
        return self._profile.nickname if self._profile else ""

    @Property(str, notify=profileChanged)
    def avatarUrl(self) -> str:
        return self._profile.avatar_url if self._profile else ""

    @Property(str, notify=profileChanged)
    def vipKind(self) -> str:
        """ "" 非会员 / "vip" 绿钻 / "hugevip" 豪华绿钻 / "svip" 超级会员."""
        return self._profile.vip_kind if self._profile else ""

    @Property(str, notify=profileChanged)
    def vipIconUrl(self) -> str:
        """服务端"绿钻等级"徽章图 (lv_N.png), **不表达会员种类** —— SVIP 账号
        它也给绿钻图. 侧栏徽章按 vipKind 走文字 pill, 此属性留作未来等级展示."""
        return self._profile.vip_icon_url if self._profile else ""

    def _login_type_label(self) -> str:
        return self._LOGIN_TYPE_LABELS.get(self._login_type, "QQ")

    @asyncSlot()
    async def loginByQrCode(self) -> None:
        await self.login_by_qrcode_async()

    @asyncSlot(str)
    async def loginByQrCodeWithType(self, login_type: str) -> None:
        await self.login_by_qrcode_async(login_type=login_type)

    async def login_by_qrcode_async(self, login_type: str = "qq") -> None:
        if self._logging_in:
            task = self._login_task
            if task is not None and not task.done():
                task.cancel()
                await asyncio.wait([task])
        if self._service_controller is None:
            self._set_login_error("登录服务未初始化")
            return

        self._set_login_type(login_type)
        self._set_logging_in(True)
        self._login_task = asyncio.current_task()
        self._set_qrcode("", "")
        self._set_login_state("loading")
        self._set_login_message("正在获取二维码")
        try:
            success = await self._service_controller.login_by_qrcode(
                self._handle_qrcode,
                self._handle_login_status,
                login_type=login_type,
            )
        except asyncio.CancelledError:
            logger.info("二维码登录已取消")
            self._set_login_state("idle")
            self._set_login_message("")
            self._set_qrcode("", "")
            raise
        except Exception as exc:
            logger.exception("QR login failed")
            self._set_authed(False, "error")
            self._set_login_error(str(exc) or exc.__class__.__name__)
            return
        finally:
            self._set_logging_in(False)
            self._login_task = None

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

    @Slot()
    def cancelLogin(self) -> None:
        task = self._login_task
        if task is not None and not task.done():
            task.cancel()

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
        label = self._login_type_label()
        self._set_login_state("waiting")
        self._set_login_message(f"请使用 {label} 扫描二维码并确认登录")

    def _handle_login_status(self, status: str) -> None:
        label = self._login_type_label()
        if status in ("qrcode", "waiting"):
            self._set_login_state("waiting")
            self._set_login_message(f"请使用 {label} 扫描二维码并确认登录")
        elif status == "scanned":
            self._set_login_state("scanned")
            self._set_login_message(f"已扫码，请在 {label} 上确认登录")
        elif status == "confirm":
            self._set_login_state("confirming")
            self._set_login_message("已确认，正在等待返回登录凭据")
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
        # 身份区随登录态联动: 登录 (login/cached) 拉画像, 登出/过期立刻清空
        if value:
            self._schedule_profile_refresh()
        else:
            self._cancel_profile_task()
            self._set_profile(None)
        self.authedChanged.emit()
        self.authChanged.emit(value, reason)

    def prime_profile_from_cache(self, account_key: str) -> None:
        """启动首帧: 同步用上次缓存的画像填充身份区 (本地, 不联网).

        SWR: 与 prime_private_from_cache 同批在 engine.load 前调用, 首帧直出
        头像/昵称/徽章; 真值由随后的后台刷新校正 (同值时 _set_profile 去重零跳变).
        归属由 HomeCache 的 per-block account_key 校验, 换号不串.
        """
        if self._home_cache is None or not account_key:
            return
        profile = self._home_cache.load(account_key).profile
        if profile is not None and self._profile is None:
            self._set_profile(profile)

    def _schedule_profile_refresh(self) -> None:
        self._cancel_profile_task()
        try:
            self._profile_task = asyncio.ensure_future(self.refresh_profile_async())
        except RuntimeError:  # 无事件循环 (同步上下文), 等下一次登录态变化再拉
            self._profile_task = None

    def _cancel_profile_task(self) -> None:
        task = self._profile_task
        if task is not None and not task.done():
            task.cancel()
        self._profile_task = None

    async def refresh_profile_async(self) -> None:
        """拉登录账号画像 (昵称 / 头像 / VIP). 失败静默缺席, 不挡登录主流程."""
        if self._service_controller is None or not self._authed:
            return
        get_profile = getattr(self._service_controller, "get_user_profile", None)
        if not callable(get_profile):
            return
        try:
            profile = await get_profile()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 凭据过期已由 ServiceController.call_service 链路广播 credentialExpired;
            # 这里只兜底防 fire-and-forget task 抛未处理异常.
            logger.warning("refresh user profile failed: %s", exc)
            return
        if not self._authed:  # 拉取期间已登出, 丢弃迟到结果
            return
        # service 在双请求都失败 (断网) 时"成功返回 None"而非抛异常 —— 此时
        # 保留 prime 自 HomeCache 的画像 (SWR: 刷新失败不回退首帧); 清空职责
        # 完全由 _set_authed(False) 的登出/过期路径承担.
        if profile is not None:
            self._set_profile(profile)
            self._persist_profile(profile)

    def _persist_profile(self, profile: UserProfile | None) -> None:
        """网络刷新成功后回写缓存, 下次启动首帧直出; 登出清理走 clear_private 链路."""
        if self._home_cache is None or profile is None:
            return
        get_key = getattr(self._service_controller, "account_key", None)
        key = get_key() if callable(get_key) else ""
        if not key:
            return
        try:
            self._home_cache.update(profile=profile, account_key=key)
        except OSError as exc:
            logger.warning("persist user profile failed: %s", exc)

    def _set_profile(self, profile: UserProfile | None) -> None:
        if self._profile == profile:
            return
        self._profile = profile
        self.profileChanged.emit()

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

    def _set_login_type(self, value: str) -> None:
        if self._login_type == value:
            return
        self._login_type = value
        self.loginTypeChanged.emit()

    def _set_login_error(self, message: str) -> None:
        text = f"登录失败：{message}" if message else "登录失败"
        self._set_login_state("error")
        self._set_login_message(text)
        self.errorRaised.emit(text)
