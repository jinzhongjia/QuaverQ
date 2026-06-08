"""QuaverQ PySide6 + Qt Quick entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import qasync
from PySide6.QtCore import QSettings, QtMsgType, QUrl, qInstallMessageHandler
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import diagnostics, resources
from .bridge import (
    AppController,
    CoverController,
    CoverImageProvider,
    DetailControllerFactory,
    HomeController,
    LibraryController,
    LyricController,
    PlayerController,
    ServiceController,
    SettingsController,
    SongDetailController,
)
from .bridge.stream_proxy import StreamProxy
from .config import CACHE_DIR, CONFIG_DIR, load as load_config, purge_orphan_caches
from .core.cover_cache import CoverCache
from .core.home_cache import HomeCache
from .core.state import SessionState
from .platform import get_platform

logger = logging.getLogger("quaverq")


def _open_settings_ini() -> QSettings:
    """所有用户设置统一落在 CONFIG_DIR/settings.ini, 与 state.json / config.toml 同目录."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return QSettings(str(CONFIG_DIR / "settings.ini"), QSettings.Format.IniFormat)


def _should_suppress_qt_message(message: str) -> bool:
    return (
        (
            message.startswith("QSocketNotifier: Invalid socket ")
            and message.endswith(" and type 'Read', disabling...")
        )
        or "Could not register app ID" in message
        or "Could not update timestamps for skipped samples" in message
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


def _setup_tray(
    app: QApplication,
    engine: QQmlApplicationEngine,
    player_controller: PlayerController,
) -> QSystemTrayIcon:
    """系统托盘: 左键 / 「显示」恢复窗口, 「退出」才真正退出 app.

    triggered 会带 checked 参数, 用 ``lambda *_`` 吸收.
    """
    tray = QSystemTrayIcon(QIcon(str(resources.icon_file())), app)
    tray.setToolTip("QuaverQ")

    menu = QMenu()
    menu.addAction("显示 QuaverQ").triggered.connect(lambda *_: _raise_main_window(engine))
    menu.addSeparator()
    menu.addAction("播放 / 暂停").triggered.connect(lambda *_: player_controller.togglePlayPause())
    menu.addAction("下一首").triggered.connect(lambda *_: player_controller.next())
    menu.addAction("上一首").triggered.connect(lambda *_: player_controller.prev())
    menu.addSeparator()
    menu.addAction("退出 QuaverQ").triggered.connect(lambda *_: app.quit())
    tray.setContextMenu(menu)
    tray._menu = menu  # 持有引用, 防 QMenu 被 GC

    def _on_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            _raise_main_window(engine)

    tray.activated.connect(_on_activated)
    tray.show()
    return tray


async def _load_initial_state(
    home_controller: HomeController,
    service_controller: ServiceController,
    lyric_controller: LyricController,
) -> None:
    # 凭据已在启动时同步预载 (乐观登录); 这里做真正的 connect + 网络有效性校验 (过期则降级),
    # 再走网络刷新覆盖 stale 缓存 —— SWR 的 revalidate 半边.
    await service_controller.start()
    await asyncio.gather(
        home_controller.refresh_home_async(),
        lyric_controller.refresh_current_lyric_async(),
    )


async def _shutdown(
    mpris_controller: object | None,
    lyrics_dbus_controller: object | None,
    cover_cache: CoverCache,
) -> None:
    """关窗后清理 (run_forever 返回后, 趁 loop 未关 / QObject 仍存活时跑):
    关封面下载 session -> 停 MPRIS / Lyrics D-Bus -> 取消并排空所有挂起任务.

    - cover_cache.close(): 中断在途封面下载, 让下载线程秒退; 否则 loop.close() 会
      join 它们 (qasync 默认 executor shutdown(wait=True)), 在途下载多大就钝多久.
    - 取消挂起任务: 用户在后台刷新完成前关窗时, refresh_* 等任务仍挂起; 不主动取消的话
      它们会在 loop.close() 时被 GC, finally 里 emit 信号撞上已析构的 C++ QObject。
    - mpris / lyrics 为 None: 当前平台无 D-Bus 实现 (Windows / macOS), 直接跳.
    """
    cover_cache.close()
    if mpris_controller is not None:
        try:
            await mpris_controller.stop_async()
        except Exception:
            logger.debug("MPRIS 退出清理失败", exc_info=True)
    if lyrics_dbus_controller is not None:
        try:
            await lyrics_dbus_controller.stop_async()
        except Exception:
            logger.debug("Lyrics D-Bus 退出清理失败", exc_info=True)
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


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
    # ApplicationName **必须小写** 与 platformdirs ``appname="quaverq"`` 完全一致:
    # Qt 用 setApplicationName 作 QStandardPaths 路径段, 跟 platformdirs 大小写不一致
    # 会在 Linux 上分裂出两个目录 (case-sensitive), 在 Windows 上虽然合并但首创者
    # 的大小写会"污染"后续所有路径显示.
    # **故意不设 setOrganizationName**: Qt 路径默认布局是 ``<base>/<orgname>/<appname>``,
    # 设了 orgname 就会嵌套 (如 ``%LOCALAPPDATA%\quaverq\quaverq\``). 留空后 Qt 单层布局
    # ``%LOCALAPPDATA%\quaverq\`` 与 CACHE_DIR 父目录重叠, Qt 内部 cache 自动落到
    # ``%LOCALAPPDATA%\quaverq\cache\`` (Qt 自己加 ``cache`` 子目录), 与我们的
    # ``covers/`` / ``home.json`` 在 CACHE_DIR 顶层并列, 清晰分层.
    app.setApplicationName("quaverq")
    app.setDesktopFileName(resources.APP_ID)
    app.setWindowIcon(QIcon(str(resources.icon_file())))

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 平台抽象层 (PAL): 单实例 / 系统主题 / 媒体会话 / 歌词外发四项能力按平台派发,
    # 当前平台不支持时 (Windows / macOS) 返回 None, 走"降级到无对应集成"路径.
    pal = get_platform()

    # 单实例闸门: 占住 lock -> 第一实例; 占不到 -> 通知已有实例前置窗口后退出.
    # bus / mutex 连接由 guard 持有, 引用必须存活到 app 退出, 否则名字 / 锁会被释放.
    instance_guard = pal.single_instance()
    if instance_guard is not None:
        if not loop.run_until_complete(instance_guard.acquire()):
            loop.run_until_complete(instance_guard.notify_existing_raise())
            instance_guard.release()
            logger.info("QuaverQ 已在运行, 已请求现有窗口前置, 本实例退出")
            sys.exit(0)
        app.aboutToQuit.connect(instance_guard.release)
    else:
        logger.info("当前平台 (%s) 暂无单实例守卫, 允许多开", pal.name)

    service_controller = ServiceController()
    cover_cache = CoverCache(CACHE_DIR / "covers")
    home_cache = HomeCache(CACHE_DIR / "home.json")
    settings_controller = SettingsController(
        settings=_open_settings_ini(),
        cover_cache=cover_cache,
        orphan_cleanup=purge_orphan_caches,
    )
    # 系统主题: Linux 走 freedesktop portal; Windows / macOS 暂返回 None.
    # QML 端 (Main.qml) 已 null-guard systemTheme, None 时退化为"跟随 Qt palette".
    # 注意: start() 必须在 engine.load() 之前用 run_until_complete 同步等完,
    # 否则首帧按 _dark=False 渲染浅色, portal 回包后翻深色 -> 视觉上"白闪一下".
    system_theme_watcher = pal.system_theme()
    if system_theme_watcher is not None:
        loop.run_until_complete(system_theme_watcher.start())
    cover_controller = CoverController(cover_cache)
    app_controller = AppController(service_controller)
    detail_controller_factory = DetailControllerFactory(service_controller)
    song_detail_controller = SongDetailController(service_controller)
    library_controller = LibraryController(service_controller, home_cache=home_cache)
    # Windows SMTC 用 stream_proxy 暴露封面给系统 (SMTC 的 RandomAccessStreamReference
    # 不支持 file:// URI, 必须走 http://); 其他平台无影响.
    stream_proxy = StreamProxy(local_dir=CACHE_DIR / "covers")
    stream_proxy.start()
    player_controller = PlayerController(
        service_controller,
        settings_controller=settings_controller,
        session_state=SessionState(CONFIG_DIR / "state.json"),
        stream_proxy=stream_proxy,
    )
    home_controller = HomeController(
        service_controller,
        home_cache=home_cache,
        player_controller=player_controller,
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
    engine.rootContext().setContextProperty("DetailControllerFactory", detail_controller_factory)
    engine.rootContext().setContextProperty("SongDetailController", song_detail_controller)
    engine.rootContext().setContextProperty("ServiceController", service_controller)
    engine.rootContext().setContextProperty("LibraryController", library_controller)
    engine.rootContext().setContextProperty("LyricController", lyric_controller)
    engine.rootContext().setContextProperty("PlayerController", player_controller)
    engine.rootContext().setContextProperty("SettingsController", settings_controller)
    engine.rootContext().setContextProperty("SystemTheme", system_theme_watcher)
    # 启动同步读盘加载凭据 -> 首帧即登录态 (本地, 不联网, 不需事件循环);
    # connect + 网络有效性校验由后台 start() 完成. 让私有区块也能在 QML 绑定前用缓存填好.
    service_controller.prime_credential_sync()
    account_key = service_controller.account_key()
    # SWR 首帧: 公共 + 私有区块都用上次缓存同步填好, QML 绑定时即有完整内容
    home_controller.prime_public_from_cache()
    home_controller.prime_private_from_cache(account_key)
    library_controller.prime_from_cache(account_key)
    qml_path = _qml_main_path()
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        logger.error("QML load failed: %s", qml_path)
        sys.exit(1)

    # 系统托盘 + 关闭到托盘: 托盘可用时关闭仅隐藏窗口, 仅托盘/MPRIS「退出」才真正退出;
    # 托盘不可用则保持默认 (关闭即退出), 避免窗口隐藏后无处召回成僵尸进程.
    # _setup_tray 内部 QSystemTrayIcon(parent=app) + tray._menu=menu 已持有引用, 此处不存
    if QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        engine.rootObjects()[0].setProperty("closeToTray", True)
        _setup_tray(app, engine, player_controller)
    else:
        logger.info("系统托盘不可用, 关闭窗口将退出程序")

    # 媒体会话 (Linux: MPRIS2; Windows: SMTC; macOS: TODO Stage 4) + 歌词外发 (Linux: D-Bus).
    # None 时 _shutdown / start 钩子都已 None-guard, 应用功能不受影响.
    # cover_cache 仅 Windows SMTC 使用 (本地 file:// URI -> Now Playing 卡片 Thumbnail).
    mpris_controller = pal.media_session(
        player_controller,
        raise_window=lambda: _raise_main_window(engine),
        quit_app=app.quit,
        cover_cache=cover_cache,
        stream_proxy=stream_proxy,
    )
    lyrics_dbus_controller = pal.lyric_publisher(
        lyric_controller=lyric_controller,
        player_controller=player_controller,
    )
    logger.info("QuaverQ started with QML: %s", qml_path)
    with loop:
        loop.create_task(
            _load_initial_state(
                home_controller,
                service_controller,
                lyric_controller,
            )
        )
        if mpris_controller is not None:
            loop.create_task(mpris_controller.start_async())
        if lyrics_dbus_controller is not None:
            loop.create_task(lyrics_dbus_controller.start_async())
        loop.run_forever()  # qasync 在关窗 (app.quit) 时干净返回
        # 关窗后趁 loop 未关 / QObject 仍存活: 关下载 session + 停 D-Bus 服务 + 取消排空挂起任务
        loop.run_until_complete(_shutdown(mpris_controller, lyrics_dbus_controller, cover_cache))


if __name__ == "__main__":
    main()
