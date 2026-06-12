"""探针: UrlGetVkey 单请求多 filename 的响应结构 (issue #11 / Stage A1 前置实验).

验证目标 (见 docs/plan/search-playback-fade-and-speed.md):
1. filename 数组塞多个档位 (songmid/songtype 对齐重复) 时, midurlinfo 是否按序逐条对应;
2. 混合可播/不可播档时, 不可播条目的形状 (purl 空 + result 码) 是否与单请求一致;
3. 多 filename 是否影响 result 码透出 (104003 无版权等).

跑法: uv run python scripts/debug_vkey_batch.py
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
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    queue_raw = state.get("queue", [])
    if not queue_raw:
        print("queue 为空, 退出")
        return
    song = song_from_dict(queue_raw[0])
    print(f"取第一首: mid={song.mid} name={song.name!r} media_mid={song.media_mid!r}")

    await svc.connect()
    svc.set_credential_sync(cred)
    print(f"本次会话 ct={svc._ct_value}")
    try:
        file_mid = song.media_mid or song.mid
        labels = list(svc._QUALITY_PROFILES["high"])  # 全部四档
        filenames = []
        for label in labels:
            prefix, ext = svc._QUALITY_FILE[label]
            filenames.append(f"{prefix}{file_mid}{file_mid}.{ext}")
        print(f"\n=== 单请求 {len(filenames)} 个 filename: {labels} ===")
        data = await svc._bypass_post(
            "music.vkey.GetVkey",
            "UrlGetVkey",
            {
                "filename": filenames,
                "guid": svc._device_guid or "abcdef0123456789",
                "songmid": [song.mid] * len(filenames),
                "songtype": [0] * len(filenames),
            },
            require_login=True,
            timeout=svc._VKEY_REQUEST_TIMEOUT_SEC,
        )
        if not data:
            print("→ 空响应")
            return
        midurlinfo = data.get("midurlinfo") or []
        print(f"→ midurlinfo 条数={len(midurlinfo)} (期望 {len(filenames)})")
        for i, entry in enumerate(midurlinfo):
            if not isinstance(entry, dict):
                print(f"  [{i}] 非 dict: {entry!r}")
                continue
            purl = entry.get("purl", "") or ""
            print(
                f"  [{i}] label={labels[i] if i < len(labels) else '?'}"
                f" filename_req={filenames[i] if i < len(filenames) else '?'}"
                f"\n      resp_filename={entry.get('filename', '')!r}"
                f" result={entry.get('result')!r}"
                f" purl[:80]={purl[:80]!r}"
            )
        # 顺序对应性: 响应自带 filename 字段时逐条比对
        resp_names = [e.get("filename", "") for e in midurlinfo if isinstance(e, dict)]
        if all(resp_names) and len(resp_names) == len(filenames):
            aligned = all(rn == fn for rn, fn in zip(resp_names, filenames, strict=True))
            print(f"\n→ 顺序对应 (resp.filename == 请求顺序): {aligned}")
        else:
            print("\n→ 响应缺 filename 字段, 只能按下标对应 (条数一致即可用)")
    finally:
        await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
