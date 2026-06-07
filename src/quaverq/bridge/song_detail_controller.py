"""Song detail popup QObject exposed to QML (第二档 2.1 + 2.4).

提供"相似歌曲" / "相关歌单" / "歌曲附加信息" 三块数据, 由 ``open(songData)`` 异步并发拉.
不进 SWR 首帧链路: 仅在用户主动打开 popup 时才请求.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from qasync import asyncSlot

from quaverq.core.models import Playlist, Song, SongInfo
from quaverq.core.service import QuaverService

from .error_utils import log_bridge_error
from .models import CardListModel, SongListModel, playlist_to_card, song_from_map, song_to_map
from .service_controller import ServiceController


async def _gather_song_payload(
    service: QuaverService, song: Song
) -> tuple[list[Song], list[Playlist], SongInfo]:
    """单次 call_service 内并发 get_song_related + get_song_info."""
    (similar, related), info = await asyncio.gather(
        service.get_song_related(song.id),
        service.get_song_info(song.mid, song.id),
    )
    return similar, related, info


logger = logging.getLogger(__name__)


class SongDetailController(QObject):
    """QML-facing song detail popup state."""

    currentSongChanged = Signal()
    similarModelChanged = Signal()
    relatedModelChanged = Signal()
    songInfoChanged = Signal()
    loadingChanged = Signal()
    errorMessageChanged = Signal()
    visibleChanged = Signal()
    errorRaised = Signal(str)

    def __init__(
        self,
        service_controller: ServiceController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._similar_model = SongListModel(self)
        self._related_model = CardListModel(self)
        self._current_song: Song | None = None
        self._song_info: SongInfo = SongInfo()
        self._loading = False
        self._error_message = ""
        self._visible = False
        # 多次快速 open 时只采纳最后一次结果, 避免 race
        self._load_generation = 0

    # ------------------------------------------------------------------ props
    @Property(QObject, notify=similarModelChanged)
    def similarSongsModel(self) -> SongListModel:
        return self._similar_model

    @Property(QObject, notify=relatedModelChanged)
    def relatedPlaylistsModel(self) -> CardListModel:
        return self._related_model

    @Property("QVariant", notify=currentSongChanged)
    def currentSong(self) -> dict[str, Any]:
        return song_to_map(self._current_song) if self._current_song is not None else {}

    @Property("QVariant", notify=songInfoChanged)
    def songInfo(self) -> dict[str, Any]:
        """歌曲附加信息 (语种/流派/制作人 等), 2.4 加入. QML 用 dict 形式消费."""
        info = self._song_info
        return {
            "language": info.language,
            "genre": info.genre,
            "company": info.company,
            "publishTime": info.publish_time,
            "intro": info.intro,
            "tags": list(info.tags),
            "producers": [{"title": g.title, "names": list(g.names)} for g in info.producers],
        }

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @Property(bool, notify=visibleChanged)
    def visible(self) -> bool:
        return self._visible

    # ------------------------------------------------------------------ slots
    @asyncSlot("QVariant")
    async def open(self, song_data: Any) -> None:
        await self.open_async(song_data)

    @asyncSlot()
    async def retry(self) -> None:
        """错误态下重试加载当前 song."""
        if self._current_song is None:
            return
        await self._load_async(self._current_song)

    @Slot()
    def close(self) -> None:
        self._set_visible(False)
        # 不清 model: 关掉对话框时保留上次内容, 下次 open 再覆盖

    async def open_async(self, song_data: Any) -> None:
        song = song_from_map(song_data if isinstance(song_data, Mapping) else {})
        if not song.mid or song.id == 0:
            self._raise_error("无法显示歌曲详情：歌曲数据不完整")
            return

        self._current_song = song
        self.currentSongChanged.emit()
        self._set_visible(True)
        await self._load_async(song)

    async def _load_async(self, song: Song) -> None:
        """实际加载相似 + 相关 + 歌曲附加信息. 切歌时立刻清空 model + 进 loading 态."""
        self._set_error_message("")
        self._similar_model.set_songs([])
        self._related_model.set_cards([])
        self._song_info = SongInfo()
        self.songInfoChanged.emit()

        self._load_generation += 1
        gen = self._load_generation
        self._set_loading(True)
        try:
            similar, related, song_info = await self._service_controller.call_service(
                lambda service: _gather_song_payload(service, song),
                operation_name=f"get song detail payload (songid={song.id})",
            )
        except Exception as exc:
            if gen != self._load_generation:
                return  # 已被更新的请求覆盖
            message = log_bridge_error(logger, "load song detail payload failed", exc)
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            if gen == self._load_generation:
                self._set_loading(False)

        if gen != self._load_generation:
            return
        self._similar_model.set_songs(similar)
        self._related_model.set_cards([playlist_to_card(p) for p in related])
        self._song_info = song_info
        self.similarModelChanged.emit()
        self.relatedModelChanged.emit()
        self.songInfoChanged.emit()

    # ------------------------------------------------------------------ helpers
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

    def _set_visible(self, value: bool) -> None:
        if self._visible == value:
            return
        self._visible = value
        self.visibleChanged.emit()

    def _raise_error(self, message: str) -> None:
        self._set_error_message(message)
        self.errorRaised.emit(message)
