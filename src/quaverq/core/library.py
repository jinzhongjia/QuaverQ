"""用户库 (P1.2): 喜欢 / 取消喜欢 + 本地 cache 镜像 + 远端同步.

策略 (本地 + 远端双写, 失败容错):
- like(song):  立即 cache.put_liked() 让 UI 即时反应; 同时后台调 QQ API 远端同步
- unlike(song): 立即 cache.remove_liked(); 同时后台 QQ del
- sync_from_remote(): 启动 + 登录成功后调, 用远端 get_liked_songs 覆盖本地

UI 通过 is_liked(mid) 查询当前喜欢态; toggle_like(song) 翻转.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cache import Cache
    from .models import Song
    from .service import QuaverService

logger = logging.getLogger(__name__)


@dataclass
class Library:
    """用户库门面: 协调 cache (本地状态) 和 service (远端 QQ API)."""

    cache: "Cache"
    service: "QuaverService"

    # ------------------------------------------------------------------
    # 同步查询 (UI 渲染用, 必须秒级)
    # ------------------------------------------------------------------

    def is_liked(self, mid: str) -> bool:
        return self.cache.is_liked(mid)

    def list_liked(self) -> list["Song"]:
        return self.cache.list_liked()

    # ------------------------------------------------------------------
    # 异步操作
    # ------------------------------------------------------------------

    async def toggle_like(self, song: "Song") -> bool:
        """翻转喜欢状态; 返回新状态 (True=已喜欢, False=已取消)."""
        if self.cache.is_liked(song.mid):
            await self.unlike(song)
            return False
        await self.like(song)
        return True

    async def like(self, song: "Song") -> None:
        # 1) 本地立刻写, UI 秒变化
        self.cache.put_liked(song)
        # 2) 远端尽力而为, 失败不回滚本地 (用户态优先)
        try:
            ok = await self.service.like_song(song)
            if not ok:
                logger.info("like 远端同步未成功 (本地已记录): %s", song.name)
        except Exception:
            logger.exception("like 远端同步异常")

    async def unlike(self, song: "Song") -> None:
        self.cache.remove_liked(song.mid)
        try:
            ok = await self.service.unlike_song(song)
            if not ok:
                logger.info("unlike 远端同步未成功 (本地已删除): %s", song.name)
        except Exception:
            logger.exception("unlike 远端同步异常")

    async def sync_from_remote(self) -> int:
        """登录/启动后调; 用远端 fav 列表覆盖本地. 返回拉到的歌数."""
        try:
            songs = await self.service.get_liked_songs(limit=500)
        except Exception as exc:
            logger.warning("拉远端我喜欢失败: %s", exc)
            return 0
        self.cache.replace_liked(songs)
        logger.info("我喜欢 同步到本地: %d 首", len(songs))
        return len(songs)
