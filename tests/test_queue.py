"""PlayQueue 单元测试.

4 种播放模式 (SEQUENCE / REPEAT_ALL / REPEAT_ONE / SHUFFLE) 的 next/prev/EOS
行为 + push / insert_next / jump_to / clear.
"""

from __future__ import annotations

import random

from quaverq.core.models import Song
from quaverq.core.queue import PlayMode, PlayQueue


def _make_songs(n: int) -> list[Song]:
    return [Song(mid=f"m{i}", name=f"S{i}") for i in range(n)]


# ============================================================== 基础

def test_empty_queue_has_no_current():
    q = PlayQueue()
    assert q.current() is None
    assert q.next() is None
    assert q.prev() is None
    assert len(q) == 0


def test_push_replaces_with_play_now_at_first_song():
    q = PlayQueue()
    songs = _make_songs(3)
    first = q.push(songs, play_now=True)
    assert first is not None
    assert first.mid == "m0"
    assert q.current().mid == "m0"
    assert len(q) == 3


def test_push_with_play_now_index_jumps_to_that_song():
    q = PlayQueue()
    songs = _make_songs(5)
    chosen = q.push(songs, play_now=True, start_index=3)
    assert chosen.mid == "m3"
    assert q.current().mid == "m3"


def test_push_without_play_now_does_not_change_current():
    q = PlayQueue()
    q.push(_make_songs(2), play_now=True)
    q.next()  # at m1
    q.push(_make_songs(3), play_now=False)  # 替换 list 不改 current_index
    # current_index 仍指向上一首 (m1) 但 list 已换了, 退化到 index=0
    # 我们的契约: push(play_now=False) 替换列表并把 current 拉回 index 0
    assert q.current().mid == "m0"


def test_clear_empties_queue():
    q = PlayQueue()
    q.push(_make_songs(3), play_now=True)
    q.clear()
    assert len(q) == 0
    assert q.current() is None


# ============================================================== SEQUENCE

def test_sequence_next_walks_through_then_stops_at_end():
    q = PlayQueue(mode=PlayMode.SEQUENCE)
    q.push(_make_songs(3), play_now=True)  # current m0
    assert q.next().mid == "m1"
    assert q.next().mid == "m2"
    # 末尾再 next 应该 None (顺序模式播完即停)
    assert q.next() is None


def test_sequence_prev_walks_back_then_stops_at_start():
    q = PlayQueue(mode=PlayMode.SEQUENCE)
    q.push(_make_songs(3), play_now=True, start_index=2)
    assert q.prev().mid == "m1"
    assert q.prev().mid == "m0"
    assert q.prev() is None


def test_sequence_on_song_end_advances_then_stops():
    q = PlayQueue(mode=PlayMode.SEQUENCE)
    q.push(_make_songs(2), play_now=True)
    assert q.on_song_end().mid == "m1"
    assert q.on_song_end() is None  # 列表末尾


# ============================================================== REPEAT_ALL

def test_repeat_all_wraps_around_at_end():
    q = PlayQueue(mode=PlayMode.REPEAT_ALL)
    q.push(_make_songs(3), play_now=True, start_index=2)
    assert q.next().mid == "m0"
    assert q.next().mid == "m1"


def test_repeat_all_prev_wraps_around_at_start():
    q = PlayQueue(mode=PlayMode.REPEAT_ALL)
    q.push(_make_songs(3), play_now=True, start_index=0)
    assert q.prev().mid == "m2"


def test_repeat_all_on_song_end_wraps_forever():
    q = PlayQueue(mode=PlayMode.REPEAT_ALL)
    q.push(_make_songs(2), play_now=True)
    assert q.on_song_end().mid == "m1"
    assert q.on_song_end().mid == "m0"
    assert q.on_song_end().mid == "m1"


# ============================================================== REPEAT_ONE

