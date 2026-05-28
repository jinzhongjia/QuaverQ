"""Bridge PlayerController state to MPRIS."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QObject

from quaverq.core.mpris import MprisCallbacks, MprisService

from .models import song_from_map
from .player_controller import PlayerController

logger = logging.getLogger(__name__)


class MprisServiceLike(Protocol):
    async def start(self) -> bool: ...
    async def stop(self) -> None: ...
    def push_metadata(self, song, *, local_cover_uri: str | None = None) -> None: ...
    def push_playback_status(self, state: str | None) -> None: ...
    def push_position(self, position_ms: int) -> None: ...
    def push_volume(self, volume: float) -> None: ...
    def push_playback_mode(self, mode: str | None) -> None: ...


MprisServiceFactory = Callable[[MprisCallbacks], MprisServiceLike]


class MprisController(QObject):
    """Synchronize PlayerController with the Linux MPRIS service."""

    def __init__(
        self,
        player_controller: PlayerController,
        *,
        service_factory: MprisServiceFactory = MprisService,
        raise_window: Callable[[], None] | None = None,
        quit_app: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player_controller = player_controller
        self._started = False
        self._service = service_factory(
            MprisCallbacks(
                play_pause=self._player_controller.togglePlayPause,
                play=self._player_controller.play,
                pause=self._player_controller.pause,
                stop=self._player_controller.stop,
                next=lambda: self._invoke_player_command(self._player_controller.next),
                prev=lambda: self._invoke_player_command(self._player_controller.prev),
                seek=self._player_controller.seek,
                raise_window=raise_window or (lambda: None),
                quit=quit_app or (lambda: None),
            )
        )

        self._player_controller.currentSongChanged.connect(self._push_metadata)
        self._player_controller.playbackStateChanged.connect(self._push_playback_status)
        self._player_controller.positionMsChanged.connect(self._push_position)
        self._player_controller.volumeChanged.connect(self._push_volume)
        self._player_controller.modeChanged.connect(self._push_playback_mode)

    async def start_async(self) -> bool:
        self._started = await self._service.start()
        if self._started:
            self._sync_all()
        return self._started

    async def stop_async(self) -> None:
        await self._service.stop()
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def _sync_all(self) -> None:
        self._push_metadata()
        self._push_playback_status()
        self._push_position()
        self._push_volume()
        self._push_playback_mode()

    def _push_metadata(self) -> None:
        if not self._started:
            return
        song = song_from_map(self._player_controller.currentSong)
        if song.mid:
            self._service.push_metadata(song)

    def _push_playback_status(self) -> None:
        if self._started:
            self._service.push_playback_status(self._player_controller.playbackState)

    def _push_position(self) -> None:
        if self._started:
            self._service.push_position(self._player_controller.positionMs)

    def _push_volume(self) -> None:
        if self._started:
            self._service.push_volume(self._player_controller.volume)

    def _push_playback_mode(self) -> None:
        if self._started:
            self._service.push_playback_mode(self._player_controller.mode)

    @staticmethod
    def _invoke_player_command(command: Callable[[], object]) -> None:
        try:
            result = command()
        except RuntimeError as exc:
            logger.warning("MPRIS command ignored: %s", exc)
            return
        if asyncio.isfuture(result):
            return
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("MPRIS command ignored: no running event loop")
                return
            loop.create_task(result)
