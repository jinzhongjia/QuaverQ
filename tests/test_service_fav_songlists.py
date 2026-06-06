"""service.get_fav_songlist 契约 (我收藏的歌单).

第一档 1.2: 走 _bypass_post music.musicasset.PlaylistFavRead/CgiGetPlaylistFavInfo,
和 get_fav_albums 同款 v_list 兼容: 0/1 项时 QQ 返回 dict 而非 list, 库的 pydantic
v2 jsonpath 直接挂; bypass + 手动 parse 避开.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from qqmusic_api import Credential

from quaverq.core.models import Playlist
from quaverq.core.service import CredentialExpiredError, QuaverService


def _svc_with_bypass(payload: dict[str, Any] | None) -> QuaverService:
    """构造一个 svc, 给定 _bypass_post 直接返回 payload."""
    svc = QuaverService()
    svc._client = SimpleNamespace(
        credential=Credential(musicid=1, musickey="k", str_musicid="1", encrypt_uin="EUIN_X"),
    )
    svc.credential = svc._client.credential

    async def _fake_bypass(module, method, param, *, require_login=False):
        # 必须带 euin / size / offset
        assert param.get("uin") or param.get("euin"), "fav_songlist 请求要带 uin/euin"
        assert "size" in param and "offset" in param
        return payload or {}

    svc._bypass_post = _fake_bypass  # type: ignore[assignment]
    return svc


async def test_get_fav_songlist_returns_empty_when_no_credential():
    svc = QuaverService()  # 无 client / 无 cred
    result = await svc.get_fav_songlist()
    assert result == []


async def test_get_fav_songlist_returns_empty_when_no_encrypt_uin():
    svc = QuaverService()
    svc._client = SimpleNamespace(credential=Credential(musicid=1, musickey="k", str_musicid="1"))
    svc.credential = svc._client.credential
    assert await svc.get_fav_songlist() == []


async def test_get_fav_songlist_parses_v_list_array():
    """正常多个收藏歌单: v_list 是 list."""
    payload = {
        "v_list": [
            {
                "id": 9527,
                "dirid": 201,
                "title": "周杰伦精选",
                "picurl": "https://example/p9527.jpg",
                "songnum": 30,
                "uin": "12345",
                "nickname": "歌单作者A",
            },
            {
                "id": 9528,
                "title": "夏日清凉",
                "picurl": "",
                "songnum": 12,
                "nickname": "歌单作者B",
            },
        ],
        "total": 2,
        "hasmore": 0,
    }
    svc = _svc_with_bypass(payload)
    result = await svc.get_fav_songlist()
    assert len(result) == 2
    assert all(isinstance(p, Playlist) for p in result)
    assert result[0].pid == "9527"
    assert result[0].name == "周杰伦精选"
    assert result[0].cover_url == "https://example/p9527.jpg"
    assert result[0].song_count == 30
    assert result[0].creator == "歌单作者A"
    assert result[1].pid == "9528"


async def test_get_fav_songlist_handles_v_list_as_single_dict():
    """边缘场景: 用户只收藏 1 个歌单时, QQ 直接返回 dict, 不能挂."""
    payload = {
        "v_list": {
            "id": 7777,
            "title": "孤独的一个",
            "picurl": "https://example/p7.jpg",
            "songnum": 5,
            "nickname": "某用户",
        }
    }
    svc = _svc_with_bypass(payload)
    result = await svc.get_fav_songlist()
    assert len(result) == 1
    assert result[0].pid == "7777"
    assert result[0].name == "孤独的一个"


async def test_get_fav_songlist_handles_empty_and_missing_v_list():
    """0 项: v_list 为 [] 或字段缺失."""
    svc1 = _svc_with_bypass({"v_list": []})
    assert await svc1.get_fav_songlist() == []
    svc2 = _svc_with_bypass({})
    assert await svc2.get_fav_songlist() == []


async def test_get_fav_songlist_raises_on_expired_credential():
    """bypass 层报登录过期 → 上抛 CredentialExpiredError, 让 controller 走清缓存路径."""
    svc = QuaverService()
    svc._client = SimpleNamespace(
        credential=Credential(musicid=1, musickey="k", str_musicid="1", encrypt_uin="EUIN_X"),
    )
    svc.credential = svc._client.credential

    async def _fake_bypass(*args, **kwargs):
        raise CredentialExpiredError("登录已过期")

    svc._bypass_post = _fake_bypass  # type: ignore[assignment]

    with pytest.raises(CredentialExpiredError):
        await svc.get_fav_songlist()


async def test_get_fav_songlist_skips_items_without_id():
    """脏数据防御: 没有 id/dissid 的条目直接跳过, 不爆破."""
    payload = {
        "v_list": [
            {"id": 1, "title": "可用"},
            {"title": "没有 id 的项"},
            {"id": 0, "title": "id=0 视作脏"},
        ]
    }
    svc = _svc_with_bypass(payload)
    result = await svc.get_fav_songlist()
    assert len(result) == 1
    assert result[0].pid == "1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
