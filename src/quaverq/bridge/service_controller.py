"""Service QObject exposed to QML."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar

from PySide6.QtCore import Property, QObject, Signal, Slot
from qasync import asyncSlot

from quaverq.core.models import Lyric, Song
from quaverq.core.service import (
    CredentialExpiredError,
    QuaverService,
    is_credential_expired_error,
)

from .error_utils import log_bridge_error
from .models import (
    CardListModel,
    SongListModel,
    album_to_card,
    playlist_to_card,
    singer_to_card,
    song_from_map,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

_SEARCH_TYPES = ("songs", "singers", "albums", "playlists")
_CARD_CONVERTERS = {
    "singers": singer_to_card,
    "albums": album_to_card,
    "playlists": playlist_to_card,
}


class ServiceController(QObject):
    """QML-facing wrapper around QuaverService."""

    songResultsChanged = Signal()
    loadingChanged = Signal()
    currentPageChanged = Signal()
    hasNextPageChanged = Signal()
    errorMessageChanged = Signal()
    errorRaised = Signal(str)
    authStateChanged = Signal()
    credentialExpired = Signal(str)
    searchTypeChanged = Signal()

    def __init__(
        self,
        service: QuaverService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service or QuaverService()
        self._song_results = SongListModel(self)
        self._card_results = CardListModel(self)
        self._search_type = "songs"
        self._loading = False
        self._has_next_page = False
        self._search_keyword = ""
        self._current_page = 0
        self._page_size = 30
        self._error_message = ""
        self._started = False
        # 串行化 start(): 乐观登录后 Sidebar 刷新与 _load_initial_state 会并发触发 start,
        # 没锁会双 connect()/probe -> 泄漏第二个 Client (curl_cffi 线程) -> 退出卡死.
        self._start_lock = asyncio.Lock()

    @Property(QObject, notify=songResultsChanged)
    def songResults(self) -> SongListModel:
        return self._song_results

    @Property(QObject, constant=True)
    def cardResults(self) -> CardListModel:
        return self._card_results

    @Property(str, notify=searchTypeChanged)
    def searchType(self) -> str:
        return self._search_type

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(int, notify=currentPageChanged)
    def currentPage(self) -> int:
        return self._current_page

    @Property(bool, notify=hasNextPageChanged)
    def hasNextPage(self) -> bool:
        return self._has_next_page

    @Property(int, constant=True)
    def pageSize(self) -> int:
        return self._page_size

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @Property(bool, notify=authStateChanged)
    def authed(self) -> bool:
        return bool(getattr(self._service, "is_authenticated", False))

    def account_key(self) -> str:
        """当前登录账号的稳定指纹 hash(musicid); 未登录或拿不到返 ''.

        供 HomeCache 隔离账号私有缓存 (猜你喜欢 / 我的歌单), 不外泄原始 musicid.
        """
        if not self.authed:
            return ""
        get_cred = getattr(self._service, "_effective_credential", None)
        cred = get_cred() if callable(get_cred) else None
        musicid = getattr(cred, "musicid", "") if cred is not None else ""
        if not musicid:
            return ""
        return hashlib.sha1(str(musicid).encode("utf-8")).hexdigest()[:16]

    def prime_credential_sync(self) -> bool:
        """启动期同步读盘加载缓存凭据 -> authed 首帧即生效 (本地, 不联网, 不需事件循环).

        只设内存 credential 并广播 authState (乐观登录, 消除首帧登录态抖动); 真正的
        connect() + 网络有效性校验仍由随后的 start() 完成 (幂等). 返回是否加载到凭据.
        """
        read_sync = getattr(self._service, "load_cached_credential_sync", None)
        set_sync = getattr(self._service, "set_credential_sync", None)
        if not (callable(read_sync) and callable(set_sync)):
            return False
        cred = read_sync()
        if cred is None:
            return False
        set_sync(cred)
        self.authStateChanged.emit()
        return True

    async def start(self) -> None:
        if self._started:
            return
        async with self._start_lock:
            if self._started:  # 等锁期间别的调用已完成
                return
            await self._service.connect()
            get_cached = getattr(self._service, "_get_cached_credential", None)
            set_credential = getattr(self._service, "set_credential", None)
            if callable(get_cached) and callable(set_credential):
                cached_credential = await get_cached()
                if cached_credential is not None:
                    await set_credential(cached_credential)
                    probe_result = await self._probe_current_credential()
                    if probe_result is False:
                        await self._expire_credential(
                            "登录已过期，请重新扫码",
                            remove_cache=True,
                            emit_error=False,
                        )
                    else:
                        if probe_result is True:
                            logger.info("loaded verified QQ Music credential")
                        else:
                            logger.info(
                                "loaded cached QQ Music credential (credential probe unavailable)"
                            )
                        self.authStateChanged.emit()
            self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self._service.disconnect()
        self._started = False

    async def _ensure_started(self) -> None:
        if not self._started:
            await self.start()

    async def call_service(
        self,
        operation: Callable[[QuaverService], Awaitable[T]],
        *,
        operation_name: str = "service operation",
    ) -> T:
        await self._ensure_started()
        try:
            return await operation(self._service)
        except Exception as exc:
            if is_credential_expired_error(exc):
                logger.warning("%s detected expired credential", operation_name)
                await self._expire_credential(
                    "登录已过期，请重新扫码",
                    remove_cache=True,
                )
                raise CredentialExpiredError("登录已过期，请重新扫码") from exc
            raise

    @asyncSlot(str)
    async def search(self, keyword: str) -> None:
        await self.search_async(keyword)

    async def search_async(self, keyword: str) -> None:
        kw = (keyword or "").strip()
        self._set_error_message("")
        if not kw:
            self._reset_search_state()
            self._song_results.clear()
            self._card_results.clear()
            return
        if self._search_type == "songs":
            await self._load_search_page(kw, 1)
        else:
            await self._load_card_search(kw)

    @asyncSlot(str)
    async def setSearchType(self, search_type: str) -> None:
        await self.set_search_type_async(search_type)

    async def set_search_type_async(self, search_type: str) -> None:
        value = search_type if search_type in _SEARCH_TYPES else "songs"
        if self._search_type == value:
            return
        self._search_type = value
        self.searchTypeChanged.emit()
        keyword = self._search_keyword
        self._song_results.clear()
        self._card_results.clear()
        if keyword:
            await self.search_async(keyword)
        else:
            self._reset_search_state()

    async def _load_card_search(self, keyword: str) -> None:
        self._set_loading(True)
        self._set_error_message("")
        try:
            to_card = _CARD_CONVERTERS[self._search_type]
            items = await self.call_service(
                lambda service: self._fetch_cards(service, keyword),
                operation_name=f"search {self._search_type} {keyword}",
            )
            self._search_keyword = keyword
            self._card_results.set_cards([to_card(item) for item in items])
            self._set_current_page(1 if items else 0)
            self._set_has_next_page(False)
        except Exception as exc:
            message = log_bridge_error(logger, f"search {self._search_type} failed: {keyword}", exc)
            self._set_error_message(message)
            self.errorRaised.emit(message)
        finally:
            self._set_loading(False)

    def _fetch_cards(self, service: Any, keyword: str) -> Any:
        if self._search_type == "singers":
            return service.search_singers(keyword, limit=self._page_size)
        if self._search_type == "albums":
            return service.search_albums(keyword, limit=self._page_size)
        return service.search_playlists(keyword, limit=self._page_size)

    @asyncSlot()
    async def nextPage(self) -> None:
        await self.next_page_async()

    async def next_page_async(self) -> None:
        if not self._search_keyword or self._loading or not self._has_next_page:
            return
        await self._load_search_page(self._search_keyword, self._current_page + 1)

    @asyncSlot()
    async def previousPage(self) -> None:
        await self.previous_page_async()

    async def previous_page_async(self) -> None:
        if not self._search_keyword or self._loading or self._current_page <= 1:
            return
        await self._load_search_page(self._search_keyword, self._current_page - 1)

    async def _load_search_page(self, keyword: str, page: int) -> None:
        self._set_loading(True)
        self._set_error_message("")
        try:
            songs = await self.call_service(
                lambda service: service.search_songs(
                    keyword,
                    page=page,
                    limit=self._page_size,
                ),
                operation_name=f"search {keyword}",
            )
            if page > 1 and not songs:
                self._set_has_next_page(False)
                return
            self._search_keyword = keyword
            self._song_results.set_songs(songs)
            self._set_current_page(page if songs or page == 1 else 0)
            self._set_has_next_page(len(songs) >= self._page_size)
        except Exception as exc:
            message = log_bridge_error(
                logger,
                f"search failed: {keyword} page {page}",
                exc,
            )
            self._set_error_message(message)
            self.errorRaised.emit(message)
        finally:
            self._set_loading(False)

    @Slot()
    def clear(self) -> None:
        self._set_error_message("")
        self._reset_search_state()
        self._song_results.clear()
        self._card_results.clear()

    async def get_song_url(
        self,
        song: Mapping[str, Any] | Song,
        quality_preference: str,
    ) -> Any:
        await self._ensure_started()
        is_authenticated = getattr(self._service, "is_authenticated", True)
        if is_authenticated is False:
            raise RuntimeError("播放需要先登录 QQ 音乐")
        return await self.call_service(
            lambda service: service.get_song_url(
                song_from_map(song),
                quality_preference=quality_preference or "balanced",
            ),
            operation_name="get song url",
        )

    async def get_lyric(
        self,
        mid: str,
        *,
        with_translation: bool = True,
    ) -> Lyric:
        await self._ensure_started()
        return await self.call_service(
            lambda service: service.get_lyric(
                mid,
                with_translation=with_translation,
            ),
            operation_name="get lyric",
        )

    async def get_user_profile(self) -> Any:
        """登录账号画像 (昵称 / 头像 / VIP 种类); 走 call_service 统一过期处理."""
        return await self.call_service(
            lambda service: service.get_user_profile(),
            operation_name="get user profile",
        )

    async def login_by_qrcode(
        self,
        on_qrcode: Callable[[bytes, str, str], None],
        on_status: Callable[[str], None] | None = None,
        *,
        login_type: str = "qq",
    ) -> bool:
        from qqmusic_api.models.login import QRLoginType

        type_map = {"qq": QRLoginType.QQ, "wx": QRLoginType.WX}
        qr_login_type = type_map.get(login_type, QRLoginType.QQ)

        await self._ensure_started()
        previous_callback = self._service.on_qrcode
        previous_status_callback = getattr(self._service, "on_login_status", None)

        def emit_qrcode(data: bytes, kind: str, mimetype: str = "image/png") -> None:
            on_qrcode(data, kind, mimetype)

        self._service.on_qrcode = emit_qrcode
        self._service.on_login_status = on_status
        try:
            success = await self._service.login_by_qrcode(qr_login_type)
            if success:
                await self._service.save_credential()
                self.authStateChanged.emit()
            return success
        finally:
            self._service.on_qrcode = previous_callback
            self._service.on_login_status = previous_status_callback

    async def logout_async(self) -> None:
        await self._ensure_started()
        set_credential = getattr(self._service, "set_credential", None)
        if callable(set_credential):
            await set_credential(None)
            logger.info("cleared QQ Music credential from memory")
        credential_path = getattr(self._service, "_credential_cache_path", "")
        if credential_path and os.path.exists(credential_path):
            os.remove(credential_path)
            logger.info("removed cached QQ Music credential: %s", credential_path)
        else:
            logger.info("no cached QQ Music credential to remove")
        self.authStateChanged.emit()

    async def _probe_current_credential(self) -> bool | None:
        probe = getattr(self._service, "probe_login_expired", None)
        if not callable(probe):
            return bool(self.authed)
        expired = await probe()
        if expired is None:
            return None
        return not bool(expired)

    async def _expire_credential(
        self,
        message: str,
        *,
        remove_cache: bool,
        emit_error: bool = True,
    ) -> None:
        logger.warning("QQ Music credential expired: %s", message)
        await self._clear_credential(remove_cache=remove_cache)
        if emit_error:
            self.errorRaised.emit(message)
        self.credentialExpired.emit(message)
        self.authStateChanged.emit()

    async def _clear_credential(self, *, remove_cache: bool) -> None:
        set_credential = getattr(self._service, "set_credential", None)
        if callable(set_credential):
            await set_credential(None)
            logger.info("cleared QQ Music credential from memory")
        else:
            with contextlib.suppress(Exception):
                self._service.is_authenticated = False

        if not remove_cache:
            return

        credential_path = getattr(self._service, "_credential_cache_path", "")
        if credential_path and os.path.exists(credential_path):
            os.remove(credential_path)
            logger.info("removed cached QQ Music credential: %s", credential_path)

    def _set_loading(self, value: bool) -> None:
        if self._loading == value:
            return
        self._loading = value
        self.loadingChanged.emit()

    def _set_current_page(self, value: int) -> None:
        if self._current_page == value:
            return
        self._current_page = value
        self.currentPageChanged.emit()

    def _set_has_next_page(self, value: bool) -> None:
        if self._has_next_page == value:
            return
        self._has_next_page = value
        self.hasNextPageChanged.emit()

    def _reset_search_state(self) -> None:
        self._search_keyword = ""
        self._set_current_page(0)
        self._set_has_next_page(False)

    def _set_error_message(self, value: str) -> None:
        if self._error_message == value:
            return
        self._error_message = value
        self.errorMessageChanged.emit()
