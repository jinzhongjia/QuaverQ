"""KaraokeLine.qml 行为契约: 逐字渐进高亮 (wipe), 替代整字瞬时变色.

加载真实 KaraokeLine.qml (offscreen), 验证:

1. 贪心分行: 词为原子不拆, 可用宽度收窄时折行, 顺序 / 时间字段保持;
2. fraction 推进: positionMs 在词前 = 0, 词中 = elapsed/duration 线性, 词后 = 1
   (与桌面歌词 ``DesktopLyricsWindow._word_fractions`` 同构);
3. wipe 宽度是渐进动画 (Behavior 追赶), 不是瞬跳 —— 本特性的核心契约;
4. ``wipeDurationMs=0`` (reduceMotion) 时瞬时到位;
5. ``durationMs=0`` 词除零保护: pos >= start 即满格.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication

_KARAOKE_LINE_QML = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "quaverq"
    / "qml"
    / "components"
    / "KaraokeLine.qml"
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


@pytest.fixture
def karaoke_line(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_KARAOKE_LINE_QML)))
    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    item = component.create()
    assert item is not None
    item.setProperty("fontPixelSize", 22)
    yield SimpleNamespace(app=qapp, item=item, engine=engine)
    item.deleteLater()
    qapp.processEvents()


def _word(text: str, start_ms: int, duration_ms: int) -> dict:
    return {"text": text, "startMs": start_ms, "durationMs": duration_ms}


def _line_groups(item) -> list[list[dict]]:
    groups = item.property("lineGroups")
    if hasattr(groups, "toVariant"):
        groups = groups.toVariant()
    return [[dict(w) for w in line] for line in groups]


def _find_item(root: QQuickItem, object_name: str) -> QQuickItem | None:
    """Repeater delegate 只挂 visual tree (childItems), QObject findChild 找不到."""
    for child in root.childItems():
        if child.objectName() == object_name:
            return child
        found = _find_item(child, object_name)
        if found is not None:
            return found
    return None


def _word_item(item, index: int) -> QQuickItem:
    child = _find_item(item, f"karaokeWord-{index}")
    assert child is not None, f"karaokeWord-{index} not found"
    return child


def test_line_groups_keep_words_atomic_and_wrap(karaoke_line):
    item = karaoke_line.item
    words = [_word("我们", 0, 500), _word("一起", 500, 500), _word("唱歌", 1000, 500)]
    item.setProperty("width", 600)
    item.setProperty("words", words)

    single = _line_groups(item)
    assert len(single) == 1
    assert [w["text"] for w in single[0]] == ["我们", "一起", "唱歌"]
    # 时间字段透传 (wipe fraction 依赖)
    assert single[0][1]["startMs"] == 500
    assert single[0][1]["durationMs"] == 500
    widths = [w["w"] for w in single[0]]
    assert all(w > 0 for w in widths)

    # 收窄到恰好放下前两词: 第三词折到下一行, 词不拆
    item.setProperty("width", widths[0] + widths[1])
    wrapped = _line_groups(item)
    assert len(wrapped) == 2
    assert [w["text"] for w in wrapped[0]] == ["我们", "一起"]
    assert [w["text"] for w in wrapped[1]] == ["唱歌"]


def test_fraction_zero_before_start_full_after_end(karaoke_line):
    item = karaoke_line.item
    item.setProperty("width", 600)
    item.setProperty("wipeDurationMs", 0)
    item.setProperty("words", [_word("第一", 1000, 500), _word("第二", 1500, 500)])

    item.setProperty("positionMs", 0)
    assert _wait_until(karaoke_line.app, lambda: _word_item(item, 0).property("wipeWidth") == 0)
    assert _word_item(item, 0).property("sungFraction") == 0
    assert _word_item(item, 1).property("sungFraction") == 0

    item.setProperty("positionMs", 5000)
    word0 = _word_item(item, 0)
    assert _wait_until(
        karaoke_line.app,
        lambda: word0.property("wipeWidth") == word0.property("width"),
    )
    assert word0.property("sungFraction") == 1
    assert _word_item(item, 1).property("sungFraction") == 1


def test_fraction_is_linear_within_word(karaoke_line):
    item = karaoke_line.item
    item.setProperty("width", 600)
    item.setProperty("words", [_word("绿洲", 1000, 800)])

    item.setProperty("positionMs", 1200)
    assert _word_item(item, 0).property("sungFraction") == pytest.approx(0.25)
    item.setProperty("positionMs", 1600)
    assert _word_item(item, 0).property("sungFraction") == pytest.approx(0.75)


def test_wipe_width_animates_instead_of_jumping(karaoke_line):
    """positionMs 跳变后 wipe 宽度从旧值渐进收敛到目标, 不瞬跳."""
    item = karaoke_line.item
    item.setProperty("width", 600)
    item.setProperty("wipeDurationMs", 250)
    item.setProperty("words", [_word("光年之外", 0, 1000)])
    karaoke_line.app.processEvents()

    word0 = _word_item(item, 0)
    full_w = word0.property("width")
    assert full_w > 0
    assert word0.property("wipeWidth") == 0

    item.setProperty("positionMs", 500)
    target = full_w * 0.5
    # Behavior 拦截赋值: 目标已更新, 但当前值仍接近 0 (动画刚起步)
    assert word0.property("wipeWidth") < target * 0.5
    # 动画期间能观察到中间值 (0 < w < target), 证明是渐进 wipe
    assert _wait_until(
        karaoke_line.app,
        lambda: 0 < word0.property("wipeWidth") < target,
        timeout_s=2.0,
    )
    # 最终收敛到 fraction 对应宽度
    assert _wait_until(
        karaoke_line.app,
        lambda: abs(word0.property("wipeWidth") - target) < 1.0,
        timeout_s=2.0,
    )


def test_zero_wipe_duration_applies_instantly(karaoke_line):
    """reduceMotion (durFast=0) 等价: 不动画, 直接到位."""
    item = karaoke_line.item
    item.setProperty("width", 600)
    item.setProperty("wipeDurationMs", 0)
    item.setProperty("words", [_word("瞬时", 0, 1000)])
    karaoke_line.app.processEvents()

    word0 = _word_item(item, 0)
    item.setProperty("positionMs", 500)
    karaoke_line.app.processEvents()
    assert word0.property("wipeWidth") == pytest.approx(word0.property("width") * 0.5)


def test_zero_duration_word_is_instant_full(karaoke_line):
    item = karaoke_line.item
    item.setProperty("width", 600)
    item.setProperty("words", [_word("骤亮", 1000, 0)])

    item.setProperty("positionMs", 999)
    assert _word_item(item, 0).property("sungFraction") == 0
    item.setProperty("positionMs", 1000)
    assert _word_item(item, 0).property("sungFraction") == 1


def test_empty_words_renders_nothing(karaoke_line):
    item = karaoke_line.item
    item.setProperty("width", 600)
    item.setProperty("words", [])
    assert _line_groups(item) == []
    assert _find_item(item, "karaokeWord-0") is None
