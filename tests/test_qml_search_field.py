"""SearchField.qml 输入联想 (suggest) 离屏契约测试.

用 QQuickView 承载 (需真实窗口才能拿到 TextField 焦点), 验证:

1. 聚焦后输入 -> debounce 触发 suggestRequested(文本);
2. 清空输入 -> suggestRequested("") 清空联想;
3. 有联想词 + 聚焦 + 非空输入 -> suggestVisible 为真 (下拉应显示);
4. chooseSuggestion(词) -> 发 suggestionChosen 并收起下拉 (suggestDismissed)。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, QUrl
from PySide6.QtQuick import QQuickView
from PySide6.QtWidgets import QApplication

_FIELD_QML = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "quaverq"
    / "qml"
    / "components"
    / "SearchField.qml"
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _process(app, rounds: int = 12) -> None:
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.003)


@pytest.fixture
def field(qapp):
    view = QQuickView()
    view.setSource(QUrl.fromLocalFile(str(_FIELD_QML)))
    assert view.status() == QQuickView.Status.Ready, view.errors()
    item = view.rootObject()
    assert item is not None
    item.setProperty("suggestDebounceMs", 5)
    view.show()
    _process(qapp)
    yield item, qapp
    view.close()
    qapp.processEvents()


def test_typing_emits_debounced_suggest_request(field):
    item, app = field
    emitted: list[str] = []
    item.suggestRequested.connect(emitted.append)

    QMetaObject.invokeMethod(item, "focusInput")
    _process(app)
    item.setProperty("text", "周")
    _process(app)

    assert "周" in emitted


def test_clearing_text_requests_empty_suggest(field):
    item, app = field
    QMetaObject.invokeMethod(item, "focusInput")
    item.setProperty("text", "周")
    _process(app)

    emitted: list[str] = []
    item.suggestRequested.connect(emitted.append)
    item.setProperty("text", "")
    _process(app)

    assert emitted and emitted[-1] == ""


def test_suggest_dropdown_visible_when_focused_with_suggestions(field):
    item, app = field
    item.setProperty("suggestions", ["周杰伦", "周深"])
    QMetaObject.invokeMethod(item, "focusInput")
    item.setProperty("text", "周")
    _process(app)

    assert item.property("suggestVisible") is True


def test_choose_suggestion_emits_and_dismisses(field):
    item, app = field
    item.setProperty("suggestions", ["周杰伦", "周深"])
    QMetaObject.invokeMethod(item, "focusInput")
    item.setProperty("text", "周")
    _process(app)

    chosen: list[str] = []
    item.suggestionChosen.connect(chosen.append)
    QMetaObject.invokeMethod(item, "chooseSuggestion", Q_ARG("QVariant", "周杰伦"))
    _process(app)

    assert chosen == ["周杰伦"]
    assert item.property("suggestDismissed") is True
    assert item.property("suggestVisible") is False
