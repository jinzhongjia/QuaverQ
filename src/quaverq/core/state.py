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
from dataclasses import dataclass, field
from pathlib import Path

from .models import Song
from .queue import PlayMode, PlayQueue
from .serde import song_from_dict as _song_from_dict, song_to_dict as _song_to_dict

logger = logging.getLogger(__name__)


# 序列化: Song <-> dict 复用 core/serde (与 home.json 共享, 防字段漂移)。


# ---------------------------------------------------------------- 快照


@dataclass
class SessionSnapshot:
    """从 state.json 读出来的快照, 可 apply_to(queue) 还原."""

    songs: list[Song] = field(default_factory=list)
    current_index: int = -1
    position_ms: int = 0
    play_mode: PlayMode = PlayMode.SEQUENCE
    volume: float = 0.8
    source: str = ""

    def apply_to(self, queue: PlayQueue) -> None:
        """把快照状态写回一个空白 PlayQueue."""
        queue.mode = self.play_mode
        if not self.songs:
            queue.clear()
            return
        # push 然后 jump_to
        queue.push(self.songs, play_now=False, source=self.source)
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

    def save(
        self,
        queue: PlayQueue,
        *,
        position_ms: int = 0,
        volume: float = 0.8,
    ) -> None:
        """退出时调; 写 state.json. 失败只 log, 不抛."""
        try:
            data = {
                "queue": [_song_to_dict(s) for s in queue.songs],
                "current_index": queue.current_index,
                "position_ms": int(position_ms),
                "play_mode": queue.mode.name,
                "volume": max(0.0, min(1.0, float(volume))),
                "source": queue.source,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # encoding 必须显式 UTF-8: Windows 中文 locale 默认 GBK, 含 Ø / Unicode 标题
            # (如 Concrete Blonde 的 ``Joey``) 会 UnicodeEncodeError 让快照保存失败.
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.info("会话快照已保存: %d 首, mode=%s", len(queue.songs), queue.mode.name)
        except Exception as exc:
            logger.warning("保存会话快照失败: %s", exc)

    def restore(self) -> SessionSnapshot | None:
        """启动时调; 不存在/损坏返 None."""
        if not self.path.exists():
            return None
        try:
            # 同 save: 必须显式 UTF-8, 否则在 Windows 上读 Linux 写的快照会 UnicodeDecodeError.
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception as exc:
            logger.warning("读取会话快照失败: %s", exc)
            return None

        songs = [_song_from_dict(x) for x in (d.get("queue") or [])]
        ci = int(d.get("current_index", -1) or -1)
        pos = int(d.get("position_ms", 0) or 0)
        volume = max(0.0, min(1.0, float(d.get("volume", 0.8) or 0.8)))

        mode_name = d.get("play_mode", "SEQUENCE")
        try:
            mode = PlayMode[mode_name]
        except (KeyError, TypeError):
            logger.info("快照的 play_mode=%r 未知, 回退 SEQUENCE", mode_name)
            mode = PlayMode.SEQUENCE

        logger.info("会话快照恢复: %d 首, mode=%s", len(songs), mode.name)
        source = str(d.get("source") or "")
        return SessionSnapshot(
            songs=songs,
            current_index=ci,
            position_ms=pos,
            play_mode=mode,
            volume=volume,
            source=source,
        )

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("删除会话快照失败: %s", exc)
