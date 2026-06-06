"""service.get_fav_songlist 契约 (我收藏的歌单).

第一档 1.2: 走 0.6.1 库方法 ``client.user.get_fav_songlist`` 分页拉全部.
- SongList 基类用 ``AliasChoices`` 识别服务端 ``tid``/``name``/``logo`` 字段, 不会挂
- 服务端单页 cap=50, 必须循环 ``hasmore=1`` 翻页, 否则 113 项只能拿到 50
- 库 ``ValidationError`` 时回退 ``_bypass_post`` + 手动 parse (复用 0/1 项 v_list dict 兜底)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from qqmusic_api import Credential

from quaverq.core.models import Playlist
from quaverq.core.service import CredentialExpiredError, QuaverService


def _resp(playlists: list[dict[str, Any]], *, hasmore: int, total: int) -> SimpleNamespace:
    """模拟 UserFavSonglistResponse pydantic 对象 (库方法返回值)."""
    items = [SimpleNamespace(**p) for p in playlists]
    return SimpleNamespace(playlists=items, hasmore=hasmore, total=total)


def _attach_library_mock(svc: QuaverService, pages: list[SimpleNamespace]) -> list[dict[str, Any]]:
    """把分页响应按 page 顺序挂到 client.user.get_fav_songlist; 返回收到的请求记录."""
    calls: list[dict[str, Any]] = []
    pages_iter = iter(pages)

    async def _get_fav_songlist(euin, page=1, num=10, *, credential=None):
        calls.append({"euin": euin, "page": page, "num": num, "credential": credential})
        try:
            return next(pages_iter)
        except StopIteration as exc:
            raise AssertionError(f"页码 {page} 超出预设响应") from exc

    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_fav_songlist=_get_fav_songlist),
        credential=Credential(musicid=1, musickey="k", str_musicid="1", encrypt_uin="EUIN_X"),
    )
    svc.credential = svc._client.credential
    return calls


async def test_get_fav_songlist_returns_empty_when_no_credential():
    svc = QuaverService()
    assert await svc.get_fav_songlist() == []


async def test_get_fav_songlist_returns_empty_when_no_encrypt_uin():
    svc = QuaverService()
    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_fav_songlist=lambda *a, **k: None),
        credential=Credential(musicid=1, musickey="k", str_musicid="1"),
    )
    svc.credential = svc._client.credential
    assert await svc.get_fav_songlist() == []


async def test_get_fav_songlist_parses_library_alias_fields():
    """SongList 基类 AliasChoices 让 tid/name/logo 都映射到 id/title/picurl."""
    svc = QuaverService()
    _attach_library_mock(
        svc,
        [
            _resp(
                [
                    {
                        "id": 8317276554,
                        "title": "停止联系，是我们做过最默契的事",
                        "picurl": "http://qpic/p1.jpg",
                        "songnum": 50,
                        "nickname": "用户A",
                    },
                    {
                        "id": 7709152142,
                        "title": "欧美励志",
                        "picurl": "http://qpic/p2.jpg",
                        "songnum": 20,
                        "nickname": "用户B",
                    },
                ],
                hasmore=0,
                total=2,
            )
        ],
    )

    result = await svc.get_fav_songlist()
    assert len(result) == 2
    assert all(isinstance(p, Playlist) for p in result)
    assert result[0].pid == "8317276554"
    assert result[0].name == "停止联系，是我们做过最默契的事"
    assert result[0].cover_url == "http://qpic/p1.jpg"
    assert result[0].creator == "用户A"
    assert result[0].song_count == 50


async def test_get_fav_songlist_paginates_until_hasmore_zero():
    """113 项总计, 单页 50: 必须翻 3 页 (50 + 50 + 13)."""
    svc = QuaverService()
    page1 = _resp(
        [{"id": i, "title": f"P{i}", "picurl": "", "songnum": 1} for i in range(1, 51)],
        hasmore=1,
        total=113,
    )
    page2 = _resp(
        [{"id": i, "title": f"P{i}", "picurl": "", "songnum": 1} for i in range(51, 101)],
        hasmore=1,
        total=113,
    )
    page3 = _resp(
        [{"id": i, "title": f"P{i}", "picurl": "", "songnum": 1} for i in range(101, 114)],
        hasmore=0,
        total=113,
    )
    calls = _attach_library_mock(svc, [page1, page2, page3])

    result = await svc.get_fav_songlist()

    assert len(result) == 113
    assert {p.pid for p in result} == {str(i) for i in range(1, 114)}
    assert [c["page"] for c in calls] == [1, 2, 3]
    assert all(c["num"] == 50 for c in calls), "页大小取上限 50 减少请求次数"
    assert all(c["euin"] == "EUIN_X" for c in calls)


async def test_get_fav_songlist_stops_on_empty_page_guard():
    """防 server bug: 即使 hasmore=1 但返回空列表也要停, 否则死循环."""
    svc = QuaverService()
    _attach_library_mock(
        svc,
        [
            _resp([{"id": 1, "title": "A"}], hasmore=1, total=10),
            _resp([], hasmore=1, total=10),  # server 错误地说还有, 但实际给空
        ],
    )
    result = await svc.get_fav_songlist()
    assert len(result) == 1


async def test_get_fav_songlist_raises_on_expired_credential():
    """库方法抛过期错 → 上抛 CredentialExpiredError 让 controller 走清缓存路径."""
    svc = QuaverService()

    async def _expired(*args, **kwargs):
        raise CredentialExpiredError("登录已过期")

    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_fav_songlist=_expired),
        credential=Credential(musicid=1, musickey="k", str_musicid="1", encrypt_uin="EUIN_X"),
    )
    svc.credential = svc._client.credential

    with pytest.raises(CredentialExpiredError):
        await svc.get_fav_songlist()


async def test_get_fav_songlist_falls_back_to_bypass_on_validation_error(monkeypatch):
    """库 pydantic 校验挂 (例如 0/1 项 v_list 是 dict) → 自动退 bypass + 手动 parse."""
    from pydantic import ValidationError

    svc = QuaverService()

    async def _validation_fail(*args, **kwargs):
        # 构造一个真实的 ValidationError (用 line_errors 列表)
        raise ValidationError.from_exception_data("UserFavSonglistResponse", [])

    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_fav_songlist=_validation_fail),
        credential=Credential(musicid=1, musickey="k", str_musicid="1", encrypt_uin="EUIN_X"),
    )
    svc.credential = svc._client.credential

    async def _fake_bypass(module, method, param, *, require_login=False):
        return {
            "v_list": {  # 单项时 dict
                "tid": 6561218699,
                "name": "影翼的新歌推荐",
                "logo": "http://qpic/p.jpg",
                "songnum": 30,
                "nickname": "影翼",
            }
        }

    monkeypatch.setattr(svc, "_bypass_post", _fake_bypass)

    result = await svc.get_fav_songlist()
    assert len(result) == 1
    assert result[0].pid == "6561218699"
    assert result[0].name == "影翼的新歌推荐"
    assert result[0].cover_url == "http://qpic/p.jpg"


async def test_parse_fav_songlists_accepts_server_field_names():
    """bypass parser 需要认服务端实际返回的 tid/name/logo 字段名."""
    data = {
        "v_list": [
            {
                "tid": 6561218699,
                "name": "影翼的新歌推荐",
                "logo": "http://qpic/p1.jpg",
                "songnum": 30,
                "nickname": "影翼",
            },
            {
                "id": 7777,  # 老格式
                "title": "老歌",
                "picurl": "http://qpic/p2.jpg",
                "songnum": 12,
                "nickname": "某人",
            },
        ]
    }
    result = QuaverService._parse_fav_songlists(data)
    assert len(result) == 2
    assert result[0].pid == "6561218699"
    assert result[0].name == "影翼的新歌推荐"
    assert result[0].cover_url == "http://qpic/p1.jpg"
    assert result[1].pid == "7777"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
