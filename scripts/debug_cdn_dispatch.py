"""探针: 看 get_cdn_dispatch 返回的 sip 列表, 逐个 host 拼 vkey purl 测可用性.

跑法: uv run python scripts/debug_cdn_dispatch.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curl_cffi.requests as req

from quaverq.config import CONFIG_DIR
from quaverq.core.serde import song_from_dict
from quaverq.core.service import QuaverService


async def main() -> None:
    svc = QuaverService()
    cred = svc.load_cached_credential_sync()
    if cred is None:
        print("no cached credential; 请先在 app 内扫码登录")
        return
    await svc.connect()
    svc.set_credential_sync(cred)

    resp = await svc.client.song.get_cdn_dispatch()
    print("=== get_cdn_dispatch ===")
    print(f"sip = {getattr(resp, 'sip', None)}")
    print(
        f"cache_time={getattr(resp, 'cache_time', None)} expiration={getattr(resp, 'expiration', None)}"
    )
    for s in getattr(resp, "sipinfo", []) or []:
        print(f"  sipinfo: cdn={s.cdn!r} ipstack={s.ipstack} quic={s.quic}")

    # 拿一首歌的裸 purl
    with open(CONFIG_DIR / "state.json", encoding="utf-8") as f:
        state = json.load(f)
    queue_raw = state.get("queue", [])
    if not queue_raw:
        print("queue 空, 跳过 purl 测试")
        await svc.disconnect()
        return
    song = song_from_dict(queue_raw[0])
    fetched = await svc._try_bypass_urls(song.mid, ("MP3_128",), media_mid=song.media_mid)
    url, _ = fetched.get("MP3_128", (None, None))
    if not url:
        print("没拿到 purl")
        await svc.disconnect()
        return
    # 还原裸路径 (去掉当前拼的 host)
    purl = url.split("/", 3)[-1]
    print(f"\n=== 裸 purl = {purl[:80]}... ===")

    hosts = list(getattr(resp, "sip", []) or [])
    hosts.append("https://isure.stream.qqmusic.qq.com/")  # 对照
    for host in hosts:
        h = host if host.startswith("http") else "https://" + host
        if not h.endswith("/"):
            h += "/"
        full = f"{h}{purl}"
        try:
            r = req.get(
                full,
                impersonate=svc._IMPERSONATE,
                timeout=5,
                allow_redirects=False,
                headers={"Range": "bytes=0-"},
                stream=True,
            )
            print(f"  {h:<45} -> {r.status_code}")
            r.close()
        except Exception as exc:
            print(f"  {h:<45} -> ERR {type(exc).__name__}: {exc}")

    await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
