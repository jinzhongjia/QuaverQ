"""音频 CDN 调度 (get_cdn_dispatch): 动态拿 CDN 根地址替代固定兜底域名.

bare-path purl 要拼一个 CDN host 才能播; 旧实现硬编码 isure.stream.qqmusic.qq.com,
改走 get_cdn_dispatch 让服务端按网络环境调度最优节点 + 按服务端给的 TTL 缓存,
失败 / 空 sip / 未连接时回落原固定兜底域名 (保证永远有可拼的 host).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from qqmusic_api import Credential

from quaverq.core.service import QuaverService

_FALLBACK = "https://isure.stream.qqmusic.qq.com/"


def _svc() -> QuaverService:
    svc = QuaverService()
    svc.credential = Credential(musicid=1, musickey="k")
    return svc


def _stub_bypass(svc: QuaverService, payload) -> None:
    async def fake_post(module, method, param, **_kwargs):
        return payload

    svc._bypass_post = fake_post


def _stub_dispatch(svc: QuaverService, *, sip, cache_time: int = 600, expiration: int = 600):
    """把 client.song.get_cdn_dispatch 替成固定返回; 返回调用计数列表."""
    calls: list[int] = []

    async def fake_dispatch():
        calls.append(1)
        return SimpleNamespace(sip=sip, sipinfo=[], cache_time=cache_time, expiration=expiration)

    svc._client = SimpleNamespace(
        song=SimpleNamespace(get_cdn_dispatch=fake_dispatch),
        credential=svc.credential,
    )
    return calls


async def test_bare_purl_uses_dispatched_cdn_host():
    # sip 不带 scheme / 尾斜杠也要被规整成 https + 单尾斜杠
    svc = _svc()
    _stub_bypass(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})
    _stub_dispatch(svc, sip=["http://ws6.stream.qqmusic.qq.com"])

    result = await svc._try_bypass_urls("abc", ("MP3_128",))
    assert result["MP3_128"] == (
        "https://ws6.stream.qqmusic.qq.com/M500abcabc.mp3?vkey=XYZ",
        None,
    )


async def test_skips_non_stream_host_picks_qqmusic_family():
    # 真机 sip[0]=aqqmusic.tc.qq.com 不在 StreamProxy 白名单 (.qqmusic.qq.com), 拼了会被代理拒 403;
    # 必须跳过它选第一个 .qqmusic.qq.com 族 host (实测 vkey purl 在 stream 家族全可用)
    svc = _svc()
    _stub_bypass(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})
    _stub_dispatch(
        svc,
        sip=[
            "http://aqqmusic.tc.qq.com/",
            "http://sjy6.stream.qqmusic.qq.com/",
            "http://ws6.stream.qqmusic.qq.com/",
        ],
    )

    result = await svc._try_bypass_urls("abc", ("MP3_128",))
    assert result["MP3_128"][0] == "https://sjy6.stream.qqmusic.qq.com/M500abcabc.mp3?vkey=XYZ"


async def test_only_incompatible_hosts_falls_back_to_fixed_domain():
    # sip 里全是非 .qqmusic.qq.com host: 没有可用的, 回落固定兜底域名
    svc = _svc()
    _stub_bypass(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})
    _stub_dispatch(svc, sip=["http://aqqmusic.tc.qq.com/", "https://other.cdn.example/"])

    result = await svc._try_bypass_urls("abc", ("MP3_128",))
    assert result["MP3_128"][0] == f"{_FALLBACK}M500abcabc.mp3?vkey=XYZ"


async def test_dispatch_cached_across_calls():
    svc = _svc()
    _stub_bypass(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})
    calls = _stub_dispatch(svc, sip=["http://ws6.stream.qqmusic.qq.com/"], cache_time=600)

    await svc._try_bypass_urls("abc", ("MP3_128",))
    await svc._try_bypass_urls("abc", ("MP3_128",))
    assert len(calls) == 1  # 第二次命中 TTL 缓存, 不再调度


async def test_dispatch_failure_falls_back_to_fixed_domain():
    svc = _svc()
    _stub_bypass(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})

    async def boom():
        raise RuntimeError("dispatch down")

    svc._client = SimpleNamespace(
        song=SimpleNamespace(get_cdn_dispatch=boom), credential=svc.credential
    )

    result = await svc._try_bypass_urls("abc", ("MP3_128",))
    assert result["MP3_128"] == (f"{_FALLBACK}M500abcabc.mp3?vkey=XYZ", None)


async def test_empty_sip_falls_back_to_fixed_domain():
    svc = _svc()
    _stub_bypass(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})
    _stub_dispatch(svc, sip=[])

    result = await svc._try_bypass_urls("abc", ("MP3_128",))
    assert result["MP3_128"][0] == f"{_FALLBACK}M500abcabc.mp3?vkey=XYZ"


async def test_not_connected_uses_fixed_domain_silently():
    # _client 为 None (未 connect): bare purl 仍能拼出兜底域名, 不抛
    svc = _svc()
    _stub_bypass(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})

    result = await svc._try_bypass_urls("abc", ("MP3_128",))
    assert result["MP3_128"][0] == f"{_FALLBACK}M500abcabc.mp3?vkey=XYZ"


async def test_concurrent_calls_dispatch_once():
    # 冷启多首歌并发取流: 只发一次 get_cdn_dispatch, 其余等锁后命中缓存
    svc = _svc()
    _stub_bypass(svc, {"midurlinfo": [{"purl": "M500abcabc.mp3?vkey=XYZ"}]})

    calls: list[int] = []

    async def fake_dispatch():
        calls.append(1)
        await asyncio.sleep(0)  # 让出控制权, 暴露并发窗口 (无锁时这里会被多个协程抢入)
        return SimpleNamespace(
            sip=["http://ws6.stream.qqmusic.qq.com/"], sipinfo=[], cache_time=600, expiration=600
        )

    svc._client = SimpleNamespace(
        song=SimpleNamespace(get_cdn_dispatch=fake_dispatch), credential=svc.credential
    )

    results = await asyncio.gather(*(svc._try_bypass_urls("abc", ("MP3_128",)) for _ in range(5)))
    assert len(calls) == 1
    for r in results:
        assert r["MP3_128"][0] == "https://ws6.stream.qqmusic.qq.com/M500abcabc.mp3?vkey=XYZ"


async def test_full_url_purl_unaffected_no_dispatch():
    # 完整 URL purl 原样保留, 不拼 CDN 前缀, 也不应触发调度 (按需取 host)
    svc = _svc()
    full = "https://ws6.stream.qqmusic.qq.com/F000abcabc.flac?vkey=XYZ"
    _stub_bypass(svc, {"midurlinfo": [{"purl": full}]})
    calls = _stub_dispatch(svc, sip=["http://other.cdn/"])

    result = await svc._try_bypass_urls("abc", ("FLAC",))
    assert result["FLAC"] == (full, None)
    assert calls == []  # 没有 bare purl, 不该调度
