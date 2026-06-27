"""service.fav_songlist / unfav_songlist 契约 (收藏 / 取消收藏外部歌单).

走 0.6.x 库方法 ``client.user.fav_songlist`` / ``unfav_songlist``
(module ``music.musicasset.PlaylistFavWrite`` / ``FavPlaylist``·``CancelFavPlaylist``):
- pid 是歌单 disstid/pid (字符串), 服务端要 int, 服务层负责转换
- 返回 bool; 库内部判 ``result == 0`` 且目标 id 不在 ``v_failedPlaylistId``
- 无凭据 / 非法 pid 直接返 False, 不打网络
- 凭据过期错上抛 CredentialExpiredError, 让 controller 走清缓存路径
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from qqmusic_api import Credential

from quaverq.core.service import CredentialExpiredError, QuaverService


def _attach_write_mock(
    svc: QuaverService, *, fav_result: Any = True, unfav_result: Any = True
) -> list[dict[str, Any]]:
    """挂 client.user.fav_songlist / unfav_songlist mock; 返回收到的请求记录."""
    calls: list[dict[str, Any]] = []

    async def _fav_songlist(songlist_id, *, credential=None):
        calls.append({"method": "fav", "songlist_id": songlist_id, "credential": credential})
        if isinstance(fav_result, Exception):
            raise fav_result
        return fav_result

    async def _unfav_songlist(songlist_id, *, credential=None):
        calls.append({"method": "unfav", "songlist_id": songlist_id, "credential": credential})
        if isinstance(unfav_result, Exception):
            raise unfav_result
        return unfav_result

    svc._client = SimpleNamespace(
        user=SimpleNamespace(fav_songlist=_fav_songlist, unfav_songlist=_unfav_songlist),
        credential=Credential(musicid=1, musickey="k", str_musicid="1", encrypt_uin="EUIN_X"),
    )
    svc.credential = svc._client.credential
    return calls


async def test_fav_songlist_returns_false_without_credential():
    svc = QuaverService()
    assert await svc.fav_songlist("9578424174") is False


async def test_unfav_songlist_returns_false_without_credential():
    svc = QuaverService()
    assert await svc.unfav_songlist("9578424174") is False


async def test_fav_songlist_calls_library_with_int_id_and_credential():
    svc = QuaverService()
    calls = _attach_write_mock(svc)
    assert await svc.fav_songlist("9578424174") is True
    assert calls == [{"method": "fav", "songlist_id": 9578424174, "credential": svc.credential}]


async def test_unfav_songlist_calls_library_with_int_id_and_credential():
    svc = QuaverService()
    calls = _attach_write_mock(svc)
    assert await svc.unfav_songlist("9578424174") is True
    assert calls == [{"method": "unfav", "songlist_id": 9578424174, "credential": svc.credential}]


async def test_fav_songlist_returns_false_on_api_failure():
    svc = QuaverService()
    _attach_write_mock(svc, fav_result=False)
    assert await svc.fav_songlist("9578424174") is False


async def test_fav_songlist_returns_false_on_invalid_pid_without_calling_api():
    svc = QuaverService()
    calls = _attach_write_mock(svc)
    assert await svc.fav_songlist("not-a-number") is False
    assert calls == []


async def test_fav_songlist_raises_on_expired_credential():
    svc = QuaverService()
    _attach_write_mock(svc, fav_result=CredentialExpiredError("登录已过期"))
    with pytest.raises(CredentialExpiredError):
        await svc.fav_songlist("9578424174")


async def test_unfav_songlist_raises_on_expired_credential():
    svc = QuaverService()
    _attach_write_mock(svc, unfav_result=CredentialExpiredError("登录已过期"))
    with pytest.raises(CredentialExpiredError):
        await svc.unfav_songlist("9578424174")
