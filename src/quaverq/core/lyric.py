"""LRC 歌词解析 + 同步定位.

LRC 格式:
    [00:12.50]第一行
    [00:18.200]第二行
    [01:00.00][02:00.00]副歌  (一行多个时间戳)
    [ar:周杰伦]                (元数据, 忽略)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Lyric, LyricLine


# [mm:ss(.xxx)?]  支持 2/3 位毫秒, 毫秒可缺省
_TS_RE = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\]")


def parse_lrc(raw: str) -> list[LyricLine]:
    """解析 LRC 文本为 LyricLine 列表 (按时间戳升序)."""
    if not raw:
        return []

    result: list[LyricLine] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # 提取所有时间戳; 找不到说明是元数据/无效行
        matches = list(_TS_RE.finditer(line))
        if not matches:
            continue
        # 取最后一个时间戳之后的文本作为歌词内容
        text = line[matches[-1].end():].strip()
        for m in matches:
            mm = int(m.group(1))
            ss = int(m.group(2))
            ms_part = m.group(3) or "0"
            # 两位毫秒补 *10 (LRC 常见 xx 实际 0.0xx 秒)
            if len(ms_part) == 1:
                ms = int(ms_part) * 100
            elif len(ms_part) == 2:
                ms = int(ms_part) * 10
            else:
                ms = int(ms_part)
            ts = mm * 60_000 + ss * 1000 + ms
            result.append(LyricLine(timestamp_ms=ts, text=text))

    result.sort(key=lambda ln: ln.timestamp_ms)
    return result


@dataclass
class LyricSync:
    """根据播放位置定位当前行 + 提供窗口视图.

    UI 用法:
        sync = LyricSync()
        sync.set_lyric(lyric)
        # 每 200ms 刷新一次
        win, active_in_win = sync.window(player.position_ms, before=2, after=4)
        # active_in_win = -1 表示当前还在第一行之前
    """

    _lines: list[LyricLine] = field(default_factory=list, init=False)

    def set_lyric(self, lyric: Lyric | None) -> None:
        self._lines = list(lyric.lines) if lyric else []

    def line_at(self, position_ms: int) -> int:
        """返回当前 position 对应的行索引; -1 表示在第一行之前; 末行之后返回末行."""
        if not self._lines:
            return -1
        if position_ms < self._lines[0].timestamp_ms:
            return -1
        # 线性扫描足够 (歌词通常 <300 行)
        for i in range(len(self._lines) - 1):
            if position_ms < self._lines[i + 1].timestamp_ms:
                return i
        return len(self._lines) - 1

    def window(
        self,
        position_ms: int,
        *,
        before: int = 2,
        after: int = 4,
    ) -> tuple[list[LyricLine], int]:
        """返回以当前行为中心的窗口 + active line 在窗口内的相对索引.

        当 position 在首行之前: active_in_win = -1, window 取前 (before + after + 1) 行.
        当 position 已到末行附近: window 在末尾收紧, active_in_win 反映其位置.
        """
        if not self._lines:
            return [], -1

        active = self.line_at(position_ms)
        n = len(self._lines)

        if active < 0:
            # 还没开始唱; 给前几行作窗口预览
            size = before + after + 1
            return list(self._lines[:size]), -1

        start = max(0, active - before)
        end = min(n, active + after + 1)
        return list(self._lines[start:end]), active - start
