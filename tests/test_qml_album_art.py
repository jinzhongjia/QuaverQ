"""AlbumArt.qml 行为契约: 拖动窗口边框改变封面尺寸时不闪烁.

加载真实 AlbumArt.qml (offscreen + 真实 CoverImageProvider), 验证:

1. ``imageSize`` 量化到 64px 桶 —— 桶内 resize 不换 provider id (零重载, 只拉伸纹理);
2. 圆角按 ``bakeScale`` (纹理/显示拉伸比) 放大烘焙 —— 固定小封面 (列表行 36px)
   不因纹理量化放大而视觉圆角变小;
3. 同一封面仅切换分辨率桶时换层瞬切 (``animateSwap`` False, 消除交叉淡入的
   合成透明度凹陷闪烁), 真换封面仍保留交叉淡入 (True);
4. 桶内 resize 停止后防抖刷新 ``bakeScale`` —— 拖动中圆角快照过期可接受,
   但静止后必须收敛到当前显示边长对应的精确圆角, 不能永久停在拖动前的值.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication

from quaverq.bridge.cover_provider import CoverController, CoverImageProvider
from quaverq.core.cover_cache import CoverCache

_ALBUM_ART_QML = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "quaverq"
    / "qml"
    / "components"
    / "AlbumArt.qml"
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _wait_until(app, predicate, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def _write_cached_cover(cache: CoverCache, url: str, color: str = "#15803d") -> None:
    cache.dir.mkdir(parents=True, exist_ok=True)
    image = QImage(24, 24, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(cache.dir / cache._filename_for(url)))


@pytest.fixture
def album_art(qapp, tmp_path):
    cache = CoverCache(tmp_path / "covers")
    engine = QQmlEngine()
    engine.addImageProvider("covers", CoverImageProvider(cache))
    controller = CoverController(cache)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_ALBUM_ART_QML)))
    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    item = component.create()
    assert item is not None
    item.setProperty("coverController", controller)
    yield SimpleNamespace(app=qapp, item=item, cache=cache, engine=engine, controller=controller)
    item.deleteLater()
    qapp.processEvents()


def _settled(item) -> bool:
    """双缓冲换层完成: 前层就是当前目标, 后台层空."""
    return (
        item.property("frontSource") == item.property("displaySource")
        and item.property("backSource") == ""
        and bool(item.property("hasImage"))
    )


def test_image_size_quantized_within_bucket_keeps_provider_id(album_art):
    url = "https://example.test/cover-a.jpg"
    _write_cached_cover(album_art.cache, url)
    item = album_art.item
    item.setWidth(161)
    item.setHeight(161)
    item.setProperty("coverUrl", url)
    assert _wait_until(album_art.app, lambda: _settled(item))

    assert item.property("imageSize") == 192
    source_at_161 = item.property("imageSource")
    assert "|192|" in source_at_161

    # 桶内逐像素 resize: provider id 不变 → 不触发任何重载
    for edge in (165, 172, 180, 192):
        item.setWidth(edge)
        item.setHeight(edge)
        assert item.property("imageSource") == source_at_161

    # 跨桶才换 id, 重载一次
    item.setWidth(193)
    item.setHeight(193)
    assert item.property("imageSize") == 256
    assert item.property("imageSource") != source_at_161
    assert _wait_until(album_art.app, lambda: _settled(item))


def test_baked_radius_compensates_bucket_upscale(album_art):
    url = "https://example.test/cover-compact.jpg"
    _write_cached_cover(album_art.cache, url)
    item = album_art.item
    item.setProperty("compact", True)
    item.setWidth(36)
    item.setHeight(36)
    # coverUrl 设置 → revision 变化 (反正要重载) 时刷新 bakeScale 快照
    item.setProperty("coverUrl", url)

    # 显示 36px 落进 64px 桶, 拉伸比 64/36; radiusSm=4 烘成 7,
    # 显示端缩回 36px 后视觉圆角仍 ≈4px (不补偿会缩成 2.25px)
    assert item.property("imageSize") == 64
    assert item.property("bakedRadius") == 7
    assert _wait_until(album_art.app, lambda: _settled(item))


def test_same_cover_resolution_swap_is_instant(album_art):
    url = "https://example.test/cover-a.jpg"
    _write_cached_cover(album_art.cache, url)
    item = album_art.item
    item.setWidth(100)
    item.setHeight(100)
    item.setProperty("coverUrl", url)

    assert _wait_until(album_art.app, lambda: _settled(item))
    # 首图出现仍是淡入
    assert item.property("animateSwap") is True

    # 同封面跨桶 (128 → 256): 新分辨率就绪后瞬切, 不交叉淡入
    item.setWidth(200)
    item.setHeight(200)
    assert item.property("imageSize") == 256
    assert _wait_until(album_art.app, lambda: _settled(item))
    assert item.property("animateSwap") is False


def test_bake_scale_refreshes_after_within_bucket_resize_settles(album_art):
    """桶内拖动 settle 后防抖刷新 bakeScale: 圆角不永久停留在拖动前的过期快照."""
    url = "https://example.test/cover-a.jpg"
    _write_cached_cover(album_art.cache, url)
    item = album_art.item
    item.setWidth(130)
    item.setHeight(130)
    item.setProperty("coverUrl", url)
    assert _wait_until(album_art.app, lambda: _settled(item))
    assert item.property("imageSize") == 192
    # 快照在 130px 打: coverRadius 6 烘成 round(6 * 192/130) = 9
    assert item.property("bakedRadius") == 9

    # 桶内拖大到 190: imageSize 不变 (拖动中零重载), 圆角暂时仍是过期快照
    for edge in (140, 155, 170, 190):
        item.setWidth(edge)
        item.setHeight(edge)
    assert item.property("imageSize") == 192
    assert item.property("bakedRadius") == 9

    # 停止拖动后防抖刷新: bakeScale 收敛到 192/190, 烘焙圆角回到 round(6*1.01) = 6;
    # 同图换层瞬切 (不交叉淡入), 静止后视觉圆角重新精确
    assert _wait_until(album_art.app, lambda: item.property("bakedRadius") == 6)
    assert _wait_until(album_art.app, lambda: _settled(item))
    assert item.property("animateSwap") is False


def test_cover_change_swap_still_animates(album_art):
    url_a = "https://example.test/cover-a.jpg"
    url_b = "https://example.test/cover-b.jpg"
    _write_cached_cover(album_art.cache, url_a)
    _write_cached_cover(album_art.cache, url_b, color="#1d4ed8")
    item = album_art.item
    item.setWidth(100)
    item.setHeight(100)
    item.setProperty("coverUrl", url_a)
    assert _wait_until(album_art.app, lambda: _settled(item))

    # 同尺寸先做一次同图换层把 animateSwap 打到 False, 再换封面验证恢复淡入
    item.setWidth(200)
    item.setHeight(200)
    assert _wait_until(album_art.app, lambda: _settled(item))
    assert item.property("animateSwap") is False

    item.setProperty("coverUrl", url_b)
    assert _wait_until(album_art.app, lambda: _settled(item))
    assert item.property("animateSwap") is True
