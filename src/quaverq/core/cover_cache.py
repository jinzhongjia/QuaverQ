"""封面磁盘缓存.

文件位置: ~/.cache/quaverq/covers/  (controller 注入路径)
文件名: sha1(url) + 原 URL 的扩展名 (.jpg / .png; 未知默认 .jpg)

设计:
- get_path(url): 同步, 秒级查询, UI 渲染前调
- fetch(url):    异步, 内部用 asyncio.to_thread + niquests 同步下载
- 没做 LRU 淘汰 (P2.4 离线音频缓存时一起做)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_VALID_EXTS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass
class CoverCache:
    dir: Path

    def __init__(self, dir_: str | Path):
        self.dir = Path(dir_)

    # ------------------------------------------------------------------ 同步查询

    def get_path(self, url: str | None) -> Path | None:
        """本地已下载返路径; 未下载返 None."""
        if not url:
            return None
        path = self.dir / self._filename_for(url)
        return path if path.exists() else None

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

    # ------------------------------------------------------------------ 异步下载

    async def fetch(self, url: str | None) -> Path | None:
        """下载封面到本地; 已存在直接返路径. 失败返 None."""
        if not url:
            return None
        path = self.dir / self._filename_for(url)
        if path.exists():
            return path

        # 同步下载放到 to_thread (niquests 同步 client; 避免阻塞 event loop)
        try:
            ok = await asyncio.to_thread(self._download_sync, url, path)
        except Exception as exc:
            logger.warning("封面下载异常 (%s): %s", url[:60], exc)
            return None
        return path if ok else None

    # ------------------------------------------------------------------ 内部

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
