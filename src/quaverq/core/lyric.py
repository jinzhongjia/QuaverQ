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

from .models import Lyric, LyricLine, LyricWord

# [mm:ss(.xxx)?]  支持 2/3 位毫秒, 毫秒可缺省
_TS_RE = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\]")

# QRC 逐字: 行首 [行起始ms,行时长ms], 行内每字 文本(字起始ms,字时长ms)
_QRC_LINE_RE = re.compile(r"\[(\d+),(\d+)\](.*)")
_QRC_WORD_RE = re.compile(r"\((\d+),(\d+)\)")


def parse_qrc(raw: str) -> list[LyricLine]:
    """解析解密后的 QRC 逐字歌词为带 words 的 LyricLine 列表 (按行起始升序).

    QRC 解密后是 XML, 真正的歌词体形如::

        [1185,2339]雨(1185,289)过(1474,221)...景(2321,112)

    逐行扫描, 只取行首匹配 ``[数字,数字]`` 的行 (XML 标签 / [ti:]/[offset:] 等
    元数据自然跳过). 字文本可含括号 (如 "Dizzo ("), 故以 ``(数字,数字)`` 时间标记
    为界切分, 文本取两个时间标记之间的部分.
    """
    if not raw:
        return []

    result: list[LyricLine] = []
    for raw_line in raw.splitlines():
        match = _QRC_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        line_start = int(match.group(1))
        content = match.group(3)

        words: list[LyricWord] = []
        cursor = 0
        for wm in _QRC_WORD_RE.finditer(content):
            text = content[cursor : wm.start()]
            words.append(
                LyricWord(
                    text=text,
                    start_ms=int(wm.group(1)),
                    duration_ms=int(wm.group(2)),
                )
            )
            cursor = wm.end()

        if not words:
            continue
        result.append(
            LyricLine(
                timestamp_ms=line_start,
                text="".join(w.text for w in words),
                words=words,
            )
        )

    result.sort(key=lambda ln: ln.timestamp_ms)
    return result


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
        text = line[matches[-1].end() :].strip()
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


def _format_lrc_timestamp(ms: int) -> str:
    """毫秒 -> ``[mm:ss.xx]`` (厘秒向下取整, 分钟不进位到小时, 长曲自然超两位)."""
    ms = max(0, ms)
    minutes, rem = divmod(ms, 60_000)
    seconds, milli = divmod(rem, 1000)
    return f"[{minutes:02d}:{seconds:02d}.{milli // 10:02d}]"


def to_lrc(
    lyric: Lyric | None,
    *,
    title: str = "",
    artist: str = "",
    album: str = "",
    with_translation: bool = True,
) -> str:
    """把解析后的 Lyric 序列化为标准 LRC 文本 (用于下载落盘).

    QRC 逐字行只取行级时间戳 (外部播放器普遍只认逐行 LRC); 翻译按 QQ 双行风格
    以同时间戳紧随原文行. 空歌词返回空串 (调用方据此跳过写盘).
    """
    if lyric is None or not lyric.lines:
        return ""

    out: list[str] = []
    if title:
        out.append(f"[ti:{title}]")
    if artist:
        out.append(f"[ar:{artist}]")
    if album:
        out.append(f"[al:{album}]")

    for line in lyric.lines:
        ts = _format_lrc_timestamp(line.timestamp_ms)
        out.append(f"{ts}{line.text}")
        if with_translation and line.translation:
            out.append(f"{ts}{line.translation}")
    return "\n".join(out) + "\n"


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
