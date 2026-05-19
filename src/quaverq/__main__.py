"""QuaverQ 入口 — Controller 层.

协调 API、播放器和 UI，管理登录态生命周期。

线程模型：
    - 主线程跑 UI 主循环 (Qt 或 GTK)
    - 后台线程跑 asyncio 事件循环 (AsyncRunner)
    - UI 回调通过 runner.submit(coro) 提交协程到后台执行
    - 协程内对 UI 的更新由 UI 实现自行 marshalling 回主线程
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING

from .config import load as load_config
from .core.player import create_player
from .core.service import QuaverService
from .ui import check_availability, create_ui, resolve_backend

if TYPE_CHECKING:
    from collections.abc import Coroutine

logger = logging.getLogger("quaverq")


class AsyncRunner:
    """在后台线程运行 asyncio 事件循环，避免阻塞 UI 主线程."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._spin, daemon=True, name="quaverq-asyncio"
        )
        self._thread.start()

    def _spin(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: "Coroutine") -> Future:
        """提交协程，立即返回 concurrent.futures.Future."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def run_sync(self, coro: "Coroutine", timeout: float | None = None):
        """同步等待协程完成 (用于启动期/关闭期的短任务)."""
        return self.submit(coro).result(timeout)

    def shutdown(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=2)


def main() -> None:
    """主入口."""
    parser = argparse.ArgumentParser(
        prog="quaverq",
        description="QuaverQ — QQ 音乐桌面客户端",
    )
    parser.add_argument(
        "--ui",
        choices=["auto", "qt", "gtk"],
        default="auto",
        help="强制指定 UI 后端 (默认: auto 自动检测)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启 DEBUG 日志",
    )
    args = parser.parse_args()

    # 日志
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 加载配置 + 决定后端
    config = load_config()
    ui_pref = (
        args.ui
        if args.ui != "auto"
        else config.get("ui", {}).get("backend", "auto")
    )
    backend = resolve_backend(ui_pref)

    from quaverq import __version__

    logger.info("QuaverQ v%s 启动, UI 后端: %s", __version__, backend)

    if not check_availability(backend):
        logger.error(
            "%s 后端所需的库未安装。\n"
            "  Qt:  pip install quaverq[qt]\n"
            "  GTK: pip install quaverq[gtk]",
            backend.upper(),
        )
        sys.exit(1)

    # 创建组件
    ui = create_ui(backend)
    player = create_player()
    api = QuaverService()
    runner = AsyncRunner()

    # 播放器错误/EOS 透传到 UI (GStreamer bus 错误不再静默吞掉)
    player.on_error = lambda msg: ui.show_message(
        f"播放错误: {msg}", level="error"
    )
    player.on_eos = lambda: ui.set_play_state(False)

    # ---- 启动期: 连接 API + 加载凭据 ----
    runner.run_sync(api.connect())

    cached_cred = runner.run_sync(api._get_cached_credential())
    if cached_cred:
        api.set_credential_sync(cached_cred)
        expired = runner.run_sync(api.check_login_expired())
        if expired:
            logger.warning("缓存的凭据已过期，需要重新登录")
            ui.show_message("凭据已过期，请重新登录", level="warning")
            api.set_credential_sync(None)
        else:
            logger.info("缓存的凭据仍然有效")
            ui.show_message("凭据已加载，可直接使用")
            ui.set_authenticated(True)
    else:
        logger.info("未找到缓存的凭据，首次运行需要登录")

    # ---- 状态 ----
    _current_song = None

    # ---- 二维码回调（API → UI） ----
    def _on_qrcode(data: bytes, qr_type: str) -> None:
        ui.show_qrcode(data, qr_type)

    api.on_qrcode = _on_qrcode

    # ---- Controller 协程 ----

    async def _on_search(keyword: str) -> None:
        if not api.is_authenticated:
            ui.show_message("请先登录", level="warning")
            return
        # 并发拉 4 个类型, 任一失败不影响其他
        songs, singers, albums, playlists = await asyncio.gather(
            api.search_songs(keyword),
            api.search_singers(keyword),
            api.search_albums(keyword),
            api.search_playlists(keyword),
            return_exceptions=True,
        )
        for kind, result in (
            ("songs", songs),
            ("singers", singers),
            ("albums", albums),
            ("playlists", playlists),
        ):
            if isinstance(result, Exception):
                logger.warning("搜索 %s 失败: %s", kind, result)

        if isinstance(songs, list):
            ui.show_search_results(songs)
        if isinstance(singers, list):
            ui.show_singer_results(singers)
        if isinstance(albums, list):
            ui.show_album_results(albums)
        if isinstance(playlists, list):
            ui.show_playlist_results(playlists)

        # 全部 4 类都炸 → 给个反馈; 否则只要有任一类型出结果就静默
        if all(isinstance(r, Exception) for r in (songs, singers, albums, playlists)):
            ui.show_message(f"搜索失败: {songs}", level="error")

    async def _on_play(song) -> None:
        nonlocal _current_song
        _current_song = song
        if not api.is_authenticated:
            ui.show_message("请先登录", level="warning")
            return
        try:
            url_result = await api.get_song_url(song)
            if url_result and url_result.url:
                await player.play(url_result.url)
                ui.set_now_playing(song)
                ui.set_play_state(True)
                ui.show_message(
                    f"播放: {song.name} [{url_result.quality}]"
                )
            else:
                ui.show_message(
                    "无法获取播放地址（无版权或需更高级会员）", level="error"
                )
        except Exception as exc:
            logger.exception("播放失败")
            ui.show_message(f"播放失败: {exc}", level="error")

    async def _on_login() -> None:
        ui.show_message("正在获取二维码...", level="info")
        try:
            success = await api.login_by_qrcode()
        except Exception as exc:
            logger.exception("登录异常")
            ui.show_message(f"登录异常: {exc}", level="error")
            ui.show_welcome()
            return
        if success:
            ui.show_message("登录成功！")
            ui.set_authenticated(True)
            ui.show_welcome()
            try:
                await api.save_credential()
            except Exception as exc:
                logger.warning("保存凭据失败: %s", exc)
        else:
            ui.show_message("登录失败或已取消", level="error")
            ui.show_welcome()

    # 注册 UI 回调 → 提交到后台协程 (fire-and-forget)
    ui.on("search", lambda kw: runner.submit(_on_search(kw)))
    ui.on("play_song", lambda song: runner.submit(_on_play(song)))
    ui.on("pause", lambda: runner.submit(player.pause()))
    ui.on("resume", lambda: runner.submit(player.resume()))
    ui.on("stop", lambda: runner.submit(player.stop()))
    ui.on("login", lambda: runner.submit(_on_login()))

    # P0.3 才有真详情页, 现在先 toast 占位避免点击无反应
    ui.on(
        "open_singer",
        lambda singer: ui.show_message(f"歌手详情 (P0.3 实现): {singer.name}"),
    )
    ui.on(
        "open_album",
        lambda album: ui.show_message(f"专辑详情 (P0.3 实现): {album.name}"),
    )
    ui.on(
        "open_playlist",
        lambda playlist: ui.show_message(
            f"歌单详情 (P0.3 实现): {playlist.name}"
        ),
    )

    # ---- 进度更新 (UI 主线程触发 → 提交协程获取位置) ----
    async def _do_update() -> None:
        try:
            pos = await player.get_position()
            dur = await player.get_duration()
            ui.set_position(pos, dur)
        except Exception:
            pass

    def _update_progress() -> None:
        if _current_song is not None:
            runner.submit(_do_update())

    ui.schedule_periodic(500, _update_progress)

    # ---- 清理 (UI 退出时触发) ----
    def _cleanup() -> None:
        try:
            runner.run_sync(player.stop(), timeout=2)
        except Exception:
            logger.exception("停止播放器失败")
        try:
            runner.run_sync(api.disconnect(), timeout=2)
        except Exception:
            logger.exception("断开 API 失败")
        runner.shutdown()
        logger.info("QuaverQ 退出")

    ui.set_quit_callback(_cleanup)

    if not api.is_authenticated:
        ui.show_message("首次启动，请点击「登录」扫描二维码", level="info")

    # 启动 UI 主循环（阻塞，直到用户退出或 Ctrl+C）
    ui.run()


if __name__ == "__main__":
    main()
