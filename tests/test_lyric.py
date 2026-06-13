"""LRC 解析 + LyricSync 单元测试."""

from __future__ import annotations

from quaverq.core.lyric import LyricSync, parse_lrc, parse_qrc, to_lrc
from quaverq.core.models import Lyric, LyricLine

# ============================================================== parse_lrc


def test_parse_lrc_basic():
    raw = "[00:12.50]第一行\n[00:18.20]第二行"
    lines = parse_lrc(raw)
    assert lines == [
        LyricLine(timestamp_ms=12500, text="第一行"),
        LyricLine(timestamp_ms=18200, text="第二行"),
    ]


def test_parse_lrc_with_minutes_seconds_millis():
    raw = "[01:23.450]hello\n[02:00.000]world"
    lines = parse_lrc(raw)
    assert lines[0].timestamp_ms == 83450
    assert lines[1].timestamp_ms == 120000


def test_parse_lrc_two_digit_millis():
    """[mm:ss.xx] 两位毫秒, 应当 *10 补到 3 位."""
    raw = "[00:05.00]a\n[00:05.20]b"
    lines = parse_lrc(raw)
    assert lines[0].timestamp_ms == 5000
    assert lines[1].timestamp_ms == 5200


def test_parse_lrc_no_millis():
    raw = "[01:00]hello"
    lines = parse_lrc(raw)
    assert lines[0].timestamp_ms == 60000


def test_parse_lrc_multi_timestamp_line_expands():
    """一行多个时间戳: [00:01][00:05]文本 → 两条 line 同样 text."""
    raw = "[00:01.00][00:05.00]chorus"
    lines = parse_lrc(raw)
    assert len(lines) == 2
    assert lines[0].timestamp_ms == 1000
    assert lines[1].timestamp_ms == 5000
    assert all(ln.text == "chorus" for ln in lines)


def test_parse_lrc_skips_metadata_only_lines():
    """[ar:周杰伦][ti:晴天][by:xxx] 这种元数据行无音频时间戳, 应跳过."""
    raw = "[ar:周杰伦]\n[ti:晴天]\n[00:10.00]真实歌词"
    lines = parse_lrc(raw)
    assert len(lines) == 1
    assert lines[0].text == "真实歌词"


def test_parse_lrc_strips_empty_text_lines():
    """空 text 行 (如纯时间戳 [00:30.00]) 保留 (作为间奏占位)."""
    raw = "[00:10.00]第一行\n[00:20.00]\n[00:30.00]第三行"
    lines = parse_lrc(raw)
    assert len(lines) == 3
    assert lines[1].text == ""


def test_parse_lrc_filters_double_slash_separator():
    """QQ 音乐 LRC 中的 '//' 行间分隔符应被过滤掉."""
    raw = "[00:10.00]第一行\n[00:15.00]//\n[00:20.00]第二行"
    lines = parse_lrc(raw)
    assert len(lines) == 2
    assert [ln.text for ln in lines] == ["第一行", "第二行"]


def test_parse_lrc_sorts_by_timestamp():
    raw = "[00:30.00]后\n[00:10.00]先\n[00:20.00]中"
    lines = parse_lrc(raw)
    assert [ln.timestamp_ms for ln in lines] == [10000, 20000, 30000]


def test_parse_lrc_empty_input():
    assert parse_lrc("") == []
    assert parse_lrc("   \n  ") == []


def test_parse_lrc_malformed_lines_ignored():
    raw = "not-a-lrc-line\n[bad-format]\n[00:15.00]ok\nrandom"
    lines = parse_lrc(raw)
    assert len(lines) == 1
    assert lines[0].text == "ok"


# ============================================================== parse_qrc


def test_parse_qrc_basic_word_timings():
    raw = "[1185,2339]雨(1185,289)过(1474,221)后(1695,202)"
    lines = parse_qrc(raw)
    assert len(lines) == 1
    line = lines[0]
    assert line.timestamp_ms == 1185
    assert line.text == "雨过后"
    assert [(w.text, w.start_ms, w.duration_ms) for w in line.words] == [
        ("雨", 1185, 289),
        ("过", 1474, 221),
        ("后", 1695, 202),
    ]


