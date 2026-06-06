"""首屏发现页快照 (SWR: 先显示上次缓存, 再后台刷新).

文件位置: ~/.cache/quaverq/home.json (controller 注入路径; 属派生数据, 放 cache 而非 config)

区块:
- 公共 (无条件恢复):   playlists(今日推荐) / new_songs(新歌速递) / tops(排行榜)
- 账号私有 (各自 account_key 匹配才恢复): daily(猜你喜欢) / my_playlists(我的歌单)
  每个私有区块单独存自己的 account_key (= hash(musicid)); 防止账号切换时一个区块
  刚刷新、另一个还是旧账号数据被错误归属到新账号. 登出时 clear_private() 抹掉两块.

策略 (对齐 core/state.py):
- update(**sections): 读现有 -> 仅覆盖传入 (not None) 的 section -> 写回.
  None  = 本次不更新 (保留旧值; 用于"该区块刷新失败");
  []    = 明确清空该区块.
- load(account_key): 缺失 / 损坏 / 版本不符 -> 空快照, 绝不抛.
- card 区块存的就是 CardListModel 持有的普通 dict, 原样存取; song 区块用 serde 往返.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Song
from .serde import song_from_dict, song_to_dict

logger = logging.getLogger(__name__)

_VERSION = 1
_PRIVATE_SECTIONS = ("daily", "my_playlists")


@dataclass
class HomeSnapshot:
    """从 home.json 读出的首屏快照 (已按账号过滤私有区块)."""

    daily: list[Song] = field(default_factory=list)
    new_songs: list[Song] = field(default_factory=list)
    playlists: list[dict[str, Any]] = field(default_factory=list)
    tops: list[dict[str, Any]] = field(default_factory=list)
    my_playlists: list[dict[str, Any]] = field(default_factory=list)
    account_key: str = ""

    def is_empty(self) -> bool:
        return not (
            self.daily or self.new_songs or self.playlists or self.tops or self.my_playlists
        )


@dataclass
class HomeCache:
    path: Path

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------------ 读
    def load(self, account_key: str = "") -> HomeSnapshot:
        raw = self._read_raw()
        if raw is None:
            return HomeSnapshot()
        sections = raw.get("sections") or {}

        def songs(name: str) -> list[Song]:
            block = sections.get(name) or {}
            return [song_from_dict(s) for s in (block.get("songs") or [])]

        def cards(name: str) -> list[dict[str, Any]]:
            block = sections.get(name) or {}
            return [dict(c) for c in (block.get("cards") or [])]

        def private_ok(name: str) -> bool:
            block = sections.get(name) or {}
            stored = str(block.get("account_key", "") or "")
            return bool(account_key) and account_key == stored

        snap = HomeSnapshot(
            new_songs=songs("new_songs"),
            playlists=cards("playlists"),
            tops=cards("tops"),
            account_key=account_key,
        )
        if private_ok("daily"):
            snap.daily = songs("daily")
        if private_ok("my_playlists"):
            snap.my_playlists = cards("my_playlists")
        return snap

    # ------------------------------------------------------------------ 写
    def update(
        self,
        *,
        daily: list[Song] | None = None,
        new_songs: list[Song] | None = None,
        playlists: list[dict[str, Any]] | None = None,
        tops: list[dict[str, Any]] | None = None,
        my_playlists: list[dict[str, Any]] | None = None,
        account_key: str | None = None,
    ) -> None:
        """仅覆盖传入 (not None) 的 section; None 保留旧值, 空 list 清空该 section.

        私有区块 (daily / my_playlists) 把当次 account_key 写进自己的 block,
        各自独立判定归属.
        """
        raw = self._read_raw() or {"version": _VERSION, "sections": {}}
        sections = raw.setdefault("sections", {})
        key = str(account_key or "")
        if daily is not None:
            sections["daily"] = {
                "songs": [song_to_dict(s) for s in daily],
                "account_key": key,
            }
        if my_playlists is not None:
            sections["my_playlists"] = {
                "cards": [dict(c) for c in my_playlists],
                "account_key": key,
            }
        if new_songs is not None:
            sections["new_songs"] = {"songs": [song_to_dict(s) for s in new_songs]}
        if playlists is not None:
            sections["playlists"] = {"cards": [dict(c) for c in playlists]}
        if tops is not None:
            sections["tops"] = {"cards": [dict(c) for c in tops]}
        self._write_raw(raw)

    def clear_private(self) -> None:
        """登出时调: 抹掉账号私有区块, 公共区块保留."""
        raw = self._read_raw()
        if raw is None:
            return
        sections = raw.get("sections") or {}
        for name in _PRIVATE_SECTIONS:
            sections.pop(name, None)
        self._write_raw(raw)

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("删除首屏缓存失败: %s", exc)

    # ------------------------------------------------------------------ 内部
    def _read_raw(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            logger.warning("读取首屏缓存失败: %s", exc)
            return None
        if not isinstance(data, dict) or data.get("version") != _VERSION:
            return None
        return data

    def _write_raw(self, raw: dict[str, Any]) -> None:
        raw["version"] = _VERSION
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
        except OSError as exc:
            logger.warning("保存首屏缓存失败: %s", exc)
