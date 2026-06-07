"""service.get_song_info 契约 (第二档 2.4).

并发拉 song.get_detail / get_labels / get_producer, 合并为 SongInfo.
任一接口失败降级为空字段, 不抛 (跟相似/相关一致). 凭据过期透传.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qqmusic_api.core.exceptions import CredentialExpiredError as QQCredentialExpiredError

from quaverq.core.models import SongInfo
from quaverq.core.service import CredentialExpiredError, QuaverService


def _content(value: str, jumpurl: str = "") -> SimpleNamespace:
    return SimpleNamespace(value=value, jumpurl=jumpurl, id=0, show_type=0)


def _label(txt: str, *, type_: int = 0, species: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=0, tag_txt=txt, tag_icon="", tag_url="", tag_type=type_, species=species
    )


def _producer(name: str, mid: str = "") -> SimpleNamespace:
    return SimpleNamespace(type=0, name=name, icon="", scheme="", singer_mid=mid, follow=0)


def _group(title: str, names: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        producers=[_producer(n) for n in names],
        type=0,
    )


def _attach_mock(
    svc: QuaverService,
    *,
    detail_resp=None,
    detail_exc=None,
    labels_resp=None,
    labels_exc=None,
    producer_resp=None,
    producer_exc=None,
):
    async def _detail(value):
        if detail_exc is not None:
            raise detail_exc
        return detail_resp

    async def _labels(songid):
        if labels_exc is not None:
            raise labels_exc
        return labels_resp

    async def _producer_call(value):
        if producer_exc is not None:
            raise producer_exc
        return producer_resp

    svc._client = SimpleNamespace(
        song=SimpleNamespace(
            get_detail=_detail,
            get_labels=_labels,
            get_producer=_producer_call,
        )
    )


async def test_get_song_info_returns_empty_when_no_mid_or_id():
    svc = QuaverService()
    _attach_mock(
        svc,
        detail_resp=SimpleNamespace(),
        labels_resp=SimpleNamespace(labels=[]),
        producer_resp=SimpleNamespace(data=[]),
    )
    result = await svc.get_song_info("", 0)
    assert isinstance(result, SongInfo)
    assert result.language == ""
    assert result.tags == []


async def test_get_song_info_pulls_all_three_endpoints_concurrently():
    """三个接口都成功时, 字段全部就位."""
    svc = QuaverService()
    detail = SimpleNamespace(
        company=[_content("杰威尔音乐有限公司")],
        genre=[_content("Pop", jumpurl="http://x/")],
        intro=[_content("这是简介")],
        lan=[_content("国语")],
        pub_time=[_content("2003-07-31")],
        extras={"name": "晴天"},
    )
    labels = SimpleNamespace(
        labels=[
            _label("传唱TOP100", type_=0, species=8),
            _label("#Ballad Pop", type_=1, species=1),
            _label("飙升榜No.48", type_=2, species=1),
            _label("84%的人听完", type_=31, species=1),  # 噪声
            _label("24255 人在听", type_=23, species=5),  # 噪声
        ]
    )
    producer = SimpleNamespace(
        data=[
            _group("演唱", ["周杰伦"]),
            _group("作词", ["周杰伦"]),
            _group("作曲", ["周杰伦"]),
            _group("编曲", ["周杰伦"]),
            _group("制作人", ["周杰伦"]),
            _group("吉他", ["蔡科俊"]),
        ],
        reinforce_msg="词：周杰伦 / 曲：周杰伦 / 编曲：周杰伦",
    )
    _attach_mock(svc, detail_resp=detail, labels_resp=labels, producer_resp=producer)

    result = await svc.get_song_info("mid", 97773)

    assert result.language == "国语"
    assert result.genre == "Pop"
    assert result.company == "杰威尔音乐有限公司"
    assert result.publish_time == "2003-07-31"
    assert result.intro == "这是简介"
    # producers 按顺序透传
    titles = [g.title for g in result.producers]
    assert "作词" in titles and "作曲" in titles and "演唱" in titles


async def test_get_song_info_filters_noise_tags():
    """标签接口含统计/营销噪声 (type 20+ / species 3/4/5), 应过滤掉."""
    svc = QuaverService()
    labels = SimpleNamespace(
        labels=[
            _label("传唱TOP100", type_=0, species=8),
            _label("飙升榜No.48", type_=2, species=1),
            _label("#Ballad Pop", type_=1, species=1),
            _label("84%的人听完", type_=31, species=1),  # 应被过滤
            _label("24255 人在听", type_=23, species=5),  # 应被过滤
            _label("141517", type_=20, species=4),  # 应被过滤 (纯数字)
            _label("", type_=0, species=1),  # 应被过滤 (空)
        ]
    )
    _attach_mock(
        svc,
        detail_resp=SimpleNamespace(company=[], genre=[], intro=[], lan=[], pub_time=[], extras={}),
        labels_resp=labels,
        producer_resp=SimpleNamespace(data=[], reinforce_msg=""),
    )

    result = await svc.get_song_info("mid", 1)
    assert "传唱TOP100" in result.tags
    assert "飙升榜No.48" in result.tags
    assert "#Ballad Pop" in result.tags
    assert "84%的人听完" not in result.tags
    assert "24255 人在听" not in result.tags
    assert "141517" not in result.tags
    assert "" not in result.tags


async def test_get_song_info_splits_pipe_concat_awards_and_drops_too_long():
    """服务端 award 标签用 | 把多奖项拼成一长串, 应拆开; 单条过长 (>28 字符) 直接丢."""
    svc = QuaverService()
    labels = SimpleNamespace(
        labels=[
            _label("传唱TOP100", type_=0, species=8),
            # 拼接奖项, 拆出来其中两个奖项都 <28 字, 长的那个丢掉
            _label("金曲奖获奖|短奖项|" + ("超长奖项名字带年份" * 5), type_=0, species=2),
        ]
    )
    _attach_mock(
        svc,
        detail_resp=SimpleNamespace(company=[], genre=[], intro=[], lan=[], pub_time=[], extras={}),
        labels_resp=labels,
        producer_resp=SimpleNamespace(data=[], reinforce_msg=""),
    )

    result = await svc.get_song_info("mid", 1)
    assert "金曲奖获奖" in result.tags
    assert "短奖项" in result.tags
    # 拆出来仍 > 28 字的那条应被丢
    assert not any(len(t) > 28 for t in result.tags)


async def test_get_song_info_dedupes_tags():
    """拆完后重复的 tag 只留一次."""
    svc = QuaverService()
    labels = SimpleNamespace(
        labels=[
            _label("传唱TOP100", type_=0, species=8),
            _label("传唱TOP100|另一个", type_=0, species=2),
        ]
    )
    _attach_mock(
        svc,
        detail_resp=SimpleNamespace(company=[], genre=[], intro=[], lan=[], pub_time=[], extras={}),
        labels_resp=labels,
        producer_resp=SimpleNamespace(data=[], reinforce_msg=""),
    )
    result = await svc.get_song_info("mid", 1)
    assert result.tags.count("传唱TOP100") == 1
    assert "另一个" in result.tags


async def test_get_song_info_returns_empty_fields_when_endpoints_empty():
    svc = QuaverService()
    _attach_mock(
        svc,
        detail_resp=SimpleNamespace(company=[], genre=[], intro=[], lan=[], pub_time=[], extras={}),
        labels_resp=SimpleNamespace(labels=[]),
        producer_resp=SimpleNamespace(data=[], reinforce_msg=""),
    )
    result = await svc.get_song_info("mid", 1)
    assert result.language == ""
    assert result.genre == ""
    assert result.tags == []
    assert result.producers == []


async def test_get_song_info_partial_success_when_one_endpoint_fails():
    """labels 挂了不影响 detail/producer 的结果."""
    svc = QuaverService()
    _attach_mock(
        svc,
        detail_resp=SimpleNamespace(
            company=[],
            genre=[_content("Pop")],
            intro=[],
            lan=[_content("国语")],
            pub_time=[],
            extras={},
        ),
        labels_exc=RuntimeError("labels boom"),
        producer_resp=SimpleNamespace(data=[_group("作词", ["X"])], reinforce_msg=""),
    )
    result = await svc.get_song_info("mid", 1)
    assert result.language == "国语"
    assert result.genre == "Pop"
    assert result.tags == []  # labels 失败 → 降级为空
    assert len(result.producers) == 1
    assert result.producers[0].title == "作词"


async def test_get_song_info_raises_on_expired_credential():
    """凭据过期类异常需要透传, 让 controller 走清缓存路径."""
    svc = QuaverService()
    _attach_mock(
        svc,
        detail_exc=QQCredentialExpiredError(code=1000, data={}),
        labels_resp=SimpleNamespace(labels=[]),
        producer_resp=SimpleNamespace(data=[]),
    )
    with pytest.raises(CredentialExpiredError):
        await svc.get_song_info("mid", 1)


async def test_get_song_info_all_fail_returns_empty_song_info():
    """三个接口全挂时返回完全空的 SongInfo, 不崩."""
    svc = QuaverService()
    _attach_mock(
        svc,
        detail_exc=RuntimeError("boom1"),
        labels_exc=RuntimeError("boom2"),
        producer_exc=RuntimeError("boom3"),
    )
    result = await svc.get_song_info("mid", 1)
    assert isinstance(result, SongInfo)
    assert result.language == ""
    assert result.producers == []


async def test_get_song_info_uses_mid_for_detail_when_id_is_zero():
    """song_id=0 时 get_detail 应该用 mid 调用 (探针验证 mid 也行)."""
    svc = QuaverService()
    captured: list = []

    async def _detail(value):
        captured.append(value)
        return SimpleNamespace(
            company=[], genre=[], intro=[], lan=[_content("国语")], pub_time=[], extras={}
        )

    async def _labels(songid):
        return SimpleNamespace(labels=[])

    async def _producer_call(value):
        return SimpleNamespace(data=[], reinforce_msg="")

    svc._client = SimpleNamespace(
        song=SimpleNamespace(
            get_detail=_detail,
            get_labels=_labels,
            get_producer=_producer_call,
        )
    )

    await svc.get_song_info("songmid_xyz", 0)
    assert captured == ["songmid_xyz"]
