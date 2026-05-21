"""QuaverQ 入口 — UI 已移除, 仅保留 QQ 音乐核心服务.

`quaverq.core.service.QuaverService` 是 QQ 音乐 API 的门面 (登录 / 搜索 /
详情 / 推荐 / 排行 / 喜欢 / 播放 URL / 歌词). 这个入口只演示服务可达,
真正的 UI 等后续重建.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import load as load_config
from .core.service import QuaverService

logger = logging.getLogger("quaverq")


async def _smoke() -> int:
    service = QuaverService()
    await service.connect()
    try:
        cred = await service._get_cached_credential()
        if cred is None:
            print("无缓存凭据 — 请通过 QuaverService.login_by_qrcode() 登录")
            return 0
        service.set_credential_sync(cred)
        expired = await service.check_login_expired()
        if expired:
            print("缓存凭据已过期 — 请重新登录")
        else:
            print(f"凭据有效 (musicid={cred.musicid}) — 服务可用")
    finally:
        await service.disconnect()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="quaverq",
        description="QuaverQ — UI 已移除, 仅保留 QQ 音乐核心服务",
    )
    parser.add_argument("--debug", action="store_true", help="开启 DEBUG 日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 加载配置 (保留, 后续 UI 会用)
    load_config()

    sys.exit(asyncio.run(_smoke()))


if __name__ == "__main__":
    main()
