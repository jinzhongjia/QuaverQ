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
    DetailController,
    HomeController,
    LibraryController,
    LyricController,
    MprisController,
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


def _raise_main_window(engine: QQmlApplicationEngine) -> None:
    roots = engine.rootObjects()
    if not roots:
        return
    window = roots[0]
    show_normal = getattr(window, "showNormal", None)
    if callable(show_normal):
        show_normal()
    raise_window = getattr(window, "raise_", None)
    if callable(raise_window):
        raise_window()
    request_activate = getattr(window, "requestActivate", None)
    if callable(request_activate):
        request_activate()


async def _load_initial_state(
    app_controller: AppController,
    home_controller: HomeController,
    lyric_controller: LyricController,
) -> None:
    await app_controller.refresh_auth_state_async()
    await asyncio.gather(
        home_controller.refresh_home_async(),
        lyric_controller.refresh_current_lyric_async(),
    )


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
    home_controller = HomeController(service_controller)
    detail_controller = DetailController(service_controller)
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
    engine.rootContext().setContextProperty("HomeController", home_controller)
    engine.rootContext().setContextProperty("DetailController", detail_controller)
    engine.rootContext().setContextProperty("ServiceController", service_controller)
    engine.rootContext().setContextProperty("LibraryController", library_controller)
    engine.rootContext().setContextProperty("LyricController", lyric_controller)
    engine.rootContext().setContextProperty("PlayerController", player_controller)
    qml_path = _qml_main_path()
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        logger.error("QML load failed: %s", qml_path)
        sys.exit(1)

    mpris_controller = MprisController(
        player_controller,
        raise_window=lambda: _raise_main_window(engine),
        quit_app=app.quit,
    )
    app.aboutToQuit.connect(lambda: loop.create_task(mpris_controller.stop_async()))

    logger.info("QuaverQ started with QML: %s", qml_path)
    with loop:
        loop.create_task(
            _load_initial_state(
                app_controller,
                home_controller,
                lyric_controller,
            )
        )
        loop.create_task(mpris_controller.start_async())
        loop.run_forever()


if __name__ == "__main__":
    main()
