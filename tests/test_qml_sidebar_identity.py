"""Sidebar.qml 身份区 (C4) 离屏契约测试.

加载真实 Sidebar.qml + 真 AppController (fake service 喂 profile), 验证:

1. 未登录: 身份区显示「点击登录」, 无 VIP 徽章;
2. 登录 + 画像就绪: 显示昵称 + 对应种类徽章文案 (svip/hugevip/vip 优先级映射);
3. 画像缺席 (拉取失败) 时昵称回退「已登录」;
4. 登出: 身份区回到未登录态.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication

from quaverq.bridge.app_controller import AppController
from quaverq.bridge.cover_provider import CoverController, CoverImageProvider
from quaverq.core.cover_cache import CoverCache
from quaverq.core.models import UserProfile

_SIDEBAR_QML = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "quaverq"
    / "qml"
    / "components"
    / "Sidebar.qml"
)


class _FakeServiceController(QObject):
    authStateChanged = Signal()
    credentialExpired = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.authed = False
        self.profile_result: UserProfile | None = UserProfile(
            nickname="鹿鸣",
            avatar_url="",
            vip_kind="hugevip",
            vip_icon_url="",
        )
        self.profile_error: Exception | None = None

    async def start(self) -> None:
        pass

    async def get_user_profile(self) -> UserProfile | None:
        if self.profile_error is not None:
            raise self.profile_error
        return self.profile_result

    async def logout_async(self) -> None:
        self.authed = False
        self.authStateChanged.emit()


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _process(app, rounds: int = 6) -> None:
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.002)


async def _drain_profile_task(controller: AppController) -> None:
    task = controller._profile_task
    if task is not None:
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.fixture
def sidebar(qapp, tmp_path):
    service = _FakeServiceController()
    app_controller = AppController(service)  # type: ignore[arg-type]
    cover_controller = CoverController(CoverCache(tmp_path / "covers"))

    engine = QQmlEngine()
    engine.addImageProvider("covers", CoverImageProvider(CoverCache(tmp_path / "covers")))
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_SIDEBAR_QML)))
    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    item = component.create()
    assert item is not None
    item.setProperty("appController", app_controller)
    item.setProperty("coverController", cover_controller)
    _process(qapp)

    identity = item.findChild(QObject, "identityArea")
    assert identity is not None, "Sidebar 应有 objectName=identityArea 的身份区"
    yield SimpleNamespace(
        app=qapp,
        item=item,
        identity=identity,
        service=service,
        controller=app_controller,
    )
    item.deleteLater()
    qapp.processEvents()


def test_identity_logged_out_shows_login_entry(sidebar):
    assert sidebar.identity.property("loggedIn") is False
    assert sidebar.identity.property("displayName") == "点击登录"
    assert sidebar.identity.property("vipLabel") == ""


async def test_identity_logged_in_shows_nickname_and_badge(sidebar):
    sidebar.service.authed = True
    sidebar.service.authStateChanged.emit()
    await _drain_profile_task(sidebar.controller)
    _process(sidebar.app)

    assert sidebar.identity.property("loggedIn") is True
    assert sidebar.identity.property("displayName") == "鹿鸣"
    assert sidebar.identity.property("vipLabel") == "豪华绿钻"


async def test_identity_badge_label_follows_vip_kind(sidebar):
    for kind, label in (("svip", "SVIP"), ("vip", "绿钻"), ("", "")):
        sidebar.service.authed = False
        sidebar.service.authStateChanged.emit()
        sidebar.service.profile_result = UserProfile(nickname="鹿鸣", vip_kind=kind)
        sidebar.service.authed = True
        sidebar.service.authStateChanged.emit()
        await _drain_profile_task(sidebar.controller)
        _process(sidebar.app)
        assert sidebar.identity.property("vipLabel") == label, kind


async def test_identity_profile_failure_falls_back_to_logged_in(sidebar):
    sidebar.service.profile_error = RuntimeError("boom")
    sidebar.service.authed = True
    sidebar.service.authStateChanged.emit()
    await _drain_profile_task(sidebar.controller)
    _process(sidebar.app)

    assert sidebar.identity.property("displayName") == "已登录"
    assert sidebar.identity.property("vipLabel") == ""


async def test_identity_logout_resets_to_login_entry(sidebar):
    sidebar.service.authed = True
    sidebar.service.authStateChanged.emit()
    await _drain_profile_task(sidebar.controller)
    _process(sidebar.app)
    assert sidebar.identity.property("displayName") == "鹿鸣"

    await sidebar.controller.logout_async()
    _process(sidebar.app)

    assert sidebar.identity.property("loggedIn") is False
    assert sidebar.identity.property("displayName") == "点击登录"
    assert sidebar.identity.property("vipLabel") == ""
