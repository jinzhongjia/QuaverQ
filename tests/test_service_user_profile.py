"""get_user_profile / _parse_user_profile 契约测试.

数据面方案见 docs/plan/search-user-profile-vip-api.md:
- 昵称 / 头像来自 ``client.user.get_homepage`` (UserHomepageResponse.base_info)
- VIP 种类来自 ``client.user.get_vip_info`` (UserVipInfoResponse, 上游 #258 起
  携带 identity 身份块), 徽章优先级 SVIP > 豪华绿钻 > 绿钻 > 无
- 任一请求失败不挡另一半; 双失败返 None; 凭据过期统一抛 CredentialExpiredError
"""

from types import SimpleNamespace

import pytest

from quaverq.core.models import UserProfile
from quaverq.core.service import CredentialExpiredError, QuaverService

# ============================================================== _parse_user_profile (纯函数)


def _homepage(name="鹿鸣", avatar="http://thirdqq.qlogo.cn/g?b=sdk&k=abc&s=140"):
    return SimpleNamespace(base_info=SimpleNamespace(name=name, avatar=avatar))


def _vip_info(
    *,
    svip=0,
    vip=0,
    huge_vip=0,
    year_flag=0,
    huge_year_flag=0,
    icon="https://y.qq.com/mediastyle/global/vip_icon/lv_7.png",
):
    return SimpleNamespace(
        svip=svip,
        identity=SimpleNamespace(
            vip=vip,
            huge_vip=huge_vip,
            year_flag=year_flag,
            huge_year_flag=huge_year_flag,
            icon=icon,
        ),
    )


def test_parse_profile_full():
    p = QuaverService._parse_user_profile(_homepage(), _vip_info(vip=1, huge_vip=1))
    assert p.nickname == "鹿鸣"
    assert p.avatar_url.startswith("http://thirdqq.qlogo.cn/")
    assert p.vip_kind == "hugevip"
    assert p.vip_icon_url.endswith("lv_7.png")


def test_parse_profile_svip_wins_over_hugevip():
    p = QuaverService._parse_user_profile(None, _vip_info(svip=1, vip=1, huge_vip=1))
    assert p.vip_kind == "svip"


def test_parse_profile_plain_green_vip():
    p = QuaverService._parse_user_profile(None, _vip_info(vip=1))
    assert p.vip_kind == "vip"


def test_parse_profile_non_vip_hides_badge():
    """非会员: 不显示负面标签, 服务端等级 icon 一并抑制."""
    p = QuaverService._parse_user_profile(_homepage(), _vip_info())
    assert p.vip_kind == ""
    assert p.vip_icon_url == ""
    assert p.is_year_vip is False


def test_parse_profile_year_flags():
    assert QuaverService._parse_user_profile(None, _vip_info(vip=1, year_flag=1)).is_year_vip
    assert QuaverService._parse_user_profile(
        None, _vip_info(huge_vip=1, huge_year_flag=1)
    ).is_year_vip
    assert not QuaverService._parse_user_profile(None, _vip_info(vip=1)).is_year_vip


def test_parse_profile_homepage_missing_keeps_vip_half():
    p = QuaverService._parse_user_profile(None, _vip_info(svip=1))
    assert p.nickname == ""
    assert p.avatar_url == ""
    assert p.vip_kind == "svip"


def test_parse_profile_vip_missing_keeps_identity_half():
    p = QuaverService._parse_user_profile(_homepage(), None)
    assert p.nickname == "鹿鸣"
    assert p.vip_kind == ""
    assert p.vip_icon_url == ""


def test_parse_profile_nickname_cleaned():
    """昵称走 _clean_text: 折空白 + 40 字截断加省略号, 不让超长昵称撑爆侧栏."""
    p = QuaverService._parse_user_profile(_homepage(name="昵  称\n" + "长" * 100), None)
    assert p.nickname.startswith("昵 称")  # 多空白折单空格
    assert len(p.nickname) <= 41  # max_len=40 + "…"
    assert p.nickname.endswith("…")


