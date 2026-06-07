"""service.probe_login_expired 静默续命契约 (login.refresh_credential).

第一档 1.1: check_expired==True 时, 自动尝试 refresh_credential, 成功 → 续命; 失败 → 走旧 expired 流程.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from qqmusic_api import Credential
from qqmusic_api.core.exceptions import (
    CredentialExpiredError as QQCredentialExpiredError,
    CredentialRefreshError as QQCredentialRefreshError,
)

from quaverq.core.service import QuaverService


def _fake_client(*, check_expired, refresh_credential):
    """构造最小 mock client: 仅 login.{check_expired, refresh_credential} + credential."""
    return SimpleNamespace(
        login=SimpleNamespace(
            check_expired=check_expired,
            refresh_credential=refresh_credential,
        ),
        credential=Credential(musicid=1, musickey="old", str_musicid="1"),
    )


async def test_probe_returns_false_when_not_expired_and_does_not_refresh():
    calls: list[str] = []

    async def _check_expired() -> bool:
        calls.append("check")
        return False

    async def _refresh(*args, **kwargs) -> Credential:
        calls.append("refresh")
        raise AssertionError("不应被调用")

    svc = QuaverService()
    svc._client = _fake_client(check_expired=_check_expired, refresh_credential=_refresh)

    assert await svc.probe_login_expired() is False
    assert calls == ["check"]


async def test_probe_silently_refreshes_when_check_expired_returns_true(monkeypatch):
    """check_expired==True → refresh_credential 成功 → 返回 False, 新 cred 同步并落盘."""
    new_cred = Credential(musicid=2, musickey="fresh", str_musicid="2")

    async def _check_expired() -> bool:
        return True

    async def _refresh(*args, **kwargs) -> Credential:
        return new_cred

    saved: list[Credential | None] = []

    async def _save_credential(path=None):
        saved.append(svc._effective_credential())

    svc = QuaverService()
    svc._client = _fake_client(check_expired=_check_expired, refresh_credential=_refresh)
    monkeypatch.setattr(svc, "save_credential", _save_credential)

    result = await svc.probe_login_expired()

    assert result is False, "刷新成功后应当报告未过期"
    assert svc._effective_credential().musickey == "fresh"
    assert svc._client.credential.musickey == "fresh"
    assert saved and saved[-1].musickey == "fresh", "刷新后的凭据要落盘"


async def test_probe_returns_true_when_refresh_credential_fails(monkeypatch):
    async def _check_expired() -> bool:
        return True

    async def _refresh(*args, **kwargs) -> Credential:
        raise QQCredentialRefreshError("refresh_token expired", code=2001, data={})

    saved: list[Credential | None] = []

    async def _save_credential(path=None):
        saved.append(svc._effective_credential())

    svc = QuaverService()
    svc._client = _fake_client(check_expired=_check_expired, refresh_credential=_refresh)
    monkeypatch.setattr(svc, "save_credential", _save_credential)

    result = await svc.probe_login_expired()

    assert result is True, "刷新失败应当报告仍然过期"
    assert svc._effective_credential().musickey == "old", "刷新失败不应丢弃旧凭据"
    assert saved == [], "刷新失败不应落盘"


async def test_probe_tries_refresh_when_check_expired_raises_expired_exception(monkeypatch):
    """check_expired 本身抛 QQCredentialExpiredError 也应尝试刷新 (服务端拦截路径)."""
    new_cred = Credential(musicid=3, musickey="fresh-from-exc", str_musicid="3")

    async def _check_expired() -> bool:
        raise QQCredentialExpiredError(code=1000, data={})

    async def _refresh(*args, **kwargs) -> Credential:
        return new_cred

    async def _save_credential(path=None):
        return None

    svc = QuaverService()
    svc._client = _fake_client(check_expired=_check_expired, refresh_credential=_refresh)
    monkeypatch.setattr(svc, "save_credential", _save_credential)

    assert await svc.probe_login_expired() is False
    assert svc._effective_credential().musickey == "fresh-from-exc"


async def test_probe_returns_none_when_check_expired_raises_generic_error():
    """非过期类异常 (网络抖动等) 不应触发刷新, 维持原来"无法判定"语义."""
    refresh_called: list[bool] = []

    async def _check_expired() -> bool:
        raise RuntimeError("network glitch")

    async def _refresh(*args, **kwargs) -> Credential:
        refresh_called.append(True)
        raise AssertionError("不应被调用")

    svc = QuaverService()
    svc._client = _fake_client(check_expired=_check_expired, refresh_credential=_refresh)

    assert await svc.probe_login_expired() is None
    assert refresh_called == []


async def test_probe_returns_true_when_refresh_returns_empty_credential(monkeypatch):
    """refresh_credential 返回缺 musickey 的脏数据要被视作失败, 不能误认为成功."""

    async def _check_expired() -> bool:
        return True

    async def _refresh(*args, **kwargs) -> Credential:
        return Credential()  # musickey 为空

    async def _save_credential(path=None):
        return None

    svc = QuaverService()
    svc._client = _fake_client(check_expired=_check_expired, refresh_credential=_refresh)
    monkeypatch.setattr(svc, "save_credential", _save_credential)

    assert await svc.probe_login_expired() is True
    assert svc._effective_credential().musickey == "old"


async def test_concurrent_probes_only_trigger_single_refresh(monkeypatch):
    """两个协程同时 probe → refresh_credential 只被实际调用一次 (token rotation 防御).

    场景: 多 controller 路径并发触发 probe_login_expired, 不能各自再发起一次 refresh.
    refresh_token 通常是一次性 (rotation), 第二次刷新会拿到失效 token, 整条续命链断裂.
    """
    new_cred = Credential(musicid=42, musickey="rotated", str_musicid="42")
    refresh_calls = 0
    save_calls = 0

    refresh_started = asyncio.Event()
    refresh_unblock = asyncio.Event()

    async def _check_expired() -> bool:
        return True

    async def _refresh(*args, **kwargs) -> Credential:
        nonlocal refresh_calls
        refresh_calls += 1
        refresh_started.set()
        await refresh_unblock.wait()  # 给第二个协程跑到锁前的时间窗
        return new_cred

    async def _save_credential(path=None):
        nonlocal save_calls
        save_calls += 1

    svc = QuaverService()
    svc._client = _fake_client(check_expired=_check_expired, refresh_credential=_refresh)
    monkeypatch.setattr(svc, "save_credential", _save_credential)

    async def _race():
        # 第一个协程先起跑, 让它进入 refresh 阻塞点
        first = asyncio.create_task(svc.probe_login_expired())
        await refresh_started.wait()
        # 第二个协程在这时启动: 它应被锁挡住, 不应触发第二次 refresh
        second = asyncio.create_task(svc.probe_login_expired())
        # 给 second 一些时间跑到锁前
        await asyncio.sleep(0.01)
        refresh_unblock.set()
        return await asyncio.gather(first, second)

    results = await _race()

    assert results == [False, False], "两个 probe 都应报告未过期"
    assert refresh_calls == 1, f"refresh_credential 应只被实际调用一次, 实际 {refresh_calls}"
    assert save_calls == 1, f"save_credential 应只落盘一次, 实际 {save_calls}"
    assert svc._effective_credential().musickey == "rotated"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
