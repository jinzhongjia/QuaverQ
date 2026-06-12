"""AppController authentication tests."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from PySide6.QtCore import QObject, Signal

from quaverq.bridge.app_controller import AppController
from quaverq.core.home_cache import HomeCache
from quaverq.core.models import UserProfile


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
        self.profile_calls = 0
        self.profile_error: Exception | None = None
        self.account_key_value = ""

        self.profile_result = UserProfile(
            nickname="鹿鸣",
            avatar_url="http://thirdqq.qlogo.cn/g?k=abc",
            vip_kind="svip",
            vip_icon_url="https://y.qq.com/mediastyle/global/vip_icon/lv_7.png",
        )

    def account_key(self) -> str:
        return self.account_key_value

    async def get_user_profile(self) -> UserProfile | None:
        self.profile_calls += 1
        if self.profile_error is not None:
            raise self.profile_error
        return self.profile_result

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


# ============================================================== 用户身份区 (C4 侧栏)


async def _drain_profile_task(controller: AppController) -> None:
    """等 fire-and-forget 的 profile 刷新 task 跑完 (被取消也算完)."""
    task = controller._profile_task
    if task is not None:
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_login_populates_user_profile():
    service = _FakeServiceController()
    controller = AppController(service)  # type: ignore[arg-type]
    changes: list[str] = []
    controller.profileChanged.connect(lambda: changes.append(controller.nickname))

    await controller.login_by_qrcode_async()
    await _drain_profile_task(controller)

    assert service.profile_calls == 1
    assert controller.nickname == "鹿鸣"
    assert controller.avatarUrl == "http://thirdqq.qlogo.cn/g?k=abc"
    assert controller.vipKind == "svip"
    assert controller.vipIconUrl.endswith("lv_7.png")
    assert changes  # profileChanged 已发射


async def test_cached_credential_prime_populates_user_profile():
    """启动期 prime 凭据走 _sync_auth_state ("cached" reason) 同样触发刷新."""
    service = _FakeServiceController()
    controller = AppController(service)  # type: ignore[arg-type]

    service.authed = True
    service.authStateChanged.emit()
    await _drain_profile_task(controller)

    assert controller.nickname == "鹿鸣"


async def test_logout_clears_user_profile():
    service = _FakeServiceController()
    controller = AppController(service)  # type: ignore[arg-type]
    await controller.login_by_qrcode_async()
    await _drain_profile_task(controller)
    changes: list[str] = []
    controller.profileChanged.connect(lambda: changes.append(controller.nickname))

    await controller.logout_async()

    assert controller.nickname == ""
    assert controller.avatarUrl == ""
    assert controller.vipKind == ""
    assert controller.vipIconUrl == ""
    assert changes == [""]


async def test_credential_expired_clears_user_profile():
    service = _FakeServiceController()
    controller = AppController(service)  # type: ignore[arg-type]
    await controller.login_by_qrcode_async()
    await _drain_profile_task(controller)

    service.expire()

    assert controller.nickname == ""
    assert controller.vipKind == ""


async def test_profile_fetch_failure_keeps_identity_empty(caplog):
    """拉取失败不挡登录主流程: 身份区静默缺席, 仅 log warning."""
    caplog.set_level(logging.WARNING, logger="quaverq.bridge.app_controller")
    service = _FakeServiceController()
    service.profile_error = RuntimeError("profile boom")
    controller = AppController(service)  # type: ignore[arg-type]

    await controller.login_by_qrcode_async()
    await _drain_profile_task(controller)

    assert controller.authed is True
    assert controller.nickname == ""
    assert controller.vipKind == ""
    assert "profile boom" in caplog.text


async def test_profile_discarded_when_logged_out_during_fetch():
    """拉取期间登出: 迟到的结果不得复活身份区 (竞态保护)."""
    gate = asyncio.Event()

    class _SlowProfileService(_FakeServiceController):
        async def get_user_profile(self) -> UserProfile | None:
            await gate.wait()
            return await super().get_user_profile()

    service = _SlowProfileService()
    controller = AppController(service)  # type: ignore[arg-type]
    await controller.login_by_qrcode_async()

    await controller.logout_async()
    gate.set()
    await _drain_profile_task(controller)

    assert controller.nickname == ""
    assert controller.vipKind == ""


# ============================================================== profile 缓存 (SWR 首帧)


def _cached_profile() -> UserProfile:
    return UserProfile(
        nickname="影翼",
        avatar_url="http://thirdqq.qlogo.cn/g?k=abc",
        vip_kind="svip",
        is_year_vip=True,
        vip_icon_url="http://y.gtimg.cn/lv_7.png",
    )


def _home_cache_with_profile(tmp_path, account_key: str) -> HomeCache:
    cache = HomeCache(tmp_path / "home.json")
    cache.update(profile=_cached_profile(), account_key=account_key)
    return cache


async def test_prime_profile_from_cache_fills_first_frame(tmp_path):
    """启动期同步喂缓存画像: 不联网、立即可读、profileChanged 发射."""
    service = _FakeServiceController()
    cache = _home_cache_with_profile(tmp_path, "acc1")
    controller = AppController(service, home_cache=cache)  # type: ignore[arg-type]
    changes: list[str] = []
    controller.profileChanged.connect(lambda: changes.append(controller.nickname))

    controller.prime_profile_from_cache("acc1")

    assert service.profile_calls == 0  # 纯本地
    assert controller.nickname == "影翼"
    assert controller.vipKind == "svip"
    assert changes == ["影翼"]


async def test_prime_profile_skips_on_account_mismatch(tmp_path):
    service = _FakeServiceController()
    cache = _home_cache_with_profile(tmp_path, "acc1")
    controller = AppController(service, home_cache=cache)  # type: ignore[arg-type]

    controller.prime_profile_from_cache("other")
    assert controller.nickname == ""

    controller.prime_profile_from_cache("")
    assert controller.nickname == ""


async def test_refresh_writes_profile_back_to_cache(tmp_path):
    """网络刷新成功后回写缓存 (带 account_key), 下次启动首帧直出."""
    service = _FakeServiceController()
    service.account_key_value = "acc1"
    cache = HomeCache(tmp_path / "home.json")
    controller = AppController(service, home_cache=cache)  # type: ignore[arg-type]

    await controller.login_by_qrcode_async()
    await _drain_profile_task(controller)

    cached = cache.load("acc1").profile
    assert cached is not None
    assert cached.nickname == "鹿鸣"
    assert cached.vip_kind == "svip"


async def test_same_profile_refresh_does_not_re_emit(tmp_path):
    """SWR 零跳变契约: prime 的缓存值与网络值相同时, 刷新不再发 profileChanged."""
    service = _FakeServiceController()
    service.account_key_value = "acc1"
    service.profile_result = _cached_profile()
    cache = _home_cache_with_profile(tmp_path, "acc1")
    controller = AppController(service, home_cache=cache)  # type: ignore[arg-type]
    controller.prime_profile_from_cache("acc1")
    changes: list[str] = []
    controller.profileChanged.connect(lambda: changes.append(controller.nickname))

    await controller.login_by_qrcode_async()
    await _drain_profile_task(controller)

    assert service.profile_calls == 1  # 网络刷新仍发生 (SWR 的 revalidate)
    assert changes == []  # 但同值不引发第二次 UI 跳变


async def test_refresh_returning_none_keeps_primed_cache_profile(tmp_path):
    """回归 (PR #17 评论): 刷新"成功返回 None"不得清空 prime 的缓存画像.

    QuaverService.get_user_profile 在双请求都失败 (断网) 时 log warning 后
    返回 None 而非抛异常 —— 走的是 refresh 的正常路径, 不是 except 分支.
    此前 _set_profile(None) 会把启动时从 HomeCache 恢复的画像清掉, 断网下
    身份区从「昵称+徽章」跳回「已登录」, 破坏 SWR.
    """
    service = _FakeServiceController()
    service.account_key_value = "acc1"
    service.profile_result = None  # 模拟双失败: 成功返回 None
    cache = _home_cache_with_profile(tmp_path, "acc1")
    controller = AppController(service, home_cache=cache)  # type: ignore[arg-type]
    controller.prime_profile_from_cache("acc1")
    assert controller.nickname == "影翼"
    changes: list[str] = []
    controller.profileChanged.connect(lambda: changes.append(controller.nickname))

    await controller.login_by_qrcode_async()
    await _drain_profile_task(controller)

    assert service.profile_calls == 1  # 刷新仍发生
    assert controller.nickname == "影翼"  # 缓存画像未被清空
    assert controller.vipKind == "svip"
    assert changes == []
    assert cache.load("acc1").profile is not None  # 缓存文件也未被动


async def test_refresh_returning_none_without_cache_stays_empty():
    """无缓存画像时刷新返回 None: 身份区保持空态, 不发多余信号."""
    service = _FakeServiceController()
    service.profile_result = None
    controller = AppController(service)  # type: ignore[arg-type]
    changes: list[str] = []
    controller.profileChanged.connect(lambda: changes.append(controller.nickname))

    await controller.login_by_qrcode_async()
    await _drain_profile_task(controller)

    assert controller.nickname == ""
    assert changes == []
