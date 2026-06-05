"""封面磁盘缓存.

文件位置: ~/.cache/quaverq/covers/  (controller 注入路径)
文件名: sha1(url) + 原 URL 的扩展名 (.jpg / .png; 未知默认 .jpg)

设计:
- get_path(url): 同步, 秒级查询, UI 渲染前调; 命中时按节流刷新 mtime 充当 LRU 访问时间
- fetch(url):    异步, 内部用 asyncio.to_thread + niquests 同步下载; 新下载后触发上限淘汰
- LRU 上限:      max_bytes > 0 时, 超限按 mtime 最旧优先淘汰, 永不淘汰最新一条
                 (单个封面大于上限时保留而不是反复重下); max_bytes <= 0 表示不限

音频缓存(后续)预留: v1 不实装. 届时复用本模块的 max_bytes + enforce_limit LRU 模式,
设置键命名空间预留 cache/audioMaxBytes, 缓存目录 ~/.cache/quaverq/audio/.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_VALID_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# 命中渲染路径很热; 只有 mtime 比这个间隔更旧才回写一次, 避免每帧落盘.
_ACCESS_BUMP_INTERVAL = 300.0


@dataclass
class CoverCache:
    dir: Path
    max_bytes: int = 0

    def __init__(self, dir_: str | Path, max_bytes: int = 0):
        self.dir = Path(dir_)
        self.max_bytes = max(0, int(max_bytes))

    # ------------------------------------------------------------------ 同步查询

    def get_path(self, url: str | None) -> Path | None:
        """本地已下载返路径; 未下载返 None."""
        if not url:
            return None
        path = self.dir / self._filename_for(url)
        if not path.exists():
            return None
        self._bump_access(path)
        return path

    def to_file_uri(self, path: Path) -> str:
        """把本地 Path 转成 file:// URI (供 MPRIS artUrl 用)."""
        return f"file://{path.resolve()}"

    def size_bytes(self) -> int:
        """Return total cached cover bytes."""
        if not self.dir.exists():
            return 0
        total = 0
        for path in self.dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def clear(self) -> int:
        """Remove cached covers and return removed bytes."""
        removed = self.size_bytes()
        if self.dir.exists():
            for path in self.dir.iterdir():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
        return removed

    # ------------------------------------------------------------------ 上限 / LRU

    def set_max_bytes(self, max_bytes: int) -> int:
        """更新缓存上限并立即执行一次淘汰; 返回被淘汰的字节数."""
        self.max_bytes = max(0, int(max_bytes))
        return self.enforce_limit()

    def enforce_limit(self) -> int:
        """超过 max_bytes 时按最久未使用 (mtime 最旧) 优先淘汰, 返回淘汰字节数.

        max_bytes <= 0 时不限, 直接返回 0. 永不淘汰最新一条, 因此单个封面大于
        上限时会被保留而不是每次访问后又被自己挤掉重下.
        """
        if self.max_bytes <= 0 or not self.dir.exists():
            return 0

        entries: list[tuple[float, int, Path]] = []
        total = 0
        for path in self.dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
            total += stat.st_size

        if total <= self.max_bytes:
            return 0

        entries.sort(key=lambda item: item[0])  # 最旧优先
        removed = 0
        for _mtime, size, path in entries[:-1]:  # 保留最新一条
            if total <= self.max_bytes:
                break
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("封面缓存淘汰失败 (%s): %s", path.name, exc)
                continue
            total -= size
            removed += size
        return removed

    # ------------------------------------------------------------------ 异步下载

    async def fetch(self, url: str | None) -> Path | None:
        """下载封面到本地; 已存在直接返路径. 失败返 None."""
        if not url:
            return None
        path = self.dir / self._filename_for(url)
        if path.exists():
            self._bump_access(path)
            return path

        # 同步下载放到 to_thread (niquests 同步 client; 避免阻塞 event loop)
        try:
            ok = await asyncio.to_thread(self._download_sync, url, path)
        except Exception as exc:
            logger.warning("封面下载异常 (%s): %s", url[:60], exc)
            return None
        if not ok:
            return None
        if self.max_bytes > 0:
            try:
                await asyncio.to_thread(self.enforce_limit)
            except Exception as exc:
                logger.warning("封面缓存淘汰异常: %s", exc)
        return path

    # ------------------------------------------------------------------ 内部

    def _bump_access(self, path: Path) -> None:
        """命中时刷新 mtime, 让 LRU 反映"最近显示"而不仅是下载时间.

        节流: 仅当现有 mtime 比 _ACCESS_BUMP_INTERVAL 更旧才回写, 渲染热路径基本无写入.
        """
        try:
            now = time.time()
            if now - path.stat().st_mtime > _ACCESS_BUMP_INTERVAL:
                os.utime(path, (now, now))
        except OSError:
            pass

    def _filename_for(self, url: str) -> str:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        ext = self._ext_from_url(url)
        return f"{digest}{ext}"

    @staticmethod
    def _ext_from_url(url: str) -> str:
        """从 URL 末尾推断扩展名; 未知默认 .jpg."""
        path = urllib.parse.urlparse(url).path
        suffix = Path(path).suffix.lower()
        if suffix in _VALID_EXTS:
            return suffix
        return ".jpg"

    def _download_sync(self, url: str, dest: Path) -> bool:
        import niquests

        try:
            with niquests.Session() as s:
                r = s.get(url, timeout=10)
                if r.status_code != 200 or not r.content:
                    return False
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                return True
        except Exception as exc:
            logger.warning("封面下载失败 (%s): %s", url[:60], exc)
            return False
