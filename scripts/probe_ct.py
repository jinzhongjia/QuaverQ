"""探针: 实测哪些 ct 值在 vkey 取流时被风控.

对 state.json 队列里的歌 (默认第一首; 传 mid 参数则用指定 mid), 遍历 ct=0..46
逐个请求 UrlGetVkey, 报告每个 ct 拿到的 purl 是否非空 + result 码.
据此核对 service._SAFE_CT_VALUES 是否仍准 (findings.md 第三节的黑名单会随时间变).

跑法:
    uv run python scripts/probe_ct.py            # 用队列第一首
    uv run python scripts/probe_ct.py 003abcXXXX  # 指定 songmid

注意:
- 需先在 app 内扫码登录 (读 keyring 缓存凭据).
- **跑前请关掉正在运行的 app** —— 多实例并发拉 vkey 会让 vkey 互相失效返 401,
  污染结果 (见 memory: project-stream-401-multi-instance).
- 顺序请求 + 间隔 0.4s, 别改成并发.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quaverq.config import CONFIG_DIR
from quaverq.core.serde import song_from_dict
from quaverq.core.service import CredentialExpiredError, QuaverService

CT_RANGE = range(47)  # 0..46, 覆盖 findings 标过的 1/3/4/11/18/19/23/27/46
LABEL = "MP3_128"  # 用最低档探测: 几乎所有歌都有, 信号最干净
GAP_SEC = 0.4


async def _probe_one(svc: QuaverService, mid: str, media_mid: str, ct: int) -> tuple[bool, object]:
    """单个 ct 请求一次 vkey, 返回 (是否拿到非空 purl, result 码/异常)."""
    svc._ct_value = ct
    file_mid = media_mid or mid
    prefix, ext = svc._QUALITY_FILE[LABEL]
    filename = f"{prefix}{file_mid}{file_mid}.{ext}"
    try:
        data = await svc._bypass_post(
            "music.vkey.GetVkey",
            "UrlGetVkey",
            {
                "filename": [filename],
                "guid": svc._device_guid or "abcdef0123456789",
                "songmid": [mid],
                "songtype": [0],
            },
            require_login=True,
            timeout=svc._VKEY_REQUEST_TIMEOUT_SEC,
        )
    except CredentialExpiredError:
        return False, "CRED_EXPIRED"
    except Exception as exc:  # noqa: BLE001 - 探针: 任何异常都记录不中断
        return False, f"EXC:{exc}"
    if not data:
        return False, "空响应"
    info = (data.get("midurlinfo") or [{}])[0]
    if not isinstance(info, dict):
        return False, f"非dict:{info!r}"
    purl = info.get("purl", "") or ""
    return bool(purl), info.get("result")


async def main() -> None:
    svc = QuaverService()
    cred = svc.load_cached_credential_sync()
    if cred is None:
        print("no cached credential; 请先在 app 内扫码登录")
        return

    if len(sys.argv) > 1:
        # argv: mid [media_mid]  —— vkey filename 用 media_mid, 缺了会拼错 → 全 104003
        mid = sys.argv[1]
        media_mid = sys.argv[2] if len(sys.argv) > 2 else ""
        name = "(指定 mid)"
    else:
        with open(CONFIG_DIR / "state.json", encoding="utf-8") as f:
            queue = json.load(f).get("queue", [])
        if not queue:
            print("queue 为空; 传 mid 参数或先在 app 里放首歌")
            return
        song = song_from_dict(queue[0])
        mid, media_mid, name = song.mid, song.media_mid, song.name

    await svc.connect()
    svc.set_credential_sync(cred)
    print(f"探测歌曲: mid={mid} name={name!r} media_mid={media_mid!r}  (档={LABEL})")
    print(f"{'ct':>4} | {'可播':^4} | result")
    print("-" * 32)
    ok, bad = [], []
    try:
        for ct in CT_RANGE:
            playable, code = await _probe_one(svc, mid, media_mid, ct)
            (ok if playable else bad).append(ct)
            print(f"{ct:>4} | {'✅' if playable else '❌':^3} | {code}")
            await asyncio.sleep(GAP_SEC)
    finally:
        await svc.disconnect()

    print("\n=== 汇总 ===")
    print(f"✅ 可播 ct ({len(ok)}): {ok}")
    print(f"❌ 不可播 ct ({len(bad)}): {bad}")
    pool = list(svc._SAFE_CT_VALUES)
    stale = sorted(set(pool) & set(bad))
    print(f"\n当前 _SAFE_CT_VALUES: {pool}")
    if stale:
        print(f"⚠️ 池中已失效, 建议剔除: {stale}")
    else:
        print("✅ 池中所有 ct 本次均可播")


if __name__ == "__main__":
    asyncio.run(main())
