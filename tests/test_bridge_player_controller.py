"""PlayerController tests."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer

from quaverq.bridge.models import SongListModel, song_to_map
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
    assert controller.onlineStreamActive is True
    assert play_requests == [True]


async def test_online_stream_active_clears_on_stop():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]

    await controller.play_songs_async([_song("m1", "晴天")], 0)
    assert controller.onlineStreamActive is True

    controller.stop()

    assert controller.onlineStreamActive is False


async def test_local_playback_does_not_mark_online_stream_active(tmp_path):
    service = _FakeServiceController()
    local_file = tmp_path / "m1.mp3"
    local_file.write_bytes(b"audio")
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller.set_local_resolver(lambda mid: str(local_file) if mid == "m1" else "")

    await controller.play_songs_async([_song("m1", "晴天")], 0)

    assert service.calls == []
    assert controller.sourceUrl == QUrl.fromLocalFile(str(local_file)).toString()
    assert controller.onlineStreamActive is False


async def test_source_url_routed_through_stream_proxy():
    """反风控 U2：有代理时 sourceUrl 指向本机回环，真实 CDN url 交给代理拉。"""

    class _FakeProxy:
        running = True

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


async def test_remote_play_starts_stream_proxy_lazily_before_routing():
    """启动期不预热代理；第一次在线挂源前再启动, 省掉空闲线程/Session。"""

    class _LazyProxy:
        def __init__(self) -> None:
            self.running = False
            self.start_calls = 0

        def start(self) -> None:
            self.running = True
            self.start_calls += 1

        def local_url(self, real: str) -> str:
            assert self.running is True
            return f"http://127.0.0.1:9000/tok?u={real}"

    service = _FakeServiceController()
    proxy = _LazyProxy()
    controller = PlayerController(service, stream_proxy=proxy)  # type: ignore[arg-type]

    await controller.push_and_play_async(
        {
            "mid": "m1",
            "name": "晴天",
            "singers": [{"mid": "s1", "name": "周杰伦"}],
            "albumName": "叶惠美",
            "duration": 269,
        }
    )

    assert proxy.start_calls == 1
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


async def test_end_of_media_repeat_one_replays_without_refetching_url():
    """单曲循环 EOS: 链接未变, 回卷重播, 不重取链 (issue #11 Stage A2)."""
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller.setMode("repeat_one")
    await controller.play_songs_async([_song("m1", "晴天"), _song("m2", "七里香")], 1)

    seeks: list[int] = []
    plays: list[bool] = []
    controller.seekRequested.connect(seeks.append)
    controller.playRequested.connect(lambda: plays.append(True))

    await controller.handleEndOfMedia()

    assert controller.currentIndex == 1
    assert controller.currentSong["name"] == "七里香"
    # 只有首次加载取过一次链
    assert [(song.mid, quality) for song, quality in service.calls] == [("m2", "balanced")]
    assert seeks == [0]
    assert plays == [True]
    assert controller.sourceUrl == "https://audio.example.test/m2.mp3"
    assert controller.positionMs == 0


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


def test_toggle_mute_flips_state_and_keeps_volume():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    muted_events: list[bool] = []
    controller.mutedChanged.connect(lambda: muted_events.append(controller.muted))
    controller.setVolume(0.6)

    assert controller.muted is False
    controller.toggleMute()
    assert controller.muted is True
    # 静音是独立标志: 音量值不动, 恢复时天然回到原音量
    assert controller.volume == 0.6
    controller.toggleMute()
    assert controller.muted is False
    assert controller.volume == 0.6
    assert muted_events == [True, False]


def test_set_volume_unmutes():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    controller.setVolume(0.6)
    controller.toggleMute()
    assert controller.muted is True

    # 用户主动调音量 = 想听到声音 (平台标准行为); 设相同值也要解除静音
    controller.setVolume(0.6)
    assert controller.muted is False
    assert controller.volume == 0.6

    controller.toggleMute()
    controller.setVolume(0.3)
    assert controller.muted is False
    assert controller.volume == 0.3


def test_nudge_volume_steps_clamps_and_unmutes():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    controller.setVolume(0.8)

    controller.nudgeVolume(0.05)
    assert abs(controller.volume - 0.85) < 1e-9

    controller.nudgeVolume(0.5)
    assert controller.volume == 1.0

    controller.nudgeVolume(-2.0)
    assert controller.volume == 0.0

    controller.toggleMute()
    controller.nudgeVolume(0.05)
    assert controller.muted is False
    assert abs(controller.volume - 0.05) < 1e-9


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
    # FormatError 解码错误重试无意义 -> 直接报错, 不重取链 (歌中段/开头损坏)
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)
    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 200})

    await controller.handle_media_error_async(QMediaPlayer.Error.FormatError.value, "bad codec")

    assert len(service.calls) == 1  # 没重取链
    assert controller.playbackState == "stopped"
    assert errors and "晴天" in errors[-1]


