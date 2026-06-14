"""Bridge LyricController state to org.quaverq.Lyrics1 D-Bus 服务.

类比 MprisController:
- 注入 fake service (test) / 真 LyricsService (runtime)
- 订阅 LyricController.lyricChanged + PlayerController.positionMsChanged
- 推送状态: push_lyric / push_position / push_active

active word 计算放在这里, 因为它依赖 player 实时 position + lyric_controller 当前行,
而 LyricController 没有 word 级别的状态.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QObject

from quaverq.core.lyric_dbus import LyricsService, compute_active_word
from quaverq.core.models import Lyric

from .lyric_controller import LyricController
from .player_controller import PlayerController

logger = logging.getLogger(__name__)


class LyricsServiceLike(Protocol):
    async def start(self) -> bool: ...
    async def stop(self) -> None: ...
    def push_lyric(self, lyric: Lyric | None, *, include_translation: bool = True) -> None: ...
    def push_position(self, position_ms: int) -> None: ...
    def push_active(self, line_index: int, word_index: int) -> None: ...


LyricsServiceFactory = Callable[[], LyricsServiceLike]


class LyricsDBusController(QObject):
    """Synchronize LyricController + PlayerController with org.quaverq.Lyrics1."""

    def __init__(
        self,
        *,
        lyric_controller: LyricController,
        player_controller: PlayerController,
        settings_controller: object | None = None,
        service_factory: LyricsServiceFactory = LyricsService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._lyric_controller = lyric_controller
        self._player_controller = player_controller
        self._settings_controller = settings_controller
        self._service = service_factory()
        self._started = False
        # 上次 push 的 (line, word); 用来去重避免 PositionMs tick 内 word 未变也刷.
        self._last_active: tuple[int, int] = (-2, -2)

        self._lyric_controller.lyricChanged.connect(self._push_lyric)
        self._player_controller.positionMsChanged.connect(self._on_position_changed)

    async def start_async(self) -> bool:
        self._started = await self._service.start()
        if self._started:
            self._sync_all()
        return self._started

    async def stop_async(self) -> None:
        await self._service.stop()
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def _sync_all(self) -> None:
        self._push_lyric()
        self._push_position()
        self._push_active()

    def _push_lyric(self) -> None:
        if not self._started:
            return
        lyric = self._lyric_controller.current_lyric
        include_translation = bool(getattr(self._lyric_controller, "translationVisible", True))
        self._service.push_lyric(
            lyric if lyric.lines else None,
            include_translation=include_translation,
        )
        # 切歌时把去重 cache 重置 → 下一次 active 一定会推
        self._last_active = (-2, -2)
        self._push_active()

    def _on_position_changed(self) -> None:
        if not self._started:
            return
        self._push_position()
        self._push_active()

    def _push_position(self) -> None:
        if self._started:
            self._service.push_position(self._player_controller.positionMs)

    def _push_active(self) -> None:
        line_index = self._lyric_controller.activeIndex
        word_index = self._compute_word(line_index)
        active = (line_index, word_index)
        if active == self._last_active:
            return
        self._last_active = active
        self._service.push_active(line_index, word_index)

    def _compute_word(self, line_index: int) -> int:
        lyric = self._lyric_controller.current_lyric
        if line_index < 0 or line_index >= len(lyric.lines):
            return -1
        return compute_active_word(lyric.lines[line_index], self._player_controller.positionMs)
