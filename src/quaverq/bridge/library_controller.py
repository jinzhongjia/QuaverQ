"""Library QObject exposed to QML."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from qasync import asyncSlot

from quaverq.core.home_cache import HomeCache
from quaverq.core.models import Song
from quaverq.perf import log_elapsed

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
    favPlaylistsRevisionChanged = Signal()
    favPlaylistChanged = Signal(str, bool)
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
        self._fav_pids: set[str] = set()
        self._loading_sections: set[str] = set()
        self._refresh_tasks: dict[str, asyncio.Task[None]] = {}
        self._error_message = ""
        self._liked_revision = 0
        self._fav_playlists_revision = 0
        self._fav_songlists_loaded = False
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

    @Property(int, notify=favPlaylistsRevisionChanged)
    def favPlaylistsRevision(self) -> int:
        return self._fav_playlists_revision

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return bool(self._loading_sections)

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
        await self._run_singleton_refresh("liked", self._refresh_liked_impl)

    async def _refresh_liked_impl(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._set_liked_songs([])
            return

        self._set_section_loading("liked", True)
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
            self._set_section_loading("liked", False)

        self._set_liked_songs(songs)

    @asyncSlot()
    async def refreshMyPlaylists(self) -> None:
        await self.refresh_my_playlists_async()

    async def refresh_my_playlists_async(self) -> None:
        await self._run_singleton_refresh("myPlaylists", self._refresh_my_playlists_impl)

    async def _refresh_my_playlists_impl(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._playlist_model.clear()
            return

        self._set_section_loading("myPlaylists", True)
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
            self._set_section_loading("myPlaylists", False)

        self._playlist_model.set_cards([playlist_to_card(item) for item in playlists])
        if self._home_cache is not None:
            self._home_cache.update(
                my_playlists=self._playlist_model.cards(),
                account_key=self._service_controller.account_key(),
            )

    @asyncSlot()
    async def refreshFavSonglists(self) -> None:
        await self.refresh_fav_songlists_async()

    @asyncSlot()
    async def refreshFavSonglistsIfNeeded(self) -> None:
        """仅在尚未加载过时拉取 (详情页进入用): 避免频繁切歌单页重复打接口触发风控."""
        if self._fav_songlists_loaded:
            return
        await self.refresh_fav_songlists_async()

    async def refresh_fav_songlists_async(self) -> None:
        await self._run_singleton_refresh("favSonglists", self._refresh_fav_songlists_impl)

    async def _refresh_fav_songlists_impl(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._fav_playlist_model.clear()
            return

        self._set_section_loading("favSonglists", True)
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
            self._set_section_loading("favSonglists", False)

        self._fav_playlist_model.set_cards([playlist_to_card(item) for item in playlists])
        # pid 统一存 str: QML / isPlaylistFaved 均传 str, 避免 int/str 不匹配致收藏态恒为 False
        self._set_fav_pids({str(item.pid) for item in playlists if item.pid})
        self._fav_songlists_loaded = True

    @asyncSlot()
    async def refreshFavAlbums(self) -> None:
        await self.refresh_fav_albums_async()

    async def refresh_fav_albums_async(self) -> None:
        await self._run_singleton_refresh("favAlbums", self._refresh_fav_albums_impl)

    async def _refresh_fav_albums_impl(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._album_model.clear()
            return

        self._set_section_loading("favAlbums", True)
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
            self._set_section_loading("favAlbums", False)

        self._album_model.set_cards([album_to_card(item) for item in albums])

    @asyncSlot()
    async def refreshFollowedSingers(self) -> None:
        await self.refresh_followed_singers_async()

    async def refresh_followed_singers_async(self) -> None:
        await self._run_singleton_refresh("followedSingers", self._refresh_followed_singers_impl)

    async def _refresh_followed_singers_impl(self) -> None:
        self._set_error_message("")
        if not self.authed:
            self._artist_model.clear()
            return

        self._set_section_loading("followedSingers", True)
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
            self._set_section_loading("followedSingers", False)

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
        self._set_section_loading("toggleLike", True)
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
            self._set_section_loading("toggleLike", False)

        if not ok:
            self._raise_error("喜欢同步失败")
            return

        self._set_song_liked(song, not liked)

    @Slot(str, result=bool)
    def isLiked(self, mid: str) -> bool:
        return bool(mid) and mid in self._liked_mids

    @Slot(str, result=bool)
    def isPlaylistFaved(self, pid: str) -> bool:
        return bool(pid) and pid in self._fav_pids

    @Slot(str, result=bool)
    def isMyPlaylist(self, pid: str) -> bool:
        """pid 是否属于"我创建的歌单"(用于在详情页隐藏对自建歌单的收藏按钮)."""
        return bool(pid) and any(
            str(card.get("id") or "") == pid for card in self._playlist_model.cards()
        )

    @asyncSlot(str)
    async def togglePlaylistFav(self, pid: str) -> None:
        await self.toggle_playlist_fav_async(pid)

    async def toggle_playlist_fav_async(self, pid: str) -> None:
        pid = str(pid or "")
        if not pid:
            self._raise_error("无法收藏：歌单数据不完整")
            return
        if not self.authed:
            self._raise_error("登录后才能收藏歌单")
            return

        faved = pid in self._fav_pids
        self._set_section_loading("togglePlaylistFav", True)
        self._set_error_message("")
        try:
            if faved:
                ok = await self._service_controller.call_service(
                    lambda service: service.unfav_songlist(pid),
                    operation_name="unfav songlist",
                )
            else:
                ok = await self._service_controller.call_service(
                    lambda service: service.fav_songlist(pid),
                    operation_name="fav songlist",
                )
        except Exception as exc:
            self._raise_error(log_bridge_error(logger, f"toggle playlist fav failed: {pid}", exc))
            return
        finally:
            self._set_section_loading("togglePlaylistFav", False)

        if not ok:
            self._raise_error("取消收藏失败" if faved else "收藏失败")
            return

        # 先翻转本地态让详情页按钮即时响应, 再从服务端重拉"我收藏的"列表对齐 model
        if faved:
            self._fav_pids.discard(pid)
        else:
            self._fav_pids.add(pid)
        self._bump_fav_playlists_revision()
        self.favPlaylistChanged.emit(pid, not faved)
        await self.refresh_fav_songlists_async()

    @Slot()
    def _handle_auth_state_changed(self) -> None:
        self.authStateChanged.emit()
        if not self.authed:
            self._set_liked_songs([])
            self._playlist_model.clear()
            self._fav_playlist_model.clear()
            self._set_fav_pids(set())
            self._fav_songlists_loaded = False
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

    def _set_fav_pids(self, pids: set[str]) -> None:
        if pids == self._fav_pids:
            return
        self._fav_pids = pids
        self._bump_fav_playlists_revision()

    def _bump_fav_playlists_revision(self) -> None:
        self._fav_playlists_revision += 1
        self.favPlaylistsRevisionChanged.emit()

    async def _run_singleton_refresh(
        self,
        section: str,
        refresh: Callable[[], Awaitable[None]],
    ) -> None:
        task = self._refresh_tasks.get(section)
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            await task
            return
        if current is None:
            with log_elapsed(logger, "library.refresh_section", section=section):
                await refresh()
            return
        self._refresh_tasks[section] = current
        try:
            with log_elapsed(logger, "library.refresh_section", section=section):
                await refresh()
        finally:
            if self._refresh_tasks.get(section) is current:
                self._refresh_tasks.pop(section, None)

    def _set_section_loading(self, section: str, value: bool) -> None:
        old_loading = bool(self._loading_sections)
        if value:
            if section in self._loading_sections:
                return
            self._loading_sections.add(section)
        else:
            if section not in self._loading_sections:
                return
            self._loading_sections.discard(section)
        if bool(self._loading_sections) == old_loading:
            return
        self.loadingChanged.emit()

    def _set_error_message(self, value: str) -> None:
        if self._error_message == value:
            return
        self._error_message = value
        self.errorMessageChanged.emit()

    def _raise_error(self, message: str) -> None:
        self._set_error_message(message)
        self.errorRaised.emit(message)