async def test_format_error_near_stream_end_ignored_as_normal_finish():
    """CDN FLAC 尾部坏帧: 播到末尾 emit FormatError, 但歌已播完, 不误报'播放失败'.

    issue #11 真机暴露: 每首 FLAC 最后几秒 errorOccurred(FormatError) + 紧随 EndOfMedia,
    旧逻辑报'播放失败'+ stopped, UI 闪错误又被 EndOfMedia 切歌 -> 诡异. 末尾豁免后
    静默忽略, 由 EndOfMedia 正常切歌.
    """
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)
    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 200})
    controller.updatePlaybackState("playing")
    controller.updatePosition(197_000)  # 200s 歌, 末尾前 3s
    service.calls.clear()

    await controller.handle_media_error_async(QMediaPlayer.Error.FormatError.value, "Invalid data")

    assert errors == []  # 不误报"播放失败"
    assert controller.errorMessage == ""
    assert service.calls == []  # 不重取链
    assert controller.playbackState == "playing"  # 不设 stopped, 让 EndOfMedia 接管切歌


async def test_resource_error_near_stream_end_still_retries():
    """末尾的 ResourceError (网络断/401) 仍重取链重试: 末尾豁免只针对解码类 FormatError."""
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 200})
    controller.updatePlaybackState("playing")
    controller.updatePosition(197_000)
    service.calls.clear()

    await controller.handle_media_error_async(QMediaPlayer.Error.ResourceError.value, "401")

    assert len(service.calls) == 1  # 网络类错误末尾也重取链, 不豁免


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


def _queue_model_events(model):
    """监听队列模型的变更信号: 粒度操作 (插/删/移) vs 整表 reset."""
    events: list = []
    model.modelReset.connect(lambda: events.append("reset"))
    model.rowsInserted.connect(lambda _p, first, last: events.append(("ins", first, last)))
    model.rowsRemoved.connect(lambda _p, first, last: events.append(("rm", first, last)))
    model.rowsMoved.connect(lambda *_a: events.append("move"))
    return events


def _model_mids(model) -> list[str]:
    return [model.data(model.index(i, 0), model.MidRole) for i in range(model.rowCount())]


async def test_append_to_queue_granular_insert_not_reset():
    # 待播面板开着时追加歌曲: 整表 reset 会让 ListView 重建并滚回顶部 (真机反馈),
    # 必须走 rowsInserted 粒度信号
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "一"), _song("m2", "二")], 0)
    events = _queue_model_events(controller.queueModel)

    controller.appendToQueue([song_to_map(_song("m3", "三")), song_to_map(_song("m4", "四"))])

    assert events == [("ins", 2, 3)]
    assert _model_mids(controller.queueModel) == ["m1", "m2", "m3", "m4"]

    # 重复追加: 队列不变, 模型零事件
    events.clear()
    controller.appendToQueue([song_to_map(_song("m3", "三"))])
    assert events == []
    assert _model_mids(controller.queueModel) == ["m1", "m2", "m3", "m4"]


