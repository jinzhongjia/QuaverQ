"""Library QObject exposed to QML."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from qasync import asyncSlot

from quaverq.core.models import Song

from .models import (
    CardListModel,
    album_to_card,
    playlist_to_card,
    singer_to_card,
    SongListModel,
    song_from_map,
)
from .service_controller import ServiceController

logger = logging.getLogger(__name__)


class LibraryController(QObject):
    """QML-facing user library state."""

    likedModelChanged = Signal()
    playlistModelChanged = Signal()
    albumModelChanged = Signal()
    artistModelChanged = Signal()
    likedCountChanged = Signal()
    likedRevisionChanged = Signal()
    loadingChanged = Signal()
    errorMessageChanged = Signal()
    authStateChanged = Signal()
    likedChanged = Signal(str, bool)
    errorRaised = Signal(str)

    def __init__(
        self,
        service_controller: ServiceController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._liked_model = SongListModel(self)
        self._playlist_model = CardListModel(self)
        self._album_model = CardListModel(self)
        self._artist_model = CardListModel(self)
        self._liked_mids: set[str] = set()
        self._loading = False
        self._error_message = ""
        self._liked_revision = 0
        self._service_controller.authStateChanged.connect(self._handle_auth_state_changed)

    @Property(QObject, notify=likedModelChanged)
    def likedModel(self) -> SongListModel:
        return self._liked_model

    @Property(QObject, notify=playlistModelChanged)
    def playlistModel(self) -> CardListModel:
        return self._playlist_model

    @Property(QObject, notify=albumModelChanged)
    def albumModel(self) -> CardListModel:
        return self._album_model

    @Property(QObject, notify=artistModelChanged)
    def artistModel(self) -> CardListModel:
        return self._artist_model

    @Property(int, notify=likedCountChanged)
    def likedCount(self) -> int:
        return len(self._liked_mids)

    @Property(int, notify=likedRevisionChanged)
    def likedRevision(self) -> int:
        return self._liked_revision

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @Property(bool, notify=authStateChanged)
    def authed(self) -> bool:
        return self._service_controller.authed

    @asyncSlot()
    async def refreshLiked(self) -> None:
        await self.refresh_liked_async()

    async def refresh_liked_async(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._set_liked_songs([])
            return

        self._set_loading(True)
        try:
            await self._service_controller._ensure_started()  # noqa: SLF001
            songs = await self._service_controller._service.get_liked_songs()  # noqa: SLF001
        except Exception as exc:
            logger.exception("refresh liked songs failed")
            message = str(exc) or exc.__class__.__name__
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            self._set_loading(False)

        self._set_liked_songs(songs)

    @asyncSlot()
    async def refreshMyPlaylists(self) -> None:
        await self.refresh_my_playlists_async()

    async def refresh_my_playlists_async(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._playlist_model.clear()
            return

        self._set_loading(True)
        try:
            await self._service_controller._ensure_started()  # noqa: SLF001
            playlists = await self._service_controller._service.get_my_playlists()  # noqa: SLF001
        except Exception as exc:
            logger.exception("refresh my playlists failed")
            message = str(exc) or exc.__class__.__name__
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            self._set_loading(False)

        self._playlist_model.set_cards([playlist_to_card(item) for item in playlists])

    @asyncSlot()
    async def refreshFavAlbums(self) -> None:
        await self.refresh_fav_albums_async()

    async def refresh_fav_albums_async(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._album_model.clear()
            return

        self._set_loading(True)
        try:
            await self._service_controller._ensure_started()  # noqa: SLF001
            albums = await self._service_controller._service.get_fav_albums()  # noqa: SLF001
        except Exception as exc:
            logger.exception("refresh fav albums failed")
            message = str(exc) or exc.__class__.__name__
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            self._set_loading(False)

        self._album_model.set_cards([album_to_card(item) for item in albums])

    @asyncSlot()
    async def refreshFollowedSingers(self) -> None:
        await self.refresh_followed_singers_async()

    async def refresh_followed_singers_async(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._artist_model.clear()
            return

        self._set_loading(True)
        try:
            await self._service_controller._ensure_started()  # noqa: SLF001
            singers = await self._service_controller._service.get_followed_singers()  # noqa: SLF001
        except Exception as exc:
            logger.exception("refresh followed singers failed")
            message = str(exc) or exc.__class__.__name__
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            self._set_loading(False)

        self._artist_model.set_cards([singer_to_card(item) for item in singers])

    @asyncSlot("QVariant")
    async def toggleLike(self, song_data: Any) -> None:
        await self.toggle_like_async(song_data)

    async def toggle_like_async(self, song_data: Any) -> None:
        song = song_from_map(song_data if isinstance(song_data, Mapping) else {})
        if not song.mid:
            self._raise_error("无法同步喜欢：歌曲数据不完整")
            return
        if not self.authed:
            self._raise_error("登录后才能同步喜欢")
            return
        if song.id == 0:
            self._raise_error("无法同步喜欢：歌曲缺少数字 ID")
            return

        liked = song.mid in self._liked_mids
        self._set_loading(True)
        self._set_error_message("")
        try:
            await self._service_controller._ensure_started()  # noqa: SLF001
            if liked:
                ok = await self._service_controller._service.unlike_song(song)  # noqa: SLF001
            else:
                ok = await self._service_controller._service.like_song(song)  # noqa: SLF001
        except Exception as exc:
            logger.exception("toggle like failed: %s", song.name)
            self._raise_error(str(exc) or exc.__class__.__name__)
            return
        finally:
            self._set_loading(False)

        if not ok:
            self._raise_error("喜欢同步失败")
            return

        self._set_song_liked(song, not liked)

    @Slot(str, result=bool)
    def isLiked(self, mid: str) -> bool:
        return bool(mid) and mid in self._liked_mids

    @Slot()
    def _handle_auth_state_changed(self) -> None:
        self.authStateChanged.emit()
        if not self.authed:
            self._set_liked_songs([])
            self._playlist_model.clear()
            self._album_model.clear()
            self._artist_model.clear()
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.refresh_liked_async())

    def _set_liked_songs(self, songs: list[Song]) -> None:
        old_count = len(self._liked_mids)
        self._liked_mids = {song.mid for song in songs if song.mid}
        self._liked_model.set_songs(songs)
        if len(self._liked_mids) != old_count:
            self.likedCountChanged.emit()
        self._bump_liked_revision()

    def _set_song_liked(self, song: Song, liked: bool) -> None:
        old_count = len(self._liked_mids)
        songs = self._liked_model.songs()
        if liked:
            self._liked_mids.add(song.mid)
            if not any(item.mid == song.mid for item in songs):
                songs.insert(0, song)
        else:
            self._liked_mids.discard(song.mid)
            songs = [item for item in songs if item.mid != song.mid]

        self._liked_model.set_songs(songs)
        if len(self._liked_mids) != old_count:
            self.likedCountChanged.emit()
        self._bump_liked_revision()
        self.likedChanged.emit(song.mid, liked)

    def _bump_liked_revision(self) -> None:
        self._liked_revision += 1
        self.likedRevisionChanged.emit()

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

    def _raise_error(self, message: str) -> None:
        self._set_error_message(message)
        self.errorRaised.emit(message)
