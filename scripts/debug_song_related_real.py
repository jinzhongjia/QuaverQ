"""探针: 用真实「我喜欢」的歌跑一遍完整 get_song_related, 验证数据链路.

跑法: uv run python scripts/debug_song_related_real.py
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

    svc = QuaverService(credential=cred)
    await svc.connect()
    svc.set_credential_sync(cred)
    print(f"ct={svc._ct_value}  musicid={cred.musicid}")
    try:
        liked = await svc.get_liked_songs(limit=5)
        print("\n我喜欢 (前 5 首):")
        for s in liked:
            print(f"  mid={s.mid!r:24} id={s.id:>10}  name={s.name!r}")

        for s in liked[:3]:
            print(f"\n--- {s.name} (id={s.id}) ---")
            if s.id == 0:
                print("  [SKIP] song.id == 0, 我们 controller 会拦掉, 不会去拉相关")
                continue
            try:
                similar, related = await svc.get_song_related(s.id)
                print(f"  similar={len(similar)} (前 3: {[x.name for x in similar[:3]]})")
                print(f"  related={len(related)} (前 3: {[p.name for p in related[:3]]})")
            except Exception as exc:
                print(f"  exc: {type(exc).__name__}: {exc}")
    finally:
        await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
