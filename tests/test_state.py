"""SessionState 测试 - 启动/退出快照, 恢复 queue + position + mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quaverq.core.models import Singer, Song
from quaverq.core.queue import PlayMode, PlayQueue
from quaverq.core.state import SessionSnapshot, SessionState


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


def _make_queue(n: int = 3, mode: PlayMode = PlayMode.SEQUENCE) -> PlayQueue:
    songs = [
        Song(
            mid=f"m{i}",
            name=f"S{i}",
            singers=[Singer(mid=f"s{i}", name=f"歌手{i}")],
            album_name=f"album{i}",
            duration=200 + i,
        )
        for i in range(n)
    ]
    q = PlayQueue(mode=mode)
    q.push(songs, play_now=True, start_index=1)
    return q


# ============================================================== 基础


def test_restore_missing_file_returns_none(state_path: Path):
    s = SessionState(state_path)
    assert s.restore() is None


def test_restore_corrupted_file_returns_none(state_path: Path):
    state_path.write_text("not json at all")
    s = SessionState(state_path)
    assert s.restore() is None


# ============================================================== save/restore


def test_save_creates_file(state_path: Path):
    s = SessionState(state_path)
    q = _make_queue(3)
    s.save(q, position_ms=12345)
    assert state_path.exists()
    # JSON 解析
    data = json.loads(state_path.read_text())
    assert "queue" in data
    assert data["current_index"] == 1
    assert data["position_ms"] == 12345
    assert data["play_mode"] == "SEQUENCE"
    assert data["volume"] == 0.8


def test_roundtrip_queue_with_songs(state_path: Path):
    s = SessionState(state_path)
    q = _make_queue(3, mode=PlayMode.SHUFFLE)
    s.save(q, position_ms=5000, volume=0.35)

    snap = s.restore()
    assert isinstance(snap, SessionSnapshot)
    assert len(snap.songs) == 3
    assert snap.songs[0].mid == "m0"
    assert snap.songs[1].name == "S1"
    assert snap.songs[1].singers == [Singer(mid="s1", name="歌手1")]
    assert snap.current_index == 1
    assert snap.position_ms == 5000
    assert snap.play_mode == PlayMode.SHUFFLE
    assert snap.volume == 0.35


def test_restore_clamps_volume(state_path: Path):
    state_path.write_text(
        json.dumps(
            {
                "queue": [],
                "current_index": -1,
                "position_ms": 0,
                "play_mode": "SEQUENCE",
                "volume": 2.0,
            }
        )
    )
    s = SessionState(state_path)
    snap = s.restore()
    assert snap is not None
    assert snap.volume == 1.0


def test_roundtrip_empty_queue(state_path: Path):
    """空队列也能存读 (退出时没在播)."""
    s = SessionState(state_path)
    q = PlayQueue(mode=PlayMode.REPEAT_ALL)
    s.save(q, position_ms=0)
    snap = s.restore()
    assert snap is not None
    assert snap.songs == []
    assert snap.current_index == -1
    assert snap.play_mode == PlayMode.REPEAT_ALL


def test_save_overwrites_previous(state_path: Path):
    s = SessionState(state_path)
    q1 = _make_queue(2)
    s.save(q1, position_ms=1000)
    q2 = _make_queue(5)
    s.save(q2, position_ms=8000)

    snap = s.restore()
    assert len(snap.songs) == 5
    assert snap.position_ms == 8000


# ============================================================== apply_to_queue


def test_apply_snapshot_to_queue(state_path: Path):
    """SessionSnapshot.apply_to(queue) 还原 queue 状态."""
    s = SessionState(state_path)
    q = _make_queue(3, mode=PlayMode.SHUFFLE)
    s.save(q, position_ms=4321)

    snap = s.restore()
    new_q = PlayQueue()
    snap.apply_to(new_q)

    assert len(new_q.songs) == 3
    assert new_q.current_index == 1
    assert new_q.current().name == "S1"
    assert new_q.mode == PlayMode.SHUFFLE


def test_save_restore_preserves_queue_source(state_path: Path):
    """source 标签 (如 "daily") 必须跨重启保留, 否则猜你喜欢卡片认不出当前播放曲."""
    s = SessionState(state_path)
    q = _make_queue(3)
    q.source = "daily"
    s.save(q, position_ms=0)

    snap = s.restore()
    assert snap.source == "daily"
    new_q = PlayQueue()
    snap.apply_to(new_q)
    assert new_q.source == "daily"


def test_restore_missing_source_defaults_to_empty(state_path: Path):
    """旧版 state.json 没有 source 字段时, 恢复为空 (非 daily 队列)."""
    state_path.write_text(
        json.dumps({"queue": [], "current_index": -1, "position_ms": 0, "play_mode": "SEQUENCE"})
    )
    snap = SessionState(state_path).restore()
    assert snap is not None
    assert snap.source == ""


def test_apply_empty_snapshot_does_not_crash(state_path: Path):
    s = SessionState(state_path)
    s.save(PlayQueue(), position_ms=0)
    snap = s.restore()
    q = PlayQueue()
    snap.apply_to(q)
    assert q.current() is None


# ============================================================== invalid play_mode 容错


def test_restore_unknown_play_mode_falls_back_to_sequence(state_path: Path):
    state_path.write_text(
        json.dumps(
            {
                "queue": [],
                "current_index": -1,
                "position_ms": 0,
                "play_mode": "WEIRD_VALUE_FROM_FUTURE_VERSION",
            }
        )
    )
    s = SessionState(state_path)
    snap = s.restore()
    assert snap is not None
    assert snap.play_mode == PlayMode.SEQUENCE


# ============================================================== clear


def test_clear_removes_file(state_path: Path):
    s = SessionState(state_path)
    s.save(_make_queue(1), position_ms=0)
    assert state_path.exists()
    s.clear()
    assert not state_path.exists()


def test_clear_missing_file_does_not_raise(state_path: Path):
    s = SessionState(state_path)
    s.clear()  # 文件不存在不抛错