async def test_play_song_next_insert_new_without_reset():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "一"), _song("m2", "二")], 0)
    events = _queue_model_events(controller.queueModel)

    controller.playSongNext(song_to_map(_song("m9", "九")))

    assert events == [("ins", 1, 1)]
    assert _model_mids(controller.queueModel) == ["m1", "m9", "m2"]


async def test_play_song_next_moves_existing_without_reset():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "一"), _song("m2", "二"), _song("m3", "三")], 0)
    events = _queue_model_events(controller.queueModel)

    controller.playSongNext(song_to_map(_song("m3", "三")))

    assert "reset" not in events
    assert "move" in events
    assert _model_mids(controller.queueModel) == ["m1", "m3", "m2"]


async def test_remove_queue_index_granular_remove_not_reset():
    controller = PlayerController(_FakeServiceController())  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "一"), _song("m2", "二"), _song("m3", "三")], 0)
    events = _queue_model_events(controller.queueModel)

    controller.removeQueueIndex(1)

    assert events == [("rm", 1, 1)]
    assert _model_mids(controller.queueModel) == ["m1", "m3"]


class _PartialFailService:
    """指定 mid 集合不可播 (get_song_url 返 None = 服务端明确拒发, 如 104003 无版权)."""

    def __init__(self, unplayable: set[str]) -> None:
        self.unplayable = unplayable
        self.calls: list[str] = []

    async def get_song_url(self, song: Song, *, quality_preference: str) -> SongUrl | None:
        self.calls.append(song.mid)
        if song.mid in self.unplayable:
            return None
        return SongUrl(mid=song.mid, url=f"https://audio.example.test/{song.mid}.mp3")


async def test_auto_skip_unplayable_song_advances_and_notices():
    service = _PartialFailService({"m1"})
    controller = PlayerController(service)  # type: ignore[arg-type]
    notices: list[str] = []
    errors: list[str] = []
    controller.noticeRaised.connect(notices.append)
    controller.errorRaised.connect(errors.append)

    await controller.play_songs_async([_song("m1", "坏一"), _song("m2", "好二")], 0)

    # 不可播的 m1 被自动跳过, 落到 m2 正常加载
    assert controller.currentIndex == 1
    assert controller.sourceUrl == "https://audio.example.test/m2.mp3"
    assert notices == ["已跳过无法播放的歌曲：坏一"]
    assert errors == []
    assert controller.errorMessage == ""
    assert controller._url_failure_streak == 0  # noqa: SLF001  成功后清零


async def test_auto_skip_sequence_end_stops_without_error():
    # 顺序模式所有歌都不可播: 逐首跳过, 到队列尽头自然停, 不挂错误横幅
    service = _PartialFailService({"m1", "m2"})
    controller = PlayerController(service)  # type: ignore[arg-type]
    notices: list[str] = []
    controller.noticeRaised.connect(notices.append)

    await controller.play_songs_async([_song("m1", "一"), _song("m2", "二")], 0)

    assert controller.playbackState == "stopped"
    assert controller.errorMessage == ""
    assert len(notices) == 2


async def test_auto_skip_streak_cap_stops_with_error():
    # REPEAT_ALL 全队列不可播会绕圈: 连跳到上限必须停下报错, 不允许无限空转
    service = _PartialFailService({"m1", "m2"})
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller.setMode("repeat_all")
    notices: list[str] = []
    errors: list[str] = []
    controller.noticeRaised.connect(notices.append)
    controller.errorRaised.connect(errors.append)

    await controller.play_songs_async([_song("m1", "一"), _song("m2", "二")], 0)

    assert controller.playbackState == "stopped"
    assert "无法获取播放链接" in controller.errorMessage
    assert len(errors) == 1
    # 上限 5: 前 4 次是跳过提示, 第 5 次失败直接停
    assert len(notices) == 4


