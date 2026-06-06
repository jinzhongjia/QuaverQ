"""Home/discovery QObject exposed to QML."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from PySide6.QtCore import Property, QObject, Signal
from qasync import asyncSlot

from quaverq.core.home_cache import HomeCache
from quaverq.core.models import Playlist, Song, TopList

from .error_utils import log_bridge_error
from .models import (
    CardListModel,
    SongListModel,
    playlist_to_card,
    song_to_map,
    top_to_card,
)
from .service_controller import ServiceController

logger = logging.getLogger(__name__)

T = TypeVar("T")


class HomeController(QObject):
    """QML-facing home/discovery state."""

    dailyModelChanged = Signal()
    playlistModelChanged = Signal()
    newSongModelChanged = Signal()
    topModelChanged = Signal()
    loadingChanged = Signal()
    loadingSectionsChanged = Signal()
    sectionStateChanged = Signal()
    dailyRequiresLoginChanged = Signal()
    errorMessageChanged = Signal()
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
        self._daily_model = SongListModel(self)
        self._playlist_model = CardListModel(self)
        self._new_song_model = SongListModel(self)
        self._top_model = CardListModel(self)
        self._loading_sections: set[str] = set()
        self._section_errors: dict[str, str] = {}
        self._daily_refresh_task: asyncio.Task[None] | None = None
        self._daily_requires_login = False
        self._error_message = ""
        self._service_controller.authStateChanged.connect(self._handle_auth_state_changed)

    # ---------------------------------------------------------------- SWR 缓存
    def prime_public_from_cache(self) -> None:
        """启动首帧: 同步用上次缓存填充公共区块 (今日推荐 / 新歌速递 / 排行榜).

        仅在对应 model 还空时填充, 不覆盖已到达的网络数据 (SWR: 缓存只补空窗).
        在 engine.load 前调用, 让第一帧就有内容.
        """
        if self._home_cache is None:
            return
        snapshot = self._home_cache.load("")
        if snapshot.playlists and self._playlist_model.count == 0:
            self._playlist_model.set_cards(snapshot.playlists)
        if snapshot.new_songs and self._new_song_model.count == 0:
            self._new_song_model.set_songs(snapshot.new_songs)
        if snapshot.tops and self._top_model.count == 0:
            self._top_model.set_cards(snapshot.tops)

    def prime_private_from_cache(self, account_key: str) -> None:
        """凭据就绪后: 按账号填充私有区块 (猜你喜欢); 仅当 model 空且账号匹配."""
        if self._home_cache is None or not account_key:
            return
        snapshot = self._home_cache.load(account_key)
        if snapshot.daily and self._daily_model.count == 0:
            self._set_daily_requires_login(False)
            self._daily_model.set_songs(snapshot.daily)
            self.dailyModelChanged.emit()

    def _persist(self, **sections: object) -> None:
        if self._home_cache is not None:
            self._home_cache.update(**sections)  # type: ignore[arg-type]

    @Property(QObject, notify=dailyModelChanged)
    def dailyModel(self) -> SongListModel:
        return self._daily_model

    @Property("QVariant", notify=dailyModelChanged)
    def dailyPreviewSong(self) -> dict[str, Any]:
        songs = self._daily_model.songs()
        if not songs:
            return {}
        return song_to_map(songs[0])

    @Property(QObject, notify=playlistModelChanged)
    def playlistModel(self) -> CardListModel:
        return self._playlist_model

    @Property(QObject, notify=newSongModelChanged)
    def newSongModel(self) -> SongListModel:
        return self._new_song_model

    @Property(QObject, notify=topModelChanged)
    def topModel(self) -> CardListModel:
        return self._top_model

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return bool(self._loading_sections)

    @Property("QStringList", notify=loadingSectionsChanged)
    def loadingSections(self) -> list[str]:
        return sorted(self._loading_sections)

    @Property(bool, notify=loadingSectionsChanged)
    def dailyLoading(self) -> bool:
        return "daily" in self._loading_sections

    @Property(bool, notify=loadingSectionsChanged)
    def playlistLoading(self) -> bool:
        return "playlists" in self._loading_sections

    @Property(bool, notify=loadingSectionsChanged)
    def newSongLoading(self) -> bool:
        return "newSongs" in self._loading_sections

    @Property(bool, notify=loadingSectionsChanged)
    def topLoading(self) -> bool:
        return "tops" in self._loading_sections

    @Property(bool, notify=dailyRequiresLoginChanged)
    def dailyRequiresLogin(self) -> bool:
        return self._daily_requires_login

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @Property(str, notify=sectionStateChanged)
    def dailyErrorMessage(self) -> str:
        return self._section_errors.get("daily", "")

    @Property(str, notify=sectionStateChanged)
    def playlistErrorMessage(self) -> str:
        return self._section_errors.get("playlists", "")

    @Property(str, notify=sectionStateChanged)
    def newSongErrorMessage(self) -> str:
        return self._section_errors.get("newSongs", "")

    @Property(str, notify=sectionStateChanged)
    def topErrorMessage(self) -> str:
        return self._section_errors.get("tops", "")

    @asyncSlot()
    async def refreshHome(self) -> None:
        await self.refresh_home_async()

    async def refresh_home_async(self) -> None:
        await asyncio.gather(
            self.refresh_daily_thirty_async(),
            self.refresh_playlists_async(),
            self.refresh_new_songs_async(),
            self.refresh_top_lists_async(),
        )

    @asyncSlot()
    async def refreshDailyThirty(self) -> None:
        await self.refresh_daily_thirty_async()

    async def refresh_daily_thirty_async(self) -> None:
        task = self._daily_refresh_task
        current_task = asyncio.current_task()
        if task is not None and task is not current_task and not task.done():
            await task
            return
        if "daily" in self._loading_sections:
            if task is not None and task is not current_task:
                await task
            return
        if not self._service_controller.authed:
            self._set_daily_requires_login(True)
            self._daily_model.clear()
            self.dailyModelChanged.emit()
            self._clear_section_error("daily")
            return

        self._set_daily_requires_login(False)

        async def load() -> list[Song]:
            return await self._service_controller.call_service(
                lambda service: service.get_daily_recommend_songs(limit=30),
                operation_name="daily recommend songs",
            )

        current_task = asyncio.current_task()
        if current_task is not None:
            self._daily_refresh_task = current_task
        try:
            songs = await self._load_section("daily", load)
            if songs is not None:
                self._daily_model.set_songs(songs)
                self.dailyModelChanged.emit()
                self._persist(daily=songs, account_key=self._service_controller.account_key())
        finally:
            if self._daily_refresh_task is current_task:
                self._daily_refresh_task = None

    @asyncSlot()
    async def refreshPlaylists(self) -> None:
        await self.refresh_playlists_async()

    async def refresh_playlists_async(self) -> None:
        if "playlists" in self._loading_sections:
            return

        async def load() -> list[Playlist]:
            return await self._service_controller.call_service(
                lambda service: service.get_recommend_playlists(limit=8),
                operation_name="recommend playlists",
            )

        playlists = await self._load_section("playlists", load)
        if playlists is not None:
            self._playlist_model.set_cards([playlist_to_card(item) for item in playlists])
            self._persist(playlists=self._playlist_model.cards())

    @asyncSlot()
    async def refreshNewSongs(self) -> None:
        await self.refresh_new_songs_async()

    async def refresh_new_songs_async(self) -> None:
        if "newSongs" in self._loading_sections:
            return

        async def load() -> list[Song]:
            return await self._service_controller.call_service(
                lambda service: service.get_recommend_new_songs(limit=12),
                operation_name="recommend new songs",
            )

        songs = await self._load_section("newSongs", load)
        if songs is not None:
            self._new_song_model.set_songs(songs)
            self._persist(new_songs=songs)

    @asyncSlot()
    async def refreshTopLists(self) -> None:
        await self.refresh_top_lists_async()

    async def refresh_top_lists_async(self) -> None:
        if "tops" in self._loading_sections:
            return

        async def load() -> list[TopList]:
            tops = await self._service_controller.call_service(
                lambda service: service.get_top_categories(limit_per_group=3),
                operation_name="top categories",
            )
            return tops[:9]

        tops = await self._load_section("tops", load)
        if tops is not None:
            self._top_model.set_cards([top_to_card(item) for item in tops])
            self._persist(tops=self._top_model.cards())

    async def _load_section(
        self,
        section: str,
        loader: Callable[[], Awaitable[T]],
    ) -> T | None:
        self._set_section_loading(section, True)
        self._clear_section_error(section)
        try:
            return await loader()
        except Exception as exc:
            message = log_bridge_error(logger, f"home section failed: {section}", exc)
            self._set_section_error(section, message)
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return None
        finally:
            self._set_section_loading(section, False)

    def _handle_auth_state_changed(self) -> None:
        if self._service_controller.authed:
            self._set_daily_requires_login(False)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            if self._daily_refresh_task is None or self._daily_refresh_task.done():
                self._daily_refresh_task = loop.create_task(self.refresh_daily_thirty_async())
            return
        self._set_daily_requires_login(True)
        self._daily_model.clear()
        self.dailyModelChanged.emit()
        if self._home_cache is not None:
            self._home_cache.clear_private()

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
        if bool(self._loading_sections) != old_loading:
            self.loadingChanged.emit()
        self.loadingSectionsChanged.emit()

    def _set_daily_requires_login(self, value: bool) -> None:
        if self._daily_requires_login == value:
            return
        self._daily_requires_login = value
        self.dailyRequiresLoginChanged.emit()

    def _set_section_error(self, section: str, message: str) -> None:
        if self._section_errors.get(section) == message:
            return
        self._section_errors[section] = message
        self.sectionStateChanged.emit()

    def _clear_section_error(self, section: str) -> None:
        if section not in self._section_errors:
            return
        del self._section_errors[section]
        self.sectionStateChanged.emit()

    def _set_error_message(self, value: str) -> None:
        if self._error_message == value:
            return
        self._error_message = value
        self.errorMessageChanged.emit()
