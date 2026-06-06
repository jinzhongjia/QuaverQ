"""Cover image provider tests."""

from __future__ import annotations

import urllib.parse

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

import asyncio

from quaverq.bridge.cover_provider import (
    _MAX_CONCURRENT_DOWNLOADS,
    CoverController,
    CoverImageProvider,
)
from quaverq.core.cover_cache import CoverCache


def _write_cached_cover(cache: CoverCache, url: str) -> None:
    cache.dir.mkdir(parents=True, exist_ok=True)
    image = QImage(24, 24, QImage.Format.Format_RGB32)
    image.fill(QColor("#15803d"))
    assert image.save(str(cache.dir / cache._filename_for(url)))


def test_cover_provider_returns_cached_image(tmp_path):
    url = "https://example.test/cover.jpg?size=300"
    cache = CoverCache(tmp_path / "covers")
    _write_cached_cover(cache, url)
    provider = CoverImageProvider(cache)

    image = provider.requestImage(
        f"{urllib.parse.quote(url, safe='')}|32|1",
        QSize(),
        QSize(32, 32),
    )

    assert not image.isNull()
    assert image.width() == 32
    assert image.height() == 32


def test_cover_provider_accepts_qml_escaped_separator(tmp_path):
    url = "https://example.test/cover.jpg?size=300|quality=high"
    cache = CoverCache(tmp_path / "covers")
    _write_cached_cover(cache, url)
    provider = CoverImageProvider(cache)

    image = provider.requestImage(
        urllib.parse.quote(f"{url}|32|1", safe=""),
        QSize(),
        QSize(32, 32),
    )

    assert not image.isNull()


def test_cover_provider_applies_rounded_alpha_mask(tmp_path):
    url = "https://example.test/cover.jpg?size=300|quality=high"
    cache = CoverCache(tmp_path / "covers")
    _write_cached_cover(cache, url)
    provider = CoverImageProvider(cache)

    image = provider.requestImage(
        urllib.parse.quote(f"{url}|32|6|1", safe=""),
        QSize(),
        QSize(32, 32),
    )

    assert not image.isNull()
    assert image.width() == 32
    assert image.height() == 32
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(16, 16).alpha() == 255


def test_cover_provider_returns_null_when_uncached(tmp_path):
    provider = CoverImageProvider(CoverCache(tmp_path / "covers"))

    image = provider.requestImage(
        f"{urllib.parse.quote('https://example.test/missing.jpg', safe='')}|32|1",
        QSize(),
        QSize(32, 32),
    )

    assert image.isNull()


def test_cover_controller_emits_ready_for_cached_url(tmp_path):
    url = "https://example.test/cover.jpg"
    cache = CoverCache(tmp_path / "covers")
    _write_cached_cover(cache, url)
    controller = CoverController(cache)
    ready: list[str] = []
    controller.coverReady.connect(ready.append)

    assert controller.isCached(url) is True
    controller.fetchCover(url)

    assert ready == [url]


async def test_fetch_cover_caps_concurrent_downloads():
    """并发下载不超过上限 (配合 keep-alive 复用少量连接, 防 CDN 限流)."""
    state = {"in_flight": 0, "peak": 0}
    release = asyncio.Event()

    class _SlowCache:
        def get_path(self, url):
            return None  # 强制走下载路径

        async def fetch(self, url):
            state["in_flight"] += 1
            state["peak"] = max(state["peak"], state["in_flight"])
            await release.wait()
            state["in_flight"] -= 1
            return None

    controller = CoverController(_SlowCache())  # type: ignore[arg-type]
    for i in range(_MAX_CONCURRENT_DOWNLOADS + 4):
        controller.fetchCover(f"https://x/{i}.jpg")

    await asyncio.sleep(0.05)  # 让任务跑到信号量边界
    assert state["peak"] == _MAX_CONCURRENT_DOWNLOADS

    release.set()
    await asyncio.gather(*list(controller._tasks.values()), return_exceptions=True)
