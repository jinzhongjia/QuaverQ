"""QuaverQ PySide6 + Qt Quick entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import qasync
from PySide6.QtCore import QtMsgType, QUrl, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .bridge import (
    AppController,
    LibraryController,
    LyricController,
    PlayerController,
    ServiceController,
)
from .config import CONFIG_DIR, load as load_config
from .core.state import SessionState

logger = logging.getLogger("quaverq")


def _should_suppress_qt_message(message: str) -> bool:
    return (
        message.startswith("QSocketNotifier: Invalid socket ")
        and message.endswith(" and type 'Read', disabling...")
    )


def _qt_message_handler(
    _mode: QtMsgType,
    context: object,
    message: str,
) -> None:
    if _should_suppress_qt_message(message):
        return

    category = getattr(context, "category", None)
    prefix = f"{category}: " if category and category != "default" else ""
    sys.stderr.write(f"{prefix}{message}\n")
    sys.stderr.flush()


def _install_qt_message_filter() -> None:
    qInstallMessageHandler(_qt_message_handler)


def _qml_main_path() -> Path:
    return Path(__file__).resolve().parent / "qml" / "Main.qml"


def _qml_root_path() -> Path:
    return Path(__file__).resolve().parent / "qml"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _install_qt_message_filter()
    load_config()

    QQuickStyle.setStyle("Basic")

    app = QApplication(sys.argv)
    app.setApplicationName("QuaverQ")
    app.setOrganizationName("QuaverQ")

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    service_controller = ServiceController()
    app_controller = AppController(service_controller)
    library_controller = LibraryController(service_controller)
    player_controller = PlayerController(
        service_controller,
        session_state=SessionState(CONFIG_DIR / "state.json"),
    )
    lyric_controller = LyricController(service_controller, player_controller)
    app.aboutToQuit.connect(player_controller.saveSessionSnapshot)

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(_qml_root_path()))
    engine.rootContext().setContextProperty("AppController", app_controller)
    engine.rootContext().setContextProperty("ServiceController", service_controller)
    engine.rootContext().setContextProperty("LibraryController", library_controller)
    engine.rootContext().setContextProperty("LyricController", lyric_controller)
    engine.rootContext().setContextProperty("PlayerController", player_controller)
    qml_path = _qml_main_path()
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        logger.error("QML load failed: %s", qml_path)
        sys.exit(1)

    logger.info("QuaverQ started with QML: %s", qml_path)
    with loop:
        loop.create_task(app_controller.refresh_auth_state_async())
        loop.create_task(lyric_controller.refresh_current_lyric_async())
        loop.run_forever()


if __name__ == "__main__":
    main()
