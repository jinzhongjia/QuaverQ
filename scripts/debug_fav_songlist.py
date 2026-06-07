"""验证 service.get_fav_songlist 修复后能拿全 113 个收藏歌单.

跑法: uv run python scripts/debug_fav_songlist.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quaverq.core.service import QuaverService, _credential_from_dict


async def main() -> None:
    cred_path = os.path.expanduser("~/.config/quaverq/credential.json")
    with open(cred_path) as f:
        cred = _credential_from_dict(json.load(f))
    print(f"musicid={cred.musicid} encrypt_uin={cred.encrypt_uin}")

    svc = QuaverService(credential=cred)
    await svc.connect()
    svc.set_credential_sync(cred)
    try:
        playlists = await svc.get_fav_songlist()
        print(f"\n拿到 {len(playlists)} 个收藏歌单 (期望 113):")
        for p in playlists[:5]:
            print(f"  pid={p.pid} name={p.name!r} cover={p.cover_url[:60]} songs={p.song_count}")
        if len(playlists) > 5:
            print(f"  ... 还有 {len(playlists) - 5} 个")
    finally:
        await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