def test_parse_profile_upstream_model_contract():
    """真 pydantic 模型走一遍: 调研记录的原始响应形状 -> 上游模型 -> 我们的解析.

    防上游 #258 之后字段改名/挪位导致解析静默落空 (alias 漂移即红).
    """
    from qqmusic_api.models.user import UserVipInfoResponse

    raw = {
        "svip": 0,
        "identity": {
            "vip": 1,
            "HugeVip": 1,
            "HugeVipStart": "2024-01-01 00:00:00",
            "HugeVipEnd": "2027-01-01 00:00:00",
            "yearflag": 0,
            "HugeYearFlag": 1,
            "icon": "https://y.qq.com/mediastyle/global/vip_icon/lv_7.png",
            "purchaseUrl": "https://y.qq.com/portal/vipportal/index.html",
        },
        "userinfo": {"expire": 1798675200, "music_level": 7},
    }
    vip_info = UserVipInfoResponse.model_validate(raw)
    p = QuaverService._parse_user_profile(None, vip_info)
    assert p.vip_kind == "hugevip"
    assert p.is_year_vip is True
    assert p.vip_icon_url.endswith("lv_7.png")


# ============================================================== get_user_profile (并发 + 容错)


class _RequestLike:
    """还原 qqmusic-api ``Request`` 的真实形态: awaitable 但 **unhashable**.

    库的 ``client.user.get_homepage()`` 是同步方法, 返回实现了 ``__await__`` 的
    Request 对象 (pydantic 系 ``__eq__`` 无 ``__hash__``). 直接塞进
    ``asyncio.gather`` 会在其内部去重 dict 查找时炸
    ``TypeError: unhashable type: 'Request'`` —— 真机实测踩到, async-def mock
    是真 coroutine 暴露不了 (2026-06-12 回归).
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


def _cred():
    return SimpleNamespace(encrypt_uin="euin42", musickey="key", musicid=7)


def _svc_with_user_api(get_homepage, get_vip_info):
    svc = QuaverService()
    svc._effective_credential = _cred
    svc._client = SimpleNamespace(
        user=SimpleNamespace(get_homepage=get_homepage, get_vip_info=get_vip_info)
    )
    return svc


async def test_get_user_profile_no_credential_returns_none():
    svc = QuaverService()
    svc._effective_credential = lambda: None
    assert await svc.get_user_profile() is None


async def test_get_user_profile_merges_both_halves():
    async def homepage(euin, *, credential=None):
        return _homepage()

    async def vip(*, credential=None):
        return _vip_info(svip=1)

    profile = await _svc_with_user_api(homepage, vip).get_user_profile()
    assert isinstance(profile, UserProfile)
    assert profile.nickname == "鹿鸣"
    assert profile.vip_kind == "svip"


async def test_get_user_profile_passes_euin_and_credential():
    captured: dict[str, object] = {}

    async def homepage(euin, *, credential=None):
        captured["euin"] = euin
        captured["credential"] = credential
        return _homepage()

    async def vip(*, credential=None):
        captured["vip_credential"] = credential
        return _vip_info()

    await _svc_with_user_api(homepage, vip).get_user_profile()
    assert captured["euin"] == "euin42"
    assert captured["credential"] is not None
    assert captured["vip_credential"] is not None


async def test_get_user_profile_survives_one_failure():
    async def homepage(euin, *, credential=None):
        raise RuntimeError("homepage boom")

    async def vip(*, credential=None):
        return _vip_info(vip=1)

    profile = await _svc_with_user_api(homepage, vip).get_user_profile()
    assert profile is not None
    assert profile.nickname == ""
    assert profile.vip_kind == "vip"


async def test_get_user_profile_none_when_both_fail():
    async def homepage(euin, *, credential=None):
        raise RuntimeError("boom")

    async def vip(*, credential=None):
        raise RuntimeError("boom")

    assert await _svc_with_user_api(homepage, vip).get_user_profile() is None


async def test_get_user_profile_accepts_library_request_objects():
    """库 API 返回 Request 对象 (同步方法 + awaitable + unhashable), 并发路径必须兼容."""

    def homepage(euin, *, credential=None):
        return _RequestLike(_homepage())

    def vip(*, credential=None):
        return _RequestLike(_vip_info(svip=1))

    profile = await _svc_with_user_api(homepage, vip).get_user_profile()
    assert profile is not None
    assert profile.nickname == "鹿鸣"
    assert profile.vip_kind == "svip"


async def test_get_user_profile_raises_on_expired_credential():
    async def homepage(euin, *, credential=None):
        return _homepage()

    async def vip(*, credential=None):
        exc = RuntimeError("login expired")
        exc.code = 104401
        raise exc

    with pytest.raises(CredentialExpiredError):
        await _svc_with_user_api(homepage, vip).get_user_profile()
