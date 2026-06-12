"""下载记录持久化: downloads.json.

记录已下载歌曲的本地文件路径 + 音质 + 歌曲元数据, 供:
- 下载页重启后展示历史
- 播放核心按 mid 定位本地文件 (本地优先播放)

文件位置 ~/.config/quaverq/downloads.json (controller 注入路径, 遵 core 约定
不写隐式常量); 配置型数据, 不放会被 LRU 清的 CACHE_DIR. Song <-> dict 复用
core/serde (与 state.json / home.json 共享, 防字段漂移).

策略 (对齐 core/state.py):
- add / remove 立即原子落盘 (tmp + os.replace), 崩溃不丢记录
- load 不存在 / 损坏返 [] (遵 core 容错, 绝不抛阻塞启动)
- 显式 encoding="utf-8" (Windows 中文 locale 默认 GBK, 含 Ø / Unicode 会炸)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .models import Song
from .serde import song_from_dict as _song_from_dict, song_to_dict as _song_to_dict

logger = logging.getLogger(__name__)


@dataclass
class DownloadRecord:
    """一条已下载记录: 歌曲元数据 + 本地文件信息."""

    song: Song
    path: str
    quality_label: str = ""
    size: int = 0
    downloaded_at: int = 0  # unix 秒, 0 = 未知

    @property
    def mid(self) -> str:
        return self.song.mid

    def file_exists(self) -> bool:
        """本地文件是否还在 (用户可能在外部删除/移动)."""
        return bool(self.path) and Path(self.path).is_file()


def _record_to_dict(record: DownloadRecord) -> dict:
    return {
        "song": _song_to_dict(record.song),
        "path": record.path,
        "quality_label": record.quality_label,
        "size": record.size,
        "downloaded_at": record.downloaded_at,
    }


def _record_from_dict(data: dict) -> DownloadRecord:
    return DownloadRecord(
        song=_song_from_dict(data.get("song") or {}),
        path=str(data.get("path") or ""),
        quality_label=str(data.get("quality_label") or ""),
        size=int(data.get("size") or 0),
        downloaded_at=int(data.get("downloaded_at") or 0),
    )


@dataclass
class DownloadStore:
    """downloads.json 的内存镜像 + 持久化. 内存持记录避免播放时频繁读盘."""

    path: Path

    def __init__(self, path) -> None:
        self.path = Path(path)
        self._records: list[DownloadRecord] = []

    def load(self) -> list[DownloadRecord]:
        """读盘填充内存; 不存在 / 损坏返 []. 可重复调用 (幂等替换内存)."""
        self._records = []
        if not self.path.exists():
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning("读取下载记录失败: %s", exc)
            return []
        if not isinstance(data, list):
            return []
        records: list[DownloadRecord] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                records.append(_record_from_dict(item))
            except Exception:
                logger.warning("跳过损坏的下载记录条目")
        self._records = records
        return list(self._records)

    def all(self) -> list[DownloadRecord]:
        """按添加顺序返回全部记录 (副本)."""
        return list(self._records)

    def find(self, mid: str) -> DownloadRecord | None:
        return next((r for r in self._records if r.song.mid == mid), None)

    def add(self, record: DownloadRecord) -> None:
        """按 mid 去重 (原位替换或追加到末尾), 立即落盘."""
        for i, existing in enumerate(self._records):
            if existing.song.mid == record.song.mid:
                self._records[i] = record
                break
        else:
            self._records.append(record)
        self._persist()

    def remove(self, mid: str) -> None:
        """移除指定 mid 的记录并落盘; 不存在则 no-op."""
        before = len(self._records)
        self._records = [r for r in self._records if r.song.mid != mid]
        if len(self._records) != before:
            self._persist()

    def _persist(self) -> None:
        """原子写 (tmp + os.replace), 失败只 log 不抛."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([_record_to_dict(r) for r in self._records], f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception as exc:
            logger.warning("保存下载记录失败: %s", exc)
