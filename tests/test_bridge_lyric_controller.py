"""LyricController tests."""

from __future__ import annotations

from quaverq.bridge.lyric_controller import LyricController
from quaverq.bridge.player_controller import PlayerController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.lyric_cache import LyricCache
from quaverq.core.models import Lyric, LyricLine, Singer, Song, SongUrl
from quaverq.core.queue import PlayQueue
from quaverq.core.state import SessionState


class _FakeLyricService:
    def __init__(self) -> None:
        self.connected = False
        self.is_authenticated = True
        self.lyric_calls: list[tuple[str, bool]] = []
        self.lyrics: dict[str, Lyric] = {
            "m1": Lyric(
                mid="m1",
                has_translation=True,
                lines=[
                    LyricLine(timestamp_ms=0, text="第一行", translation="line one"),
                    LyricLine(timestamp_ms=1000, text="第二行", translation="line two"),
                    LyricLine(timestamp_ms=2000, text="第三行"),
                ],
            )
        }

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_song_url(
        self,
        song: Song,
        *,
        quality_preference: str,
    ) -> SongUrl:
        return SongUrl(mid=song.mid, url=f"https://audio.example.test/{song.mid}.mp3")

    async def get_lyric(
        self,
        mid: str,
        *,
        with_translation: bool = True,
    ) -> Lyric:
        self.lyric_calls.append((mid, with_translation))
        return self.lyrics.get(mid, Lyric(mid=mid))


def _song(mid: str = "m1") -> Song:
    return Song(
        mid=mid,
        name="晴天",
        singers=[Singer(mid="s1", name="周杰伦")],
        album_name="叶惠美",
        duration=269,
    )


async def test_refresh_current_lyric_populates_model_and_translation():
    service = _FakeLyricService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player_controller = PlayerController(service_controller)
    player_controller._queue.push([_song()], play_now=True)  # noqa: SLF001
    player_controller._emit_current_changed()  # noqa: SLF001
    controller = LyricController(service_controller, player_controller)

    await controller.refresh_current_lyric_async()

    assert service.connected is True
    assert service.lyric_calls == [("m1", True)]
    assert controller.currentMid == "m1"
    assert controller.lineCount == 3
    assert controller.hasTranslation is True
    assert controller.lyricModel.lineAt(1)["lineText"] == "第二行"
    assert controller.lyricModel.lineAt(1)["translation"] == "line two"


async def test_active_index_tracks_player_position():
    service = _FakeLyricService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player_controller = PlayerController(service_controller)
    player_controller._queue.push([_song()], play_now=True)  # noqa: SLF001
    player_controller._emit_current_changed()  # noqa: SLF001
    controller = LyricController(service_controller, player_controller)

    await controller.refresh_current_lyric_async()
    player_controller.updatePosition(1500)

    assert controller.activeIndex == 1
    assert controller.currentLineText == "第二行"
    assert controller.currentLineTranslation == "line two"


async def test_restored_session_primes_current_mid_and_position(tmp_path):
    """重启恢复队列 + 进度后, LyricController 不应错过当前歌曲状态."""
    state_path = tmp_path / "state.json"
    queue = PlayQueue()
    queue.push([_song()], play_now=True)
    SessionState(state_path).save(queue, position_ms=1500, volume=0.8)

    service = _FakeLyricService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player_controller = PlayerController(
        service_controller,
        session_state=SessionState(state_path),
    )
    controller = LyricController(service_controller, player_controller)

    assert controller.currentMid == "m1"
    assert controller.positionMs == 1500
    assert service.lyric_calls == []

    await controller.refresh_current_lyric_async()

    assert controller.activeIndex == 1
    assert controller.currentLineText == "第二行"
    assert controller.currentLineTranslation == "line two"


async def test_current_song_primes_cached_lyric_before_network_refresh(tmp_path):
    cache = LyricCache(tmp_path / "lyrics")
    cache.save(
        Lyric(
            mid="m1",
            has_translation=True,
            lines=[
                LyricLine(timestamp_ms=0, text="缓存第一行", translation="cached"),
                LyricLine(timestamp_ms=1000, text="缓存第二行", translation="cached 2"),
            ],
        ),
        with_translation=True,
    )
    service = _FakeLyricService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player_controller = PlayerController(service_controller)
    player_controller._queue.push([_song()], play_now=True)  # noqa: SLF001
    player_controller._emit_current_changed()  # noqa: SLF001

    controller = LyricController(service_controller, player_controller, lyric_cache=cache)

    assert service.lyric_calls == []
    assert controller.lineCount == 2
    assert controller.currentLineText == "缓存第一行"
    assert controller.hasTranslation is True

    await controller.refresh_current_lyric_async()

    assert service.lyric_calls == [("m1", True)]
    assert controller.lineCount == 3
    assert controller.currentLineText == "第一行"
    assert cache.load("m1", with_translation=True) == service.lyrics["m1"]


async def test_cached_lyric_survives_refresh_failure(tmp_path):
    class _FailingLyricService(_FakeLyricService):
        async def get_lyric(
            self,
            mid: str,
            *,
            with_translation: bool = True,
        ) -> Lyric:
            self.lyric_calls.append((mid, with_translation))
            raise RuntimeError("network down")

    cache = LyricCache(tmp_path / "lyrics")
    cache.save(
        Lyric(mid="m1", lines=[LyricLine(timestamp_ms=0, text="缓存行")]),
        with_translation=True,
    )
    service = _FailingLyricService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player_controller = PlayerController(service_controller)
    player_controller._queue.push([_song()], play_now=True)  # noqa: SLF001
    player_controller._emit_current_changed()  # noqa: SLF001
    controller = LyricController(service_controller, player_controller, lyric_cache=cache)

    await controller.refresh_current_lyric_async()

    assert service.lyric_calls == [("m1", True)]
    assert controller.lineCount == 1
    assert controller.currentLineText == "缓存行"
    assert controller.errorMessage


async def test_song_change_clears_lyric_before_next_refresh():
    service = _FakeLyricService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player_controller = PlayerController(service_controller)
    player_controller._queue.push([_song()], play_now=True)  # noqa: SLF001
    player_controller._emit_current_changed()  # noqa: SLF001
    controller = LyricController(service_controller, player_controller)
    await controller.refresh_current_lyric_async()

    player_controller._queue.push([_song("m2")], play_now=True)  # noqa: SLF001
    player_controller._emit_current_changed()  # noqa: SLF001

    assert controller.currentMid == "m2"
    assert controller.lineCount == 0
    assert controller.currentLineText == ""


async def test_refresh_without_current_song_clears_state():
    service = _FakeLyricService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player_controller = PlayerController(service_controller)
    controller = LyricController(service_controller, player_controller)

    await controller.refresh_current_lyric_async()

    assert service.lyric_calls == []
    assert controller.currentMid == ""
    assert controller.lineCount == 0


async def test_position_ms_proxies_player_and_notifies():
    service = _FakeLyricService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    player_controller = PlayerController(service_controller)
    controller = LyricController(service_controller, player_controller)
    seen: list[int] = []
    controller.positionMsChanged.connect(lambda: seen.append(controller.positionMs))

    player_controller.updatePosition(1234)

    assert controller.positionMs == 1234
    assert seen and seen[-1] == 1234
