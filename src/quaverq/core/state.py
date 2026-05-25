"""会话快照: 退出存 / 启动恢复 queue + current_index + position + mode.

文件位置: ~/.config/quaverq/state.json (controller 注入路径)

策略:
- save: 退出 cleanup 时同步写; 失败不影响退出
- restore: 启动期同步读; 失败/缺失返 None
- 不自动恢复播放, UI 显示历史 queue 但停在 paused 状态 (controller 决定)
- play_mode 用 enum.name 持久化 (跨版本兼容; 未知值回退 SEQUENCE)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import Singer, Song
from .queue import PlayMode, PlayQueue

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- 序列化


def _song_to_dict(s: Song) -> dict:
    d = asdict(s)
    # file_qualities 是 set, asdict 不友好; 转 list
    d["file_qualities"] = list(s.file_qualities)
    return d


def _song_from_dict(d: dict) -> Song:
    singers = [
        Singer(
            mid=s.get("mid", "") or "",
            name=s.get("name", "") or "",
            avatar_url=s.get("avatar_url", "") or "",
        )
        for s in (d.get("singers") or [])
    ]
    return Song(
        mid=d.get("mid", "") or "",
        name=d.get("name", "") or "",
        singers=singers,
        album_mid=d.get("album_mid", "") or "",
        album_name=d.get("album_name", "") or "",
        cover_url=d.get("cover_url", "") or "",
        duration=int(d.get("duration", 0) or 0),
        pay_play=int(d.get("pay_play", 0) or 0),
        file_qualities=set(d.get("file_qualities") or []),
        media_mid=d.get("media_mid", "") or "",
        id=int(d.get("id", 0) or 0),
    )


# ---------------------------------------------------------------- 快照


@dataclass
class SessionSnapshot:
    """从 state.json 读出来的快照, 可 apply_to(queue) 还原."""

    songs: list[Song] = field(default_factory=list)
    current_index: int = -1
    position_ms: int = 0
    play_mode: PlayMode = PlayMode.SEQUENCE

    def apply_to(self, queue: PlayQueue) -> None:
        """把快照状态写回一个空白 PlayQueue."""
        queue.mode = self.play_mode
        if not self.songs:
            queue.clear()
            return
        # push 然后 jump_to
        queue.push(self.songs, play_now=False)
        if 0 <= self.current_index < len(self.songs):
            queue.current_index = self.current_index
            # SHUFFLE 模式下重新生成 shuffle 池 (current 排除)
            if queue.mode == PlayMode.SHUFFLE:
                queue._reset_shuffle_pool(excluding=self.current_index)


# ---------------------------------------------------------------- SessionState

@dataclass
class SessionState:
    path: Path

    def __init__(self, path):
        self.path = Path(path)

    def save(self, queue: PlayQueue, *, position_ms: int = 0) -> None:
        """退出时调; 写 state.json. 失败只 log, 不抛."""
        try:
            data = {
                "queue": [_song_to_dict(s) for s in queue.songs],
                "current_index": queue.current_index,
                "position_ms": int(position_ms),
                "play_mode": queue.mode.name,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.info("会话快照已保存: %d 首, mode=%s", len(queue.songs), queue.mode.name)
        except Exception as exc:
            logger.warning("保存会话快照失败: %s", exc)

    def restore(self) -> SessionSnapshot | None:
        """启动时调; 不存在/损坏返 None."""
        if not self.path.exists():
            return None
        try:
            with open(self.path) as f:
                d = json.load(f)
        except Exception as exc:
            logger.warning("读取会话快照失败: %s", exc)
            return None

        songs = [_song_from_dict(x) for x in (d.get("queue") or [])]
        ci = int(d.get("current_index", -1) or -1)
        pos = int(d.get("position_ms", 0) or 0)

        mode_name = d.get("play_mode", "SEQUENCE")
        try:
            mode = PlayMode[mode_name]
        except (KeyError, TypeError):
            logger.info("快照的 play_mode=%r 未知, 回退 SEQUENCE", mode_name)
            mode = PlayMode.SEQUENCE

        logger.info("会话快照恢复: %d 首, mode=%s", len(songs), mode.name)
        return SessionSnapshot(
            songs=songs,
            current_index=ci,
            position_ms=pos,
            play_mode=mode,
        )

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("删除会话快照失败: %s", exc)
