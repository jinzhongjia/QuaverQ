"""Qt bridge model tests."""

from __future__ import annotations

from PySide6.QtCore import Qt

from quaverq.bridge.models import (
    CardListModel,
    album_to_card,
    playlist_to_card,
    singer_to_card,
    song_from_map,
    SongListModel,
    song_to_map,
    top_to_card,
)
from quaverq.core.models import Album, Playlist, Singer, Song, TopList


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


def test_songs_returns_copy_of_model_items():
    model = SongListModel()
    song = _song()
    model.set_songs([song])

    songs = model.songs()
    songs.clear()

    assert model.count == 1
    assert model.songs() == [song]


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


def test_set_songs_skips_reset_when_unchanged():
    # SWR: 网络结果与缓存相同时不应整体重建 (否则列表闪烁)
    model = SongListModel()
    model.set_songs([_song()])
    resets: list[int] = []
    model.modelAboutToBeReset.connect(lambda: resets.append(1))

    model.set_songs([_song()])  # 等价数据 -> 跳过
    assert resets == []

    model.set_songs([])  # 真的变了 -> 重建
    assert resets == [1]


def test_set_cards_skips_reset_when_unchanged():
    model = CardListModel()
    card = playlist_to_card(Playlist(pid="p1", name="每日歌单", creator="QuaverQ", song_count=30))
    model.set_cards([card])
    resets: list[int] = []
    model.modelAboutToBeReset.connect(lambda: resets.append(1))

    model.set_cards(
        [playlist_to_card(Playlist(pid="p1", name="每日歌单", creator="QuaverQ", song_count=30))]
    )  # 等价数据 -> 跳过
    assert resets == []

    model.set_cards(
        [playlist_to_card(Playlist(pid="p2", name="别的", creator="QuaverQ", song_count=1))]
    )  # 变了 -> 重建
    assert resets == [1]


def test_card_list_model_roles_and_helpers():
    model = CardListModel()
    cards = [
        playlist_to_card(Playlist(pid="p1", name="每日歌单", creator="QuaverQ", song_count=30)),
        album_to_card(Album(mid="a1", name="叶惠美", singers=[Singer(mid="s1", name="周杰伦")], song_count=11)),
        singer_to_card(Singer(mid="ar1", name="周杰伦")),
        top_to_card(TopList(top_id=4, name="流行指数榜", total_num=100)),
    ]

    model.set_cards(cards)

    roles = {bytes(value).decode(): key for key, value in model.roleNames().items()}
    assert {"card", "kind", "cardId", "title", "subtitle", "coverUrl", "meta"} <= set(roles)
    assert model.count == 4
    assert model.data(model.index(0, 0), roles["kind"]) == "playlist"
    assert model.data(model.index(1, 0), roles["cardId"]) == "a1"
    assert model.cardAt(2)["kind"] == "artist"
    assert model.cardAt(3)["id"] == "4"
    assert model.cardAt(99) == {}


def test_lyric_line_to_map_includes_words():
    from quaverq.bridge.models import lyric_line_to_map
    from quaverq.core.models import LyricLine, LyricWord

    line = LyricLine(
        timestamp_ms=1000,
        text="你好",
        words=[LyricWord("你", 1000, 250), LyricWord("好", 1250, 250)],
    )
    data = lyric_line_to_map(line)
    assert data["lineText"] == "你好"
    assert data["words"] == [
        {"text": "你", "startMs": 1000, "durationMs": 250},
        {"text": "好", "startMs": 1250, "durationMs": 250},
    ]


def test_lyric_model_exposes_words_role():
    from quaverq.bridge.models import LyricLineListModel
    from quaverq.core.models import LyricLine, LyricWord

    model = LyricLineListModel()
    model.set_lines([LyricLine(timestamp_ms=0, text="hi", words=[LyricWord("hi", 0, 500)])])
    roles = {bytes(v).decode(): k for k, v in model.roleNames().items()}
    assert "words" in roles
    assert model.data(model.index(0, 0), roles["words"]) == [
        {"text": "hi", "startMs": 0, "durationMs": 500}
    ]
    # 纯逐行 (无 words) -> 空列表
    model.set_lines([LyricLine(timestamp_ms=0, text="plain")])
    assert model.data(model.index(0, 0), roles["words"]) == []
