"""core.download_store 单元测试: 下载记录持久化."""

from __future__ import annotations

import json

from quaverq.core.download_store import DownloadRecord, DownloadStore
from quaverq.core.models import Singer, Song


def _song(mid: str = "m1", name: str = "晴天") -> Song:
    return Song(
        mid=mid,
        name=name,
        singers=[Singer(mid="s1", name="周杰伦")],
        album_mid="alb1",
        album_name="叶惠美",
        cover_url="https://c/x.jpg",
        duration=269,
    )


def _record(
    mid: str = "m1",
    name: str = "晴天",
    path: str = "/tmp/x.mp3",
    quality: str = "MP3_320",
) -> DownloadRecord:
    return DownloadRecord(
        song=_song(mid, name),
        path=path,
        quality_label=quality,
        size=123,
        downloaded_at=1700000000,
    )


def test_add_then_find(tmp_path):
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(_record())

    rec = store.find("m1")
    assert rec is not None
    assert rec.song.name == "晴天"
    assert rec.path == "/tmp/x.mp3"
    assert rec.quality_label == "MP3_320"
    assert rec.mid == "m1"


def test_find_missing_returns_none(tmp_path):
    store = DownloadStore(tmp_path / "downloads.json")
    assert store.find("nope") is None


def test_add_same_mid_overwrites_in_place(tmp_path):
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(_record(path="/tmp/old.flac", quality="FLAC"))
    store.add(_record(path="/tmp/new.mp3", quality="MP3_320"))

    assert len(store.all()) == 1
    assert store.find("m1").path == "/tmp/new.mp3"
    assert store.find("m1").quality_label == "MP3_320"


def test_remove(tmp_path):
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(_record())
    store.remove("m1")

    assert store.find("m1") is None
    assert store.all() == []


def test_remove_missing_is_noop(tmp_path):
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(_record("m1"))
    store.remove("nope")
    assert len(store.all()) == 1


def test_persist_roundtrip(tmp_path):
    path = tmp_path / "downloads.json"
    s1 = DownloadStore(path)
    s1.add(_record("m1", "晴天"))
    s1.add(_record("m2", "稻香", path="/tmp/y.mp3"))

    s2 = DownloadStore(path)
    assert len(s2.load()) == 2
    assert s2.find("m1").song.name == "晴天"
    assert s2.find("m2").path == "/tmp/y.mp3"
    assert s2.find("m2").downloaded_at == 1700000000


def test_load_missing_file_returns_empty(tmp_path):
    store = DownloadStore(tmp_path / "nope.json")
    assert store.load() == []
    assert store.all() == []


def test_load_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "downloads.json"
    path.write_text("{ broken json", encoding="utf-8")

    store = DownloadStore(path)
    assert store.load() == []  # 不抛


def test_load_non_list_payload_returns_empty(tmp_path):
    path = tmp_path / "downloads.json"
    path.write_text('{"not": "a list"}', encoding="utf-8")

    store = DownloadStore(path)
    assert store.load() == []


def test_add_persists_immediately(tmp_path):
    # add 立即落盘 (无需显式 save), 崩溃也不丢记录
    path = tmp_path / "downloads.json"
    DownloadStore(path).add(_record())

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    assert not list(tmp_path.glob("*.tmp"))  # 原子写不留临时文件


def test_utf8_roundtrip(tmp_path):
    path = tmp_path / "downloads.json"
    s1 = DownloadStore(path)
    s1.add(_record(name="稻香Ø中文"))

    assert "稻香" in path.read_text(encoding="utf-8")  # 非 ASCII 转义关闭
    s2 = DownloadStore(path)
    s2.load()
    assert s2.find("m1").song.name == "稻香Ø中文"


def test_insertion_order_preserved(tmp_path):
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(_record("m1", "A"))
    store.add(_record("m2", "B"))
    store.add(_record("m3", "C"))
    assert [r.song.mid for r in store.all()] == ["m1", "m2", "m3"]


def test_record_file_exists(tmp_path):
    real = tmp_path / "song.mp3"
    real.write_bytes(b"x")
    present = DownloadRecord(song=_song(), path=str(real))
    absent = DownloadRecord(song=_song(), path=str(tmp_path / "gone.mp3"))
    empty = DownloadRecord(song=_song(), path="")

    assert present.file_exists() is True
    assert absent.file_exists() is False
    assert empty.file_exists() is False
