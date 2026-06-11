"""PlayerController tests."""

from __future__ import annotations

import asyncio

from PySide6.QtMultimedia import QMediaPlayer

from quaverq.bridge.models import SongListModel
from quaverq.bridge.player_controller import PlayerController
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


async def test_source_url_routed_through_stream_proxy():
    """反风控 U2：有代理时 sourceUrl 指向本机回环，真实 CDN url 交给代理拉。"""

    class _FakeProxy:
        def local_url(self, real: str) -> str:
            return f"http://127.0.0.1:9000/tok?u={real}"

    service = _FakeServiceController()
    controller = PlayerController(service, stream_proxy=_FakeProxy())  # type: ignore[arg-type]
    await controller.push_and_play_async(
        {
            "mid": "m1",
            "name": "晴天",
            "singers": [{"mid": "s1", "name": "周杰伦"}],
            "albumName": "叶惠美",
            "duration": 269,
        }
    )
    assert controller.sourceUrl == "http://127.0.0.1:9000/tok?u=https://audio.example.test/m1.mp3"


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


async def test_media_error_retries_with_fresh_url_once():
    # 瞬态 401 (ResourceError): 自动重取链 (新 vkey) 重播一次, 不报错
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    play_requests: list[bool] = []
    controller.playRequested.connect(lambda: play_requests.append(True))
    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 200})
    assert len(service.calls) == 1

    await controller.handle_media_error_async(QMediaPlayer.Error.ResourceError.value, "401")

    assert len(service.calls) == 2  # 重取链 (现签新 vkey)
    assert play_requests == [True, True]  # 重新播放
    assert controller.errorMessage == ""  # 重试中不报错


async def test_media_error_gives_up_after_one_retry():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)
    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 200})

    await controller.handle_media_error_async(QMediaPlayer.Error.ResourceError.value, "401")
    await controller.handle_media_error_async(QMediaPlayer.Error.ResourceError.value, "401")

    assert len(service.calls) == 2  # 首播 + 1 次重试, 不再重试
    assert controller.playbackState == "stopped"
    assert errors and "晴天" in errors[-1]


async def test_media_error_non_retryable_reports_immediately():
    # FormatError 解码错误重试无意义 -> 直接报错, 不重取链
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)
    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 200})

    await controller.handle_media_error_async(QMediaPlayer.Error.FormatError.value, "bad codec")

    assert len(service.calls) == 1  # 没重取链
    assert controller.playbackState == "stopped"
    assert errors and "晴天" in errors[-1]


async def test_play_songs_records_queue_source_and_emits_change():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    source_changes: list[str] = []
    controller.queueSourceChanged.connect(lambda: source_changes.append(controller.queueSource))

    await controller.play_songs_async([_song("m1", "晴天")], 0, source="daily")

    assert controller.queueSource == "daily"
    assert source_changes == ["daily"]


async def test_end_of_media_with_source_emits_queue_exhausted():
    """SEQUENCE 末尾自然播完且队列带 source -> 发出 queueExhausted(source); 不带 source 不发."""
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    exhausted: list[str] = []
    controller.queueExhausted.connect(exhausted.append)
    await controller.play_songs_async(
        [_song("m1", "晴天"), _song("m2", "七里香")], 0, source="daily"
    )

    await controller.handleEndOfMedia()  # 到 m2
    controller.updatePlaybackState("playing")
    await controller.handleEndOfMedia()  # m2 后再无, 触发 exhausted

    assert exhausted == ["daily"]
    assert controller.playbackState == "stopped"
    assert controller.currentSong == {}  # current_index 推过末尾


async def test_end_of_media_without_source_does_not_emit_queue_exhausted():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    exhausted: list[str] = []
    controller.queueExhausted.connect(exhausted.append)
    await controller.play_songs_async([_song("m1", "晴天")], 0)

    await controller.handleEndOfMedia()

    assert exhausted == []
    # 与历史 stop() 行为一致: current_index 不推过末尾
    assert controller.currentIndex == 0


