"""歌词磁盘缓存 (SWR: 先显示上次歌词, 再后台刷新)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Lyric
from .serde import lyric_from_dict, lyric_to_dict

logger = logging.getLogger(__name__)

_VERSION = 1


@dataclass
class LyricCache:
    """按 ``mid + with_translation`` 持久化解析后的歌词."""

    dir: Path

    def __init__(self, path: str | Path) -> None:
        self.dir = Path(path)

    def load(self, mid: str, *, with_translation: bool = True) -> Lyric | None:
        key_mid = (mid or "").strip()
        if not key_mid:
            return None
        raw = self._read_raw(self._path_for(key_mid, with_translation))
        if raw is None:
            return None
        if raw.get("mid") != key_mid or bool(raw.get("with_translation")) != with_translation:
            return None
        data = raw.get("lyric")
        if not isinstance(data, dict):
            return None
        lyric = lyric_from_dict(data)
        if lyric.mid != key_mid:
            return None
        return lyric

    def save(self, lyric: Lyric, *, with_translation: bool = True) -> None:
        key_mid = (lyric.mid or "").strip()
        if not key_mid:
            return
        raw = {
            "version": _VERSION,
            "mid": key_mid,
            "with_translation": bool(with_translation),
            "updated_at": time.time(),
            "lyric": lyric_to_dict(lyric),
        }
        self._write_raw(self._path_for(key_mid, with_translation), raw)

    def _path_for(self, mid: str, with_translation: bool) -> Path:
        key = f"{mid}\0{int(with_translation)}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.dir / f"{digest}.json"

    def _read_raw(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            logger.warning("读取歌词缓存失败: %s", exc)
            return None
        if not isinstance(data, dict) or data.get("version") != _VERSION:
            return None
        return data

    def _write_raw(self, path: Path, raw: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("保存歌词缓存失败: %s", exc)
