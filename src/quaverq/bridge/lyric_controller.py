"""Lyric QObject exposed to QML."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from qasync import asyncSlot

from quaverq.core.lyric import LyricSync
from quaverq.core.lyric_cache import LyricCache
from quaverq.core.models import Lyric

from .error_utils import log_bridge_error
from .models import LyricLineListModel, song_from_map
from .player_controller import PlayerController
from .service_controller import ServiceController

logger = logging.getLogger(__name__)


class LyricController(QObject):
    """QML-facing synchronized lyric state."""

    lyricModelChanged = Signal()
    lineCountChanged = Signal()
    activeIndexChanged = Signal()
    positionMsChanged = Signal()
    currentLineChanged = Signal()
    currentMidChanged = Signal()
    loadingChanged = Signal()
    errorMessageChanged = Signal()
    hasTranslationChanged = Signal()
    translationVisibleChanged = Signal()
    lyricChanged = Signal()
    errorRaised = Signal(str)

    def __init__(
        self,
        service_controller: ServiceController,
        player_controller: PlayerController,
        lyric_cache: LyricCache | None = None,
        parent: QObject | None = None,
        settings_controller: Any = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._player_controller = player_controller
        self._lyric_cache = lyric_cache
        self._settings_controller = settings_controller
        self._lyric_model = LyricLineListModel(self)
        self._sync = LyricSync()
        self._current_lyric: Lyric = Lyric(mid="")
        self._current_mid = ""
        self._active_index = -1
        self._loading = False
        self._error_message = ""
        self._has_translation = False
        self._translation_visible = self._read_translation_visible()
        self._lyric_model.set_translation_visible(self._translation_visible)
        self._load_generation = 0

        self._player_controller.currentSongChanged.connect(self._handle_current_song_changed)
        self._player_controller.positionMsChanged.connect(self._handle_position_changed)
        self._service_controller.authStateChanged.connect(self._handle_auth_state_changed)
        settings_changed = getattr(self._settings_controller, "settingsChanged", None)
        if settings_changed is not None:
            settings_changed.connect(self._handle_settings_changed)
        self._sync_current_song(schedule_load=False)

    @Property(QObject, notify=lyricModelChanged)
    def lyricModel(self) -> LyricLineListModel:
        return self._lyric_model

    @Property(int, notify=lineCountChanged)
    def lineCount(self) -> int:
        return self._lyric_model.count

    @Property(int, notify=activeIndexChanged)
    def activeIndex(self) -> int:
        return self._active_index

    @Property(int, notify=positionMsChanged)
    def positionMs(self) -> int:
        """当前播放位置 (ms); QML 据此在当前行内推进逐字高亮."""
        return self._player_controller.positionMs

    @Property(str, notify=currentLineChanged)
    def currentLineText(self) -> str:
        line = self._active_line()
        return line.get("lineText", "") if line else ""

    @Property(str, notify=currentLineChanged)
    def currentLineTranslation(self) -> str:
        if not self._translation_visible:
            return ""
        line = self._active_line()
        return line.get("translation", "") if line else ""

    @Property(str, notify=currentMidChanged)
    def currentMid(self) -> str:
        return self._current_mid

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @Property(bool, notify=hasTranslationChanged)
    def hasTranslation(self) -> bool:
        return self._has_translation and self._translation_visible

    @Property(bool, notify=translationVisibleChanged)
    def translationVisible(self) -> bool:
        return self._translation_visible

    @asyncSlot()
    async def refreshCurrentLyric(self) -> None:
        await self.refresh_current_lyric_async()

    async def refresh_current_lyric_async(self) -> None:
        song = song_from_map(self._player_controller.currentSong)
        self._load_generation += 1
        generation = self._load_generation
        self._set_current_mid(song.mid)
        if self._current_lyric.mid == song.mid and self._current_lyric.lines:
            pass
        elif not self._prime_lyric_from_cache(song.mid):
            self._set_lyric(Lyric(mid=song.mid))
        self._set_error_message("")
        if not song.mid:
            self._set_loading(False)
            return
        await self._load_lyric(song.mid, generation)

    @Slot()
    def _handle_current_song_changed(self) -> None:
        self._sync_current_song(schedule_load=True)

    def _sync_current_song(self, *, schedule_load: bool) -> None:
        song = song_from_map(self._player_controller.currentSong)
        if song.mid == self._current_mid:
            return
        self._load_generation += 1
        generation = self._load_generation
        self._set_current_mid(song.mid)
        if not self._prime_lyric_from_cache(song.mid):
            self._set_lyric(Lyric(mid=song.mid))
        self._set_error_message("")
        if not song.mid:
            self._set_loading(False)
            return
        if schedule_load:
            self._schedule_load(song.mid, generation)

    @Slot()
    def _handle_position_changed(self) -> None:
        self.positionMsChanged.emit()
        self._update_active_index()

    @Slot()
    def _handle_auth_state_changed(self) -> None:
        if not self._service_controller.authed:
            self._load_generation += 1
            self._set_lyric(Lyric(mid=self._current_mid))
            self._set_loading(False)
            return
        if self._current_mid:
            self._load_generation += 1
            self._schedule_load(self._current_mid, self._load_generation)

    @Slot()
    def _handle_settings_changed(self) -> None:
        self._set_translation_visible(self._read_translation_visible())

    def _schedule_load(self, mid: str, generation: int) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._load_lyric(mid, generation))

    async def _load_lyric(self, mid: str, generation: int) -> None:
        self._set_loading(True)
        self._set_error_message("")
        try:
            lyric = await self._service_controller.get_lyric(mid, with_translation=True)
        except Exception as exc:
            if generation != self._load_generation:
                return
            message = log_bridge_error(logger, f"load lyric failed: {mid}", exc)
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            if generation == self._load_generation:
                self._set_loading(False)

        if generation != self._load_generation:
            return
        self._save_lyric_to_cache(lyric)
        self._set_lyric(lyric)

    @property
    def current_lyric(self) -> Lyric:
        """当前已加载的 Lyric (供同进程消费者拿原始数据, 不上 QML)."""
        return self._current_lyric

    def _prime_lyric_from_cache(self, mid: str) -> bool:
        if self._lyric_cache is None or not mid:
            return False
        lyric = self._lyric_cache.load(mid, with_translation=True)
        if lyric is None:
            return False
        self._set_lyric(lyric)
        return True

    def _save_lyric_to_cache(self, lyric: Lyric) -> None:
        if self._lyric_cache is not None:
            self._lyric_cache.save(lyric, with_translation=True)

    def _set_lyric(self, lyric: Lyric) -> None:
        old_count = self._lyric_model.count
        old_has_translation = self.hasTranslation
        self._current_lyric = lyric
        self._has_translation = lyric.has_translation
        self._sync.set_lyric(lyric)
        self._lyric_model.set_lines(lyric.lines)
        if self._lyric_model.count != old_count:
            self.lineCountChanged.emit()
        if old_has_translation != self.hasTranslation:
            self.hasTranslationChanged.emit()
        self._update_active_index(force=True)
        self.currentLineChanged.emit()
        self.lyricChanged.emit()

    def _read_translation_visible(self) -> bool:
        return bool(getattr(self._settings_controller, "lyricTranslationVisible", True))

    def _set_translation_visible(self, visible: bool) -> None:
        value = bool(visible)
        if self._translation_visible == value:
            return
        old_has_translation = self.hasTranslation
        self._translation_visible = value
        self._lyric_model.set_translation_visible(value)
        self.translationVisibleChanged.emit()
        if old_has_translation != self.hasTranslation:
            self.hasTranslationChanged.emit()
        self.currentLineChanged.emit()
        self.lyricChanged.emit()

    def _update_active_index(self, *, force: bool = False) -> None:
        next_index = self._sync.line_at(self._player_controller.positionMs)
        if not force and next_index == self._active_index:
            return
        old_index = self._active_index
        old_line = self._active_line()
        self._active_index = next_index
        if force or next_index != old_index:
            self.activeIndexChanged.emit()
        if old_line != self._active_line():
            self.currentLineChanged.emit()

    def _active_line(self) -> dict[str, Any]:
        if not (0 <= self._active_index < self._lyric_model.count):
            return {}
        return self._lyric_model.lineAt(self._active_index)

    def _set_current_mid(self, value: str) -> None:
        if self._current_mid == value:
            return
        self._current_mid = value
        self.currentMidChanged.emit()

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
