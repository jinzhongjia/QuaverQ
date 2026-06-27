"""get_radar_recommend 契约测试.

雷达推荐 (个性化分页流) 设计见 docs/plan/search-radar-recommend.md:
- API: ``client.recommend.get_radar_recommend(page=1)`` -> RadarRecommendResponse
- **不传 credential=**: 登录态走 client 全局凭据 (service.py 设置 _client.credential),
  ``get_radar_recommend`` 本身不接受 credential 参数, 传了会 TypeError.
- 返回 ``(list[Song], has_more)``: 单页歌曲 + 是否还有下一页; 分页游标由上层 controller 管.
- 空 mid 过滤; 异常吞掉返 ([], False); 不缓存 (推荐流实时).
"""

from types import SimpleNamespace

from quaverq.core.models import Song
from quaverq.core.service import QuaverService


def _song(mid="m1", name="歌曲"):
    """最小歌曲 mock: _to_song 经 _g(getattr/get, default) 读字段, 缺省字段安全降级."""
    return SimpleNamespace(mid=mid, name=name)


def _radar_resp(songs, has_more=True):
    return SimpleNamespace(songs=list(songs), has_more=has_more)


class _RequestLike:
    """还原 qqmusic-api Request: 同步方法返回的 awaitable 但 unhashable 对象.

    见 tests/test_service_user_profile.py 的同名类; 雷达虽是串行单页 (不 gather),
    仍验证 await 路径兼容库的真实返回形态.
    """

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, result):
        self._result = result

    def __eq__(self, other):
        return self is other

    def __await__(self):
        async def _run():
            return self._result

        return _run().__await__()


def _svc_with_radar(get_radar_recommend):
    svc = QuaverService()
    svc._client = SimpleNamespace(
        recommend=SimpleNamespace(get_radar_recommend=get_radar_recommend)
    )
    return svc


async def test_returns_songs_and_has_more():
    async def radar(*, page=1):
        return _radar_resp([_song("m1", "A"), _song("m2", "B")], has_more=True)

    songs, has_more = await _svc_with_radar(radar).get_radar_recommend()
    assert has_more is True
    assert [s.mid for s in songs] == ["m1", "m2"]
    assert all(isinstance(s, Song) for s in songs)


async def test_filters_empty_mid():
    async def radar(*, page=1):
        return _radar_resp([_song("m1", "A"), _song("", "无 mid"), _song("m3", "C")])

    songs, _ = await _svc_with_radar(radar).get_radar_recommend()
    assert [s.mid for s in songs] == ["m1", "m3"]


async def test_error_returns_empty():
    async def radar(*, page=1):
        raise RuntimeError("boom")

    assert await _svc_with_radar(radar).get_radar_recommend() == ([], False)


async def test_missing_has_more_defaults_false():
    async def radar(*, page=1):
        return SimpleNamespace(songs=[_song("m1")])  # 无 has_more 字段

    _, has_more = await _svc_with_radar(radar).get_radar_recommend()
    assert has_more is False


async def test_passes_page_and_no_credential_kwarg():
    captured: dict[str, object] = {}

    def radar(*, page=1, **kwargs):
        captured["page"] = page
        captured["kwargs"] = kwargs
        return _RequestLike(_radar_resp([_song("m1")], has_more=False))

    svc = _svc_with_radar(radar)
    songs, has_more = await svc.get_radar_recommend(page=3)
    assert captured["page"] == 3
    # 关键契约: 不传 credential= (库不接受, 走 client 全局凭据)
    assert "credential" not in captured["kwargs"]
    assert [s.mid for s in songs] == ["m1"]
    assert has_more is False


async def test_empty_songs_returns_empty_list():
    async def radar(*, page=1):
        return _radar_resp([], has_more=False)

    songs, has_more = await _svc_with_radar(radar).get_radar_recommend()
    assert songs == []
    assert has_more is False
