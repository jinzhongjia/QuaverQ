"""Service QObject exposed to QML."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from qasync import asyncSlot

from quaverq.core.models import Song
from quaverq.core.service import QuaverService

from .models import SongListModel, song_from_map

logger = logging.getLogger(__name__)


class ServiceController(QObject):
    """QML-facing wrapper around QuaverService."""

    songResultsChanged = Signal()
    loadingChanged = Signal()
    errorMessageChanged = Signal()
    errorRaised = Signal(str)

    def __init__(
        self,
        service: QuaverService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service or QuaverService()
        self._song_results = SongListModel(self)
        self._loading = False
        self._error_message = ""
        self._started = False

    @Property(QObject, notify=songResultsChanged)
    def songResults(self) -> SongListModel:
        return self._song_results

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    async def start(self) -> None:
        if self._started:
            return
        await self._service.connect()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self._service.disconnect()
        self._started = False

    async def _ensure_started(self) -> None:
        if not self._started:
            await self.start()

    @asyncSlot(str)
    async def search(self, keyword: str) -> None:
        await self.search_async(keyword)

    async def search_async(self, keyword: str) -> None:
        kw = (keyword or "").strip()
        self._set_error_message("")
        if not kw:
            self._song_results.clear()
            return

        self._set_loading(True)
        try:
            await self._ensure_started()
            songs = await self._service.search_songs(kw, limit=30)
            self._song_results.set_songs(songs)
        except Exception as exc:
            logger.exception("search failed: %s", kw)
            message = str(exc) or exc.__class__.__name__
            self._set_error_message(message)
            self.errorRaised.emit(message)
        finally:
            self._set_loading(False)

    @Slot()
    def clear(self) -> None:
        self._set_error_message("")
        self._song_results.clear()

    async def get_song_url(
        self,
        song: Mapping[str, Any] | Song,
        quality_preference: str,
    ) -> Any:
        await self._ensure_started()
        return await self._service.get_song_url(
            song_from_map(song),
            quality_preference=quality_preference or "balanced",
        )

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