async def test_network_exception_stops_without_skipping():
    # 传输层异常 (断网) 与"服务端拒发"不同: 不跳过, 立即停住报错,
    # 否则一次断网会把整个队列"跳"光
    class _BoomService:
        async def get_song_url(self, song: Song, *, quality_preference: str) -> SongUrl | None:
            raise RuntimeError("network down")

    controller = PlayerController(_BoomService())  # type: ignore[arg-type]
    notices: list[str] = []
    controller.noticeRaised.connect(notices.append)

    await controller.play_songs_async([_song("m1", "一"), _song("m2", "二")], 0)

    assert controller.playbackState == "stopped"
    assert controller.errorMessage != ""
    assert notices == []
    assert controller.currentIndex == 0


# ============================================================== 本地优先播放 (阶段 9)


async def test_plays_local_file_when_resolver_hits(tmp_path):
    local = tmp_path / "song.mp3"
    local.write_bytes(b"x")
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller.set_local_resolver(lambda mid: str(local) if mid == "m1" else "")
    plays: list[bool] = []
    controller.playRequested.connect(lambda: plays.append(True))

    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 180})

    # 本地命中: sourceUrl 是 file:// 且完全跳过在线取链
    assert service.calls == []
    assert controller.sourceUrl == QUrl.fromLocalFile(str(local)).toString()
    assert controller.sourceUrl.startswith("file://")
    assert controller.loading is False
    assert controller.errorMessage == ""
    assert plays == [True]


async def test_falls_back_online_when_resolver_empty(tmp_path):
    # resolver 返 "" (没下载 / 文件已失效) → 走在线
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller.set_local_resolver(lambda mid: "")

    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 180})

    assert [s.mid for s, _ in service.calls] == ["m1"]
    assert controller.sourceUrl == "https://audio.example.test/m1.mp3"


async def test_no_resolver_uses_online():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]

    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 180})

    assert [s.mid for s, _ in service.calls] == ["m1"]


async def test_local_play_skips_stream_proxy(tmp_path):
    local = tmp_path / "song.mp3"
    local.write_bytes(b"x")

    class _FakeProxy:
        def local_url(self, real: str) -> str:
            return f"PROXIED:{real}"

    service = _FakeServiceController()
    controller = PlayerController(service, stream_proxy=_FakeProxy())  # type: ignore[arg-type]
    controller.set_local_resolver(lambda mid: str(local))

    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 180})

    # 本地文件不经代理 (代理是给在线 CDN 反风控的)
    assert controller.sourceUrl.startswith("file://")
    assert "PROXIED" not in controller.sourceUrl
    assert service.calls == []


async def test_resolver_exception_falls_back_online(tmp_path):
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]

    def _boom(mid: str) -> str:
        raise RuntimeError("resolver broke")

    controller.set_local_resolver(_boom)

    await controller.push_and_play_async({"mid": "m1", "name": "晴天", "duration": 180})

    # 解析器异常不应让播放崩, 回退在线
    assert [s.mid for s, _ in service.calls] == ["m1"]


# ------------------------------------------------------------------ 预取下一首 (issue #11 Stage A2)
# 起播后后台预取 peek_next 的链接; 切歌时 mid+音质偏好 双匹配才消费, 消费即清.


async def test_playing_state_schedules_prefetch_of_next_song():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller._prefetch_delay_s = 0  # 测试注入: 立即预取
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    assert [s.mid for s, _ in service.calls] == ["m1"]

    controller.updatePlaybackState("playing")
    assert controller._prefetch_task is not None
    await controller._prefetch_task

    assert [s.mid for s, _ in service.calls] == ["m1", "m2"]
    assert controller._prefetched is not None
    assert controller._prefetched[0] == "m2"


