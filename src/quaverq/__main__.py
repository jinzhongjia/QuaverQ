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

from .config import CONFIG_DIR, load as load_config
from .core.cache import Cache
from .core.mpris import MprisCallbacks, MprisService
from .core.player import create_player
from .core.queue import PlayMode, PlayQueue
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
    from .config import save as save_config
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
    queue = PlayQueue()
    runner = AsyncRunner()

    # SQLite cache (P1.1)
    cache = Cache(CONFIG_DIR / "cache.db")
    try:
        cache.open()
    except Exception as exc:
        logger.warning("cache 打开失败: %s, 详情页会走每次网络", exc)
        cache = None

    api = QuaverService(cache=cache)

    # 模式 cycle 顺序 + UI 显示名映射
    _MODE_ORDER = [
        PlayMode.SEQUENCE,
        PlayMode.REPEAT_ALL,
        PlayMode.REPEAT_ONE,
        PlayMode.SHUFFLE,
    ]
    _MODE_UI_NAME = {
        PlayMode.SEQUENCE: "sequence",
        PlayMode.REPEAT_ALL: "repeat_all",
        PlayMode.REPEAT_ONE: "repeat_one",
        PlayMode.SHUFFLE: "shuffle",
    }

    # 音质偏好 (运行时可变, 由 settings 改并写回 config.toml)
    _quality_pref = config.get("player", {}).get("quality", "balanced")
    if _quality_pref not in ("high", "balanced", "standard"):
        _quality_pref = "balanced"

    # 播放器错误透传到 UI
    player.on_error = lambda msg: ui.show_message(
        f"播放错误: {msg}", level="error"
    )

    # MPRIS D-Bus 集成 (媒体键 / GNOME / KDE 媒体小组件)
    # 回调闭包在更后定义, 这里先占位
    mpris_callbacks = MprisCallbacks()
    mpris = MprisService(mpris_callbacks)

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

    # ---- 状态 (current song 由 queue.current() 提供) ----

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

    async def _play_current() -> None:
        """对 queue.current() 拉 URL 播放; 失败时尝试 next 跳过."""
        song = queue.current()
        if song is None:
            ui.set_play_state(False)
            return
        if not api.is_authenticated:
            ui.show_message("请先登录", level="warning")
            return
        try:
            url_result = await api.get_song_url(
                song, quality_preference=_quality_pref
            )
        except Exception as exc:
            logger.exception("获取播放地址异常")
            ui.show_message(f"播放失败: {exc}", level="error")
            url_result = None

        if url_result and url_result.url:
            await player.play(url_result.url)
            ui.set_now_playing(song)
            ui.set_play_state(True)
            ui.show_message(f"播放: {song.name} [{url_result.quality}]")
            # MPRIS 元数据 + 状态推送
            mpris.push_metadata(song)
            mpris.push_playback_status("play")
            # 后台并发拉歌词, 失败不影响播放
            runner.submit(_fetch_lyric_for(song))
            return

        # 失败: 自动尝试下一首 (避免某首无版权时整个队列卡住)
        ui.show_message(
            f"{song.name} 无版权, 自动跳过", level="warning"
        )
        nxt = queue.next()
        if nxt is not None:
            await _play_current()
        else:
            ui.set_play_state(False)

    async def _fetch_lyric_for(song) -> None:
        try:
            ly = await api.get_lyric(song.mid)
            ui.show_lyric(ly)
        except Exception as exc:
            logger.warning("拉歌词失败 (%s): %s", song.name, exc)

    async def _on_play(song, song_list=None) -> None:
        """点歌入队 + 播放. song_list 是该 song 所在的上下文 (整个 tab / 详情页)."""
        if song_list and song in song_list:
            queue.push(
                song_list, play_now=True, start_index=song_list.index(song)
            )
        else:
            queue.push([song], play_now=True)
        await _play_current()

    async def _advance_on_eos() -> None:
        """GStreamer EOS 触发: 走 queue 决定下一首."""
        nxt = queue.on_song_end()
        if nxt is not None:
            await _play_current()
        else:
            ui.set_play_state(False)
            mpris.push_playback_status("stop")

    def set_quality_preference(new_pref: str) -> None:
        nonlocal _quality_pref
        if new_pref not in ("high", "balanced", "standard"):
            return
        _quality_pref = new_pref
        config.setdefault("player", {})["quality"] = new_pref
        try:
            save_config(config)
        except Exception as exc:
            logger.warning("保存 config.toml 失败: %s", exc)
        ui.show_message(f"音质偏好: {new_pref}", level="info")

    async def _on_logout() -> None:
        """删凭据 + 清认证态 + 切回欢迎页."""
        api.set_credential_sync(None)
        # 删凭据缓存文件
        import os
        try:
            os.remove(api._credential_cache_path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("删除凭据缓存失败: %s", exc)
        ui.set_authenticated(False)
        ui.show_welcome()
        ui.show_message("已退出登录", level="info")

    def cycle_play_mode() -> None:
        cur_idx = _MODE_ORDER.index(queue.mode)
        new_mode = _MODE_ORDER[(cur_idx + 1) % len(_MODE_ORDER)]
        queue.set_mode(new_mode)
        ui.set_play_mode_indicator(_MODE_UI_NAME[new_mode])
        ui.show_message(
            f"模式: {_MODE_UI_NAME[new_mode]}", level="info"
        )

    player.on_eos = lambda: runner.submit(_advance_on_eos())

    async def _on_login() -> None:
        ui.show_message("正在获取二维码...", level="info")
        try:
            success = await api.login_by_qrcode()
        except Exception as exc:
            logger.exception("登录异常")
            # 网络层错误给可读提示, 而非贴原始异常
            exc_name = type(exc).__name__
            if "Timeout" in exc_name or "ConnectError" in exc_name:
                friendly = (
                    "无法连接 QQ 登录服务器 (网络超时), 请检查网络后重试"
                )
            else:
                friendly = f"登录异常: {exc}"
            ui.show_message(friendly, level="error")
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

    # next/prev (用户主动按按钮): 用 queue 决定
    async def _on_next() -> None:
        if queue.next() is not None:
            await _play_current()

    async def _on_prev() -> None:
        if queue.prev() is not None:
            await _play_current()

    async def _ui_pause() -> None:
        await player.pause()
        ui.set_play_state(False)
        mpris.push_playback_status("pause")

    async def _ui_resume() -> None:
        await player.resume()
        ui.set_play_state(True)
        mpris.push_playback_status("play")

    async def _ui_stop() -> None:
        await player.stop()
        ui.set_play_state(False)
        mpris.push_playback_status("stop")

    # 注册 UI 回调 → 提交到后台协程 (fire-and-forget)
    ui.on("search", lambda kw: runner.submit(_on_search(kw)))
    ui.on(
        "play_song",
        lambda song, song_list=None: runner.submit(_on_play(song, song_list)),
    )
    ui.on("pause", lambda: runner.submit(_ui_pause()))
    ui.on("resume", lambda: runner.submit(_ui_resume()))
    ui.on("stop", lambda: runner.submit(_ui_stop()))
    ui.on("next", lambda: runner.submit(_on_next()))
    ui.on("prev", lambda: runner.submit(_on_prev()))
    ui.on("cycle_play_mode", lambda: cycle_play_mode())
    ui.on("login", lambda: runner.submit(_on_login()))
    ui.on("logout", lambda: runner.submit(_on_logout()))
    ui.on("set_quality", lambda pref: set_quality_preference(pref))

    # 详情页 (P0.3): 拉详情 → push 详情视图
    async def _open_album(album_brief) -> None:
        ui.show_message(f"加载专辑: {album_brief.name}…")
        try:
            album_full = await api.get_album_detail(album_brief.mid)
            # 服务端返回名字为空时用 search 缓存的回填
            if not album_full.name:
                album_full.name = album_brief.name
            ui.show_album_detail(album_full)
        except Exception as exc:
            logger.exception("加载专辑失败")
            ui.show_message(f"加载专辑失败: {exc}", level="error")

    async def _open_singer(singer_brief) -> None:
        ui.show_message(f"加载歌手: {singer_brief.name}…")
        try:
            artist = await api.get_artist_detail(singer_brief.mid)
            # singer.get_info 拿不到 Name 时, 用 search 时的名字兜底
            if not artist.singer.name:
                artist.singer.name = singer_brief.name
            if not artist.singer.avatar_url:
                artist.singer.avatar_url = singer_brief.avatar_url
            ui.show_artist_detail(artist)
        except Exception as exc:
            logger.exception("加载歌手失败")
            ui.show_message(f"加载歌手失败: {exc}", level="error")

    async def _open_playlist(playlist_brief) -> None:
        ui.show_message(f"加载歌单: {playlist_brief.name}…")
        try:
            pl_full = await api.get_playlist_detail(playlist_brief.pid)
            if not pl_full.name:
                pl_full.name = playlist_brief.name
            ui.show_playlist_detail(pl_full)
        except Exception as exc:
            logger.exception("加载歌单失败")
            ui.show_message(f"加载歌单失败: {exc}", level="error")

    ui.on("open_album", lambda a: runner.submit(_open_album(a)))
    ui.on("open_singer", lambda s: runner.submit(_open_singer(s)))
    ui.on("open_playlist", lambda p: runner.submit(_open_playlist(p)))

    # ---- 进度更新 (UI 主线程触发 → 提交协程获取位置) ----
    async def _do_update() -> None:
        try:
            pos = await player.get_position()
            dur = await player.get_duration()
            ui.set_position(pos, dur)
            ui.update_lyric_position(pos)
        except Exception:
            pass

    def _update_progress() -> None:
        if queue.current() is not None:
            runner.submit(_do_update())

    ui.schedule_periodic(500, _update_progress)

    # ---- 清理 (UI 退出时触发) ----
    def _cleanup() -> None:
        try:
            runner.run_sync(mpris.stop(), timeout=2)
        except Exception:
            logger.exception("关闭 MPRIS 失败")
        try:
            runner.run_sync(player.stop(), timeout=2)
        except Exception:
            logger.exception("停止播放器失败")
        try:
            runner.run_sync(api.disconnect(), timeout=2)
        except Exception:
            logger.exception("断开 API 失败")
        if cache is not None:
            try:
                cache.close()
            except Exception:
                logger.exception("关闭 cache 失败")
        runner.shutdown()
        logger.info("QuaverQ 退出")

    ui.set_quit_callback(_cleanup)

    # MPRIS 回调装配: 媒体键 → 控制器
    async def _mpris_play_pause() -> None:
        # 简化: state 没 mirror, 直接尝试 resume; player 内部决定
        # PAUSED → resume, PLAYING → pause (用 player.state 判断)
        from .core.player import PlayState
        if player.state == PlayState.PLAYING:
            await player.pause()
            mpris.push_playback_status("pause")
        else:
            await player.resume()
            mpris.push_playback_status("play")

    mpris_callbacks.play_pause = lambda: runner.submit(_mpris_play_pause())
    mpris_callbacks.play = lambda: (
        runner.submit(player.resume()),
        mpris.push_playback_status("play"),
    )
    mpris_callbacks.pause = lambda: (
        runner.submit(player.pause()),
        mpris.push_playback_status("pause"),
    )
    mpris_callbacks.stop = lambda: (
        runner.submit(player.stop()),
        mpris.push_playback_status("stop"),
    )
    mpris_callbacks.next = lambda: runner.submit(_on_next())
    mpris_callbacks.prev = lambda: runner.submit(_on_prev())
    mpris_callbacks.quit = lambda: ui.quit()
    # raise_window: GTK 没简单跨进程, 留空 (后续可加 application present)

    # 启动 MPRIS (在后台 loop 上跑 D-Bus; 失败容忍, 不阻塞应用)
    try:
        mpris_ok = runner.run_sync(mpris.start(), timeout=5)
    except Exception as exc:
        logger.warning("MPRIS 初始化超时/异常: %s", exc)
        mpris_ok = False
    if not mpris_ok:
        logger.info("MPRIS 未启用 (D-Bus session 不可用?)")

    # 初始 mode 指示器 + quality 偏好同步到 UI
    ui.set_play_mode_indicator(_MODE_UI_NAME[queue.mode])
    ui.set_quality_preference(_quality_pref)

    if not api.is_authenticated:
        ui.show_message("首次启动，请点击「登录」扫描二维码", level="info")

    # 启动 UI 主循环（阻塞，直到用户退出或 Ctrl+C）
    ui.run()


if __name__ == "__main__":
    main()
