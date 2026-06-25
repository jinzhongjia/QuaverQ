"""get_song_url 取流前过期守卫.

根因 (memory: project-musickey-expiry-104003): musickey 3 天过期后 vkey 返 104003,
被当成灰色歌曲不续期 → 整段播不了. 修法是取流前用本地 `cred.is_expired()`
(零网络) 判定, 过期就先 `_try_refresh_credential()` 再取流.

为何不用"104003 就续期重试": 灰色歌曲合法返 104003, 那样会给每首灰歌加无谓续期往返.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from quaverq.core.service import QuaverService


def _song():
    return SimpleNamespace(mid="m1", media_mid="mm1", name="歌", singers=[], album_name="")


async def _playable_bypass(mid, order, *, media_mid=""):
    return {order[0]: ("http://cdn/ok", None)}


async def test_refreshes_when_credential_expired(monkeypatch):
    svc = QuaverService()
    svc.credential = SimpleNamespace(musickey="old", is_expired=lambda: True)
    calls: list[str] = []

    async def _refresh():
        calls.append("refresh")
        return False

    monkeypatch.setattr(svc, "_try_refresh_credential", _refresh)
    monkeypatch.setattr(svc, "_try_bypass_urls", _playable_bypass)

    url = await svc.get_song_url(_song(), quality_preference="balanced")

    assert calls == ["refresh"], "过期凭据取流前应续期一次"
    assert url is not None and url.url == "http://cdn/ok"


async def test_no_refresh_when_credential_valid(monkeypatch):
    svc = QuaverService()
    svc.credential = SimpleNamespace(musickey="ok", is_expired=lambda: False)
    calls: list[str] = []

    async def _refresh():
        calls.append("refresh")
        return False

    monkeypatch.setattr(svc, "_try_refresh_credential", _refresh)
    monkeypatch.setattr(svc, "_try_bypass_urls", _playable_bypass)

    await svc.get_song_url(_song())

    assert calls == [], "未过期凭据不应续期"


async def test_no_refresh_when_no_credential(monkeypatch):
    svc = QuaverService()
    svc.credential = None
    calls: list[str] = []

    async def _refresh():
        calls.append("refresh")
        return False

    monkeypatch.setattr(svc, "_try_refresh_credential", _refresh)
    monkeypatch.setattr(svc, "_try_bypass_urls", _playable_bypass)

    await svc.get_song_url(_song())

    assert calls == [], "未登录 (cred None) 不应触发续期"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
