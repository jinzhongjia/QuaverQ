"""service.logout 契约: 退出登录时通知服务端注销 (music.login.LoginServer/Logout).

尽力而为: 未登录跳过; 服务端失败只 log 不抛, 不阻塞调用方后续的本地凭据清理.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qqmusic_api import Credential

from quaverq.core.service import QuaverService


def _svc_with_logout(logout, *, credential):
    """最小 mock client: 仅 login.logout + credential (供 _effective_credential 取)."""
    svc = QuaverService()
    svc._client = SimpleNamespace(
        login=SimpleNamespace(logout=logout),
        credential=credential,
    )
    return svc


async def test_logout_calls_server_with_current_credential():
    received: list[Credential] = []

    async def _logout(cred=None):
        received.append(cred)

    svc = _svc_with_logout(_logout, credential=Credential(musicid=1, musickey="k", str_musicid="1"))
    await svc.logout()
    assert len(received) == 1
    assert received[0].musickey == "k"


async def test_logout_noop_when_not_logged_in():
    called: list[object] = []

    async def _logout(cred=None):
        called.append(cred)

    svc = _svc_with_logout(_logout, credential=Credential())  # 空 musickey
    await svc.logout()
    assert called == []


async def test_logout_noop_when_no_client():
    svc = QuaverService()  # 未 connect, _client is None
    await svc.logout()  # 不应抛


async def test_logout_swallows_server_error():
    async def _logout(cred=None):
        raise RuntimeError("network down")

    svc = _svc_with_logout(_logout, credential=Credential(musicid=1, musickey="k", str_musicid="1"))
    await svc.logout()  # 服务端失败不上抛, 本地清理由调用方继续


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
