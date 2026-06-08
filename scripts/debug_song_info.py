"""探针: song.get_detail / song.get_labels / song.get_producer (第二档 2.4).

跑法: uv run python scripts/debug_song_info.py [songid]
默认探周杰伦《晴天》 (songid=97773).
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quaverq.core.service import QuaverService

DEFAULT_SONGID = 97773  # 周杰伦 晴天


def _dump(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return obj


async def main() -> None:
    songid = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SONGID
    svc = QuaverService()
    cred = svc.load_cached_credential_sync()
    if cred is None:
        print("no cached credential; 请先在 app 内扫码登录")
        return

    await svc.connect()
    svc.set_credential_sync(cred)
    print(f"songid={songid}  ct={svc._ct_value}")
    try:
        print("\n=== A. song.get_detail ===")
        resp = await svc.client.song.get_detail(songid)
        for fld in ("company", "genre", "intro", "lan", "pub_time"):
            items = getattr(resp, fld, None) or []
            if items:
                vals = [(_dump(i).get("value"), _dump(i).get("jumpurl")) for i in items]
                print(f"  {fld}: {vals}")
            else:
                print(f"  {fld}: <empty>")
        extras = getattr(resp, "extras", None) or {}
        if extras:
            print(f"  extras: {dict(list(extras.items())[:5])}")

        print("\n=== B. song.get_labels ===")
        resp = await svc.client.song.get_labels(songid)
        labels = getattr(resp, "labels", None) or []
        print(f"count={len(labels)}")
        for label in labels[:10]:
            d = _dump(label)
            print(
                f"  id={d.get('id'):>4} txt={d.get('tag_txt')!r:14} "
                f"type={d.get('tag_type')} species={d.get('species')}"
            )

        print("\n=== C. song.get_producer ===")
        resp = await svc.client.song.get_producer(songid)
        groups = getattr(resp, "data", None) or []
        print(f"groups={len(groups)} reinforce={getattr(resp, 'reinforce_msg', '')!r}")
        for g in groups:
            gd = _dump(g)
            title = gd.get("title")
            producers = gd.get("producers") or []
            names = [_dump(p).get("name") for p in producers]
            print(f"  {title}: {names}")
    finally:
        await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
