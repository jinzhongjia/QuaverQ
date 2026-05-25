"""用户库: 喜欢 / 取消喜欢 + 本地 cache 镜像 + 远端同步.

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
    from .models import Album, Playlist, Singer, Song
    from .service import QuaverService

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Sidebar 统一资料库 (UI-2): 把 4 种来源摊平到一个 list, 配合过滤芯片 + 搜索
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class SidebarItem:
    """资料库 sidebar 一行 (我喜欢 + 我的歌单 + 收藏专辑 + 关注艺人).

    kind: "liked" | "playlist" | "album" | "singer"
    ref:  对应原对象 (Playlist/Album/Singer); "liked" 为 None (虚拟行).
    """

    kind: str
    name: str
    subtitle: str
    ref: object = None


def build_sidebar_items(
    liked_count: int,
    my_playlists: "list[Playlist]",
    fav_albums: "list[Album]",
    followed_singers: "list[Singer]",
) -> list[SidebarItem]:
    """把 4 个来源摊平为 SidebarItem 列表; "我喜欢" 永远在第一位 (虚拟行)."""
    items: list[SidebarItem] = [
        SidebarItem(
            kind="liked",
            name="我喜欢的音乐",
            subtitle=f"{liked_count} 首" if liked_count else "暂无",
        )
    ]
    for p in my_playlists:
        sub = f"{p.song_count} 首" if p.song_count else "歌单"
        items.append(SidebarItem(kind="playlist", name=p.name, subtitle=sub, ref=p))
    for a in fav_albums:
        sub = " / ".join(s.name for s in a.singers) if a.singers else "专辑"
        items.append(SidebarItem(kind="album", name=a.name, subtitle=sub, ref=a))
    for s in followed_singers:
        items.append(SidebarItem(kind="singer", name=s.name, subtitle="艺人", ref=s))
    return items


def filter_sidebar_items(
    items: list[SidebarItem], kind_filter: str, query: str
) -> list[SidebarItem]:
    """纯函数过滤: kind_filter='all' 保留全部; "liked" 行不受 kind_filter 影响 (它是 pinned).

    query 大小写不敏感, 匹配 name 或 subtitle 子串.
    """
    q = (query or "").strip().lower()
    out: list[SidebarItem] = []
    for it in items:
        if kind_filter != "all" and it.kind != "liked" and it.kind != kind_filter:
            continue
        if q and q not in it.name.lower() and q not in it.subtitle.lower():
            continue
        out.append(it)
    return out


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
