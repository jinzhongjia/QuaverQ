"""Lyrics D-Bus 接口单元测试.

D-Bus 实际注册留到集成测试 (busctl introspect 验证). 这里只测纯函数:
- Lyric → D-Bus payload 的字段映射 (mid/has_word_timing/lines tuples)
- compute_active_word: position 落在 LyricLine.words 中的字索引定位
- compute_active_line: 复用 LyricSync.line_at 的封装语义验证
"""

from __future__ import annotations

from quaverq.core.lyric_dbus import (
    compute_active_word,
    lyric_to_payload,
    window_to_payload,
)
from quaverq.core.models import Lyric, LyricLine, LyricWord

# ============================================================== payload mapping


def _make_qrc_lyric() -> Lyric:
    return Lyric(
        mid="003abc",
        lines=[
            LyricLine(
                timestamp_ms=1000,
                text="你好世界",
                translation="hello world",
                words=[
                    LyricWord(text="你", start_ms=1000, duration_ms=200),
                    LyricWord(text="好", start_ms=1200, duration_ms=200),
                    LyricWord(text="世", start_ms=1400, duration_ms=200),
                    LyricWord(text="界", start_ms=1600, duration_ms=400),
                ],
            ),
            LyricLine(
                timestamp_ms=3000,
                text="再见",
                translation="bye",
                words=[
                    LyricWord(text="再", start_ms=3000, duration_ms=300),
                    LyricWord(text="见", start_ms=3300, duration_ms=300),
                ],
            ),
        ],
        has_translation=True,
    )


def test_lyric_to_payload_qrc_with_translation():
    mid, has_word, lines = lyric_to_payload(_make_qrc_lyric())
    assert mid == "003abc"
    assert has_word is True
    assert len(lines) == 2
    ts, text, translation, words = lines[0]
    assert ts == 1000
    assert text == "你好世界"
    assert translation == "hello world"
    assert len(words) == 4
    assert words[0] == (1000, 200, "你")
    assert words[3] == (1600, 400, "界")


def test_lyric_to_payload_can_hide_translation():
    mid, has_word, lines = lyric_to_payload(_make_qrc_lyric(), include_translation=False)

    assert mid == "003abc"
    assert has_word is True
    assert lines[0][2] == ""
    assert lines[1][2] == ""


def test_lyric_to_payload_plain_lrc():
    """无 words 时 has_word_timing=False, 每行 words=[]."""
    lyric = Lyric(
        mid="m",
        lines=[
            LyricLine(timestamp_ms=0, text="line1"),
            LyricLine(timestamp_ms=2000, text="line2"),
        ],
    )
    mid, has_word, lines = lyric_to_payload(lyric)
    assert mid == "m"
    assert has_word is False
    assert lines[0] == (0, "line1", "", [])
    assert lines[1] == (2000, "line2", "", [])


def test_lyric_to_payload_none():
    """None 歌词时返回空 payload (mid 空串, lines 空)."""
    mid, has_word, lines = lyric_to_payload(None)
    assert mid == ""
    assert has_word is False
    assert lines == []


def test_lyric_to_payload_mixed_lines_marks_has_word_true():
    """只要任一行带 words 就认为整曲是逐字模式 (与 controller 既有判定一致)."""
    lyric = Lyric(
        mid="m",
        lines=[
            LyricLine(timestamp_ms=0, text="纯文本行"),
            LyricLine(
                timestamp_ms=1000,
                text="字",
                words=[LyricWord(text="字", start_ms=1000, duration_ms=200)],
            ),
        ],
    )
    _, has_word, _ = lyric_to_payload(lyric)
    assert has_word is True


# ============================================================== active word


def test_compute_active_word_before_first_word():
    """position 在行起始之前 → -1."""
    line = _make_qrc_lyric().lines[0]
    assert compute_active_word(line, 0) == -1
    assert compute_active_word(line, 999) == -1


def test_compute_active_word_first_word_start_boundary():
    """边界: 字开始时刻应当算这个字."""
    line = _make_qrc_lyric().lines[0]
    assert compute_active_word(line, 1000) == 0


def test_compute_active_word_in_middle_of_word():
    line = _make_qrc_lyric().lines[0]
    # 第二字 (1200-1400): 1300 落在其中
    assert compute_active_word(line, 1300) == 1


def test_compute_active_word_in_gap_after_word_end():
    """字之间无 gap 时退化为命中下一字 start_ms 之前的最后一字."""
    line = _make_qrc_lyric().lines[0]
    # 1199 还在第一字 (1000+200=1200 是下一字 start)
    assert compute_active_word(line, 1199) == 0


def test_compute_active_word_past_line_end():
    """超出整行最后一字结束时间, 仍返回最后一字索引 (展示用)."""
    line = _make_qrc_lyric().lines[0]
    # 最后一字 1600+400=2000, position 2500 已过
    assert compute_active_word(line, 2500) == 3


def test_compute_active_word_no_words_returns_minus_one():
    line = LyricLine(timestamp_ms=0, text="x")  # 无 words
    assert compute_active_word(line, 0) == -1
    assert compute_active_word(line, 5000) == -1


# ============================================================== window


def test_window_to_payload_basic():
    """window_to_payload: list[LyricLine] → list[(ts, text, translation)] (不含 words)."""
    lines = _make_qrc_lyric().lines
    out = window_to_payload(lines)
    assert out == [
        (1000, "你好世界", "hello world"),
        (3000, "再见", "bye"),
    ]


def test_window_to_payload_can_hide_translation():
    lines = _make_qrc_lyric().lines
    out = window_to_payload(lines, include_translation=False)

    assert out == [
        (1000, "你好世界", ""),
        (3000, "再见", ""),
    ]


def test_window_to_payload_empty():
    assert window_to_payload([]) == []
