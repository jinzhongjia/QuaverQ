"""Library QObject exposed to QML."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from qasync import asyncSlot

from quaverq.core.home_cache import HomeCache
from quaverq.core.models import Song

from .error_utils import log_bridge_error
from .models import (
    CardListModel,
    SongListModel,
    album_to_card,
    playlist_to_card,
    singer_to_card,
    song_from_map,
)
from .service_controller import ServiceController

logger = logging.getLogger(__name__)


class LibraryController(QObject):
    """QML-facing user library state."""

    likedModelChanged = Signal()
    playlistModelChanged = Signal()
    favPlaylistModelChanged = Signal()
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
        home_cache: HomeCache | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._home_cache = home_cache
        self._liked_model = SongListModel(self)
        self._playlist_model = CardListModel(self)
        self._fav_playlist_model = CardListModel(self)
        self._album_model = CardListModel(self)
        self._artist_model = CardListModel(self)
        self._liked_mids: set[str] = set()
        self._loading = False
        self._error_message = ""
        self._liked_revision = 0
        self._service_controller.authStateChanged.connect(self._handle_auth_state_changed)

    def prime_from_cache(self, account_key: str) -> None:
        """凭据就绪后: 按账号填充我的歌单; 仅当 model 空且账号匹配 (SWR 补空窗)."""
        if self._home_cache is None or not account_key:
            return
        snapshot = self._home_cache.load(account_key)
        if snapshot.my_playlists and self._playlist_model.count == 0:
            self._playlist_model.set_cards(snapshot.my_playlists)

    @Property(QObject, notify=likedModelChanged)
    def likedModel(self) -> SongListModel:
        return self._liked_model

    @Property(QObject, notify=playlistModelChanged)
    def playlistModel(self) -> CardListModel:
        return self._playlist_model

    @Property(QObject, notify=favPlaylistModelChanged)
    def favPlaylistModel(self) -> CardListModel:
        return self._fav_playlist_model

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
            songs = await self._service_controller.call_service(
                lambda service: service.get_liked_songs(),
                operation_name="get liked songs",
            )
        except Exception as exc:
            message = log_bridge_error(logger, "refresh liked songs failed", exc)
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
            playlists = await self._service_controller.call_service(
                lambda service: service.get_my_playlists(),
                operation_name="get my playlists",
            )
        except Exception as exc:
            message = log_bridge_error(logger, "refresh my playlists failed", exc)
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            self._set_loading(False)

        self._playlist_model.set_cards([playlist_to_card(item) for item in playlists])
        if self._home_cache is not None:
            self._home_cache.update(
                my_playlists=self._playlist_model.cards(),
                account_key=self._service_controller.account_key(),
            )

    @asyncSlot()
    async def refreshFavSonglists(self) -> None:
        await self.refresh_fav_songlists_async()

    async def refresh_fav_songlists_async(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._fav_playlist_model.clear()
            return

        self._set_loading(True)
        try:
            playlists = await self._service_controller.call_service(
                lambda service: service.get_fav_songlist(),
                operation_name="get fav songlists",
            )
        except Exception as exc:
            message = log_bridge_error(logger, "refresh fav songlists failed", exc)
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        finally:
            self._set_loading(False)

        self._fav_playlist_model.set_cards([playlist_to_card(item) for item in playlists])

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
            albums = await self._service_controller.call_service(
                lambda service: service.get_fav_albums(),
                operation_name="get fav albums",
            )
        except Exception as exc:
            message = log_bridge_error(logger, "refresh fav albums failed", exc)
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
            singers = await self._service_controller.call_service(
                lambda service: service.get_followed_singers(),
                operation_name="get followed singers",
            )
        except Exception as exc:
            message = log_bridge_error(logger, "refresh followed singers failed", exc)
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
            if liked:
                ok = await self._service_controller.call_service(
                    lambda service: service.unlike_song(song),
                    operation_name="unlike song",
                )
            else:
                ok = await self._service_controller.call_service(
                    lambda service: service.like_song(song),
                    operation_name="like song",
                )
        except Exception as exc:
            self._raise_error(log_bridge_error(logger, f"toggle like failed: {song.name}", exc))
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
            self._fav_playlist_model.clear()
            self._album_model.clear()
            self._artist_model.clear()
            if self._home_cache is not None:
                self._home_cache.clear_private()
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