async def test_append_to_queue_resumes_when_previously_exhausted():
    """耗尽 (current_index 越界) 后 append 应自动跳到第一首新加曲并续播."""
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "晴天")], 0, source="daily")
    await controller.handleEndOfMedia()  # 触发 exhausted
    assert controller.currentSong == {}

    added = controller.append_to_queue([_song("m2", "七里香"), _song("m3", "稻香")])

    assert [s.mid for s in added] == ["m2", "m3"]
    assert controller.queueModel.count == 3
    # 异步 _load_current 已 schedule, 让事件循环跑一下
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert controller.currentIndex == 1
    assert controller.currentSong["name"] == "七里香"


async def test_append_to_queue_dedupes_and_does_not_disturb_playback():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async(
        [_song("m1", "晴天"), _song("m2", "七里香")], 0, source="daily"
    )

    added = controller.append_to_queue([_song("m2", "dup"), _song("m9", "new")])

    assert [s.mid for s in added] == ["m9"]
    assert controller.queueModel.count == 3
    assert controller.currentIndex == 0
    assert controller.currentSong["name"] == "晴天"


async def test_media_error_retry_counter_resets_after_successful_play():
    # 成功播放后计数清零, 同曲后续 (如 vkey 过期) 仍可再重试
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 200})

    await controller.handle_media_error_async(QMediaPlayer.Error.NetworkError.value, "x")
    controller.updatePlaybackState("playing")  # 重试成功
    await controller.handle_media_error_async(QMediaPlayer.Error.NetworkError.value, "x")

    assert len(service.calls) == 3  # 首播 + 两次 (各自允许的) 重试


# ============================================================== W5 队列增删


def _song_map(mid: str, name: str) -> dict:
    return {"mid": mid, "name": name, "singers": [], "albumName": "", "duration": 100}


async def _settled(controller: PlayerController, attr: str = "sourceUrl", timeout: float = 1.0):
    """等待异步加载落地 (sourceUrl 就位)."""
    waited = 0.0
    while waited < timeout:
        if getattr(controller, attr):
            return
        await asyncio.sleep(0.01)
        waited += 0.01


async def test_play_song_next_inserts_after_current():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)

    controller.playSongNext(_song_map("m9", "插队"))

    assert [s.mid for s in controller.queueModel.songs()] == ["m1", "m9", "m2"]
    assert controller.currentIndex == 0
    assert controller.currentSong["mid"] == "m1"


async def test_play_song_next_moves_existing_entry():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B"), _song("m3", "C")], 0)

    controller.playSongNext(_song_map("m3", "C"))

    assert [s.mid for s in controller.queueModel.songs()] == ["m1", "m3", "m2"]


async def test_play_song_next_with_current_song_is_noop():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)

    controller.playSongNext(_song_map("m1", "A"))

    assert [s.mid for s in controller.queueModel.songs()] == ["m1", "m2"]
    assert controller.currentIndex == 0


async def test_play_song_next_on_empty_queue_starts_playback():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]

    controller.playSongNext(_song_map("m1", "A"))
    await _settled(controller)

    assert controller.currentIndex == 0
    assert controller.currentSong["mid"] == "m1"
    assert controller.sourceUrl.endswith("m1.mp3")


async def test_remove_queue_index_before_current_no_reload():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B"), _song("m3", "C")], 1)
    calls_before = len(service.calls)

    controller.removeQueueIndex(0)

    assert [s.mid for s in controller.queueModel.songs()] == ["m2", "m3"]
    assert controller.currentIndex == 0
    assert controller.currentSong["mid"] == "m2"
    assert len(service.calls) == calls_before  # 没触发重新取链


async def test_remove_queue_index_current_advances_and_reloads():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")

    controller.removeQueueIndex(0)
    for _ in range(100):
        if controller.sourceUrl.endswith("m2.mp3"):
            break
        await asyncio.sleep(0.01)

    assert [s.mid for s in controller.queueModel.songs()] == ["m2"]
    assert controller.currentSong["mid"] == "m2"
    assert controller.sourceUrl.endswith("m2.mp3")


async def test_remove_last_remaining_song_stops():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "A")], 0)

    controller.removeQueueIndex(0)

    assert controller.queueModel.count == 0
    assert controller.currentSong == {}
    assert controller.sourceUrl == ""
    assert controller.playbackState == "stopped"


async def test_clear_queue_stops_and_empties():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0, source="daily")

    controller.clearQueue()

    assert controller.queueModel.count == 0
    assert controller.currentSong == {}
    assert controller.sourceUrl == ""
    assert controller.playbackState == "stopped"
    assert controller.queueSource == ""
