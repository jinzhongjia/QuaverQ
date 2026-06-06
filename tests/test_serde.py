"""Song <-> dict 序列化单测 (state.json / home.json 共用一套, 防字段漂移)."""

from __future__ import annotations

import json

from quaverq.core.models import Singer, Song
from quaverq.core.serde import song_from_dict, song_to_dict


def _sample_song() -> Song:
    return Song(
        mid="001abc",
        name="测试歌曲",
        singers=[
            Singer(mid="s1", name="歌手一", avatar_url="http://a/1.jpg"),
            Singer(mid="s2", name="歌手二"),
        ],
        album_mid="alb1",
        album_name="专辑名",
        cover_url="http://c/cover.jpg",
        duration=215,
        pay_play=1,
        file_qualities={"MP3_128", "FLAC"},
        media_mid="m123",
        id=987654,
    )


def test_round_trip_preserves_all_fields() -> None:
    song = _sample_song()
    assert song_from_dict(song_to_dict(song)) == song


def test_file_qualities_round_trips_as_set() -> None:
    restored = song_from_dict(song_to_dict(_sample_song()))
    assert isinstance(restored.file_qualities, set)
    assert restored.file_qualities == {"MP3_128", "FLAC"}


def test_to_dict_is_json_serializable() -> None:
    # set 已转 list, 不应抛
    json.dumps(song_to_dict(_sample_song()))


def test_from_dict_tolerates_missing_fields() -> None:
    song = song_from_dict({"mid": "x", "name": "y"})
    assert song.mid == "x"
    assert song.name == "y"
    assert song.singers == []
    assert song.duration == 0
    assert song.file_qualities == set()


def test_from_dict_singer_without_avatar() -> None:
    song = song_from_dict({"singers": [{"mid": "s", "name": "n"}]})
    assert song.singers[0].avatar_url == ""
