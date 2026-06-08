"""探针: 取队列中第一首的播放 URL, 看 vkey/ct 是否还能拿到链.

跑法: uv run python scripts/debug_song_url.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quaverq.config import CONFIG_DIR
from quaverq.core.serde import song_from_dict
from quaverq.core.service import QuaverService


async def main() -> None:
    svc = QuaverService()
    cred = svc.load_cached_credential_sync()
    if cred is None:
        print("no cached credential; 请先在 app 内扫码登录")
        return

    state_path = CONFIG_DIR / "state.json"
    guid_path = CONFIG_DIR / "device_id"
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    with open(guid_path, encoding="utf-8") as f:
        guid = f.read().strip()

    print(f"musicid={cred.musicid}")
    print(f"persistent device guid={guid}")
    print(f"queue size={len(state.get('queue', []))}")

    queue_raw = state.get("queue", [])
    if not queue_raw:
        print("queue 为空, 退出")
        return
    song = song_from_dict(queue_raw[0])
    print(f"取第一首: mid={song.mid} name={song.name!r} id={song.id}")

    await svc.connect()
    svc.set_credential_sync(cred)
    forced_ct = int(os.environ.get("QQ_DEBUG_CT", "0") or "0")
    if forced_ct == -1:
        # 扫描全池, 找出哪些 ct 坏
        print("\n=== 扫描 _SAFE_CT_VALUES (用 balanced/MP3_320 测试) ===")
        import curl_cffi.requests as req

        bad = []
        for ct in svc._SAFE_CT_VALUES:
            svc._ct_value = ct
            try:
                url = await svc.get_song_url(song, quality_preference="balanced")
            except Exception as exc:
                print(f"  ct={ct:>2}: vkey 调用挂: {exc}")
                bad.append(ct)
                continue
            if not url or not url.url:
                print(f"  ct={ct:>2}: vkey 返回空")
                bad.append(ct)
                continue
            try:
                resp = req.get(
                    url.url,
                    impersonate=svc._IMPERSONATE,
                    timeout=5,
                    allow_redirects=False,
                    headers={"Range": "bytes=0-"},
                    stream=True,
                )
                ok = resp.status_code in (200, 206)
                print(f"  ct={ct:>2}: GET {resp.status_code} ({url.quality})")
                resp.close()
                if not ok:
                    bad.append(ct)
            except Exception as exc:
                print(f"  ct={ct:>2}: HTTP 失败: {exc}")
                bad.append(ct)
        print(f"\n坏值列表: {bad}")
        await svc.disconnect()
        return
    if forced_ct:
        svc._ct_value = forced_ct
    print(f"本次会话 ct={svc._ct_value}")
    try:
        for q in ("high", "balanced", "standard"):
            print(f"\n=== quality={q} ===")
            try:
                url = await svc.get_song_url(song, quality_preference=q)
            except Exception as exc:
                print(f"failed: {type(exc).__name__}: {exc}")
                continue
            if not url or not url.url:
                print(f"→ 没拿到 URL (空): {url}")
                continue
            real_url = url.url
            print(f"→ quality={url.quality} size={url.size}")
            print(f"→ url length={len(real_url)}")
            print(f"→ first 240: {real_url[:240]}")
            try:
                import curl_cffi.requests as req

                # 1) HEAD 同 StreamProxy 路径 (curl_cffi + impersonate)
                resp_h = req.head(
                    real_url, impersonate=svc._IMPERSONATE, timeout=5, allow_redirects=False
                )
                print(f"→ HEAD status={resp_h.status_code}")
                # 2) Range GET (FFmpeg 默认 `bytes=0-` 拉整个)
                resp_g = req.get(
                    real_url,
                    impersonate=svc._IMPERSONATE,
                    timeout=5,
                    allow_redirects=False,
                    headers={"Range": "bytes=0-"},
                    stream=True,
                )
                body = resp_g.content[:512]
                print(f"→ GET status={resp_g.status_code} body[:200]={body[:200]!r}")
                shown_headers = {
                    k: v
                    for k, v in resp_g.headers.items()
                    if k.lower() in ("content-type", "content-length", "server", "x-cdn", "via")
                }
                print(f"→ headers={shown_headers}")
                resp_g.close()
            except Exception as exc:
                print(f"→ HEAD/GET probe failed: {type(exc).__name__}: {exc}")
    finally:
        await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
