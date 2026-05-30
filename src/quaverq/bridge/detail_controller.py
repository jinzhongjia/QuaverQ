"""Detail QObject exposed to QML."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Property, Signal
from qasync import asyncSlot

from quaverq.core.models import Album, ArtistDetail, Playlist, Song

from .error_utils import log_bridge_error
from .models import SongListModel
from .service_controller import ServiceController

logger = logging.getLogger(__name__)


class DetailController(QObject):
    """QML-facing detail page state for playlist, album, artist and top list."""

    detailChanged = Signal()
    songModelChanged = Signal()
    loadingChanged = Signal()
    errorMessageChanged = Signal()
    errorRaised = Signal(str)

    def __init__(
        self,
        service_controller: ServiceController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._song_model = SongListModel(self)
        self._kind = ""
        self._detail_id = ""
        self._title = ""
        self._subtitle = ""
        self._description = ""
        self._cover_url = ""
        self._loading = False
        self._error_message = ""
        self._load_generation = 0

    @Property(QObject, notify=songModelChanged)
    def songModel(self) -> SongListModel:
        return self._song_model

    @Property(str, notify=detailChanged)
    def kind(self) -> str:
        return self._kind

    @Property(str, notify=detailChanged)
    def detailId(self) -> str:
        return self._detail_id

    @Property(str, notify=detailChanged)
    def title(self) -> str:
        return self._title

    @Property(str, notify=detailChanged)
    def subtitle(self) -> str:
        return self._subtitle

    @Property(str, notify=detailChanged)
    def description(self) -> str:
        return self._description

    @Property(str, notify=detailChanged)
    def coverUrl(self) -> str:
        return self._cover_url

    @Property(int, notify=songModelChanged)
    def songCount(self) -> int:
        return self._song_model.count

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @asyncSlot(str, str, str, str)
    async def loadDetail(
        self,
        kind: str,
        detail_id: str,
        fallback_title: str = "",
        fallback_subtitle: str = "",
    ) -> None:
        await self.load_detail_async(
            kind,
            detail_id,
            fallback_title=fallback_title,
            fallback_subtitle=fallback_subtitle,
        )

    async def load_detail_async(
        self,
        kind: str,
        detail_id: str,
        *,
        fallback_title: str = "",
        fallback_subtitle: str = "",
    ) -> None:
        normalized_kind = (kind or "playlist").strip()
        normalized_id = (detail_id or "").strip()
        self._load_generation += 1
        generation = self._load_generation
        self._set_error_message("")
        self._set_detail(
            kind=normalized_kind,
            detail_id=normalized_id,
            title=fallback_title,
            subtitle=fallback_subtitle,
            description=fallback_subtitle,
            cover_url="",
        )
        self._set_songs([])

        if not normalized_id:
            self._set_loading(False)
            self._set_error_message("详情 ID 为空")
            self.errorRaised.emit(self._error_message)
            return

        self._set_loading(True)
        try:
            if normalized_kind == "album":
                album = await self._service_controller.call_service(
                    lambda service: service.get_album_detail(normalized_id),
                    operation_name="get album detail",
                )
                if generation == self._load_generation:
                    self._apply_album(album)
            elif normalized_kind == "artist":
                artist = await self._service_controller.call_service(
                    lambda service: service.get_artist_detail(normalized_id),
                    operation_name="get artist detail",
                )
                if generation == self._load_generation:
                    self._apply_artist(artist)
            elif normalized_kind == "top":
                playlist = await self._service_controller.call_service(
                    lambda service: service.get_top_detail(int(normalized_id)),
                    operation_name="get top detail",
                )
                if generation == self._load_generation:
                    self._apply_playlist(playlist, kind="top")
            else:
                playlist = await self._service_controller.call_service(
                    lambda service: service.get_playlist_detail(normalized_id),
                    operation_name="get playlist detail",
                )
                if generation == self._load_generation:
                    self._apply_playlist(playlist, kind="playlist")
        except Exception as exc:
            if generation != self._load_generation:
                return
            message = log_bridge_error(
                logger,
                f"load detail failed: {normalized_kind} {normalized_id}",
                exc,
            )
            self._set_error_message(message)
            self.errorRaised.emit(message)
        finally:
            if generation == self._load_generation:
                self._set_loading(False)

    def _apply_playlist(self, playlist: Playlist, *, kind: str) -> None:
        self._set_detail(
            kind=kind,
            detail_id=playlist.pid,
            title=playlist.name,
            subtitle=playlist.creator or self._format_song_count(playlist.song_count),
            description=playlist.description,
            cover_url=playlist.cover_url,
        )
        self._set_songs(playlist.songs)

    def _apply_album(self, album: Album) -> None:
        subtitle_parts = [part for part in (album.singer_name, album.publish_date) if part]
        self._set_detail(
            kind="album",
            detail_id=album.mid,
            title=album.name,
            subtitle=" · ".join(subtitle_parts),
            description=album.description,
            cover_url=album.cover_url,
        )
        self._set_songs(album.songs)

    def _apply_artist(self, artist: ArtistDetail) -> None:
        self._set_detail(
            kind="artist",
            detail_id=artist.singer.mid,
            title=artist.singer.name,
            subtitle="艺人",
            description=artist.description,
            cover_url=artist.singer.avatar_url,
        )
        self._set_songs(artist.hot_songs)

    def _set_detail(
        self,
        *,
        kind: str,
        detail_id: str,
        title: str,
        subtitle: str,
        description: str,
        cover_url: str,
    ) -> None:
        next_values = (kind, detail_id, title, subtitle, description, cover_url)
        old_values = (
            self._kind,
            self._detail_id,
            self._title,
            self._subtitle,
            self._description,
            self._cover_url,
        )
        if next_values == old_values:
            return
        self._kind = kind
        self._detail_id = detail_id
        self._title = title
        self._subtitle = subtitle
        self._description = description
        self._cover_url = cover_url
        self.detailChanged.emit()

    def _set_songs(self, songs: list[Song]) -> None:
        self._song_model.set_songs(songs)
        self.songModelChanged.emit()

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

    @staticmethod
    def _format_song_count(value: int) -> str:
        return f"{value} 首" if value > 0 else ""
