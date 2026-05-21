"""UI 抽象基类.

定义所有 UI 后端必须实现的接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from ..core.models import Album, ArtistDetail, Lyric, Playlist, Singer, Song

# 回调类型
EventCallback = Callable[..., None]


class UIBase(ABC):
    """UI 后端抽象基类.

    子类：
        - QtUI    (src/quaverq/ui/qt/app.py)
        - GtkUI   (src/quaverq/ui/gtk/app.py)

    线程模型：UI 更新方法可能从任意线程调用，实现方需自行 marshalling
    到 UI 主线程。
    """

    def __init__(self) -> None:
        self._callbacks: dict[str, EventCallback] = {}
        self._quit_callback: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self) -> None:
        """启动 UI 主循环（阻塞）. """

    @abstractmethod
    def quit(self) -> None:
        """退出主循环."""

    def set_quit_callback(self, callback: Callable[[], None]) -> None:
        """注册退出时清理回调 (在主循环退出前/后触发)."""
        self._quit_callback = callback

    @abstractmethod
    def schedule_periodic(
        self, interval_ms: int, callback: Callable[[], None]
    ) -> None:
        """注册周期性回调（在 UI 主线程执行）."""

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def on(self, event: str, callback: EventCallback) -> None:  # noqa: A003
        """注册事件回调.

        Events:
            search      → (keyword: str)
            play_song   → (song: Song)
            pause       → ()
            resume      → ()
            stop        → ()
            seek        → (position_ms: int)
            volume      → (volume: float)
            login       → ()
        """
        self._callbacks[event] = callback

    def _emit(self, event: str, *args: object) -> None:
        """触发回调."""
        cb = self._callbacks.get(event)
        if cb:
            cb(*args)

    # ------------------------------------------------------------------
    # UI 更新（由 Controller 调用）
    # ------------------------------------------------------------------

    @abstractmethod
    def show_welcome(self) -> None:
        """切回欢迎/默认视图 (登录完成、取消或失败后)."""

    @abstractmethod
    def set_authenticated(self, authed: bool) -> None:
        """更新登录态 (影响欢迎页文案、登录按钮可见性)."""

    @abstractmethod
    def show_qrcode(self, data: bytes, qr_type: str) -> None:
        """展示登录二维码."""

    @abstractmethod
    def show_search_results(self, songs: list[Song]) -> None:
        """展示搜索结果 (歌曲 Tab)."""

    @abstractmethod
    def show_singer_results(self, singers: list[Singer]) -> None:
        """展示歌手搜索结果 (歌手 Tab)."""

    @abstractmethod
    def show_album_results(self, albums: list[Album]) -> None:
        """展示专辑搜索结果 (专辑 Tab)."""

    @abstractmethod
    def show_playlist_results(self, playlists: list[Playlist]) -> None:
        """展示歌单搜索结果 (歌单 Tab)."""

    @abstractmethod
    def show_album_detail(self, album: Album) -> None:
        """进入专辑详情页 (含 songs, 可点播)."""

    @abstractmethod
    def show_artist_detail(self, artist: ArtistDetail) -> None:
        """进入歌手详情页 (含热门歌曲, 可点播)."""

    @abstractmethod
    def show_playlist_detail(self, playlist: Playlist) -> None:
        """进入歌单详情页 (含 songs, 可点播)."""

    @abstractmethod
    def show_playlist(self, playlist: Playlist) -> None:
        """展示歌单."""

    @abstractmethod
    def show_lyric(self, lyric: Lyric) -> None:
        """更新当前歌词数据 (UI 可选择何时渲染)."""

    @abstractmethod
    def update_lyric_position(self, position_ms: int) -> None:
        """同步当前播放位置, UI 据此高亮 active 行 + 滚动."""

    @abstractmethod
    def set_now_playing(self, song: Song) -> None:
        """设置当前播放歌曲信息."""

    @abstractmethod
    def set_play_state(self, playing: bool) -> None:
        """更新播放/暂停状态."""

    @abstractmethod
    def set_play_mode_indicator(self, mode: str) -> None:
        """更新播放模式指示器 (sequence/repeat_all/repeat_one/shuffle)."""

    @abstractmethod
    def set_quality_preference(self, pref: str) -> None:
        """同步当前音质偏好到 UI (high/balanced/standard), settings view 用."""

    @abstractmethod
    def set_liked_state(self, mid: str, liked: bool) -> None:
        """同步某首歌的"喜欢"状态到 UI (底栏 ❤️ + 歌曲行 suffix)."""

    @abstractmethod
    def show_library(
        self,
        liked_songs: list[Song],
        my_playlists: list[Playlist],
        fav_albums: list[Album],
        followed_singers: list[Singer],
    ) -> None:
        """打开资料库视图, 4 Tabs 同时填充."""

    @abstractmethod
    def set_position(self, position_ms: int, duration_ms: int) -> None:
        """更新进度条."""

    @abstractmethod
    def show_message(self, text: str, *, level: str = "info") -> None:
        """显示提示消息 (info / warning / error)."""
