"""Cover image provider and fetch controller for QML."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal, Slot
from PySide6.QtGui import QImage, QImageReader, QPainter, QPainterPath
from PySide6.QtQuick import QQuickImageProvider

from quaverq.core.cover_cache import CoverCache

logger = logging.getLogger(__name__)

# 封面下载并发上限: 配合 CoverCache 的 keep-alive session, 复用 ~N 条到 CDN 的长连接,
# 避免一屏几十张封面瞬间开几十个线程/连接被 CDN 限流.
_MAX_CONCURRENT_DOWNLOADS = 6


class CoverImageProvider(QQuickImageProvider):
    """Serve cached cover files through image://covers/<url>|<size>|<radius>."""

    def __init__(self, cover_cache: CoverCache) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._cover_cache = cover_cache

    def requestImage(  # noqa: N802 - Qt virtual method name
        self,
        image_id: str,
        size: QSize,
        requested_size: QSize,
    ) -> QImage:
        url, size_hint, radius_hint = self._parse_image_id(image_id)
        path = self._cover_cache.get_path(url)
        if path is None:
            return QImage()
        image = self._read_image(path, requested_size, size_hint)
        return self._rounded_image(image, radius_hint)

    @staticmethod
    def _parse_image_id(image_id: str) -> tuple[str, int, int]:
        decoded_id = urllib.parse.unquote(image_id)
        parts = decoded_id.rsplit("|", 3)
        if len(parts) == 4:
            size_hint = CoverImageProvider._parse_optional_non_negative_int(parts[1])
            radius_hint = CoverImageProvider._parse_optional_non_negative_int(parts[2])
            if size_hint is not None and radius_hint is not None:
                return parts[0], size_hint, radius_hint

        parts = decoded_id.rsplit("|", 2)
        if len(parts) == 3:
            size_hint = CoverImageProvider._parse_optional_non_negative_int(parts[1])
            if size_hint is not None:
                return parts[0], size_hint, 0

        parts = decoded_id.rsplit("|", 1)
        if len(parts) == 2:
            size_hint = CoverImageProvider._parse_optional_non_negative_int(parts[1])
            if size_hint is not None:
                return parts[0], size_hint, 0

        return decoded_id, 0, 0

    @staticmethod
    def _parse_optional_non_negative_int(value: str) -> int | None:
        try:
            return max(0, int(value))
        except ValueError:
            return None

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
        if image.isNull():
            return QImage()
        if target <= 0:
            return image
        return CoverImageProvider._center_crop(image, target)

    @staticmethod
    def _center_crop(image: QImage, target: int) -> QImage:
        width = image.width()
        height = image.height()
        crop_width = min(width, target)
        crop_height = min(height, target)
        left = max(0, (width - crop_width) // 2)
        top = max(0, (height - crop_height) // 2)
        return image.copy(left, top, crop_width, crop_height)

    @staticmethod
    def _rounded_image(image: QImage, radius: int) -> QImage:
        if image.isNull() or radius <= 0:
            return image

        bounded_radius = min(radius, image.width() // 2, image.height() // 2)
        if bounded_radius <= 0:
            return image

        rounded = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
        rounded.fill(Qt.GlobalColor.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, image.width(), image.height()),
            bounded_radius,
            bounded_radius,
        )
        painter.setClipPath(path)
        painter.drawImage(0, 0, image)
        painter.end()
        return rounded


class CoverController(QObject):
    """Fetch cover URLs into the disk cache and notify QML when ready."""

    coverReady = Signal(str)
    coverFailed = Signal(str)

    def __init__(self, cover_cache: CoverCache, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cover_cache = cover_cache
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._download_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DOWNLOADS)

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
            async with self._download_semaphore:
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
