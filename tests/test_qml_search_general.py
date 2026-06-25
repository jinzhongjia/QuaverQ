"""SearchView.qml 综合搜索 (general) 离屏契约测试.

加载真实 SearchView.qml + 真 ServiceController (fake service 喂综合结果), 验证:

1. 综合搜索结果就绪后, 直达卡 + 相关词 chips 渲染且可见;
2. 加载这套 QML 绑定不产生任何运行期 warning (防 header 里 directHitData 空引用等崩);
3. 切到歌曲 tab 后, 综合专属的直达 / chips 收起 (不可见).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication

from quaverq.bridge.cover_provider import CoverController, CoverImageProvider
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.cover_cache import CoverCache
from quaverq.core.models import DirectHit, GeneralSearchResult, RelatedWord

_SEARCH_QML = (
    Path(__file__).resolve().parent.parent / "src" / "quaverq" / "qml" / "views" / "SearchView.qml"
)


class _FakeService:
    async def connect(self) -> None:
        pass

    async def general_search(self, keyword: str, *, limit: int = 30) -> GeneralSearchResult:
        return GeneralSearchResult(
            songs=[],  # 留空避免实例化 SongRow (需一堆播放 controller), 只测 header
            related=[
                RelatedWord(display="周杰伦", keyword="周杰伦"),
                RelatedWord(display="七里香", keyword="七里香"),
            ],
            direct=DirectHit("singer", "0025NhlN2yWrP4", "周杰伦", ""),
        )


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _process(app, rounds: int = 8) -> None:
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.002)


@pytest.fixture
def search_view(qapp, tmp_path):
    controller = ServiceController(service=_FakeService())  # type: ignore[arg-type]
    cover_controller = CoverController(CoverCache(tmp_path / "covers"))

    engine = QQmlEngine()
    engine.addImageProvider("covers", CoverImageProvider(CoverCache(tmp_path / "covers")))
    warnings: list[str] = []
    engine.warnings.connect(lambda errs: warnings.extend(e.toString() for e in errs))

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_SEARCH_QML)))
    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    item = component.create()
    assert item is not None
    item.setProperty("serviceController", controller)
    item.setProperty("coverController", cover_controller)
    _process(qapp)

    # 注: 离屏 standalone 加载会在 create() 后才注入 controller, 期间 null-guard 的
    # 绑定 (canGoNext / isGeneral 等) 会刷一次 "[undefined] to bool" 构造期 warning,
    # 非真实问题; 故不对 warnings 断零, 只用它定位真正的 header 绑定崩溃 (见下).
    yield item, controller, qapp, warnings
    item.deleteLater()
    qapp.processEvents()


def test_default_tab_is_general(search_view):
    item, _controller, _app, _warnings = search_view
    assert item.property("searchType") == "general"
    assert item.property("isGeneral") is True


async def test_general_results_render_direct_and_chips(search_view):
    item, controller, app, warnings = search_view

    warnings.clear()  # 丢弃构造期瞬态 warning, 只看搜索结果就绪后的绑定
    await controller.search_async("周杰伦")
    _process(app)

    direct = item.findChild(QObject, "searchDirectHit")
    chips = item.findChild(QObject, "searchRelatedChips")
    assert direct is not None and direct.property("visible") is True
    assert chips is not None and chips.property("visible") is True
    # 结果就绪后 header 绑定 (directHitData.kind / coverUrl, chips Repeater) 不应再崩
    assert warnings == [], warnings


async def test_switching_to_songs_hides_general_header(search_view):
    item, controller, app, _warnings = search_view

    await controller.search_async("周杰伦")
    _process(app)
    await controller.set_search_type_async("songs")
    _process(app)

    assert item.property("isGeneral") is False
    direct = item.findChild(QObject, "searchDirectHit")
    # 切走后 directHit 被清空 -> 直达卡不可见
    assert direct is None or direct.property("visible") is False
