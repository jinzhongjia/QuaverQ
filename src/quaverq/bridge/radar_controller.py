"""Radar (雷达推荐) QObject exposed to QML.

个性化推荐歌曲流: 单例 controller, 持有分页游标 + 去重集. 不缓存 (推荐流实时变),
不进 SWR 首帧链路. 队列耗尽且 source=="radar" 时自动续接下一页. 设计见
docs/plan/search-radar-recommend.md.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal
from qasync import asyncSlot

from quaverq.core.models import Song

from .error_utils import log_bridge_error
from .models import SongListModel
from .service_controller import ServiceController

if TYPE_CHECKING:
    from .player_controller import PlayerController

logger = logging.getLogger(__name__)


class RadarController(QObject):
    """QML-facing 雷达推荐 state (登录门槛 + 分页流 + 队列续接)."""

    radarModelChanged = Signal()
    loadingChanged = Signal()
    hasMoreChanged = Signal()
    requiresLoginChanged = Signal()
    errorRaised = Signal(str)

    RADAR_SOURCE = "radar"

    def __init__(
        self,
        service_controller: ServiceController,
        player_controller: PlayerController | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._player_controller = player_controller
        self._radar_model = SongListModel(self)
        self._page = 0
        self._has_more = False
        self._loading = False
        self._requires_login = False
        self._seen: set[str] = set()
        self._refresh_task: asyncio.Task[None] | None = None
        self._extend_task: asyncio.Task[list[Song]] | None = None
        self._service_controller.authStateChanged.connect(self._handle_auth_state_changed)
        if self._player_controller is not None:
            self._player_controller.queueExhausted.connect(self._handle_queue_exhausted)

    # ------------------------------------------------------------------ 属性
    @Property(QObject, notify=radarModelChanged)
    def radarModel(self) -> SongListModel:
        return self._radar_model

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(bool, notify=hasMoreChanged)
    def hasMore(self) -> bool:
        return self._has_more

    @Property(bool, notify=requiresLoginChanged)
    def radarRequiresLogin(self) -> bool:
        return self._requires_login

    # ------------------------------------------------------------------ QML 槽
    @asyncSlot()
    async def refresh(self) -> None:
        await self.refresh_async()

    @asyncSlot()
    async def loadNextPage(self) -> None:
        await self.load_next_page_async()

    # ------------------------------------------------------------------ 拉取
    async def refresh_async(self) -> None:
        """重置推荐流并拉首页. 未登录则只立门槛, 不打网络."""
        if not self._service_controller.authed:
            self._set_requires_login(True)
            self._reset_stream()
            return
        # set_loading 在首个 await 前同步置位, 单线程事件循环下并发 refresh 自然合并
        if self._loading:
            return

        self._set_requires_login(False)
        self._set_loading(True)
        try:
            songs, has_more = await self._service_controller.call_service(
                lambda service: service.get_radar_recommend(page=1),
                operation_name="radar recommend",
            )
            self._page = 1
            self._seen = {s.mid for s in songs if s.mid}
            self._set_has_more(has_more)
            self._radar_model.set_songs(songs)
            self.radarModelChanged.emit()
        except Exception as exc:
            message = log_bridge_error(logger, "radar refresh failed", exc)
            self.errorRaised.emit(message)
        finally:
            self._set_loading(False)

    async def load_next_page_async(self) -> list[Song]:
        """拉下一页追加到 radarModel; 返回去重后新增歌曲 (供续接复用)."""
        if self._loading or not self._has_more or not self._service_controller.authed:
            return []
        next_page = self._page + 1
        self._set_loading(True)
        try:
            songs, has_more = await self._service_controller.call_service(
                lambda service: service.get_radar_recommend(page=next_page),
                operation_name="radar recommend (next page)",
            )
        except Exception as exc:
            message = log_bridge_error(logger, "radar next page failed", exc)
            self.errorRaised.emit(message)
            return []
        finally:
            self._set_loading(False)

        self._page = next_page
        self._set_has_more(has_more)
        fresh = [s for s in songs if s.mid and s.mid not in self._seen]
        for s in fresh:
            self._seen.add(s.mid)
        if fresh:
            self._radar_model.append_songs(fresh)
            self.radarModelChanged.emit()
        return fresh

    # ------------------------------------------------------------------ 联动
    def _handle_auth_state_changed(self) -> None:
        if self._service_controller.authed:
            self._set_requires_login(False)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            if self._refresh_task is None or self._refresh_task.done():
                self._refresh_task = loop.create_task(self.refresh_async())
            return
        self._set_requires_login(True)
        self._reset_stream()

    def _handle_queue_exhausted(self, source: str) -> None:
        """队列自然耗尽: 仅当来源是雷达且还有下一页时续接."""
        if source != self.RADAR_SOURCE:
            return
        if not self._service_controller.authed or not self._has_more:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._extend_task is not None and not self._extend_task.done():
            return
        self._extend_task = loop.create_task(self._extend_async())

    async def _extend_async(self) -> list[Song]:
        """续取下一页, 去重后追加到 player 队列 (model 由 load_next_page_async 负责)."""
        if self._player_controller is None:
            return []
        fresh = await self.load_next_page_async()
        if not fresh:
            return []
        return self._player_controller.append_to_queue(fresh)

    # ------------------------------------------------------------------ setters
    def _reset_stream(self) -> None:
        self._page = 0
        self._seen = set()
        self._radar_model.clear()
        self.radarModelChanged.emit()
        self._set_has_more(False)

    def _set_loading(self, value: bool) -> None:
        if self._loading == value:
            return
        self._loading = value
        self.loadingChanged.emit()

    def _set_has_more(self, value: bool) -> None:
        if self._has_more == value:
            return
        self._has_more = value
        self.hasMoreChanged.emit()

    def _set_requires_login(self, value: bool) -> None:
        if self._requires_login == value:
            return
        self._requires_login = value
        self.requiresLoginChanged.emit()
