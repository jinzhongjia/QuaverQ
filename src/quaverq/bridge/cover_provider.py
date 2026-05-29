"""Cover image provider and fetch controller for QML."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtQuick import QQuickImageProvider

from quaverq.core.cover_cache import CoverCache

logger = logging.getLogger(__name__)


class CoverImageProvider(QQuickImageProvider):
    """Serve cached cover files through image://covers/<url>|<size>."""

    def __init__(self, cover_cache: CoverCache) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._cover_cache = cover_cache

    def requestImage(  # noqa: N802 - Qt virtual method name
        self,
        image_id: str,
        size: QSize,
        requested_size: QSize,
    ) -> QImage:
        url, size_hint = self._parse_image_id(image_id)
        path = self._cover_cache.get_path(url)
        if path is None:
            return QImage()
        return self._read_image(path, requested_size, size_hint)

    @staticmethod
    def _parse_image_id(image_id: str) -> tuple[str, int]:
        decoded_id = urllib.parse.unquote(image_id)
        parts = decoded_id.split("|", 2)
        url = parts[0] if parts else ""
        size_hint = 0
        if len(parts) > 1:
            try:
                size_hint = max(0, int(parts[1]))
            except ValueError:
                size_hint = 0
        return url, size_hint

    @staticmethod
    def _read_image(path: Path, requested_size: QSize, size_hint: int) -> QImage:
        target_width = requested_size.width() if requested_size.isValid() else 0
        target_height = requested_size.height() if requested_size.isValid() else 0
        target = max(target_width, target_height, size_hint)

        reader = QImageReader(str(path))
        if target > 0:
            source_size = reader.size()
            if source_size.isValid():
                source_size.scale(
                    target,
                    target,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                )
                reader.setScaledSize(source_size)
        image = reader.read()
        return image if not image.isNull() else QImage()


class CoverController(QObject):
    """Fetch cover URLs into the disk cache and notify QML when ready."""

    coverReady = Signal(str)
    coverFailed = Signal(str)

    def __init__(self, cover_cache: CoverCache, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cover_cache = cover_cache
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @Slot(str)
    def fetchCover(self, url: str) -> None:
        normalized_url = (url or "").strip()
        if not normalized_url:
            return
        if self._cover_cache.get_path(normalized_url) is not None:
            self.coverReady.emit(normalized_url)
            return
        task = self._tasks.get(normalized_url)
        if task is not None and not task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._tasks[normalized_url] = loop.create_task(self._fetch(normalized_url))

    @Slot(str, result=bool)
    def isCached(self, url: str) -> bool:
        return self._cover_cache.get_path((url or "").strip()) is not None

    async def _fetch(self, url: str) -> None:
        try:
            path = await self._cover_cache.fetch(url)
            if path is None:
                self.coverFailed.emit(url)
                return
            self.coverReady.emit(url)
        except Exception as exc:
            logger.warning("cover fetch failed (%s): %s", url[:80], exc)
            self.coverFailed.emit(url)
        finally:
            self._tasks.pop(url, None)
