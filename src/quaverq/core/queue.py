"""播放队列 + 4 种播放模式.

设计要点:
- 4 种 PlayMode: SEQUENCE / REPEAT_ALL / REPEAT_ONE / SHUFFLE
- on_song_end() 由 player 的 GStreamer EOS 回调触发; 顺序模式播完即停, 循环模式
  无限继续, 单曲模式 EOS 回到同一首, 随机模式按打乱顺序往下走.
- next() / prev() 是用户主动操作; REPEAT_ONE 模式下用户还是能跳下一首.
- SHUFFLE 模式维护独立的索引置换列表; 切到 SHUFFLE 时重新生成.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum, auto

from .models import Song

logger = logging.getLogger(__name__)


class PlayMode(Enum):
    """播放模式."""

    SEQUENCE = auto()  # 顺序: 播完最后一首即停
    REPEAT_ALL = auto()  # 列表循环
    REPEAT_ONE = auto()  # 单曲循环 (EOS 时回到同一首, next/prev 仍跳)
    SHUFFLE = auto()  # 随机播放


@dataclass
class PlayQueue:
    """播放队列.

    所有操作都是同步的; 适合在异步上下文中直接调用.
    EOS 由 player 通过 controller 转调 `on_song_end()`.
    """

    songs: list[Song] = field(default_factory=list)
    current_index: int = -1
    mode: PlayMode = PlayMode.SEQUENCE
    rng: random.Random = field(default_factory=random.Random)
    # 队列来源标识 (e.g. "daily" 表示猜你喜欢自动续接); 默认 "" 不参与自动续接.
    source: str = ""

    # 私有: SHUFFLE 模式下的下一首索引轮次 (打乱后剩余可播的索引列表)
    _shuffle_remaining: list[int] = field(default_factory=list, init=False, repr=False)
    _shuffle_history: list[int] = field(default_factory=list, init=False, repr=False)

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.songs)

    def current(self) -> Song | None:
        if 0 <= self.current_index < len(self.songs):
            return self.songs[self.current_index]
        return None

    def push(
        self,
        songs: list[Song],
        *,
        play_now: bool = False,
        start_index: int = 0,
        source: str = "",
    ) -> Song | None:
        """替换整个队列.

        play_now=True: 把 current 设到 start_index 并返回那首歌 (调用方负责真播放).
        play_now=False: 替换 list, current 拉回 index 0 (但不强制播放).
        source: 标记队列来源, 触发自动续接 (e.g. "daily" 猜你喜欢播完取下一批).
        """
        self.source = source
        self.songs = list(songs)
        if not self.songs:
            self.current_index = -1
            self._shuffle_remaining = []
            self._shuffle_history = []
            return None

        idx = start_index if play_now else 0
        if not (0 <= idx < len(self.songs)):
            idx = 0
        self.current_index = idx
        # SHUFFLE 模式下, 重置剩余索引池 (排除当前)
        if self.mode == PlayMode.SHUFFLE:
            self._reset_shuffle_pool(excluding=idx)
        return self.current() if play_now else None

    def insert_next(self, song: Song) -> None:
        """在 current 之后插一首 (下一首播放). 不影响 current."""
        if not self.songs:
            self.songs = [song]
            self.current_index = 0
            return
        insert_at = self.current_index + 1
        self.songs.insert(insert_at, song)
        # SHUFFLE 池中, 新索引插入到下一首位置
        if self.mode == PlayMode.SHUFFLE:
            # 已存在索引 >= insert_at 的全部 +1
            self._shuffle_remaining = [
                i + 1 if i >= insert_at else i for i in self._shuffle_remaining
            ]
            self._shuffle_history = [i + 1 if i >= insert_at else i for i in self._shuffle_history]
            self._shuffle_remaining.insert(0, insert_at)

    def clear(self) -> None:
        self.songs = []
        self.current_index = -1
        self.source = ""
        self._shuffle_remaining = []
        self._shuffle_history = []

    def remove_at(self, index: int) -> Song | None:
        """移除指定索引的歌; 返回被移除的歌, 索引无效返 None.

        - 移除 current 之前的: current_index 前移 1, 仍指向同一首;
        - 移除 current 本身: current_index 不动 (顶上来的是原下一首),
          越界 (移的是末尾) 则钳到新末尾, 队列空时 -1;
        - SHUFFLE 池/历史同步剔除该索引并重映射.
        """
        if not (0 <= index < len(self.songs)):
            return None
        removed = self.songs.pop(index)
        if index < self.current_index:
            self.current_index -= 1
        elif index == self.current_index and self.current_index >= len(self.songs):
            self.current_index = len(self.songs) - 1
        if self.mode == PlayMode.SHUFFLE:
            self._shuffle_remaining = [
                i - 1 if i > index else i for i in self._shuffle_remaining if i != index
            ]
            self._shuffle_history = [
                i - 1 if i > index else i for i in self._shuffle_history if i != index
            ]
        return removed

    def append(self, songs: list[Song]) -> list[Song]:
        """在队列末尾追加歌曲, 去重已存在的 mid; 返回真正被加入的歌. 不改 current."""
        if not songs:
            return []
        existing = {s.mid for s in self.songs if s.mid}
        added: list[Song] = []
        for song in songs:
            if not song.mid or song.mid in existing:
                continue
            existing.add(song.mid)
            self.songs.append(song)
            added.append(song)
        # SHUFFLE 模式下, 把新索引并入剩余池 (位置打乱)
        if added and self.mode == PlayMode.SHUFFLE:
            new_start = len(self.songs) - len(added)
            new_indices = list(range(new_start, len(self.songs)))
            self.rng.shuffle(new_indices)
            self._shuffle_remaining.extend(new_indices)
        return added

    def jump_to(self, index: int) -> Song | None:
        """直接跳到指定索引; 失败返 None."""
        if not (0 <= index < len(self.songs)):
            return None
        self.current_index = index
        if self.mode == PlayMode.SHUFFLE:
            # 跳转后, 把当前从历史/剩余中拿掉
            if index in self._shuffle_remaining:
                self._shuffle_remaining.remove(index)
            if index not in self._shuffle_history:
                self._shuffle_history.append(index)
        return self.current()

    # ------------------------------------------------------------------
    # 模式切换
    # ------------------------------------------------------------------

    def set_mode(self, mode: PlayMode) -> None:
        if mode == self.mode:
            return
        self.mode = mode
        if mode == PlayMode.SHUFFLE:
            self._reset_shuffle_pool(excluding=self.current_index)
        else:
            self._shuffle_remaining = []
            self._shuffle_history = []

    # ------------------------------------------------------------------
    # next / prev (用户主动按按钮)
    # ------------------------------------------------------------------

    def next(self) -> Song | None:  # noqa: A003
        """用户按下一首. REPEAT_ONE 模式下仍跳到下一首 (不是循环本首)."""
        if not self.songs:
            return None
        if self.mode == PlayMode.SHUFFLE:
            return self._shuffle_advance()
        # SEQUENCE / REPEAT_ONE: 顺序往下
        # REPEAT_ALL: 末尾绕回
        nxt = self.current_index + 1
        if nxt >= len(self.songs):
            if self.mode == PlayMode.REPEAT_ALL:
                nxt = 0
            else:
                return None
        self.current_index = nxt
        return self.current()

    def prev(self) -> Song | None:
        if not self.songs:
            return None
        if self.mode == PlayMode.SHUFFLE:
            # 从历史回退
            if len(self._shuffle_history) >= 2:
                self._shuffle_history.pop()  # 弹出当前
                prev_idx = self._shuffle_history[-1]
                self.current_index = prev_idx
                return self.current()
            return None
        prev = self.current_index - 1
        if prev < 0:
            if self.mode == PlayMode.REPEAT_ALL:
                prev = len(self.songs) - 1
            else:
                return None
        self.current_index = prev
        return self.current()

    # ------------------------------------------------------------------
    # GStreamer EOS 回调
    # ------------------------------------------------------------------

    def on_song_end(self) -> Song | None:
        """歌曲自然播放结束时调用; 返回下一首应播的歌 (或 None 表示停)."""
        if not self.songs:
            return None
        if self.mode == PlayMode.REPEAT_ONE:
            return self.current()
        return self.next()

    def peek_next(self) -> Song | None:
        """非变异地看"自然播完后将播哪首" (on_song_end 语义), 供预取下一首链接用.

        SHUFFLE 空池时不重洗直接返 None —— 重洗只在真正 advance 时发生,
        否则 peek 会改变后续随机顺序.
        """
        if not self.songs:
            return None
        if self.mode == PlayMode.REPEAT_ONE:
            return self.current()
        if self.mode == PlayMode.SHUFFLE:
            if not self._shuffle_remaining:
                return None
            idx = self._shuffle_remaining[0]
            return self.songs[idx] if 0 <= idx < len(self.songs) else None
        nxt = self.current_index + 1
        if nxt >= len(self.songs):
            if self.mode != PlayMode.REPEAT_ALL:
                return None
            nxt = 0
        return self.songs[nxt] if 0 <= nxt < len(self.songs) else None

    # ------------------------------------------------------------------
    # SHUFFLE 内部
    # ------------------------------------------------------------------

    def _reset_shuffle_pool(self, *, excluding: int) -> None:
        """重新生成 shuffle 顺序; 把当前索引排到 history."""
        indices = list(range(len(self.songs)))
        if 0 <= excluding < len(self.songs):
            indices.remove(excluding)
        self.rng.shuffle(indices)
        self._shuffle_remaining = indices
        self._shuffle_history = [excluding] if 0 <= excluding < len(self.songs) else []

    def _shuffle_advance(self) -> Song | None:
        if not self._shuffle_remaining:
            if self.mode == PlayMode.SHUFFLE:
                # 一轮结束, 重新洗 (排除当前 current 以避免重复)
                self._reset_shuffle_pool(excluding=self.current_index)
                if not self._shuffle_remaining:
                    return None
            else:
                return None
        next_idx = self._shuffle_remaining.pop(0)
        self.current_index = next_idx
        self._shuffle_history.append(next_idx)
        return self.current()