async def test_prefetched_url_consumed_on_next_without_refetch():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller._prefetch_delay_s = 0
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")
    await controller._prefetch_task

    await controller.next()

    # 命中预取缓存: 不再发第三次取链请求, 消费即清
    assert [s.mid for s, _ in service.calls] == ["m1", "m2"]
    assert controller.sourceUrl == "https://audio.example.test/m2.mp3"
    assert controller._prefetched is None


async def test_prefetched_url_discarded_when_quality_pref_changes():
    service = _FakeServiceController()
    settings = _FakeSettingsController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=settings,  # type: ignore[arg-type]
    )
    controller._prefetch_delay_s = 0
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")
    await controller._prefetch_task
    assert controller._prefetched[1] == "high"

    settings.qualityPreference = "standard"
    await controller.next()

    # 音质偏好变了 -> 丢弃缓存, 以新偏好现取
    assert [(s.mid, q) for s, q in service.calls] == [
        ("m1", "high"),
        ("m2", "high"),
        ("m2", "standard"),
    ]
    assert controller._prefetched is None


async def test_prefetched_url_discarded_when_jumping_elsewhere():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller._prefetch_delay_s = 0
    await controller.play_songs_async(
        [_song("m1", "A"), _song("m2", "B"), _song("m3", "C")],
        0,
    )
    controller.updatePlaybackState("playing")
    await controller._prefetch_task
    assert controller._prefetched[0] == "m2"

    await controller.play_queue_index_async(2)

    # 跳到别处: 缓存 mid 失配 -> 丢弃, 正常取链 m3
    assert [s.mid for s, _ in service.calls] == ["m1", "m2", "m3"]
    assert controller.sourceUrl == "https://audio.example.test/m3.mp3"
    assert controller._prefetched is None


async def test_prefetch_skips_when_no_next_song():
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller._prefetch_delay_s = 0
    await controller.play_songs_async([_song("m1", "A")], 0)  # SEQUENCE 单曲: 无下一首

    controller.updatePlaybackState("playing")
    if controller._prefetch_task is not None:
        await controller._prefetch_task

    assert [s.mid for s, _ in service.calls] == ["m1"]
    assert controller._prefetched is None


async def test_prefetch_does_not_cache_rejected_song():
    """拒发 (None) 不缓存: 跳过通知/连跳计数等逻辑留给正常链路."""

    class _RejectM2Service(_FakeServiceController):
        async def get_song_url(self, song, *, quality_preference):
            if song.mid == "m2":
                self.calls.append((song, quality_preference))
                return None
            return await super().get_song_url(song, quality_preference=quality_preference)

    service = _RejectM2Service()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller._prefetch_delay_s = 0
    await controller.play_songs_async(
        [_song("m1", "A"), _song("m2", "B"), _song("m3", "C")],
        0,
    )
    controller.updatePlaybackState("playing")
    await controller._prefetch_task
    assert controller._prefetched is None  # 预取到拒发 -> 不缓存

    notices: list[str] = []
    controller.noticeRaised.connect(notices.append)
    await controller.next()

    # 正常链路重新取 m2 (第二次), 触发自动跳过到 m3
    assert [s.mid for s, _ in service.calls] == ["m1", "m2", "m2", "m3"]
    assert controller.currentSong["mid"] == "m3"
    assert notices and "无法播放" in notices[0]


async def test_prefetch_failure_is_swallowed():
    class _FlakyService(_FakeServiceController):
        async def get_song_url(self, song, *, quality_preference):
            if song.mid == "m2":
                raise RuntimeError("network down")
            return await super().get_song_url(song, quality_preference=quality_preference)

    service = _FlakyService()
    controller = PlayerController(service)  # type: ignore[arg-type]
    controller._prefetch_delay_s = 0
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")
    await controller._prefetch_task

    # 预取失败静默 (best-effort), 不冒泡错误
    assert errors == []
    assert controller._prefetched is None


# ------------------------------------------------------------------ REPEAT_ONE EOS 短路 (issue #11 Stage A2)
# 主行为见上面 test_end_of_media_repeat_one_replays_without_refetching_url


