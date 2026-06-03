"""PlayerController tests."""

from __future__ import annotations

from quaverq.bridge.player_controller import PlayerController
from quaverq.bridge.models import SongListModel
from quaverq.core.models import Singer, Song, SongUrl
from quaverq.core.queue import PlayMode, PlayQueue
from quaverq.core.state import SessionState


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


class _FakeSettingsController:
    qualityPreference = "high"


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


async def test_push_and_play_uses_settings_quality_preference():
    service = _FakeServiceController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FakeSettingsController(),  # type: ignore[arg-type]
    )

    await controller.push_and_play_async(
        {
            "mid": "m1",
            "name": "晴天",
            "singers": [{"mid": "s1", "name": "周杰伦"}],
            "albumName": "叶惠美",
            "duration": 269,
        }
    )

    assert [(song.mid, quality) for song, quality in service.calls] == [("m1", "high")]


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


async def test_end_of_media_sequence_advances_then_stops_at_end():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    stop_requests: list[bool] = []
    controller.stopRequested.connect(lambda: stop_requests.append(True))
    await controller.play_songs_async([_song("m1", "晴天"), _song("m2", "七里香")], 0)

    await controller.handleEndOfMedia()

    assert controller.currentIndex == 1
    assert controller.currentSong["name"] == "七里香"
    assert controller.sourceUrl == "https://audio.example.test/m2.mp3"

    controller.updatePlaybackState("playing")
    await controller.handleEndOfMedia()

    assert controller.currentIndex == 1
    assert controller.sourceUrl == ""
    assert controller.positionMs == 0
    assert controller.playbackState == "stopped"
    assert stop_requests == [True]
    assert [(song.mid, quality) for song, quality in service.calls] == [
        ("m1", "balanced"),
        ("m2", "balanced"),
    ]


async def test_end_of_media_repeat_all_wraps_to_first_song():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller.setMode("repeat_all")
    await controller.play_songs_async([_song("m1", "晴天"), _song("m2", "七里香")], 1)

    await controller.handleEndOfMedia()

    assert controller.currentIndex == 0
    assert controller.currentSong["name"] == "晴天"
    assert controller.sourceUrl == "https://audio.example.test/m1.mp3"


async def test_end_of_media_repeat_one_reloads_same_song():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller.setMode("repeat_one")
    await controller.play_songs_async([_song("m1", "晴天"), _song("m2", "七里香")], 1)

    await controller.handleEndOfMedia()

    assert controller.currentIndex == 1
    assert controller.currentSong["name"] == "七里香"
    assert [(song.mid, quality) for song, quality in service.calls] == [
        ("m2", "balanced"),
        ("m2", "balanced"),
    ]


def test_restore_session_snapshot_populates_queue_without_loading(tmp_path):
    path = tmp_path / "state.json"
    state = SessionState(path)
    play_queue = PlayQueue(mode=PlayMode.REPEAT_ALL)
    play_queue.push([_song("m1", "晴天"), _song("m2", "七里香")], play_now=True, start_index=1)
    state.save(play_queue, position_ms=42_000, volume=0.35)
    service = _FakeServiceController()

    controller = PlayerController(service, session_state=SessionState(path))  # type: ignore[arg-type]

    assert controller.queueModel.count == 2
    assert controller.currentIndex == 1
    assert controller.currentSong["name"] == "七里香"
    assert controller.positionMs == 42_000
    assert controller.durationMs == 180_000
    assert controller.mode == "repeat_all"
    assert controller.volume == 0.35
    assert controller.sourceUrl == ""
    assert controller.playbackState == "stopped"
    assert service.calls == []


async def test_play_after_restore_loads_current_song_and_seeks_position(tmp_path):
    path = tmp_path / "state.json"
    state = SessionState(path)

    play_queue = PlayQueue()
    play_queue.push([_song("m1", "晴天")], play_now=True)
    state.save(play_queue, position_ms=15_000, volume=0.8)
    service = _FakeServiceController()
    controller = PlayerController(service, session_state=SessionState(path))  # type: ignore[arg-type]
    seeks: list[int] = []
    plays: list[bool] = []
    events: list[str] = []
    controller.seekRequested.connect(seeks.append)
    controller.playRequested.connect(lambda: plays.append(True))
    controller.seekRequested.connect(lambda _position: events.append("seek"))
    controller.playRequested.connect(lambda: events.append("play"))

    await controller.play_async()

    assert service.calls[0][0].mid == "m1"
    assert controller.sourceUrl == "https://audio.example.test/m1.mp3"
    assert controller.positionMs == 15_000
    assert seeks == [15_000]
    assert plays == [True]
    assert events == ["seek", "play"]


async def test_save_session_snapshot_writes_current_player_state(tmp_path):
    path = tmp_path / "state.json"
    state = SessionState(path)
    controller = PlayerController(_FakeServiceController(), session_state=state)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "晴天"), _song("m2", "七里香")], 1)
    controller.updatePosition(88_000)
    controller.setVolume(0.45)
    controller.setMode("shuffle")

    controller.saveSessionSnapshot()

    snapshot = SessionState(path).restore()
    assert snapshot is not None
    assert snapshot.current_index == 1
    assert snapshot.position_ms == 88_000
    assert snapshot.volume == 0.45
    assert snapshot.play_mode == PlayMode.SHUFFLE
    assert [song.mid for song in snapshot.songs] == ["m1", "m2"]


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
