"""PlayerController tests."""

from __future__ import annotations

from quaverq.bridge.player_controller import PlayerController
from quaverq.bridge.models import SongListModel
from quaverq.core.models import Singer, Song, SongUrl


class _FakeServiceController:
    def __init__(self) -> None:
        self.calls: list[tuple[Song, str]] = []

    async def get_song_url(
        self,
        song: Song,
        *,
        quality_preference: str,
    ) -> SongUrl:
        self.calls.append((song, quality_preference))
        return SongUrl(mid=song.mid, url=f"https://audio.example.test/{song.mid}.mp3")


def _song(mid: str, name: str) -> Song:
    return Song(
        mid=mid,
        name=name,
        singers=[Singer(mid="s1", name="周杰伦")],
        album_name="叶惠美",
        duration=180,
    )


async def test_push_and_play_loads_source_and_emits_play_request():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    play_requests: list[bool] = []
    controller.playRequested.connect(lambda: play_requests.append(True))

    await controller.push_and_play_async(
        {
            "mid": "m1",
            "name": "晴天",
            "singers": [{"mid": "s1", "name": "周杰伦"}],
            "albumName": "叶惠美",
            "duration": 269,
        }
    )

    assert [(song.mid, quality) for song, quality in service.calls] == [("m1", "balanced")]
    assert controller.currentSong["name"] == "晴天"
    assert controller.currentIndex == 0
    assert controller.queueModel.count == 1
    assert controller.sourceUrl == "https://audio.example.test/m1.mp3"
    assert controller.durationMs == 269_000
    assert controller.positionMs == 0
    assert controller.loading is False
    assert controller.errorMessage == ""
    assert controller.playbackState == "loading"
    assert play_requests == [True]


async def test_push_and_play_rejects_incomplete_song_data():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.push_and_play_async({"name": "缺少 mid"})

    assert errors == ["无法播放：歌曲数据不完整"]
    assert controller.errorMessage == "无法播放：歌曲数据不完整"
    assert controller.sourceUrl == ""
    assert controller.queueModel.count == 0


async def test_play_from_model_uses_full_search_result_queue_and_next():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    model = SongListModel()
    model.set_songs([_song("m1", "晴天"), _song("m2", "七里香"), _song("m3", "稻香")])

    await controller.play_from_model_async(model, 1)

    assert controller.queueModel.count == 3
    assert controller.currentIndex == 1
    assert controller.currentSong["name"] == "七里香"
    assert controller.sourceUrl == "https://audio.example.test/m2.mp3"

    await controller.next()

    assert controller.currentIndex == 2
    assert controller.currentSong["name"] == "稻香"
    assert controller.sourceUrl == "https://audio.example.test/m3.mp3"
    assert [(song.mid, quality) for song, quality in service.calls] == [
        ("m2", "balanced"),
        ("m3", "balanced"),
    ]


async def test_play_queue_index_jumps_within_existing_queue():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    model = SongListModel()
    model.set_songs([_song("m1", "晴天"), _song("m2", "七里香"), _song("m3", "稻香")])

    await controller.play_from_model_async(model, 0)
    await controller.play_queue_index_async(2)

    assert controller.queueModel.count == 3
    assert controller.currentIndex == 2
    assert controller.currentSong["name"] == "稻香"
    assert controller.sourceUrl == "https://audio.example.test/m3.mp3"
    assert [(song.mid, quality) for song, quality in service.calls] == [
        ("m1", "balanced"),
        ("m3", "balanced"),
    ]


async def test_play_queue_index_rejects_invalid_index():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.play_queue_index_async(3)

    assert errors == ["无法播放：队列项不存在"]
    assert controller.errorMessage == "无法播放：队列项不存在"


async def test_play_songs_ignores_duplicate_request_while_loading():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    songs = [_song("m1", "晴天")]
    controller._queue.push(songs, play_now=True)  # noqa: SLF001
    controller._set_loading(True)  # noqa: SLF001

    await controller.play_songs_async(songs, 0)

    assert service.calls == []


def test_mode_and_transport_slots_emit_player_commands():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    seeks: list[int] = []
    pauses: list[bool] = []
    controller.seekRequested.connect(seeks.append)
    controller.pauseRequested.connect(lambda: pauses.append(True))

    controller.setMode("shuffle")
    controller.setVolume(2.0)
    controller.seek(-100)
    controller.pause()

    assert controller.mode == "shuffle"
    assert controller.volume == 1.0
    assert seeks == [0]
    assert pauses == [True]
