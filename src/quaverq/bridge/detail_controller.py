"""Detail QObject exposed to QML."""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, Signal
from qasync import asyncSlot

from quaverq.core.models import Album, ArtistDetail, Playlist, Song

from .error_utils import log_bridge_error
from .models import CardListModel, SongListModel, album_to_card, singer_to_card
from .service_controller import ServiceController

logger = logging.getLogger(__name__)


class DetailController(QObject):
    """QML-facing detail page state for playlist, album, artist and top list."""

    detailChanged = Signal()
    songModelChanged = Signal()
    loadingChanged = Signal()
    errorMessageChanged = Signal()
    errorRaised = Signal(str)
    # 歌手 tab 懒加载状态 (第二档 2.2)
    similarSingersChanged = Signal()
    singerSongsChanged = Signal()
    singerAlbumsChanged = Signal()
    similarSingersLoadingChanged = Signal()
    singerSongsLoadingChanged = Signal()
    singerAlbumsLoadingChanged = Signal()

    def __init__(
        self,
        service_controller: ServiceController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._song_model = SongListModel(self)
        self._similar_singers_model = CardListModel(self)
        self._singer_songs_model = SongListModel(self)
        self._singer_albums_model = CardListModel(self)
        self._similar_singers_loading = False
        self._singer_songs_loading = False
        self._singer_albums_loading = False
        self._similar_singers_loaded = False
        self._singer_songs_loaded = False
        self._singer_albums_loaded = False
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

    # ----- 歌手 tab 子模型 (2.2) -----
    @Property(QObject, notify=similarSingersChanged)
    def similarSingersModel(self) -> CardListModel:
        return self._similar_singers_model

    @Property(QObject, notify=singerSongsChanged)
    def singerSongsModel(self) -> SongListModel:
        return self._singer_songs_model

    @Property(QObject, notify=singerAlbumsChanged)
    def singerAlbumsModel(self) -> CardListModel:
        return self._singer_albums_model

    @Property(bool, notify=similarSingersLoadingChanged)
    def similarSingersLoading(self) -> bool:
        return self._similar_singers_loading

    @Property(bool, notify=singerSongsLoadingChanged)
    def singerSongsLoading(self) -> bool:
        return self._singer_songs_loading

    @Property(bool, notify=singerAlbumsLoadingChanged)
    def singerAlbumsLoading(self) -> bool:
        return self._singer_albums_loading

    @Property(bool, notify=similarSingersChanged)
    def similarSingersLoaded(self) -> bool:
        return self._similar_singers_loaded

    @Property(bool, notify=singerSongsChanged)
    def singerSongsLoaded(self) -> bool:
        return self._singer_songs_loaded

    @Property(bool, notify=singerAlbumsChanged)
    def singerAlbumsLoaded(self) -> bool:
        return self._singer_albums_loaded

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
        # 切详情页时把所有歌手 tab 状态归零, 避免下一个 artist 看到上一个的残留
        self._reset_singer_tabs()

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

    # ----------------------------------------------------------------
    # 歌手 tab 懒加载 (2.2)
    # 仅在 kind=artist 且 detail_id 有效时 QML 切到对应 tab 才调; idempotent.
    # ----------------------------------------------------------------

    @asyncSlot()
    async def loadSimilarSingers(self) -> None:
        if self._kind != "artist" or not self._detail_id:
            return
        if self._similar_singers_loading or self._similar_singers_loaded:
            return
        await self._load_similar_singers_async(self._detail_id)

    @asyncSlot()
    async def loadSingerSongs(self) -> None:
        if self._kind != "artist" or not self._detail_id:
            return
        if self._singer_songs_loading or self._singer_songs_loaded:
            return
        await self._load_singer_songs_async(self._detail_id)

    @asyncSlot()
    async def loadSingerAlbums(self) -> None:
        if self._kind != "artist" or not self._detail_id:
            return
        if self._singer_albums_loading or self._singer_albums_loaded:
            return
        await self._load_singer_albums_async(self._detail_id)

    async def _load_similar_singers_async(self, singer_mid: str) -> None:
        self._set_similar_singers_loading(True)
        try:
            singers = await self._service_controller.call_service(
                lambda service: service.get_similar_singers(singer_mid),
                operation_name="get similar singers",
            )
        except Exception as exc:
            log_bridge_error(logger, "load similar singers failed", exc)
            singers = []
        finally:
            self._set_similar_singers_loading(False)
        self._similar_singers_model.set_cards([singer_to_card(s) for s in singers])
        self._similar_singers_loaded = True
        self.similarSingersChanged.emit()

    async def _load_singer_songs_async(self, singer_mid: str) -> None:
        self._set_singer_songs_loading(True)
        try:
            songs = await self._service_controller.call_service(
                lambda service: service.get_singer_songs(singer_mid),
                operation_name="get singer songs",
            )
        except Exception as exc:
            log_bridge_error(logger, "load singer songs failed", exc)
            songs = []
        finally:
            self._set_singer_songs_loading(False)
        self._singer_songs_model.set_songs(songs)
        self._singer_songs_loaded = True
        self.singerSongsChanged.emit()

    async def _load_singer_albums_async(self, singer_mid: str) -> None:
        self._set_singer_albums_loading(True)
        try:
            albums = await self._service_controller.call_service(
                lambda service: service.get_singer_albums(singer_mid),
                operation_name="get singer albums",
            )
        except Exception as exc:
            log_bridge_error(logger, "load singer albums failed", exc)
            albums = []
        finally:
            self._set_singer_albums_loading(False)
        self._singer_albums_model.set_cards([album_to_card(a) for a in albums])
        self._singer_albums_loaded = True
        self.singerAlbumsChanged.emit()

    def _reset_singer_tabs(self) -> None:
        """切到新 detail 时清空所有歌手 tab 状态."""
        self._similar_singers_model.clear()
        self._singer_songs_model.set_songs([])
        self._singer_albums_model.clear()
        self._similar_singers_loaded = False
        self._singer_songs_loaded = False
        self._singer_albums_loaded = False
        self._set_similar_singers_loading(False)
        self._set_singer_songs_loading(False)
        self._set_singer_albums_loading(False)
        self.similarSingersChanged.emit()
        self.singerSongsChanged.emit()
        self.singerAlbumsChanged.emit()

    def _set_similar_singers_loading(self, value: bool) -> None:
        if self._similar_singers_loading == value:
            return
        self._similar_singers_loading = value
        self.similarSingersLoadingChanged.emit()

    def _set_singer_songs_loading(self, value: bool) -> None:
        if self._singer_songs_loading == value:
            return
        self._singer_songs_loading = value
        self.singerSongsLoadingChanged.emit()

    def _set_singer_albums_loading(self, value: bool) -> None:
        if self._singer_albums_loading == value:
            return
        self._singer_albums_loading = value
        self.singerAlbumsLoadingChanged.emit()
