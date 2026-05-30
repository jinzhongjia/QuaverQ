"""Service QObject exposed to QML."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any, Awaitable, Callable, TypeVar

from PySide6.QtCore import QObject, Property, Signal, Slot
from qasync import asyncSlot

from quaverq.core.models import Lyric, Song
from quaverq.core.service import (
    CredentialExpiredError,
    is_credential_expired_error,
    QuaverService,
)

from .error_utils import log_bridge_error
from .models import SongListModel, song_from_map

logger = logging.getLogger(__name__)

T = TypeVar("T")


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

    def __init__(
        self,
        service: QuaverService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service or QuaverService()
        self._song_results = SongListModel(self)
        self._loading = False
        self._has_next_page = False
        self._search_keyword = ""
        self._current_page = 0
        self._page_size = 30
        self._error_message = ""
        self._started = False

    @Property(QObject, notify=songResultsChanged)
    def songResults(self) -> SongListModel:
        return self._song_results

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

    async def start(self) -> None:
        if self._started:
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
                            "loaded cached QQ Music credential "
                            "(credential probe unavailable)"
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
            return

        await self._load_search_page(kw, 1)

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

    async def login_by_qrcode(
        self,
        on_qrcode: Callable[[bytes, str, str], None],
        on_status: Callable[[str], None] | None = None,
    ) -> bool:
        await self._ensure_started()
        previous_callback = self._service.on_qrcode
        previous_status_callback = getattr(self._service, "on_login_status", None)

        def emit_qrcode(data: bytes, kind: str, mimetype: str = "image/png") -> None:
            on_qrcode(data, kind, mimetype)

        self._service.on_qrcode = emit_qrcode
        self._service.on_login_status = on_status
        try:
            success = await self._service.login_by_qrcode()
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
            return True if self.authed else False
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
            try:
                setattr(self._service, "is_authenticated", False)
            except Exception:
                pass

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
