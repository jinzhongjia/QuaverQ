"""_bypass_post 消费方的解析契约: 服务端字段漂移 / 缺失 / 空响应时降级而非炸.

这些路径走未公开原始接口 (musicu.fcg), 字段名随服务端变是常态; 解析函数的
契约是"缺什么降什么", 绝不向上抛 KeyError / TypeError / IndexError.
"""

from __future__ import annotations

from qqmusic_api import Credential

from quaverq.core.service import QuaverService


def _svc() -> QuaverService:
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    return svc


def _stub(svc: QuaverService, payload):
    """把 _bypass_post 替成固定返回; payload 可调用时按调用次数取值."""
    calls: list[tuple[str, str, dict]] = []

    async def fake_post(module, method, param, **_kwargs):
        calls.append((module, method, param))
        return payload(len(calls)) if callable(payload) else payload

    svc._bypass_post = fake_post
    return calls


# ------------------------------------------------------------------ vkey 播放链
# _try_bypass_url 返回 (url, vkey_result 码): 失败时码随日志透出 (104003=无版权/不可下发),
# 排查不可播曲目不用再写探针.


async def test_vkey_happy_path_builds_cdn_url():
    svc = _svc()
    _stub(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})

    url, code = await svc._try_bypass_url("abc", "MP3_128")
    assert url == "https://isure.stream.qqmusic.qq.com/M500abcabc.mp3?vkey=XYZ"
    assert code is None


async def test_vkey_unknown_quality_label_short_circuits():
    svc = _svc()
    calls = _stub(svc, {"midurlinfo": [{"purl": "x"}]})

    assert await svc._try_bypass_url("abc", "APE_LOSSLESS") == (None, None)
    # 未知档位不应发请求
    assert calls == []


async def test_vkey_none_response_returns_none():
    svc = _svc()
    _stub(svc, None)
    assert await svc._try_bypass_url("abc", "MP3_128") == (None, None)


async def test_vkey_missing_midurlinfo_returns_none():
    svc = _svc()
    _stub(svc, {"servercheck": 1})
    assert await svc._try_bypass_url("abc", "MP3_128") == (None, None)


async def test_vkey_non_dict_entry_returns_none():
    # 服务端字段漂移: midurlinfo 元素不是 dict 时不能 TypeError
    svc = _svc()
    _stub(svc, {"midurlinfo": ["oops"]})
    assert await svc._try_bypass_url("abc", "MP3_128") == (None, None)


async def test_vkey_empty_purl_returns_result_code():
    # 版权/区域限制: purl 置空 + result 码 (104003=无版权; 真机排查 mid=000VBS162wAFkB 实测)
    svc = _svc()
    _stub(svc, {"midurlinfo": [{"purl": "", "result": 104003}]})

    url, code = await svc._try_bypass_url("abc", "FLAC")
    assert url is None
    assert code == 104003


async def test_vkey_media_mid_overrides_filename():
    svc = _svc()
    calls = _stub(svc, {"midurlinfo": [{"purl": "p"}]})

    await svc._try_bypass_url("abc", "MP3_128", media_mid="mmid")
    assert calls[0][2]["filename"] == ["M500mmidmmid.mp3"]
    assert calls[0][2]["songmid"] == ["abc"]


async def test_get_song_url_warning_carries_vkey_result(caplog):
    # 所有音质拒发时, warning 必须带 result 码 (一眼定性版权问题, 免再写探针)
    import logging

    from quaverq.core.models import Song

    svc = _svc()
    _stub(svc, {"midurlinfo": [{"purl": "", "result": 104003}]})

    with caplog.at_level(logging.WARNING, logger="quaverq.core.service"):
        result = await svc.get_song_url(Song(mid="bad1", name="灰歌"))

    assert result is None
    assert any("104003" in rec.getMessage() for rec in caplog.records)


# ------------------------------------------------------------------ 排行榜详情


