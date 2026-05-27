"""Qt bridge model tests."""

from __future__ import annotations

from PySide6.QtCore import Qt

from quaverq.bridge.models import SongListModel, song_from_map, song_to_map
from quaverq.core.models import Singer, Song


def _song() -> Song:
    return Song(
        mid="m1",
        name="晴天",
        singers=[Singer(mid="s1", name="周杰伦")],
        album_mid="a1",
        album_name="叶惠美",
        cover_url="https://example.test/cover.jpg",
        duration=269,
        media_mid="media1",
        id=97773,
    )


def test_song_list_model_roles_and_data():
    model = SongListModel()
    model.set_songs([_song()])

    assert model.rowCount() == 1
    assert model.count == 1

    roles = {bytes(value).decode(): key for key, value in model.roleNames().items()}
    assert {"song", "mid", "name", "singers", "albumName", "durationText", "coverUrl"} <= set(roles)

    idx = model.index(0, 0)
    assert model.data(idx, roles["mid"]) == "m1"
    assert model.data(idx, roles["name"]) == "晴天"
    assert model.data(idx, roles["singers"]) == "周杰伦"
    assert model.data(idx, roles["albumName"]) == "叶惠美"
    assert model.data(idx, roles["durationText"]) == "4:29"
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "晴天"


def test_song_at_returns_qvariant_map_shape():
    model = SongListModel()
    model.set_songs([_song()])

    data = model.songAt(0)
    assert data["mid"] == "m1"
    assert data["name"] == "晴天"
    assert data["singerNames"] == ["周杰伦"]
    assert data["durationText"] == "4:29"
    assert model.songAt(99) == {}


def test_song_map_roundtrip():
    song = _song()
    data = song_to_map(song)
    restored = song_from_map(data)

    assert restored.mid == song.mid
    assert restored.name == song.name
    assert restored.singers == song.singers
    assert restored.album_name == song.album_name
    assert restored.duration == song.duration
    assert restored.id == song.id