def test_repeat_one_on_song_end_returns_same_song():
    q = PlayQueue(mode=PlayMode.REPEAT_ONE)
    q.push(_make_songs(3), play_now=True, start_index=1)
    for _ in range(3):
        assert q.on_song_end().mid == "m1"


def test_repeat_one_next_button_still_skips_to_next():
    """REPEAT_ONE 是 EOS 时单曲循环; 用户按 next 应当能跳下一首."""
    q = PlayQueue(mode=PlayMode.REPEAT_ONE)
    q.push(_make_songs(3), play_now=True)
    assert q.next().mid == "m1"


# ============================================================== SHUFFLE

def test_shuffle_covers_all_songs_eventually():
    """SHUFFLE 模式连续 EOS 后, 所有歌都被播过 (一轮覆盖)."""
    q = PlayQueue(mode=PlayMode.SHUFFLE)
    songs = _make_songs(10)
    q.push(songs, play_now=True)
    first = q.current()
    seen = {first.mid}
    for _ in range(len(songs) - 1):
        nxt = q.on_song_end()
        assert nxt is not None
        seen.add(nxt.mid)
    assert seen == {s.mid for s in songs}


def test_shuffle_deterministic_when_seeded():
    """同 seed 产生同样的 shuffle 顺序 (回归测试用)."""
    rng_a = random.Random(42)
    rng_b = random.Random(42)
    qa = PlayQueue(mode=PlayMode.SHUFFLE, rng=rng_a)
    qb = PlayQueue(mode=PlayMode.SHUFFLE, rng=rng_b)
    songs = _make_songs(5)
    qa.push(songs, play_now=True)
    qb.push(songs, play_now=True)
    seq_a = [qa.current().mid] + [qa.on_song_end().mid for _ in range(4)]
    seq_b = [qb.current().mid] + [qb.on_song_end().mid for _ in range(4)]
    assert seq_a == seq_b


# ============================================================== insert_next / jump_to

def test_insert_next_plays_after_current():
    q = PlayQueue(mode=PlayMode.SEQUENCE)
    q.push(_make_songs(3), play_now=True)  # m0, m1, m2; current m0
    extra = Song(mid="extra", name="X")
    q.insert_next(extra)
    # 下一首应当是插入的, 而不是 m1
    assert q.next().mid == "extra"
    # 再 next 应当是 m1
    assert q.next().mid == "m1"


def test_jump_to_index_makes_it_current():
    q = PlayQueue(mode=PlayMode.SEQUENCE)
    q.push(_make_songs(5), play_now=True)
    target = q.jump_to(3)
    assert target.mid == "m3"
    assert q.current().mid == "m3"


def test_jump_to_invalid_index_returns_none():
    q = PlayQueue(mode=PlayMode.SEQUENCE)
    q.push(_make_songs(2), play_now=True)
    assert q.jump_to(99) is None
    assert q.jump_to(-1) is None


# ============================================================== mode 切换

def test_set_mode_takes_effect_for_next_on_song_end():
    q = PlayQueue(mode=PlayMode.SEQUENCE)
    q.push(_make_songs(2), play_now=True)
    q.on_song_end()  # to m1
    assert q.on_song_end() is None  # SEQUENCE 末尾停

    q.set_mode(PlayMode.REPEAT_ALL)
    q.jump_to(1)  # 重置 current
    assert q.on_song_end().mid == "m0"  # 现在循环回 m0


def test_set_mode_shuffle_regenerates_order():
    """切到 shuffle 后, 后续 on_song_end 走打乱序; 不保留旧 sequence."""
    q = PlayQueue(mode=PlayMode.SEQUENCE, rng=random.Random(0))
    q.push(_make_songs(5), play_now=True)
    q.set_mode(PlayMode.SHUFFLE)
    # 改 mode 后应该立即能给打乱的 next, 不抛错
    nxt = q.on_song_end()
    assert nxt is not None
    assert nxt.mid in {f"m{i}" for i in range(5)}
