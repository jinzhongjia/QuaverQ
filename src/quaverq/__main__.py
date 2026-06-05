"""QuaverQ PySide6 + Qt Quick entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import qasync
from PySide6.QtCore import QtMsgType, QUrl, qInstallMessageHandler
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .bridge import (
    AppController,
    CoverController,
    CoverImageProvider,
    DetailController,
    HomeController,
    LibraryController,
    LyricController,
    MprisController,
    PlayerController,
    ServiceController,
    SettingsController,
)
from . import diagnostics, resources
from .bridge.stream_proxy import StreamProxy
from .bridge.system_theme import SystemThemeWatcher
from .config import CACHE_DIR, CONFIG_DIR, load as load_config, purge_orphan_caches
from .core.cover_cache import CoverCache
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
    orphan_caches = purge_orphan_caches()
    if orphan_caches:
        logger.info(
            "清理旧架构遗留缓存: %s",
            ", ".join(str(path) for path in orphan_caches),
        )
    for diag in diagnostics.run_diagnostics():
        level = {
            diagnostics.CRITICAL: logging.ERROR,
            diagnostics.WARNING: logging.WARNING,
        }.get(diag.severity, logging.INFO)
        logger.log(level, "启动自检 [%s]: %s", diag.name, diag.detail)

    QQuickStyle.setStyle("Basic")

    app = QApplication(sys.argv)
    app.setApplicationName("QuaverQ")
    app.setOrganizationName("QuaverQ")
    app.setDesktopFileName(resources.APP_ID)
    app.setWindowIcon(QIcon(str(resources.icon_file())))

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    service_controller = ServiceController()
    cover_cache = CoverCache(CACHE_DIR / "covers")
    settings_controller = SettingsController(
        cover_cache=cover_cache,
        orphan_cleanup=purge_orphan_caches,
    )
    system_theme_watcher = SystemThemeWatcher()
    cover_controller = CoverController(cover_cache)
    app_controller = AppController(service_controller)
    home_controller = HomeController(service_controller)
    detail_controller = DetailController(service_controller)
    library_controller = LibraryController(service_controller)
    stream_proxy = StreamProxy()
    stream_proxy.start()
    player_controller = PlayerController(
        service_controller,
        settings_controller=settings_controller,
        session_state=SessionState(CONFIG_DIR / "state.json"),
        stream_proxy=stream_proxy,
    )
    lyric_controller = LyricController(service_controller, player_controller)
    app.aboutToQuit.connect(player_controller.saveSessionSnapshot)
    app.aboutToQuit.connect(stream_proxy.stop)

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(_qml_root_path()))
    engine.addImageProvider("covers", CoverImageProvider(cover_cache))
    engine.rootContext().setContextProperty("AppController", app_controller)
    engine.rootContext().setContextProperty("CoverController", cover_controller)
    engine.rootContext().setContextProperty("HomeController", home_controller)
    engine.rootContext().setContextProperty("DetailController", detail_controller)
    engine.rootContext().setContextProperty("ServiceController", service_controller)
    engine.rootContext().setContextProperty("LibraryController", library_controller)
    engine.rootContext().setContextProperty("LyricController", lyric_controller)
    engine.rootContext().setContextProperty("PlayerController", player_controller)
    engine.rootContext().setContextProperty("SettingsController", settings_controller)
    engine.rootContext().setContextProperty("SystemTheme", system_theme_watcher)
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
        loop.create_task(system_theme_watcher.start())
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