async def test_repeat_one_eos_falls_back_to_load_when_no_source():
    """加载失败后 (sourceUrl 空) 的 REPEAT_ONE EOS 仍走完整取链, 不短路."""
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.play_songs_async([_song("m1", "A")], 0)
    controller.setMode("repeat_one")
    controller.stop()  # 模拟 source 被清空
    assert controller.sourceUrl == ""

    await controller.handleEndOfMedia()

    assert len(service.calls) == 2  # 重新取链
    assert controller.sourceUrl == "https://audio.example.test/m1.mp3"


# ------------------------------------------------------------------ 切歌淡出协调 (issue #11 Stage C2)
# 正在出声时切歌: 先发 fadeOutRequested 并保留旧 source (清了立即哑), 取链与淡出
# 并行; 淡出播完才换源. 淡出窗口内冻结 QML 进度回传 (UI 已显示新歌).


class _FadeSettings:
    qualityPreference = "balanced"
    fadeEnabled = True
    fadeDurationMs = 60  # 测试用短时长


async def test_switch_while_playing_emits_fade_out_then_mounts_new_source():
    service = _FakeServiceController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FadeSettings(),  # type: ignore[arg-type]
    )
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")

    fades: list[int] = []
    sources: list[str] = []
    controller.fadeOutRequested.connect(fades.append)
    controller.sourceUrlChanged.connect(lambda: sources.append(controller.sourceUrl))

    await controller.next()

    assert fades == [60]
    # 淡出期间旧 source 不被清空: 唯一一次变更即直接挂新源 (无中间空串)
    assert sources == ["https://audio.example.test/m2.mp3"]


async def test_switch_keeps_old_source_during_fade_window():
    service = _FakeServiceController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FadeSettings(),  # type: ignore[arg-type]
    )
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")

    task = controller.next()  # @asyncSlot 调用即返回已创建的 Task
    await asyncio.sleep(0.01)  # 取链瞬时完成, 此刻应仍在等淡出播完 (60ms)
    assert controller.sourceUrl == "https://audio.example.test/m1.mp3"  # 旧源还挂着

    # 淡出窗口内冻结 QML 进度回传 (旧歌还在响, 不能把进度条拽回去)
    controller.updatePosition(123_456)
    assert controller.positionMs == 0

    await asyncio.wait_for(task, timeout=2)
    assert controller.sourceUrl == "https://audio.example.test/m2.mp3"
    # 窗口结束后进度回传恢复
    controller.updatePosition(777)
    assert controller.positionMs == 777


async def test_no_fade_out_when_not_playing():
    service = _FakeServiceController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FadeSettings(),  # type: ignore[arg-type]
    )
    fades: list[int] = []
    controller.fadeOutRequested.connect(fades.append)

    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)  # stopped 态起播
    await controller.next()  # loading 态切歌

    assert fades == []


async def test_no_fade_out_when_disabled():
    class _FadeOff(_FadeSettings):
        fadeEnabled = False

    service = _FakeServiceController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FadeOff(),  # type: ignore[arg-type]
    )
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")

    fades: list[int] = []
    controller.fadeOutRequested.connect(fades.append)
    await controller.next()

    assert fades == []
    assert controller.sourceUrl == "https://audio.example.test/m2.mp3"


async def test_fade_wait_respects_generation_guard():
    """淡出等待期间再次切歌: 旧 generation 醒来后不得覆盖新源."""
    service = _FakeServiceController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FadeSettings(),  # type: ignore[arg-type]
    )
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")

    task = controller.next()  # @asyncSlot 调用即返回已创建的 Task
    await asyncio.sleep(0.01)  # task 进入淡出等待窗口
    await controller.play_queue_index_async(0)  # 用户改主意点回第一首 (新 generation)
    await asyncio.wait_for(task, timeout=2)

    assert controller.sourceUrl == "https://audio.example.test/m1.mp3"


