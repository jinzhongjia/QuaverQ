"""Qt (PySide6) UI 后端.

提供基于 QWidget 的完整播放器界面，含登录面板。
"""

from __future__ import annotations

import logging
import signal
from typing import TYPE_CHECKING, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ..base import UIBase

if TYPE_CHECKING:
    from ...core.models import Album, Lyric, Playlist, Singer, Song

logger = logging.getLogger(__name__)


class _Dispatcher(QtCore.QObject):
    """将 callable 从任意线程派发到 Qt 主线程."""

    _invoke = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._invoke.connect(self._handle)

    @staticmethod
    def _handle(fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:
            logger.exception("Qt dispatcher 回调异常")

    def post(self, fn: Callable[[], None]) -> None:
        self._invoke.emit(fn)


class QtUI(UIBase):
    """基于 PySide6 的 QQ 音乐客户端界面."""

    def __init__(self) -> None:
        super().__init__()
        self._app: QtWidgets.QApplication | None = None
        self._window: _MainWindow | None = None
        self._dispatcher: _Dispatcher | None = None
        self._sigint_timer: QtCore.QTimer | None = None
        self._pending_calls: list[Callable[[], None]] = []
        self._pending_periodics: list[tuple[int, Callable[[], None]]] = []

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._app = QtWidgets.QApplication([])
        self._app.setApplicationName("QuaverQ")
        self._app.setOrganizationName("quaverq")

        self._dispatcher = _Dispatcher()
        self._window = _MainWindow(callbacks=self)
        self._window.show()

        # SIGINT (Ctrl+C) — 500ms 心跳让 Python 有机会处理信号
        self._sigint_timer = QtCore.QTimer()
        self._sigint_timer.start(500)
        self._sigint_timer.timeout.connect(lambda: None)
        signal.signal(
            signal.SIGINT,
            lambda *_: self._app.quit() if self._app else None,
        )

        # 清理回调
        if self._quit_callback is not None:
            self._app.aboutToQuit.connect(self._quit_callback)

        # 主循环启动前已入队的 UI 调用 / 周期任务
        for fn in self._pending_calls:
            fn()
        self._pending_calls.clear()
        for interval, cb in self._pending_periodics:
            self._start_periodic(interval, cb)
        self._pending_periodics.clear()

        logger.info("Qt UI 启动")
        self._app.exec()

    def quit(self) -> None:
        if self._app:
            self._app.quit()

    # ------------------------------------------------------------------
    # 线程派发 / 定时器
    # ------------------------------------------------------------------

    def _post(self, fn: Callable[[], None]) -> None:
        """从任意线程派发到 Qt 主线程；主循环未启动时先缓存."""
        if self._dispatcher is None:
            self._pending_calls.append(fn)
        else:
            self._dispatcher.post(fn)

    def schedule_periodic(
        self, interval_ms: int, callback: Callable[[], None]
    ) -> None:
        if self._app is None:
            self._pending_periodics.append((interval_ms, callback))
        else:
            self._start_periodic(interval_ms, callback)

    def _start_periodic(
        self, interval_ms: int, callback: Callable[[], None]
    ) -> None:
        timer = QtCore.QTimer(self._window)
        timer.timeout.connect(callback)
        timer.start(interval_ms)

    # ------------------------------------------------------------------
    # UI 更新（线程安全）
    # ------------------------------------------------------------------

    def show_welcome(self) -> None:
        self._post(
            lambda: self._window.show_welcome() if self._window else None
        )

    def set_authenticated(self, authed: bool) -> None:
        self._post(
            lambda: self._window.set_authenticated(authed) if self._window else None
        )

    def show_qrcode(self, data: bytes, qr_type: str) -> None:
        self._post(
            lambda: self._window.show_qrcode(data, qr_type) if self._window else None
        )

    def show_search_results(self, songs: list[Song]) -> None:
        self._post(
            lambda: self._window.show_search_results(songs) if self._window else None
        )

    def show_singer_results(self, singers: list[Singer]) -> None:
        self._post(
            lambda: self._window.show_singer_results(singers) if self._window else None
        )

    def show_album_results(self, albums: list[Album]) -> None:
        self._post(
            lambda: self._window.show_album_results(albums) if self._window else None
        )

    def show_playlist_results(self, playlists: list[Playlist]) -> None:
        self._post(
            lambda: self._window.show_playlist_results(playlists) if self._window else None
        )

    def show_album_detail(self, album) -> None:
        self._post(
            lambda: self._window.show_album_detail(album) if self._window else None
        )

    def show_artist_detail(self, artist) -> None:
        self._post(
            lambda: self._window.show_artist_detail(artist) if self._window else None
        )

    def show_playlist_detail(self, playlist) -> None:
        self._post(
            lambda: self._window.show_playlist_detail(playlist) if self._window else None
        )

    def update_lyric_position(self, position_ms: int) -> None:
        # Qt P0.5 暂不展示歌词页, 状态栏不打扰
        pass

    def show_playlist(self, playlist: Playlist) -> None:
        self._post(
            lambda: self._window.show_playlist(playlist) if self._window else None
        )

    def show_lyric(self, lyric: Lyric) -> None:
        self._post(
            lambda: self._window.show_lyric(lyric) if self._window else None
        )

    def set_now_playing(self, song: Song) -> None:
        self._post(
            lambda: self._window.set_now_playing(song) if self._window else None
        )

    def set_play_state(self, playing: bool) -> None:
        self._post(
            lambda: self._window.set_play_state(playing) if self._window else None
        )

    def set_play_mode_indicator(self, mode: str) -> None:
        self._post(
            lambda: self._window.set_play_mode_indicator(mode) if self._window else None
        )

    def set_quality_preference(self, pref: str) -> None:
        # Qt 端目前无 settings UI; 静默接受
        pass

    def set_liked_state(self, mid: str, liked: bool) -> None:
        # Qt 端目前没 ❤️ 按钮, 静默接受 (P0.x 完整 Qt UI 时补)
        pass

    def set_position(self, position_ms: int, duration_ms: int) -> None:
        self._post(
            lambda: self._window.set_position(position_ms, duration_ms)
            if self._window
            else None
        )

    def show_message(self, text: str, *, level: str = "info") -> None:
        self._post(
            lambda: self._window.show_message(text, level) if self._window else None
        )


class _MainWindow(QtWidgets.QMainWindow):
    """主窗口."""

    def __init__(self, callbacks: QtUI) -> None:
        super().__init__()
        self._ui = callbacks
        self.setWindowTitle("QuaverQ — QQ 音乐")
        self.resize(960, 640)

        # ---- 工具栏 ----
        self._toolbar = self.addToolBar("主工具栏")
        self._toolbar.setMovable(False)

        self._login_btn = QtWidgets.QPushButton("登录")
        self._login_btn.clicked.connect(lambda: self._ui._emit("login"))
        self._toolbar.addWidget(self._login_btn)

        # ---- 搜索栏 ----
        self._search_input = QtWidgets.QLineEdit()
        self._search_input.setPlaceholderText("搜索歌曲、歌手、专辑…")
        self._search_input.returnPressed.connect(self._on_search)

        search_btn = QtWidgets.QPushButton("搜索")
        search_btn.clicked.connect(self._on_search)

        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(self._search_input)
        search_layout.addWidget(search_btn)

        # ---- 堆叠面板（登录 vs 搜索结果） ----
        self._stack = QtWidgets.QStackedWidget()

        # 登录面板
        self._login_widget = QtWidgets.QWidget()
        self._qr_label = QtWidgets.QLabel("点击「登录」按钮获取二维码")
        self._qr_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setStyleSheet("font-size: 14px; color: #888;")
        login_layout = QtWidgets.QVBoxLayout(self._login_widget)
        login_layout.addStretch()
        login_layout.addWidget(self._qr_label)
        login_layout.addStretch()
        self._stack.addWidget(self._login_widget)

        # 搜索结果面板
        self._result_list = QtWidgets.QListWidget()
        self._result_list.itemDoubleClicked.connect(self._on_play_selected)
        self._stack.addWidget(self._result_list)

        self._stack.setCurrentIndex(0)

        # ---- 播放控制栏 ----
        self._play_btn = QtWidgets.QPushButton("▶")
        self._play_btn.setFixedSize(48, 48)
        self._play_btn.clicked.connect(self._on_play_pause)

        self._progress = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._progress.sliderMoved.connect(self._on_seek)
        self._progress.setRange(0, 1000)

        self._now_playing_label = QtWidgets.QLabel("未在播放")

        control_layout = QtWidgets.QHBoxLayout()
        control_layout.addWidget(self._play_btn)
        control_layout.addWidget(self._progress, 1)
        control_layout.addWidget(self._now_playing_label)

        # ---- 状态栏 ----
        self._status = self.statusBar()
        self._status.showMessage("就绪", 5000)

        # 登录态 (用于决定占位文案)
        self._authenticated = False

        # ---- 组装 ----
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(search_layout)
        layout.addWidget(self._stack, 1)
        layout.addLayout(control_layout)
        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        keyword = self._search_input.text().strip()
        if keyword:
            self._ui._emit("search", keyword)

    def _on_play_selected(self, item: QtWidgets.QListWidgetItem) -> None:
        song = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if song:
            self._ui._emit("play_song", song)

    def _on_play_pause(self) -> None:
        if self._play_btn.text() == "▶":
            self._ui._emit("resume")
        else:
            self._ui._emit("pause")

    def _on_seek(self, value: int) -> None:
        self._ui._emit("seek", value)

    # ------------------------------------------------------------------
    # UI 更新方法
    # ------------------------------------------------------------------

    def show_welcome(self) -> None:
        # 清除 QR, 切回登录/欢迎面板, 文案根据登录态决定
        self._qr_label.clear()
        self._refresh_placeholder_text()
        self._stack.setCurrentIndex(0)

    def set_authenticated(self, authed: bool) -> None:
        self._authenticated = authed
        self._login_btn.setVisible(not authed)
        # 仅在没有 QR 时同步占位文案
        if self._qr_label.pixmap().isNull():
            self._refresh_placeholder_text()

    def _refresh_placeholder_text(self) -> None:
        if self._authenticated:
            self._qr_label.setText("已登录，使用上方搜索框开始搜索")
        else:
            self._qr_label.setText("点击「登录」按钮获取二维码")

    def show_qrcode(self, data: bytes, qr_type: str) -> None:
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        pixmap = pixmap.scaled(280, 280, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self._qr_label.setPixmap(pixmap)
        self._qr_label.setText("")
        self._stack.setCurrentIndex(0)
        self._status.showMessage(f"请使用手机 {qr_type.upper()} 扫码登录", 30000)

    def show_search_results(self, songs: list[Song]) -> None:
        self._result_list.clear()
        for song in songs:
            text = f"{song.name}  —  {' / '.join(song.singer_names)}"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, song)
            self._result_list.addItem(item)
        self._stack.setCurrentIndex(1)

    def show_playlist(self, playlist: Playlist) -> None:
        self.setWindowTitle(f"QuaverQ — {playlist.name}")
        self._result_list.clear()
        for song in playlist.songs:
            text = f"{song.name}  —  {' / '.join(song.singer_names)}"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, song)
            self._result_list.addItem(item)
        self._stack.setCurrentIndex(1)

    # Qt 端 P0.2 暂时只有歌曲 Tab; 其他类型只在状态栏摘要 (P0.x 再补 QTabWidget)
    def show_singer_results(self, singers: list[Singer]) -> None:
        if singers:
            self._status.showMessage(
                f"找到 {len(singers)} 个歌手 (切到 GTK 后端可看 4 Tab)", 5000
            )

    def show_album_results(self, albums: list[Album]) -> None:
        if albums:
            self._status.showMessage(
                f"找到 {len(albums)} 张专辑 (切到 GTK 后端可看 4 Tab)", 5000
            )

    def show_playlist_results(self, playlists: list[Playlist]) -> None:
        if playlists:
            self._status.showMessage(
                f"找到 {len(playlists)} 个歌单 (切到 GTK 后端可看 4 Tab)", 5000
            )

    def show_album_detail(self, album) -> None:
        # P0.3 Qt 详情页占位; 把歌曲塞进现有 list
        self._status.showMessage(f"专辑: {album.name} ({len(album.songs)} 首)", 5000)
        self.show_search_results(album.songs)

    def show_artist_detail(self, artist) -> None:
        self._status.showMessage(
            f"歌手: {artist.singer.name} ({len(artist.hot_songs)} 首热门)", 5000
        )
        self.show_search_results(artist.hot_songs)

    def show_playlist_detail(self, playlist) -> None:
        self._status.showMessage(
            f"歌单: {playlist.name} ({len(playlist.songs)} 首)", 5000
        )
        self.show_search_results(playlist.songs)

    def show_lyric(self, lyric: Lyric) -> None:
        pass

    def set_now_playing(self, song: Song) -> None:
        self._now_playing_label.setText(
            f"{song.name} — {' / '.join(song.singer_names)}"
        )

    def set_play_state(self, playing: bool) -> None:
        self._play_btn.setText("⏸" if playing else "▶")

    def set_play_mode_indicator(self, mode: str) -> None:
        # Qt 端简化: 状态栏短显当前模式 (P0.x 再上正式按钮)
        labels = {
            "sequence": "顺序",
            "repeat_all": "列表循环",
            "repeat_one": "单曲循环",
            "shuffle": "随机",
        }
        self._status.showMessage(f"模式: {labels.get(mode, mode)}", 3000)

    def set_position(self, position_ms: int, duration_ms: int) -> None:
        if duration_ms > 0:
            self._progress.setValue(int(position_ms / duration_ms * 1000))

    def show_message(self, text: str, level: str = "info") -> None:
        self._status.showMessage(text, 5000)