async def test_top_detail_maps_snake_case_fields():
    svc = _svc()
    _stub(
        svc,
        {
            "data": {
                "name": "飙升榜",
                "front_pic_url": "https://img/front.jpg",
                "intro": "规则文本",
                "total_num": 100,
                "listen_num": 12345,
                "songInfoList": [
                    {
                        "mid": "",
                        "songMid": "sm1",
                        "songId": 7,
                        "title": "歌一",
                        "singerMid": "sg1",
                        "singerName": "歌手",
                        "albumMid": "al1",
                    },
                ],
            }
        },
    )

    pl = await svc.get_top_detail(4)
    assert pl.pid == "4"
    assert pl.name == "飙升榜"
    assert pl.cover_url == "https://img/front.jpg"
    assert pl.description == "规则文本"
    assert pl.song_count == 100
    assert pl.play_count == 12345
    assert [s.mid for s in pl.songs] == ["sm1"]
    assert pl.songs[0].name == "歌一"
    assert pl.songs[0].singers[0].name == "歌手"


async def test_top_detail_camel_case_and_flat_shape():
    # 字段漂移: 顶层平铺 + camelCase + song 简表字段
    svc = _svc()
    _stub(
        svc,
        {
            "title": "巅峰潮流榜",
            "frontPicUrl": "https://img/camel.jpg",
            "totalNum": "50",
            "listenNum": "999",
            "song": [{"mid": "", "songMid": "sm2", "name": "歌二"}],
        },
    )

    pl = await svc.get_top_detail(135)
    assert pl.name == "巅峰潮流榜"
    assert pl.cover_url == "https://img/camel.jpg"
    assert pl.song_count == 50
    assert pl.play_count == 999
    # 某些榜服务端本就无 intro (tid=135 这类), 容空不是错误
    assert pl.description == ""
    assert [s.mid for s in pl.songs] == ["sm2"]


async def test_top_detail_none_response_returns_placeholder():
    svc = _svc()
    _stub(svc, None)

    pl = await svc.get_top_detail(26)
    assert pl.pid == "26"
    assert pl.name == "榜单不可用"
    assert pl.songs == []


async def test_top_detail_request_error_returns_placeholder():
    svc = _svc()

    async def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    svc._bypass_post = boom
    pl = await svc.get_top_detail(26)
    assert pl.name == "榜单不可用"
    assert pl.songs == []


# ------------------------------------------------------------------ 新歌速递


async def test_new_songs_accepts_songs_field_alias():
    svc = _svc()
    _stub(svc, {"songs": [{"mid": "n1", "name": "新歌", "singer": [], "album": {}}]})

    songs = await svc.get_recommend_new_songs(limit=5)
    assert [s.mid for s in songs] == ["n1"]


async def test_new_songs_none_response_not_poisoning_memo():
    # 失败 (None) 不该写 memo 缓存; 下一次调用要能拿到真数据
    svc = _svc()
    _stub(
        svc,
        lambda n: (
            None
            if n == 1
            else {"songlist": [{"mid": "n2", "name": "第二次", "singer": [], "album": {}}]}
        ),
    )

    assert await svc.get_recommend_new_songs() == []
    songs = await svc.get_recommend_new_songs()
    assert [s.mid for s in songs] == ["n2"]


# ------------------------------------------------------------------ 歌词


async def test_lyric_lrc_invalid_base64_degrades_to_empty():
    # 服务端返回坏 base64 时整首歌词降级为空, 不向上抛 binascii.Error
    svc = _svc()
    _stub(svc, {"lyric": "!!!not-base64!!!", "trans": ""})

    lyric = await svc._get_lyric_lrc("m1", with_translation=True)
    assert lyric.lines == []
    assert lyric.has_translation is False


async def test_qrc_none_block_returns_empty_lines():
    svc = _svc()
    _stub(svc, None)
    assert await svc._try_get_qrc("m1", with_translation=True) == []