def test_parse_qrc_text_with_parens_split_by_timing():
    # 字文本本身含括号; 以 (数字,数字) 时间标记为界切分
    raw = "[0,500]Dizzo ((2764,212)蔡(2976,190))(3524,0)"
    words = parse_qrc(raw)[0].words
    assert [w.text for w in words] == ["Dizzo (", "蔡", ")"]
    assert words[0].start_ms == 2764


def test_parse_qrc_skips_xml_and_metadata_lines():
    raw = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<QrcInfos>\n"
        '<Lyric_1 LyricType="1" LyricContent="[ti:歌名]\n'
        "[ar:歌手]\n"
        "[offset:0]\n"
        "[1000,500]你(1000,250)好(1250,250)\n"
        '"></Lyric_1>\n'
        "</QrcInfos>"
    )
    lines = parse_qrc(raw)
    assert len(lines) == 1
    assert lines[0].text == "你好"
    assert lines[0].timestamp_ms == 1000


def test_parse_qrc_trailing_xml_after_last_word_ignored():
    lines = parse_qrc('[1000,500]景(1000,112)">')
    assert len(lines[0].words) == 1
    assert lines[0].text == "景"


def test_parse_qrc_sorts_by_line_start():
    raw = "[3000,500]丙(3000,100)\n[1000,500]甲(1000,100)\n[2000,500]乙(2000,100)"
    lines = parse_qrc(raw)
    assert [ln.timestamp_ms for ln in lines] == [1000, 2000, 3000]
    assert [ln.text for ln in lines] == ["甲", "乙", "丙"]


def test_parse_qrc_filters_double_slash_separator():
    """QQ 音乐 QRC 中的 '//' 行间分隔符应被过滤掉."""
    raw = "[0,500]你(0,250)好(250,250)\n[500,0]//(500,0)\n[1000,500]世(1000,250)界(1250,250)"
    lines = parse_qrc(raw)
    assert len(lines) == 2
    assert [ln.text for ln in lines] == ["你好", "世界"]


def test_parse_qrc_empty_input():
    assert parse_qrc("") == []
    assert parse_qrc("<QrcInfos></QrcInfos>") == []


# ============================================================== LyricSync.line_at


def _ly(*pairs):
    return Lyric(
        mid="x",
        lines=[LyricLine(timestamp_ms=ts, text=t) for ts, t in pairs],
    )


def test_line_at_returns_neg1_before_first_line():
    s = LyricSync()
    s.set_lyric(_ly((10000, "a"), (20000, "b")))
    assert s.line_at(0) == -1
    assert s.line_at(9999) == -1


def test_line_at_returns_correct_index_within_line():
    s = LyricSync()
    s.set_lyric(_ly((10000, "a"), (20000, "b"), (30000, "c")))
    assert s.line_at(10000) == 0
    assert s.line_at(15000) == 0
    assert s.line_at(19999) == 0
    assert s.line_at(20000) == 1
    assert s.line_at(29999) == 1
    assert s.line_at(30000) == 2


def test_line_at_past_last_line_returns_last_index():
    s = LyricSync()
    s.set_lyric(_ly((10000, "a"), (20000, "b")))
    assert s.line_at(60000) == 1


def test_line_at_with_no_lyric_returns_neg1():
    s = LyricSync()
    assert s.line_at(5000) == -1


# ============================================================== LyricSync.window


def test_window_returns_centered_slice():
    s = LyricSync()
    s.set_lyric(_ly(*[(i * 1000, f"L{i}") for i in range(10)]))
    win, active = s.window(position_ms=5000, before=2, after=3)
    # active line is index 5; window 包含 3..8 (before=2 + active + after=3)
    assert [ln.text for ln in win] == ["L3", "L4", "L5", "L6", "L7", "L8"]
    assert active == 2  # 在 window 内 active line 的相对索引