async def test_fade_error_path_clears_source_and_unfreezes_position():
    class _BoomService(_FakeServiceController):
        async def get_song_url(self, song, *, quality_preference):
            if song.mid == "m2":
                raise RuntimeError("network down")
            return await super().get_song_url(song, quality_preference=quality_preference)

    service = _BoomService()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FadeSettings(),  # type: ignore[arg-type]
    )
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")

    errors: list[str] = []
    controller.errorRaised.connect(errors.append)
    await controller.next()

    assert errors  # 报错冒泡
    assert controller.sourceUrl == ""  # 旧源已卸 (不能让它静音空转)
    controller.updatePosition(555)
    assert controller.positionMs == 555  # 冻结解除


# ------------------------------------------------------------------ review 修复回归 (issue #11)


async def test_format_error_short_track_not_exempted():
    """短歌 (duration < 容差) 开头的 FormatError 不能被末尾豁免吞掉.

    旧实现 `duration > 0` 守卫挡不住 `duration - 5000` 为负 → 短歌任何位置的
    FormatError 都被静默忽略, 用户看到播放器静默卡死 (review 发现).
    """
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.push_and_play_async({"mid": "m1", "name": "短曲", "duration": 4})  # 4s
    controller.updatePlaybackState("playing")
    controller.updatePosition(0)  # 开头
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.handle_media_error_async(QMediaPlayer.Error.FormatError.value, "bad")

    assert errors and "短曲" in errors[0]  # 报错, 不被豁免
    assert controller.playbackState == "stopped"


async def test_format_error_short_track_near_end_still_exempted():
    """短歌真播到后半段末尾的 FormatError 仍豁免 (CDN 坏帧)."""
    service = _FakeServiceController()
    controller = PlayerController(service)  # type: ignore[arg-type]
    await controller.push_and_play_async({"mid": "m1", "name": "短曲", "duration": 4})  # 4s
    controller.updatePlaybackState("playing")
    controller.updatePosition(3500)  # 4s 歌的 3.5s, 后半段末尾
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.handle_media_error_async(QMediaPlayer.Error.FormatError.value, "bad")

    assert errors == []  # 豁免
    assert controller.playbackState == "playing"


async def test_pause_during_fade_out_not_overridden_by_play():
    """fade 淡出 sleep 期间用户暂停, 不被切歌的 playRequested 覆盖 (review 发现).

    旧实现 pause() 不参与 generation, sleep 醒来照常 playRequested → 暂停意图丢失.
    """
    service = _FakeServiceController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FadeSettings(),  # type: ignore[arg-type]
    )
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")
    plays: list[bool] = []
    controller.playRequested.connect(lambda: plays.append(True))

    task = controller.next()  # 切歌, 进入 fade 淡出 sleep (60ms)
    await asyncio.sleep(0.01)  # 仍在 sleep 中
    controller.pause()  # 用户暂停
    await asyncio.wait_for(task, timeout=2)

    assert plays == []  # 不应 playRequested, 尊重用户暂停
    assert controller.sourceUrl == "https://audio.example.test/m2.mp3"  # 源已挂好但不播


async def test_play_after_pause_during_fade_resumes():
    """fade sleep 期间先 pause 又 play (改主意), 最终应播放 (pause_pending 被 play 清除)."""
    service = _FakeServiceController()
    controller = PlayerController(
        service,  # type: ignore[arg-type]
        settings_controller=_FadeSettings(),  # type: ignore[arg-type]
    )
    await controller.play_songs_async([_song("m1", "A"), _song("m2", "B")], 0)
    controller.updatePlaybackState("playing")
    plays: list[bool] = []
    controller.playRequested.connect(lambda: plays.append(True))

    task = controller.next()
    await asyncio.sleep(0.01)
    controller.pause()
    controller.play()  # 改主意, 又要播
    await asyncio.wait_for(task, timeout=2)

    assert plays  # 最终应 playRequested
