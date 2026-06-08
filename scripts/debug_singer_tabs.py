"""探针: 歌手页 tab 接口 (get_similar / get_album_list / get_songs_list).

跑法: uv run python scripts/debug_singer_tabs.py [singerMid]
默认探周杰伦 (mid=0025NhlN2yWrP4).
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quaverq.core.service import QuaverService

DEFAULT_SINGER = "0025NhlN2yWrP4"  # 周杰伦


def _to_dict(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return obj


async def main() -> None:
    mid = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SINGER
    svc = QuaverService()
    cred = svc.load_cached_credential_sync()
    if cred is None:
        print("no cached credential; 请先在 app 内扫码登录")
        return

    await svc.connect()
    svc.set_credential_sync(cred)
    print(f"singer mid={mid}  ct={svc._ct_value}")
    try:
        print("\n=== A. get_similar (相似歌手) ===")
        resp = await svc.client.singer.get_similar(mid, number=10)
        items = getattr(resp, "singerlist", None) or []
        print(f"count={len(items)} code={getattr(resp, 'code', '?')}")
        for s in items[:5]:
            sd = _to_dict(s)
            print(
                f"  mid={sd.get('mid')!r:24} name={sd.get('name')!r:18} "
                f"id={sd.get('id')} pic={(sd.get('singer_pic') or '')[:60]}"
            )

        print("\n=== B. get_songs_list (全部歌曲, page=1 num=10) ===")
        resp = await svc.client.singer.get_songs_list(mid, num=10, page=1)
        items = getattr(resp, "song_list", None) or []
        print(f"count={len(items)} total={getattr(resp, 'total_num', '?')}")
        for s in items[:5]:
            sd = _to_dict(s)
            print(f"  mid={sd.get('mid')!r:18} id={sd.get('id'):>10}  name={sd.get('name')!r}")

        print("\n=== C. get_album_list (全部专辑, page=1 num=10) ===")
        resp = await svc.client.singer.get_album_list(mid, num=10, page=1)
        items = getattr(resp, "album_list", None) or []
        print(f"count={len(items)} total={getattr(resp, 'total', '?')}")
        for a in items[:5]:
            ad = _to_dict(a)
            print(
                f"  mid={ad.get('mid')!r:18} name={ad.get('name')!r} "
                f"songnum={ad.get('songnum') or ad.get('song_num')} "
                f"publish={ad.get('publish_date') or ad.get('publishDate')}"
            )
            print(f"    all keys: {list(ad.keys())[:18]}")
    finally:
        await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