def test_window_clamps_at_start_before_first_line():
    """首行 ts=1000, position=0 还没开始 → active=-1, 给预览窗口."""
    s = LyricSync()
    s.set_lyric(_ly(*[((i + 1) * 1000, f"L{i}") for i in range(10)]))
    win, active = s.window(position_ms=0, before=3, after=2)
    assert [ln.text for ln in win] == ["L0", "L1", "L2", "L3", "L4", "L5"]
    assert active == -1


def test_window_clamps_at_start_within_first_line():
    """在首行内时 active=0, window 从 0 开始 (不能 before)."""
    s = LyricSync()
    s.set_lyric(_ly(*[(i * 1000, f"L{i}") for i in range(10)]))
    win, active = s.window(position_ms=0, before=3, after=2)
    assert [ln.text for ln in win] == ["L0", "L1", "L2"]
    assert active == 0


def test_window_clamps_at_end():
    s = LyricSync()
    s.set_lyric(_ly(*[(i * 1000, f"L{i}") for i in range(5)]))
    win, active = s.window(position_ms=10000, before=2, after=4)
    # active = 4 (last); window=2..4
    assert [ln.text for ln in win] == ["L2", "L3", "L4"]
    assert active == 2


def test_window_empty_lyric():
    s = LyricSync()
    win, active = s.window(position_ms=5000)
    assert win == []
    assert active == -1


# ============================================================== to_lrc


def test_to_lrc_basic_lines():
    lyric = Lyric(
        mid="m1",
        lines=[
            LyricLine(timestamp_ms=12500, text="第一行"),
            LyricLine(timestamp_ms=83450, text="第二行"),
        ],
    )
    assert to_lrc(lyric) == "[00:12.50]第一行\n[01:23.45]第二行\n"


def test_to_lrc_roundtrips_through_parse_lrc():
    lyric = Lyric(
        mid="m1",
        lines=[
            LyricLine(timestamp_ms=5000, text="hello"),
            LyricLine(timestamp_ms=65200, text="world"),
        ],
    )
    parsed = parse_lrc(to_lrc(lyric))
    assert [(ln.timestamp_ms, ln.text) for ln in parsed] == [(5000, "hello"), (65200, "world")]


def test_to_lrc_translation_as_second_line_same_timestamp():
    # QQ 双行风格: 译文紧随原文, 共用时间戳
    lyric = Lyric(
        mid="m1",
        lines=[LyricLine(timestamp_ms=1000, text="Hello", translation="你好")],
        has_translation=True,
    )
    assert to_lrc(lyric) == "[00:01.00]Hello\n[00:01.00]你好\n"


def test_to_lrc_translation_can_be_disabled():
    lyric = Lyric(
        mid="m1",
        lines=[LyricLine(timestamp_ms=1000, text="Hello", translation="你好")],
        has_translation=True,
    )
    assert to_lrc(lyric, with_translation=False) == "[00:01.00]Hello\n"


def test_to_lrc_metadata_header():
    lyric = Lyric(mid="m1", lines=[LyricLine(timestamp_ms=0, text="x")])
    text = to_lrc(lyric, title="晴天", artist="周杰伦", album="叶惠美")
    assert text.startswith("[ti:晴天]\n[ar:周杰伦]\n[al:叶惠美]\n")
    assert text.endswith("[00:00.00]x\n")


def test_to_lrc_empty_lyric_returns_empty():
    assert to_lrc(Lyric(mid="m1")) == ""
    assert to_lrc(None) == ""


def test_to_lrc_long_song_minutes_beyond_an_hour():
    # LRC 的 mm 字段直接放分钟数, 不进位到小时
    lyric = Lyric(mid="m1", lines=[LyricLine(timestamp_ms=75 * 60_000, text="x")])
    assert to_lrc(lyric) == "[75:00.00]x\n"


def test_to_lrc_centisecond_rounding():
    # 毫秒向下取整到厘秒, 不四舍五入进位 (避免 999ms -> 100cs 溢出)
    lyric = Lyric(mid="m1", lines=[LyricLine(timestamp_ms=1999, text="x")])
    assert to_lrc(lyric) == "[00:01.99]x\n"
