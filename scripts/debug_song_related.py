"""探针: song.get_similar_song + song.get_related_songlist 真实响应.

跑法: uv run python scripts/debug_song_related.py [songid]
没传 songid 时用一个内置的热门歌 ID 试探.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quaverq.config import CONFIG_DIR
from quaverq.core.service import QuaverService

# 周杰伦《晴天》songid (常见公开歌, 探针默认)
DEFAULT_SONGID = 102065756


def _to_dict(obj):
    """SimpleNamespace / pydantic / 普通 dict -> dict (浅一层)."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return obj


async def main() -> None:
    songid = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SONGID
    print(f"target songid = {songid}")

    svc = QuaverService()
    cred = svc.load_cached_credential_sync()
    if cred is None:
        print("no cached credential; 请先在 app 内扫码登录")
        return
    print(f"cred musicid={cred.musicid}")

    await svc.connect()
    svc.set_credential_sync(cred)
    try:
        print("\n=== A. song.get_similar_song ===")
        try:
            resp = await svc.client.song.get_similar_song(songid)
            print(f"type={type(resp).__name__}")
            print(f"tag count={len(getattr(resp, 'tag', []) or [])}")
            groups = getattr(resp, "song", None) or []
            print(f"song groups count={len(groups)}")
            for i, g in enumerate(groups[:3]):
                gd = _to_dict(g)
                print(
                    f"  [group {i}] title_template={gd.get('title_template')!r} "
                    f"title_content={gd.get('title_content')!r} "
                    f"songs={len(gd.get('song', []) or [])}"
                )
                # 第一首歌结构
                for s in (gd.get("song") or [])[:1]:
                    sd = _to_dict(s)
                    keys = list(sd.keys())[:15]
                    print(f"    sample song keys: {keys}")
                    print(
                        f"    sample mid={sd.get('mid')!r} name={sd.get('name')!r} "
                        f"id={sd.get('id')!r}"
                    )
        except Exception as exc:
            print(f"similar_song failed: {type(exc).__name__}: {exc}")

        print("\n=== B. song.get_related_songlist ===")
        try:
            resp = await svc.client.song.get_related_songlist(songid)
            print(f"type={type(resp).__name__}")
            print(f"has_more={getattr(resp, 'has_more', '?')}")
            songlists = getattr(resp, "songlist", None) or []
            print(f"songlist count={len(songlists)}")
            for i, p in enumerate(songlists[:3]):
                pd = _to_dict(p)
                keys = list(pd.keys())
                print(f"  [pl {i}] id={pd.get('id')} title={pd.get('title')!r}")
                print(f"    cover={(pd.get('picurl') or '')[:80]}")
                print(f"    creator={pd.get('creator')!r} songnum={pd.get('songnum')}")
                print(f"    all keys: {keys}")
        except Exception as exc:
            print(f"related_songlist failed: {type(exc).__name__}: {exc}")

        # 也跑 song.get_detail 看 song 的 id 长啥样 (因为我们到时候要从 Song -> id 调上面 API)
        print("\n=== C. 当前队列里第一首歌的 id (确认我们 Song.id 的字段类型) ===")
        from quaverq.core.state import SessionState

        sess_path = CONFIG_DIR / "state.json"
        if sess_path.exists():
            session = SessionState.load(str(sess_path))
            if session.queue:
                first = session.queue[0]
                print(f"first song mid={first.mid!r} id={first.id!r} name={first.name!r}")
    finally:
        await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
