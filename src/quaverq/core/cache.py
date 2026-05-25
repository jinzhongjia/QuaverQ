"""SQLite cache 层.

- 4 个表: song_meta / album_meta / playlist_meta / artist_meta
- 每条记录: 主键 + JSON blob + fetched_at
- TTL 在读时检查 (写时不清), 过期返 None
- dataclass 序列化用 asdict, 反序列化手写 helper (嵌套 Singer/Song)

文件位置: ~/.config/quaverq/cache.db (controller 注入路径)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import Album, ArtistDetail, Playlist, Singer, Song

logger = logging.getLogger(__name__)


# 默认 TTL: 元数据 7 天 (歌曲/专辑/歌单元信息变动慢)
DEFAULT_TTL_SEC = 7 * 24 * 3600


# ---------------------------------------------------------------- dataclass ↔ dict


def _singer_from_dict(d: dict[str, Any]) -> Singer:
    return Singer(
        mid=d.get("mid", "") or "",
        name=d.get("name", "") or "",
        avatar_url=d.get("avatar_url", "") or "",
    )


def _song_from_dict(d: dict[str, Any]) -> Song:
    return Song(
        mid=d.get("mid", "") or "",
        name=d.get("name", "") or "",
        singers=[_singer_from_dict(s) for s in d.get("singers") or []],
        album_mid=d.get("album_mid", "") or "",
        album_name=d.get("album_name", "") or "",
        cover_url=d.get("cover_url", "") or "",
        duration=int(d.get("duration", 0) or 0),
        pay_play=int(d.get("pay_play", 0) or 0),
        file_qualities=set(d.get("file_qualities") or []),
        media_mid=d.get("media_mid", "") or "",
    )


def _album_from_dict(d: dict[str, Any]) -> Album:
    return Album(
        mid=d.get("mid", "") or "",
        name=d.get("name", "") or "",
        singers=[_singer_from_dict(s) for s in d.get("singers") or []],
        cover_url=d.get("cover_url", "") or "",
        publish_date=d.get("publish_date", "") or "",
        description=d.get("description", "") or "",
        song_count=int(d.get("song_count", 0) or 0),
        songs=[_song_from_dict(s) for s in d.get("songs") or []],
    )


def _playlist_from_dict(d: dict[str, Any]) -> Playlist:
    return Playlist(
        pid=d.get("pid", "") or "",
        name=d.get("name", "") or "",
        cover_url=d.get("cover_url", "") or "",
        description=d.get("description", "") or "",
        creator=d.get("creator", "") or "",
        song_count=int(d.get("song_count", 0) or 0),
        play_count=int(d.get("play_count", 0) or 0),
        songs=[_song_from_dict(s) for s in d.get("songs") or []],
        is_mine=bool(d.get("is_mine", False)),
    )


def _artist_from_dict(d: dict[str, Any]) -> ArtistDetail:
    return ArtistDetail(
        singer=_singer_from_dict(d.get("singer") or {}),
        description=d.get("description", "") or "",
        hot_songs=[_song_from_dict(s) for s in d.get("hot_songs") or []],
        albums=[_album_from_dict(a) for a in d.get("albums") or []],
    )


def _dump(obj: Any) -> str:
    """dataclass → JSON 字符串. file_qualities 是 set, asdict 不友好, 单独处理."""
    d = asdict(obj)
    return json.dumps(d, ensure_ascii=False, default=_json_default)


def _json_default(o: Any) -> Any:
    if isinstance(o, set):
        return list(o)
    raise TypeError(f"unhashable type {type(o).__name__}")


# ---------------------------------------------------------------- Cache class


_SCHEMA = """
CREATE TABLE IF NOT EXISTS song_meta (
  mid TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  fetched_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS album_meta (
  mid TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  fetched_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_meta (
  pid TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  fetched_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS artist_meta (
  mid TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  fetched_at INTEGER NOT NULL
);
-- 我喜欢的歌 (用户态镜像, 没 TTL)
CREATE TABLE IF NOT EXISTS liked_song (
  mid TEXT PRIMARY KEY,
  song_data TEXT NOT NULL,   -- 完整 Song JSON, 离线显示用
  added_at INTEGER NOT NULL
);
"""


class Cache:
    """同步 SQLite cache. 调用站点是 asyncio loop 内 (asyncio.to_thread) 或直接同步."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        # 主线程 open + AsyncRunner 后台线程读写 → 必须串行 + 关闭线程绑定
        self._lock = threading.RLock()

    def open(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: 允许跨线程; 用 self._lock 自己串行 SQL
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.info("Cache opened: %s", self.db_path)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def list_tables(self) -> list[str]:
        """debug: 列出当前 schema 中的表名."""
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------ Song

    def put_song(self, s: Song) -> None:
        self._upsert("song_meta", "mid", s.mid, _dump(s))

    def get_song(self, mid: str, *, ttl_sec: int = DEFAULT_TTL_SEC) -> Song | None:
        row = self._get_fresh("song_meta", "mid", mid, ttl_sec)
        return _song_from_dict(json.loads(row)) if row else None

    def invalidate_song(self, mid: str) -> None:
        self._delete("song_meta", "mid", mid)

    # ------------------------------------------------------------------ Album

    def put_album(self, a: Album) -> None:
        self._upsert("album_meta", "mid", a.mid, _dump(a))

    def get_album(self, mid: str, *, ttl_sec: int = DEFAULT_TTL_SEC) -> Album | None:
        row = self._get_fresh("album_meta", "mid", mid, ttl_sec)
        return _album_from_dict(json.loads(row)) if row else None

    def invalidate_album(self, mid: str) -> None:
        self._delete("album_meta", "mid", mid)

    # ------------------------------------------------------------------ Playlist

    def put_playlist(self, p: Playlist) -> None:
        self._upsert("playlist_meta", "pid", p.pid, _dump(p))

    def get_playlist(
        self, pid: str, *, ttl_sec: int = DEFAULT_TTL_SEC
    ) -> Playlist | None:
        row = self._get_fresh("playlist_meta", "pid", pid, ttl_sec)
        return _playlist_from_dict(json.loads(row)) if row else None

    def invalidate_playlist(self, pid: str) -> None:
        self._delete("playlist_meta", "pid", pid)

    # ------------------------------------------------------------------ ArtistDetail

    def put_artist(self, ad: ArtistDetail) -> None:
        self._upsert("artist_meta", "mid", ad.singer.mid, _dump(ad))

    def get_artist(
        self, mid: str, *, ttl_sec: int = DEFAULT_TTL_SEC
    ) -> ArtistDetail | None:
        row = self._get_fresh("artist_meta", "mid", mid, ttl_sec)
        return _artist_from_dict(json.loads(row)) if row else None

    def invalidate_artist(self, mid: str) -> None:
        self._delete("artist_meta", "mid", mid)

    # ------------------------------------------------------------------ Liked songs

    def is_liked(self, mid: str) -> bool:
        with self._lock:
            assert self._conn is not None
            row = self._conn.execute(
                "SELECT 1 FROM liked_song WHERE mid = ?", (mid,)
            ).fetchone()
        return row is not None

    def put_liked(self, song: Song) -> None:
        """记录某首歌为'我喜欢'(本地, 无 TTL)."""
        with self._lock:
            assert self._conn is not None
            now = int(time.time())
            self._conn.execute(
                "INSERT INTO liked_song (mid, song_data, added_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(mid) DO UPDATE SET "
                "  song_data=excluded.song_data, added_at=excluded.added_at",
                (song.mid, _dump(song), now),
            )
            self._conn.commit()

    def remove_liked(self, mid: str) -> None:
        with self._lock:
            assert self._conn is not None
            self._conn.execute("DELETE FROM liked_song WHERE mid = ?", (mid,))
            self._conn.commit()

    def list_liked(self) -> list[Song]:
        with self._lock:
            assert self._conn is not None
            rows = self._conn.execute(
                "SELECT song_data FROM liked_song ORDER BY added_at DESC"
            ).fetchall()
        return [_song_from_dict(json.loads(r["song_data"])) for r in rows]

    def replace_liked(self, songs: list[Song]) -> None:
        """整批替换 (远端 sync 用); 单事务删旧+插新."""
        with self._lock:
            assert self._conn is not None
            now = int(time.time())
            self._conn.execute("DELETE FROM liked_song")
            self._conn.executemany(
                "INSERT INTO liked_song (mid, song_data, added_at) VALUES (?, ?, ?)",
                [(s.mid, _dump(s), now) for s in songs],
            )
            self._conn.commit()

    # ------------------------------------------------------------------ 内部

    def _upsert(self, table: str, pk_col: str, key: str, data: str) -> None:
        with self._lock:
            assert self._conn is not None
            now = int(time.time())
            self._conn.execute(
                f"INSERT INTO {table} ({pk_col}, data, fetched_at) "
                f"VALUES (?, ?, ?) "
                f"ON CONFLICT({pk_col}) DO UPDATE SET data=excluded.data, "
                f"fetched_at=excluded.fetched_at",
                (key, data, now),
            )
            self._conn.commit()

    def _get_fresh(
        self, table: str, pk_col: str, key: str, ttl_sec: int
    ) -> str | None:
        with self._lock:
            assert self._conn is not None
            row = self._conn.execute(
                f"SELECT data, fetched_at FROM {table} WHERE {pk_col} = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        age = int(time.time()) - int(row["fetched_at"])
        # ttl_sec=0 立即过期; >= 让边界明确
        if age >= ttl_sec:
            return None
        return row["data"]

    def _delete(self, table: str, pk_col: str, key: str) -> None:
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                f"DELETE FROM {table} WHERE {pk_col} = ?", (key,)
            )
            self._conn.commit()
