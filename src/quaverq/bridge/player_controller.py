"""Player QObject exposed to QML."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from qasync import asyncSlot

from quaverq.core.models import Song
from quaverq.core.queue import PlayMode, PlayQueue

from .models import SongListModel, song_from_map, song_to_map
from .service_controller import ServiceController

logger = logging.getLogger(__name__)


_MODE_TO_NAME = {
    PlayMode.SEQUENCE: "sequence",
    PlayMode.REPEAT_ALL: "repeat_all",
    PlayMode.REPEAT_ONE: "repeat_one",
    PlayMode.SHUFFLE: "shuffle",
}
_NAME_TO_MODE = {value: key for key, value in _MODE_TO_NAME.items()}


class PlayerController(QObject):
    """QML-facing playback state and command controller."""

    currentSongChanged = Signal()
    currentIndexChanged = Signal()
    sourceUrlChanged = Signal()
    playbackStateChanged = Signal()
    positionMsChanged = Signal()
    durationMsChanged = Signal()
    volumeChanged = Signal()
    modeChanged = Signal()
    queueChanged = Signal()
    loadingChanged = Signal()
    errorMessageChanged = Signal()
    errorRaised = Signal(str)

    playRequested = Signal()
    pauseRequested = Signal()
    stopRequested = Signal()
    seekRequested = Signal(int)

    def __init__(
        self,
        service_controller: ServiceController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._queue = PlayQueue()
        self._queue_model = SongListModel(self)
        self._source_url = ""
        self._playback_state = "stopped"
        self._position_ms = 0
        self._duration_ms = 0
        self._volume = 0.8
        self._loading = False
        self._error_message = ""
        self._load_generation = 0

    @Property("QVariant", notify=currentSongChanged)
    def currentSong(self) -> dict[str, Any]:
        song = self._queue.current()
        return song_to_map(song) if song else {}

    @Property(int, notify=currentIndexChanged)
    def currentIndex(self) -> int:
        return self._queue.current_index

    @Property(str, notify=sourceUrlChanged)
    def sourceUrl(self) -> str:
        return self._source_url

    @Property(str, notify=playbackStateChanged)
    def playbackState(self) -> str:
        return self._playback_state

    @Property(int, notify=positionMsChanged)
    def positionMs(self) -> int:
        return self._position_ms

    @Property(int, notify=durationMsChanged)
    def durationMs(self) -> int:
        return self._duration_ms

    @Property(float, notify=volumeChanged)
    def volume(self) -> float:
        return self._volume

    @Property(str, notify=modeChanged)
    def mode(self) -> str:
        return _MODE_TO_NAME[self._queue.mode]

    @Property(QObject, notify=queueChanged)
    def queueModel(self) -> SongListModel:
        return self._queue_model

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @asyncSlot("QVariant")
    async def pushAndPlay(self, song_data: Any) -> None:
        await self.push_and_play_async(song_data)

    async def push_and_play_async(self, song_data: Any) -> None:
        song = song_from_map(song_data if isinstance(song_data, Mapping) else {})
        if not song.mid:
            message = "无法播放：歌曲数据不完整"
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        await self.play_songs_async([song], 0)

    @asyncSlot(QObject, int)
    async def playFromModel(self, model: QObject, row: int) -> None:
        await self.play_from_model_async(model, row)

    async def play_from_model_async(self, model: QObject, row: int) -> None:
        songs = self._songs_from_model(model)
        await self.play_songs_async(songs, row)

    async def play_songs_async(self, songs: list[Song], start_index: int) -> None:
        if not songs or not (0 <= start_index < len(songs)):
            message = "无法播放：队列数据不完整"
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        requested_song = songs[start_index]
        current_song = self._queue.current()
        if (
            self._loading
            and current_song is not None
            and current_song.mid == requested_song.mid
            and self._queue.current_index == start_index
            and len(self._queue.songs) == len(songs)
        ):
            return
        self._queue.push(songs, play_now=True, start_index=start_index)
        self._sync_queue_model()
        self._emit_current_changed()
        await self._load_current(play_when_ready=True)

    @asyncSlot()
    async def next(self) -> None:  # noqa: A003
        song = self._queue.next()
        if song is None:
            self.stop()
            return
        self._emit_current_changed()
        await self._load_current(play_when_ready=True)

    @asyncSlot()
    async def prev(self) -> None:
        song = self._queue.prev()
        if song is None:
            return
        self._emit_current_changed()
        await self._load_current(play_when_ready=True)

    @asyncSlot()
    async def handleEndOfMedia(self) -> None:
        song = self._queue.on_song_end()
        if song is None:
            self.stop()
            return
        self._emit_current_changed()
        await self._load_current(play_when_ready=True)

    @Slot()
    def play(self) -> None:
        if not self._source_url:
            return
        self.playRequested.emit()

    @Slot()
    def pause(self) -> None:
        self.pauseRequested.emit()

    @Slot()
    def togglePlayPause(self) -> None:
        if self._playback_state == "playing":
            self.pause()
        else:
            self.play()

    @Slot()
    def stop(self) -> None:
        self._set_source_url("")
        self._set_position_ms(0)
        self._set_playback_state("stopped")
        self.stopRequested.emit()

    @Slot(int)
    def seek(self, position_ms: int) -> None:
        self.seekRequested.emit(max(0, int(position_ms)))

    @Slot(float)
    def setVolume(self, volume: float) -> None:
        value = min(1.0, max(0.0, float(volume)))
        if self._volume == value:
            return
        self._volume = value
        self.volumeChanged.emit()

    @Slot(str)
    def setMode(self, mode: str) -> None:
        next_mode = _NAME_TO_MODE.get(mode)
        if next_mode is None:
            return
        self._queue.set_mode(next_mode)
        self.modeChanged.emit()

    @Slot(int)
    def updatePosition(self, position_ms: int) -> None:
        self._set_position_ms(position_ms)

    @Slot(int)
    def updateDuration(self, duration_ms: int) -> None:
        if self._duration_ms == duration_ms:
            return
        self._duration_ms = max(0, int(duration_ms))
        self.durationMsChanged.emit()

    @Slot(str)
    def updatePlaybackState(self, state: str) -> None:
        self._set_playback_state(state)

    async def _load_current(self, *, play_when_ready: bool) -> None:
        song = self._queue.current()
        if song is None:
            self.stop()
            return
        self._load_generation += 1
        generation = self._load_generation
        self._set_source_url("")
        self._set_position_ms(0)
        self.updateDuration(song.duration * 1000)
        self._set_error_message("")
        self._set_loading(True)
        self._set_playback_state("loading")
        try:
            song_url = await self._service_controller.get_song_url(
                song,
                quality_preference="balanced",
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            if message == "播放需要先登录 QQ 音乐":
                logger.warning("%s: %s", message, song.name)
            else:
                logger.exception("load song url failed: %s", song.name)
            if generation != self._load_generation:
                return
            self._set_playback_state("stopped")
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            if generation == self._load_generation:
                self._set_loading(False)

        if generation != self._load_generation:
            return

        if song_url is None or not song_url.url:
            message = f"无法获取播放链接：{song.name}"
            self._set_playback_state("stopped")
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return

        self._set_source_url(song_url.url)
        if play_when_ready:
            self.playRequested.emit()

    def _songs_from_model(self, model: QObject) -> list[Song]:
        if isinstance(model, SongListModel):
            return model.songs()
        count = int(getattr(model, "count", 0) or 0)
        if not hasattr(model, "songAt"):
            return []
        songs: list[Song] = []
        for row in range(count):
            song = song_from_map(model.songAt(row))
            if song.mid:
                songs.append(song)
        return songs

    def _sync_queue_model(self) -> None:
        self._queue_model.set_songs(self._queue.songs)
        self.queueChanged.emit()

    def _emit_current_changed(self) -> None:
        self.currentSongChanged.emit()
        self.currentIndexChanged.emit()

    def _set_source_url(self, value: str) -> None:
        if self._source_url == value:
            return
        self._source_url = value
        self.sourceUrlChanged.emit()

    def _set_playback_state(self, value: str) -> None:
        if self._playback_state == value:
            return
        self._playback_state = value
        self.playbackStateChanged.emit()

    def _set_position_ms(self, value: int) -> None:
        value = max(0, int(value))
        if self._position_ms == value:
            return
        self._position_ms = value
        self.positionMsChanged.emit()

    def _set_loading(self, value: bool) -> None:
        if self._loading == value:
            return
        self._loading = value
        self.loadingChanged.emit()

    def _set_error_message(self, value: str) -> None:
        if self._error_message == value:
            return
        self._error_message = value
        self.errorMessageChanged.emit()
