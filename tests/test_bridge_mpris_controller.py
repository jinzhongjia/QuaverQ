"""MprisController tests."""

from __future__ import annotations

import asyncio

from quaverq.bridge.mpris_controller import MprisController
from quaverq.bridge.player_controller import PlayerController
from quaverq.core.mpris import MprisCallbacks
from quaverq.core.models import Singer, Song, SongUrl


class _FakeAudioService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_song_url(
        self,
        song: Song,
        *,
        quality_preference: str,
    ) -> SongUrl:
        self.calls.append(song.mid)
        return SongUrl(mid=song.mid, url=f"https://audio.example.test/{song.mid}.mp3")


class _FakeMprisService:
    def __init__(self, callbacks: MprisCallbacks) -> None:
        self.callbacks = callbacks
        self.started = False
        self.start_result = True
        self.stopped = False
        self.metadata: list[Song] = []
        self.statuses: list[str | None] = []
        self.positions: list[int] = []
        self.volumes: list[float] = []
        self.modes: list[str | None] = []

    async def start(self) -> bool:
        self.started = True
        return self.start_result

    async def stop(self) -> None:
        self.stopped = True

    def push_metadata(self, song: Song, *, local_cover_uri: str | None = None) -> None:
        self.metadata.append(song)

    def push_playback_status(self, state: str | None) -> None:
        self.statuses.append(state)

    def push_position(self, position_ms: int) -> None:
        self.positions.append(position_ms)

    def push_volume(self, volume: float) -> None:
        self.volumes.append(volume)

    def push_playback_mode(self, mode: str | None) -> None:
        self.modes.append(mode)


def _song(mid: str, name: str) -> Song:
    return Song(
        mid=mid,
        name=name,
        singers=[Singer(mid="s1", name="周杰伦")],
        album_name="叶惠美",
        duration=180,
    )


def _build_controller(
    player_controller: PlayerController,
    service: _FakeMprisService | None = None,
) -> tuple[MprisController, _FakeMprisService]:
    holder: dict[str, _FakeMprisService] = {}

    def factory(callbacks: MprisCallbacks) -> _FakeMprisService:
        holder["service"] = service or _FakeMprisService(callbacks)
        return holder["service"]

    controller = MprisController(player_controller, service_factory=factory)
    return controller, holder["service"]


async def test_start_syncs_current_player_state():
    player = PlayerController(_FakeAudioService())  # type: ignore[arg-type]
    player._queue.push([_song("m1", "晴天")], play_now=True)  # noqa: SLF001
    player._sync_queue_model()  # noqa: SLF001
    player._emit_current_changed()  # noqa: SLF001
    player.updatePlaybackState("playing")
    player.updatePosition(42_000)
    player.setVolume(0.35)
    player.setMode("repeat_all")
    controller, service = _build_controller(player)

    started = await controller.start_async()

    assert started is True
    assert controller.started is True
    assert [song.mid for song in service.metadata] == ["m1"]
    assert service.statuses == ["playing"]
    assert service.positions == [42_000]
    assert service.volumes == [0.35]
    assert service.modes == ["repeat_all"]


async def test_player_signals_push_mpris_updates_after_start():
    player = PlayerController(_FakeAudioService())  # type: ignore[arg-type]
    controller, service = _build_controller(player)
    await controller.start_async()

    player._queue.push([_song("m2", "七里香")], play_now=True)  # noqa: SLF001
    player._emit_current_changed()  # noqa: SLF001
    player.updatePlaybackState("paused")
    player.updatePosition(12_345)
    player.setVolume(0.6)
    player.setMode("shuffle")

    assert service.metadata[-1].mid == "m2"
    assert service.statuses[-1] == "paused"
    assert service.positions[-1] == 12_345
    assert service.volumes[-1] == 0.6
    assert service.modes[-1] == "shuffle"


async def test_mpris_callbacks_drive_player_controller():
    audio = _FakeAudioService()
    player = PlayerController(audio)  # type: ignore[arg-type]
    await player.play_songs_async([_song("m1", "晴天"), _song("m2", "七里香")], 0)
    controller, service = _build_controller(player)
    await controller.start_async()

    service.callbacks.next()
    await asyncio.sleep(0)
    assert player.currentSong["mid"] == "m2"

    service.callbacks.prev()
    await asyncio.sleep(0)
    assert player.currentSong["mid"] == "m1"

    seeks: list[int] = []
    player.seekRequested.connect(seeks.append)
    service.callbacks.seek(88_000)
    assert seeks[-1] == 88_000


async def test_start_failure_does_not_push_state():
    player = PlayerController(_FakeAudioService())  # type: ignore[arg-type]
    service = _FakeMprisService(MprisCallbacks())
    service.start_result = False
    controller, service = _build_controller(player, service)

    started = await controller.start_async()
    player.updatePlaybackState("playing")

    assert started is False
    assert controller.started is False
    assert service.statuses == []
