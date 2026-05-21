"""GTK 4 (PyGObject) UI 后端.

基于 GTK 4 + Libadwaita 1.4+ (Adw.ToolbarView) 的完整播放器界面。
"""

from __future__ import annotations

import logging
import signal
from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GLibUnix", "2.0")
from gi.repository import (  # type: ignore[import-untyped]
    Adw,
    Gdk,
    GdkPixbuf,
    Gio,
    GLib,
    GLibUnix,
    Gtk,
    Pango,
)

from ...core.lyric import LyricSync
from ..base import UIBase

if TYPE_CHECKING:
    from ...core.models import Album, Lyric, Playlist, Singer, Song

logger = logging.getLogger(__name__)


def _fmt_ms(ms: int) -> str:
    """毫秒 → m:ss."""
    if ms <= 0:
        return "0:00"
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


class GtkUI(UIBase):
    """基于 GTK 4 + Libadwaita 的 QQ 音乐客户端界面."""

    def __init__(self) -> None:
        super().__init__()
        self._app: Adw.Application | None = None
        self._window: _MainWindow | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._app = Adw.Application(
            application_id="com.quaverq.QuaverQ",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._app.connect("activate", self._on_activate)

        if self._quit_callback is not None:
            cb = self._quit_callback
            self._app.connect("shutdown", lambda _app: cb())

        GLibUnix.signal_add_full(
            GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_sigint
        )

        logger.info("GTK UI 启动")
        self._app.run()

    def _on_activate(self, app: Adw.Application) -> None:
        self._window = _MainWindow(application=app, callbacks=self)
        self._window.present()

    def _on_sigint(self) -> bool:
        if self._app:
            self._app.quit()
        return GLib.SOURCE_REMOVE

    def quit(self) -> None:
        if self._app:
            self._app.quit()

    # ------------------------------------------------------------------
    # 线程派发 / 定时器
    # ------------------------------------------------------------------

    def _glib_idle(self, fn, *args) -> None:
        GLib.idle_add(fn, *args)

    def schedule_periodic(
        self, interval_ms: int, callback: Callable[[], None]
    ) -> None:
        def _tick() -> bool:
            callback()
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(interval_ms, _tick)

    # ------------------------------------------------------------------
    # UI 更新（marshalling 到 GTK 主线程）
    # ------------------------------------------------------------------

    def show_welcome(self) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_welcome()
        self._glib_idle(_do)

    def set_authenticated(self, authed: bool) -> None:
        def _do() -> None:
            if self._window:
                self._window.set_authenticated(authed)
        self._glib_idle(_do)

    def show_qrcode(self, data: bytes, qr_type: str) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_qrcode(data, qr_type)
        self._glib_idle(_do)

    def show_search_results(self, songs: list[Song]) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_search_results(songs)
        self._glib_idle(_do)

    def show_singer_results(self, singers: list[Singer]) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_singer_results(singers)
        self._glib_idle(_do)

    def show_album_results(self, albums: list[Album]) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_album_results(albums)
        self._glib_idle(_do)

    def show_playlist_results(self, playlists: list[Playlist]) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_playlist_results(playlists)
        self._glib_idle(_do)

    def show_album_detail(self, album) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_album_detail(album)
        self._glib_idle(_do)

    def show_artist_detail(self, artist) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_artist_detail(artist)
        self._glib_idle(_do)

    def show_playlist_detail(self, playlist) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_playlist_detail(playlist)
        self._glib_idle(_do)

    def show_playlist(self, playlist: Playlist) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_playlist(playlist)
        self._glib_idle(_do)

    def show_lyric(self, lyric: Lyric) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_lyric(lyric)
        self._glib_idle(_do)

    def update_lyric_position(self, position_ms: int) -> None:
        def _do() -> None:
            if self._window:
                self._window.update_lyric_position(position_ms)
        self._glib_idle(_do)

    def set_now_playing(self, song: Song) -> None:
        def _do() -> None:
            if self._window:
                self._window.set_now_playing(song)
        self._glib_idle(_do)

    def set_play_state(self, playing: bool) -> None:
        def _do() -> None:
            if self._window:
                self._window.set_play_state(playing)
        self._glib_idle(_do)

    def set_play_mode_indicator(self, mode: str) -> None:
        def _do() -> None:
            if self._window:
                self._window.set_play_mode_indicator(mode)
        self._glib_idle(_do)

    def set_quality_preference(self, pref: str) -> None:
        def _do() -> None:
            if self._window:
                self._window.set_quality_preference(pref)
        self._glib_idle(_do)

    def set_liked_state(self, mid: str, liked: bool) -> None:
        def _do() -> None:
            if self._window:
                self._window.set_liked_state(mid, liked)
        self._glib_idle(_do)

    def show_library(self, liked_songs, my_playlists, fav_albums, followed_singers) -> None:
        def _do() -> None:
            if self._window:
                self._window.show_library(
                    liked_songs, my_playlists, fav_albums, followed_singers
                )
        self._glib_idle(_do)

    def set_position(self, position_ms: int, duration_ms: int) -> None:
        def _do() -> None:
            if self._window:
                self._window.set_position(position_ms, duration_ms)
        self._glib_idle(_do)

    def show_message(self, text: str, *, level: str = "info") -> None:
        timeout = {"error": 8, "warning": 5}.get(level, 3)

        def _do() -> None:
            if self._window:
                toast = Adw.Toast.new(text)
                toast.set_timeout(timeout)
                self._window.add_toast(toast)
        self._glib_idle(_do)


class _MainWindow(Adw.ApplicationWindow):
    """主窗口 (GTK 4 + Libadwaita)."""

    def __init__(self, callbacks: GtkUI, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ui = callbacks
        self.set_title("QuaverQ")
        self.set_default_size(1080, 720)

        # =================================================================
        # HeaderBar: 标题 WindowTitle + 左侧返回 (详情页时显示) + 右侧登录
        # =================================================================
        self._login_btn = Gtk.Button(label="登录")
        self._login_btn.add_css_class("suggested-action")
        self._login_btn.connect("clicked", lambda _b: self._ui._emit("login"))

        # 设置按钮 (在 header 右侧, 登录按钮左)
        self._settings_btn = Gtk.Button.new_from_icon_name(
            "emblem-system-symbolic"
        )
        self._settings_btn.add_css_class("flat")
        self._settings_btn.set_tooltip_text("设置")
        self._settings_btn.connect(
            "clicked", lambda _b: self._push_settings_view()
        )

        self._back_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._back_btn.add_css_class("flat")
        self._back_btn.set_visible(False)

        # 资料库入口 (HeaderBar 左侧, 仅登录后可见)
        self._library_btn = Gtk.Button.new_from_icon_name(
            "folder-music-symbolic"
        )
        self._library_btn.add_css_class("flat")
        self._library_btn.set_tooltip_text("资料库")
        self._library_btn.set_visible(False)
        self._library_btn.connect(
            "clicked", lambda _b: self._ui._emit("open_library")
        )
        # 实际 click 处理在 _on_nav_page_changed 之后设置
        # (这里仅占位; nav_view 还没构造)

        self._title_widget = Adw.WindowTitle.new("QuaverQ", "QQ 音乐")

        header = Adw.HeaderBar()
        header.pack_start(self._back_btn)
        header.pack_start(self._library_btn)
        header.set_title_widget(self._title_widget)
        header.pack_end(self._login_btn)
        header.pack_end(self._settings_btn)

        # =================================================================
        # 独立搜索栏 (HeaderBar 下方, 居中 clamp)
        # =================================================================
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("搜索歌曲、歌手、专辑…")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("activate", self._on_search)

        search_clamp = Adw.Clamp()
        search_clamp.set_maximum_size(640)
        search_clamp.set_tightening_threshold(560)
        search_clamp.set_child(self._search_entry)
        search_clamp.set_margin_top(8)
        search_clamp.set_margin_bottom(8)
        search_clamp.set_margin_start(12)
        search_clamp.set_margin_end(12)

        # =================================================================
        # 主内容堆栈
        # =================================================================
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_vexpand(True)

        self._stack.add_named(self._build_welcome_page(), "welcome")
        self._stack.add_named(self._build_login_page(), "login")
        self._stack.add_named(self._build_results_page(), "results")
        self._stack.set_visible_child_name("welcome")

        # =================================================================
        # 底部播放控制
        # =================================================================
        control_box = self._build_player_bar()

        # =================================================================
        # Adw.NavigationView — 详情页 push/pop 支持滑动返回
        # 主页 = self._stack (welcome/login/results), 详情页是 push 上去的
        # =================================================================
        self._home_page = Adw.NavigationPage.new(self._stack, "QuaverQ")
        self._home_page.set_tag("home")

        self._nav_view = Adw.NavigationView()
        self._nav_view.add(self._home_page)

        # back 按钮 + 监听页面切换更新可见性/标题
        self._back_btn.connect(
            "clicked", lambda _b: self._nav_view.pop()
        )
        self._nav_view.connect(
            "notify::visible-page", self._on_nav_page_changed
        )

        # =================================================================
        # ToolbarView 组装
        # =================================================================
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.add_top_bar(search_clamp)
        toolbar_view.set_content(self._nav_view)
        toolbar_view.add_bottom_bar(control_box)

        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(toolbar_view)
        self.set_content(self._toast_overlay)

        # 歌词同步状态
        self._current_lyric: "Lyric | None" = None
        self._lyric_sync = LyricSync()
        self._lyric_labels: list[Gtk.Label] = []
        self._lyric_active_idx: int = -1
        self._lyric_scrolled: Gtk.ScrolledWindow | None = None

        # Settings 状态
        self._quality_pref: str = "balanced"
        self._authenticated: bool = False

        # 当前播放歌的 mid + 喜欢态 (UI 内本地, 跟 library 同步)
        self._current_mid: str = ""
        self._current_liked: bool = False

    # ------------------------------------------------------------------
    # 各分页构建
    # ------------------------------------------------------------------

    def _build_welcome_page(self) -> Gtk.Widget:
        """欢迎页 (启动初始 / 未登录态 / 登录完成后)."""
        self._welcome_page = Adw.StatusPage()
        self._welcome_page.set_icon_name("audio-headphones-symbolic")

        self._welcome_login_btn = Gtk.Button(label="扫码登录")
        self._welcome_login_btn.add_css_class("pill")
        self._welcome_login_btn.add_css_class("suggested-action")
        self._welcome_login_btn.set_halign(Gtk.Align.CENTER)
        self._welcome_login_btn.connect(
            "clicked", lambda _b: self._ui._emit("login")
        )
        self._welcome_page.set_child(self._welcome_login_btn)

        self._apply_auth_state(False)
        return self._welcome_page

    def _apply_auth_state(self, authed: bool) -> None:
        self._authenticated = authed
        # 资料库入口跟登录态绑定
        self._library_btn.set_visible(authed)
        if authed:
            self._welcome_page.set_title("已就绪")
            self._welcome_page.set_description(
                "在上方搜索框输入关键词查找音乐"
            )
            self._welcome_login_btn.set_visible(False)
            self._login_btn.set_visible(False)
        else:
            self._welcome_page.set_title("欢迎使用 QuaverQ")
            self._welcome_page.set_description(
                "在上方搜索框输入关键词查找音乐\n"
                "点击下方按钮扫码登录以播放完整曲目"
            )
            self._welcome_login_btn.set_visible(True)
            self._login_btn.set_visible(True)

    def _build_login_page(self) -> Gtk.Widget:
        """扫码登录页 (居中卡片)."""
        self._qr_picture = Gtk.Picture()
        self._qr_picture.set_size_request(260, 260)
        self._qr_picture.set_can_shrink(False)
        self._qr_picture.set_halign(Gtk.Align.CENTER)

        qr_title = Gtk.Label(label="扫码登录")
        qr_title.add_css_class("title-3")
        qr_title.set_halign(Gtk.Align.CENTER)

        self._qr_hint = Gtk.Label(label="正在获取二维码…")
        self._qr_hint.add_css_class("dim-label")
        self._qr_hint.set_halign(Gtk.Align.CENTER)
        self._qr_hint.set_wrap(True)
        self._qr_hint.set_max_width_chars(36)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        inner.set_margin_top(28)
        inner.set_margin_bottom(28)
        inner.set_margin_start(28)
        inner.set_margin_end(28)
        inner.append(qr_title)
        inner.append(self._qr_picture)
        inner.append(self._qr_hint)

        card = Gtk.Frame()
        card.add_css_class("card")
        card.set_child(inner)
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)

        wrap = Gtk.Box()
        wrap.set_halign(Gtk.Align.CENTER)
        wrap.set_valign(Gtk.Align.CENTER)
        wrap.set_vexpand(True)
        wrap.set_hexpand(True)
        wrap.append(card)
        return wrap

    def _build_results_page(self) -> Gtk.Widget:
        """搜索结果 — 4 Tabs (歌曲/歌手/专辑/歌单), Libadwaita 风格.

        每 Tab 是 Adw.ViewStack 的一个 page, 用带 icon-name 的 ViewSwitcher 切换.
        每 Tab 内容为 ScrolledWindow 包 Gtk.ListBox (boxed-list) 装多个 Adw.ActionRow.
        """
        self._results_view_stack = Adw.ViewStack()

        # 4 个 Tab 内容; 每个都有自己的 ListBox 引用以便 show_*_results 重填
        self._song_listbox = self._make_results_listbox(self._on_song_row_activated)
        self._song_data: list[Song] = []
        self._results_view_stack.add_titled_with_icon(
            self._wrap_in_scroll(self._song_listbox),
            "songs", "歌曲", "emblem-music-symbolic",
        )

        self._singer_listbox = self._make_results_listbox(self._on_singer_row_activated)
        self._singer_data: list[Singer] = []
        self._results_view_stack.add_titled_with_icon(
            self._wrap_in_scroll(self._singer_listbox),
            "singers", "歌手", "avatar-default-symbolic",
        )

        self._album_listbox = self._make_results_listbox(self._on_album_row_activated)
        self._album_data: list[Album] = []
        self._results_view_stack.add_titled_with_icon(
            self._wrap_in_scroll(self._album_listbox),
            "albums", "专辑", "media-optical-symbolic",
        )

        self._playlist_listbox = self._make_results_listbox(self._on_playlist_row_activated)
        self._playlist_data: list[Playlist] = []
        self._results_view_stack.add_titled_with_icon(
            self._wrap_in_scroll(self._playlist_listbox),
            "playlists", "歌单", "view-list-symbolic",
        )

        # ViewSwitcher 在 stack 上方居中
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self._results_view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.set_margin_top(4)
        switcher.set_margin_bottom(8)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.append(switcher)
        box.append(self._results_view_stack)
        box.set_vexpand(True)
        return box

    def _make_results_listbox(self, on_activate: Callable) -> Gtk.ListBox:
        """构造一个 boxed-list 风格的 Gtk.ListBox (每个 Tab 一个)."""
        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.connect("row-activated", on_activate)
        return lb

    def _wrap_in_scroll(self, listbox: Gtk.ListBox) -> Gtk.Widget:
        """ListBox → 装到 ScrolledWindow + Adw.Clamp 限宽."""
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(700)
        clamp.set_child(listbox)
        clamp.set_margin_top(8)
        clamp.set_margin_bottom(16)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(clamp)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        return scrolled

    # ------------------------------------------------------------------
    # ActionRow 构造 (按类型分别)
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_duration(seconds: int) -> str:
        if seconds <= 0:
            return ""
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"

    def _make_song_row(self, s: Song, index: int) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(GLib.markup_escape_text(s.name))
        sub = " / ".join(s.singer_names)
        if s.album_name:
            sub = f"{sub}  ·  {s.album_name}" if sub else s.album_name
        row.set_subtitle(GLib.markup_escape_text(sub))
        row.set_activatable(True)

        icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        icon.add_css_class("dim-label")
        row.add_prefix(icon)

        dur_text = self._fmt_duration(s.duration)
        if dur_text:
            dur = Gtk.Label(label=dur_text)
            dur.add_css_class("numeric")
            dur.add_css_class("dim-label")
            row.add_suffix(dur)

        row._quaver_index = index
        return row

    def _make_singer_row(self, s: Singer, index: int) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(GLib.markup_escape_text(s.name))
        row.set_activatable(True)
        icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        icon.add_css_class("dim-label")
        row.add_prefix(icon)
        chevron = Gtk.Image.new_from_icon_name("go-next-symbolic")
        chevron.add_css_class("dim-label")
        row.add_suffix(chevron)
        row._quaver_index = index
        return row

    def _make_album_row(self, a: Album, index: int) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(GLib.markup_escape_text(a.name))
        sub_parts = []
        if a.singers:
            sub_parts.append(" / ".join(sg.name for sg in a.singers))
        if a.publish_date:
            sub_parts.append(a.publish_date)
        if sub_parts:
            row.set_subtitle(GLib.markup_escape_text("  ·  ".join(sub_parts)))
        row.set_activatable(True)
        icon = Gtk.Image.new_from_icon_name("media-optical-symbolic")
        icon.add_css_class("dim-label")
        row.add_prefix(icon)
        chevron = Gtk.Image.new_from_icon_name("go-next-symbolic")
        chevron.add_css_class("dim-label")
        row.add_suffix(chevron)
        row._quaver_index = index
        return row

    def _make_playlist_row(self, p: Playlist, index: int) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(GLib.markup_escape_text(p.name))
        sub_parts = []
        if p.creator:
            sub_parts.append(p.creator)
        if p.song_count:
            sub_parts.append(f"{p.song_count} 首")
        if sub_parts:
            row.set_subtitle(GLib.markup_escape_text("  ·  ".join(sub_parts)))
        row.set_activatable(True)
        icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
        icon.add_css_class("dim-label")
        row.add_prefix(icon)
        chevron = Gtk.Image.new_from_icon_name("go-next-symbolic")
        chevron.add_css_class("dim-label")
        row.add_suffix(chevron)
        row._quaver_index = index
        return row

    @staticmethod
    def _clear_listbox(lb: Gtk.ListBox) -> None:
        child = lb.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            lb.remove(child)
            child = nxt

    def _build_player_bar(self) -> Gtk.Box:
        """底部播放控制条 — 三栏布局：曲目信息 | 播放键 | 进度."""

        # 左：封面占位 + 标题/艺人
        self._cover = Gtk.Image.new_from_icon_name(
            "audio-x-generic-symbolic"
        )
        self._cover.set_pixel_size(40)
        self._cover.add_css_class("dim-label")
        self._cover.set_valign(Gtk.Align.CENTER)

        self._now_title = Gtk.Label(label="未在播放")
        self._now_title.set_xalign(0)
        self._now_title.add_css_class("heading")
        self._now_title.set_ellipsize(Pango.EllipsizeMode.END)

        self._now_artist = Gtk.Label(label="")
        self._now_artist.set_xalign(0)
        self._now_artist.add_css_class("caption")
        self._now_artist.add_css_class("dim-label")
        self._now_artist.set_ellipsize(Pango.EllipsizeMode.END)

        now_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        now_info.set_valign(Gtk.Align.CENTER)
        now_info.append(self._now_title)
        now_info.append(self._now_artist)

        track_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        track_inner.append(self._cover)
        track_inner.append(now_info)

        # 整个 track 区可点击 push LyricView
        track_box = Gtk.Button()
        track_box.set_child(track_inner)
        track_box.add_css_class("flat")
        track_box.set_size_request(260, -1)
        track_box.set_tooltip_text("查看歌词")
        track_box.connect("clicked", lambda _b: self._push_lyric_view())

        # 中：prev / play / next / mode 4 个按钮
        self._prev_btn = Gtk.Button.new_from_icon_name(
            "media-skip-backward-symbolic"
        )
        self._prev_btn.add_css_class("flat")
        self._prev_btn.set_valign(Gtk.Align.CENTER)
        self._prev_btn.connect(
            "clicked", lambda _b: self._ui._emit("prev")
        )

        self._play_btn = Gtk.Button()
        self._play_btn.set_icon_name("media-playback-start-symbolic")
        self._play_btn.add_css_class("circular")
        self._play_btn.add_css_class("suggested-action")
        self._play_btn.set_valign(Gtk.Align.CENTER)
        self._play_btn.connect("clicked", self._on_play_pause)

        self._next_btn = Gtk.Button.new_from_icon_name(
            "media-skip-forward-symbolic"
        )
        self._next_btn.add_css_class("flat")
        self._next_btn.set_valign(Gtk.Align.CENTER)
        self._next_btn.connect(
            "clicked", lambda _b: self._ui._emit("next")
        )

        self._mode_btn = Gtk.Button.new_from_icon_name(
            "media-playlist-consecutive-symbolic"
        )
        self._mode_btn.add_css_class("flat")
        self._mode_btn.set_valign(Gtk.Align.CENTER)
        self._mode_btn.set_tooltip_text("顺序播放")
        self._mode_btn.connect(
            "clicked", lambda _b: self._ui._emit("cycle_play_mode")
        )

        # 收藏按钮 — 用 star 系列, 空心 vs 实心对比明显
        # 未播放时禁用
        self._like_btn = Gtk.Button.new_from_icon_name("non-starred-symbolic")
        self._like_btn.add_css_class("flat")
        self._like_btn.set_valign(Gtk.Align.CENTER)
        self._like_btn.set_tooltip_text("加入「我喜欢」")
        self._like_btn.set_sensitive(False)
        self._like_btn.connect(
            "clicked", lambda _b: self._ui._emit("toggle_like_current")
        )

        # 右：时间 - 进度 - 时间
        self._time_curr = self._make_time_label(align_right=True)
        self._time_total = self._make_time_label(align_right=False)

        self._progress = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 1000, 1
        )
        self._progress.set_draw_value(False)
        self._progress.set_hexpand(True)
        self._progress.connect("value-changed", self._on_seek)

        progress_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        progress_box.set_hexpand(True)
        progress_box.append(self._time_curr)
        progress_box.append(self._progress)
        progress_box.append(self._time_total)

        # 4 个传输按钮分组
        transport = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        transport.append(self._prev_btn)
        transport.append(self._play_btn)
        transport.append(self._next_btn)
        transport.append(self._mode_btn)
        transport.append(self._like_btn)

        control_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=16
        )
        control_box.set_margin_start(16)
        control_box.set_margin_end(16)
        control_box.set_margin_top(10)
        control_box.set_margin_bottom(10)
        control_box.append(track_box)
        control_box.append(transport)
        control_box.append(progress_box)
        return control_box

    @staticmethod
    def _make_time_label(*, align_right: bool) -> Gtk.Label:
        lbl = Gtk.Label(label="0:00")
        lbl.add_css_class("numeric")
        lbl.add_css_class("caption")
        lbl.add_css_class("dim-label")
        lbl.set_xalign(1.0 if align_right else 0.0)
        lbl.set_width_chars(5)
        lbl.set_valign(Gtk.Align.CENTER)
        return lbl

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def add_toast(self, toast: Adw.Toast) -> None:
        self._toast_overlay.add_toast(toast)

    def _on_search(self, _widget) -> None:
        keyword = self._search_entry.get_text().strip()
        if keyword:
            self._ui._emit("search", keyword)

    def _on_song_row_activated(self, _lb, row: Gtk.ListBoxRow) -> None:
        idx = getattr(row, "_quaver_index", -1)
        if 0 <= idx < len(self._song_data):
            # 把整个 tab 的歌当作上下文入队
            self._ui._emit(
                "play_song", self._song_data[idx], self._song_data
            )

    def _on_singer_row_activated(self, _lb, row: Gtk.ListBoxRow) -> None:
        idx = getattr(row, "_quaver_index", -1)
        if 0 <= idx < len(self._singer_data):
            self._ui._emit("open_singer", self._singer_data[idx])

    def _on_album_row_activated(self, _lb, row: Gtk.ListBoxRow) -> None:
        idx = getattr(row, "_quaver_index", -1)
        if 0 <= idx < len(self._album_data):
            self._ui._emit("open_album", self._album_data[idx])

    def _on_playlist_row_activated(self, _lb, row: Gtk.ListBoxRow) -> None:
        idx = getattr(row, "_quaver_index", -1)
        if 0 <= idx < len(self._playlist_data):
            self._ui._emit("open_playlist", self._playlist_data[idx])

    def _on_play_pause(self, _btn) -> None:
        if self._play_btn.get_icon_name() == "media-playback-start-symbolic":
            self._ui._emit("resume")
        else:
            self._ui._emit("pause")

    def _on_nav_page_changed(self, _nv, _pspec) -> None:
        page = self._nav_view.get_visible_page()
        is_home = page is None or page.get_tag() == "home"
        self._back_btn.set_visible(not is_home)
        if is_home:
            self._title_widget.set_title("QuaverQ")
            self._title_widget.set_subtitle("QQ 音乐")
        else:
            self._title_widget.set_title(page.get_title() or "详情")
            self._title_widget.set_subtitle("")

    def _on_seek(self, scale: Gtk.Scale) -> None:
        self._ui._emit("seek", int(scale.get_value()))

    # ------------------------------------------------------------------
    # UI 更新方法
    # ------------------------------------------------------------------

    def show_welcome(self) -> None:
        # 先 pop 掉所有 push 的详情页/设置页, 回到主页
        self._nav_view.pop_to_tag("home")
        self._stack.set_visible_child_name("welcome")

    def set_authenticated(self, authed: bool) -> None:
        self._apply_auth_state(authed)

    def show_qrcode(self, data: bytes, qr_type: str) -> None:
        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(data)
        loader.close()
        pixbuf = loader.get_pixbuf()
        target = 260
        if pixbuf.get_width() != target:
            pixbuf = pixbuf.scale_simple(
                target, target, GdkPixbuf.InterpType.NEAREST
            )
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        self._qr_picture.set_paintable(texture)
        self._qr_hint.set_label(f"请使用手机 {qr_type.upper()} 扫码登录")
        # 弹掉所有 push 的页面 (settings/详情页) 再切到 login 子页, 确保可见
        self._nav_view.pop_to_tag("home")
        self._stack.set_visible_child_name("login")

    def show_search_results(self, songs: list[Song]) -> None:
        self._clear_listbox(self._song_listbox)
        self._song_data = list(songs)
        for i, s in enumerate(self._song_data):
            self._song_listbox.append(self._make_song_row(s, i))
        # 在详情页/设置页搜索时, 弹回 home 才能看到结果
        self._nav_view.pop_to_tag("home")
        self._stack.set_visible_child_name("results")
        self._results_view_stack.set_visible_child_name("songs")

    def show_singer_results(self, singers: list[Singer]) -> None:
        self._clear_listbox(self._singer_listbox)
        self._singer_data = list(singers)
        for i, s in enumerate(self._singer_data):
            self._singer_listbox.append(self._make_singer_row(s, i))

    def show_album_results(self, albums: list[Album]) -> None:
        self._clear_listbox(self._album_listbox)
        self._album_data = list(albums)
        for i, a in enumerate(self._album_data):
            self._album_listbox.append(self._make_album_row(a, i))

    def show_playlist_results(self, playlists: list[Playlist]) -> None:
        self._clear_listbox(self._playlist_listbox)
        self._playlist_data = list(playlists)
        for i, p in enumerate(self._playlist_data):
            self._playlist_listbox.append(self._make_playlist_row(p, i))

    def show_playlist(self, playlist: Playlist) -> None:
        # 进入歌单详情 = push 一个 PlaylistView NavigationPage
        self.show_playlist_detail(playlist)

    # ------------------------------------------------------------------
    # 详情页 (Adw.NavigationView push)
    # ------------------------------------------------------------------

    def show_album_detail(self, album: "Album") -> None:
        page = self._build_detail_page(
            title=album.name or "专辑",
            subtitle=" / ".join(s.name for s in album.singers) if album.singers else "",
            extra_meta=album.publish_date,
            description=album.description,
            icon_name="media-optical-symbolic",
            songs=album.songs,
        )
        self._nav_view.push(page)

    def show_artist_detail(self, artist: "ArtistDetail") -> None:
        page = self._build_detail_page(
            title=artist.singer.name or "歌手",
            subtitle="热门歌曲",
            extra_meta=f"{len(artist.hot_songs)} 首",
            description=artist.description,
            icon_name="avatar-default-symbolic",
            songs=artist.hot_songs,
        )
        self._nav_view.push(page)

    def show_playlist_detail(self, playlist: "Playlist") -> None:
        meta_parts = []
        if playlist.creator:
            meta_parts.append(f"by {playlist.creator}")
        if playlist.song_count:
            meta_parts.append(f"{playlist.song_count} 首")
        page = self._build_detail_page(
            title=playlist.name or "歌单",
            subtitle="  ·  ".join(meta_parts),
            extra_meta="",
            description=playlist.description,
            icon_name="view-list-symbolic",
            songs=playlist.songs,
        )
        self._nav_view.push(page)

    def _build_detail_page(
        self,
        *,
        title: str,
        subtitle: str,
        extra_meta: str,
        description: str,
        icon_name: str,
        songs: list["Song"],
    ) -> Adw.NavigationPage:
        """统一详情页布局: 顶部 hero (icon+title+subtitle+desc) + boxed-list songs."""
        # Hero 块
        hero_icon = Gtk.Image.new_from_icon_name(icon_name)
        hero_icon.set_pixel_size(96)
        hero_icon.add_css_class("dim-label")

        hero_title = Gtk.Label(label=GLib.markup_escape_text(title))
        hero_title.add_css_class("title-2")
        hero_title.set_xalign(0)
        hero_title.set_wrap(True)

        hero_meta_parts = [p for p in (subtitle, extra_meta) if p]
        hero_subtitle = Gtk.Label(
            label=GLib.markup_escape_text("  ·  ".join(hero_meta_parts))
        )
        hero_subtitle.add_css_class("caption")
        hero_subtitle.add_css_class("dim-label")
        hero_subtitle.set_xalign(0)
        hero_subtitle.set_wrap(True)

        hero_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hero_text.set_valign(Gtk.Align.CENTER)
        hero_text.set_hexpand(True)
        hero_text.append(hero_title)
        if hero_meta_parts:
            hero_text.append(hero_subtitle)

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        hero.set_margin_top(8)
        hero.set_margin_bottom(8)
        hero.append(hero_icon)
        hero.append(hero_text)

        # 描述 (折叠到 3 行)
        desc_widget = None
        if description:
            desc_widget = Gtk.Label(label=description)
            desc_widget.add_css_class("dim-label")
            desc_widget.set_xalign(0)
            desc_widget.set_wrap(True)
            desc_widget.set_lines(3)
            desc_widget.set_ellipsize(Pango.EllipsizeMode.END)
            desc_widget.set_margin_top(4)
            desc_widget.set_margin_bottom(8)

        # 歌曲 ListBox (boxed-list); detail 页用独立 listbox + 独立 song_data
        detail_song_data: list[Song] = list(songs)

        def _on_row_activated(_lb, row: Gtk.ListBoxRow) -> None:
            idx = getattr(row, "_quaver_index", -1)
            if 0 <= idx < len(detail_song_data):
                # 整张专辑/歌单/歌手页歌曲作为队列上下文
                self._ui._emit(
                    "play_song", detail_song_data[idx], detail_song_data
                )

        songs_lb = Gtk.ListBox()
        songs_lb.set_selection_mode(Gtk.SelectionMode.NONE)
        songs_lb.add_css_class("boxed-list")
        songs_lb.connect("row-activated", _on_row_activated)
        for i, s in enumerate(detail_song_data):
            songs_lb.append(self._make_song_row(s, i))

        # 容器
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content_box.append(hero)
        if desc_widget is not None:
            content_box.append(desc_widget)
        content_box.append(songs_lb)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(700)
        clamp.set_child(content_box)
        clamp.set_margin_top(12)
        clamp.set_margin_bottom(16)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(clamp)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        page = Adw.NavigationPage.new(scrolled, title or "详情")
        return page

    def show_lyric(self, lyric: "Lyric") -> None:
        """更新当前歌词数据 + (如果 LyricView 已 push) 重建标签."""
        self._current_lyric = lyric
        self._lyric_sync.set_lyric(lyric)
        # 如果当前在 LyricView, 重建内容
        page = self._nav_view.get_visible_page()
        if page is not None and page.get_tag() == "lyric":
            self._populate_lyric_labels()

    def update_lyric_position(self, position_ms: int) -> None:
        """schedule_periodic 调用; 高亮当前行 + 自动滚动."""
        if not self._lyric_labels:
            return
        idx = self._lyric_sync.line_at(position_ms)
        if idx == self._lyric_active_idx:
            return
        # 清旧高亮
        if 0 <= self._lyric_active_idx < len(self._lyric_labels):
            old = self._lyric_labels[self._lyric_active_idx]
            old.remove_css_class("title-3")
            old.add_css_class("dim-label")
        # 加新高亮
        if 0 <= idx < len(self._lyric_labels):
            new = self._lyric_labels[idx]
            new.remove_css_class("dim-label")
            new.add_css_class("title-3")
            # 居中滚动
            if self._lyric_scrolled is not None:
                self._scroll_lyric_to(idx)
        self._lyric_active_idx = idx

    # ------------------------------------------------------------------
    # LyricView 构造
    # ------------------------------------------------------------------

    def _push_lyric_view(self) -> None:
        if self._current_lyric is None or not self._current_lyric.lines:
            return  # 没歌词不展示空页
        # 已经在 lyric view 不重复 push
        page = self._nav_view.get_visible_page()
        if page is not None and page.get_tag() == "lyric":
            return
        self._nav_view.push(self._build_lyric_page())

    def _build_lyric_page(self) -> Adw.NavigationPage:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(64)
        box.set_margin_start(12)
        box.set_margin_end(12)

        self._lyric_labels = []
        self._lyric_active_idx = -1
        self._populate_lyric_labels_into(box)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(640)
        clamp.set_child(box)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(clamp)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self._lyric_scrolled = scrolled

        page = Adw.NavigationPage.new(scrolled, "歌词")
        page.set_tag("lyric")
        return page

    def _populate_lyric_labels(self) -> None:
        """LyricView 中重建标签 (在切歌时调用)."""
        if self._lyric_scrolled is None:
            return
        clamp = self._lyric_scrolled.get_child()
        box = clamp.get_child() if clamp else None
        if box is None:
            return
        # 清空旧 label
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt
        self._lyric_labels = []
        self._lyric_active_idx = -1
        self._populate_lyric_labels_into(box)

    def _populate_lyric_labels_into(self, box: Gtk.Box) -> None:
        if self._current_lyric is None:
            return
        for ln in self._current_lyric.lines:
            text = ln.text if ln.text else "♪"
            label = Gtk.Label(label=text)
            label.set_xalign(0.5)
            label.set_wrap(True)
            label.add_css_class("dim-label")
            label.add_css_class("body")
            box.append(label)
            self._lyric_labels.append(label)

    def _scroll_lyric_to(self, idx: int) -> None:
        """把指定行滚动到视口中心."""
        if self._lyric_scrolled is None or not (0 <= idx < len(self._lyric_labels)):
            return
        label = self._lyric_labels[idx]
        vadj = self._lyric_scrolled.get_vadjustment()
        if vadj is None:
            return
        # 用 label 的 allocation 计算居中
        alloc = label.get_allocation()
        if alloc.height <= 0:
            return
        target = alloc.y - vadj.get_page_size() / 2 + alloc.height / 2
        target = max(vadj.get_lower(), min(vadj.get_upper() - vadj.get_page_size(), target))
        vadj.set_value(target)

    # ------------------------------------------------------------------
    # Settings (P0.6)
    # ------------------------------------------------------------------

    _QUALITY_KEYS = ("high", "balanced", "standard")
    _QUALITY_LABELS = {
        "high": "高品质 (FLAC / 320k, 优先)",
        "balanced": "均衡 (320k / 192k / 128k)",
        "standard": "标准 (128k, 省流量)",
    }

    def set_quality_preference(self, pref: str) -> None:
        if pref not in self._QUALITY_KEYS:
            pref = "balanced"
        self._quality_pref = pref

    # ------------------------------------------------------------------
    # LibraryView (P1.3) — 4 Tabs 资料库
    # ------------------------------------------------------------------

    def show_library(
        self,
        liked_songs: list["Song"],
        my_playlists: list["Playlist"],
        fav_albums: list["Album"],
        followed_singers: list["Singer"],
    ) -> None:
        # 已在 library 不重复 push
        page = self._nav_view.get_visible_page()
        if page is not None and page.get_tag() == "library":
            return
        self._nav_view.push(
            self._build_library_page(
                liked_songs, my_playlists, fav_albums, followed_singers
            )
        )

    def _build_library_page(
        self,
        liked_songs: list["Song"],
        my_playlists: list["Playlist"],
        fav_albums: list["Album"],
        followed_singers: list["Singer"],
    ) -> Adw.NavigationPage:
        view_stack = Adw.ViewStack()

        # Tab 1: 我喜欢
        view_stack.add_titled_with_icon(
            self._build_library_songs_tab(liked_songs),
            "liked", "我喜欢", "starred-symbolic",
        )
        # Tab 2: 我的歌单
        view_stack.add_titled_with_icon(
            self._build_library_playlists_tab(my_playlists),
            "playlists", "我的歌单", "view-list-symbolic",
        )
        # Tab 3: 收藏的专辑
        view_stack.add_titled_with_icon(
            self._build_library_albums_tab(fav_albums),
            "albums", "收藏的专辑", "media-optical-symbolic",
        )
        # Tab 4: 关注的歌手
        view_stack.add_titled_with_icon(
            self._build_library_singers_tab(followed_singers),
            "singers", "关注的歌手", "avatar-default-symbolic",
        )

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.set_margin_top(4)
        switcher.set_margin_bottom(8)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.append(switcher)
        box.append(view_stack)
        box.set_vexpand(True)

        page = Adw.NavigationPage.new(box, "资料库")
        page.set_tag("library")
        return page

    def _build_library_songs_tab(self, songs: list["Song"]) -> Gtk.Widget:
        # 复用 _make_song_row, 但用独立 song_data 闭包让点击播放走整个列表上下文
        lib_data = list(songs)

        def _on_activate(_lb, row):
            idx = getattr(row, "_quaver_index", -1)
            if 0 <= idx < len(lib_data):
                self._ui._emit("play_song", lib_data[idx], lib_data)

        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.connect("row-activated", _on_activate)
        for i, s in enumerate(lib_data):
            lb.append(self._make_song_row(s, i))

        return self._library_wrap(lb, empty_text="还没有喜欢的歌曲")

    def _build_library_playlists_tab(self, playlists: list["Playlist"]) -> Gtk.Widget:
        data = list(playlists)

        def _on_activate(_lb, row):
            idx = getattr(row, "_quaver_index", -1)
            if 0 <= idx < len(data):
                self._ui._emit("open_playlist", data[idx])

        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.connect("row-activated", _on_activate)
        for i, p in enumerate(data):
            lb.append(self._make_playlist_row(p, i))

        return self._library_wrap(lb, empty_text="还没有创建的歌单")

    def _build_library_albums_tab(self, albums: list["Album"]) -> Gtk.Widget:
        data = list(albums)

        def _on_activate(_lb, row):
            idx = getattr(row, "_quaver_index", -1)
            if 0 <= idx < len(data):
                self._ui._emit("open_album", data[idx])

        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.connect("row-activated", _on_activate)
        for i, a in enumerate(data):
            lb.append(self._make_album_row(a, i))

        return self._library_wrap(lb, empty_text="还没有收藏的专辑")

    def _build_library_singers_tab(self, singers: list["Singer"]) -> Gtk.Widget:
        data = list(singers)

        def _on_activate(_lb, row):
            idx = getattr(row, "_quaver_index", -1)
            if 0 <= idx < len(data):
                self._ui._emit("open_singer", data[idx])

        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.connect("row-activated", _on_activate)
        for i, s in enumerate(data):
            lb.append(self._make_singer_row(s, i))

        return self._library_wrap(lb, empty_text="还没有关注的歌手")

    def _library_wrap(self, listbox: Gtk.ListBox, *, empty_text: str) -> Gtk.Widget:
        """ListBox 包 ScrolledWindow + Clamp; 空时显示提示文字."""
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(700)
        clamp.set_margin_top(8)
        clamp.set_margin_bottom(16)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)

        # 空状态
        if listbox.get_first_child() is None:
            sp = Adw.StatusPage()
            sp.set_icon_name("audio-x-generic-symbolic")
            sp.set_title(empty_text)
            sp.set_vexpand(True)
            return sp

        clamp.set_child(listbox)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(clamp)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        return scrolled

    def _push_settings_view(self) -> None:
        # 已经在 settings 不重复 push
        page = self._nav_view.get_visible_page()
        if page is not None and page.get_tag() == "settings":
            return
        self._nav_view.push(self._build_settings_page())

    def _build_settings_page(self) -> Adw.NavigationPage:
        # 音质组
        quality_group = Adw.PreferencesGroup()
        quality_group.set_title("音质")
        quality_group.set_description("拿不到首选时自动降级到次选")

        quality_model = Gtk.StringList()
        for key in self._QUALITY_KEYS:
            quality_model.append(self._QUALITY_LABELS[key])

        combo = Adw.ComboRow()
        combo.set_title("播放音质")
        combo.set_model(quality_model)
        try:
            combo.set_selected(self._QUALITY_KEYS.index(self._quality_pref))
        except ValueError:
            combo.set_selected(1)  # balanced

        def _on_quality_change(row: Adw.ComboRow, _pspec) -> None:
            idx = row.get_selected()
            if 0 <= idx < len(self._QUALITY_KEYS):
                new_key = self._QUALITY_KEYS[idx]
                if new_key != self._quality_pref:
                    self._quality_pref = new_key
                    self._ui._emit("set_quality", new_key)

        combo.connect("notify::selected", _on_quality_change)
        quality_group.add(combo)

        # 账号组
        account_group = Adw.PreferencesGroup()
        account_group.set_title("账号")

        account_row = Adw.ActionRow()
        if self._authenticated:
            account_row.set_title("已登录")
            account_row.set_subtitle("QQ 音乐 VIP 状态由服务端决定")
            logout_btn = Gtk.Button(label="退出登录")
            logout_btn.add_css_class("destructive-action")
            logout_btn.set_valign(Gtk.Align.CENTER)
            logout_btn.connect(
                "clicked", lambda _b: self._ui._emit("logout")
            )
            account_row.add_suffix(logout_btn)
        else:
            account_row.set_title("未登录")
            account_row.set_subtitle("点击「登录」扫码")
            login_btn = Gtk.Button(label="登录")
            login_btn.add_css_class("suggested-action")
            login_btn.set_valign(Gtk.Align.CENTER)
            login_btn.connect(
                "clicked", lambda _b: self._ui._emit("login")
            )
            account_row.add_suffix(login_btn)
        account_group.add(account_row)

        # 关于
        about_group = Adw.PreferencesGroup()
        about_group.set_title("关于")
        about_row = Adw.ActionRow()
        about_row.set_title("QuaverQ")
        about_row.set_subtitle("QQ 音乐桌面客户端 · GPL-3.0")
        about_group.add(about_row)

        page = Adw.PreferencesPage()
        page.add(quality_group)
        page.add(account_group)
        page.add(about_group)

        nav_page = Adw.NavigationPage.new(page, "设置")
        nav_page.set_tag("settings")
        return nav_page

    def set_now_playing(self, song: Song) -> None:
        self._now_title.set_label(song.name)
        self._now_artist.set_label(" / ".join(song.singer_names))
        # 切歌后 like 按钮可用; 喜欢态等 controller 调 set_liked_state 来同步
        self._current_mid = song.mid
        self._like_btn.set_sensitive(True)

    def set_liked_state(self, mid: str, liked: bool) -> None:
        # 只在该歌当前播放时反映 UI (列表 per-row suffix 暂未实现)
        if mid != self._current_mid:
            return
        self._current_liked = liked
        if liked:
            # 实心星 + 高亮 = 已收藏
            self._like_btn.set_icon_name("starred-symbolic")
            self._like_btn.add_css_class("accent")
            self._like_btn.set_tooltip_text("从「我喜欢」移除")
        else:
            # 空心星 + dim = 未收藏
            self._like_btn.set_icon_name("non-starred-symbolic")
            self._like_btn.remove_css_class("accent")
            self._like_btn.set_tooltip_text("加入「我喜欢」")

    def set_play_state(self, playing: bool) -> None:
        if playing:
            self._play_btn.set_icon_name("media-playback-pause-symbolic")
        else:
            self._play_btn.set_icon_name("media-playback-start-symbolic")

    _MODE_VISUAL = {
        "sequence": ("media-playlist-consecutive-symbolic", "顺序播放"),
        "repeat_all": ("media-playlist-repeat-symbolic", "列表循环"),
        "repeat_one": ("media-playlist-repeat-song-symbolic", "单曲循环"),
        "shuffle": ("media-playlist-shuffle-symbolic", "随机播放"),
    }

    def set_play_mode_indicator(self, mode: str) -> None:
        icon, tooltip = self._MODE_VISUAL.get(mode, self._MODE_VISUAL["sequence"])
        self._mode_btn.set_icon_name(icon)
        self._mode_btn.set_tooltip_text(tooltip)

    def set_position(self, position_ms: int, duration_ms: int) -> None:
        if duration_ms > 0:
            self._progress.handler_block_by_func(self._on_seek)
            self._progress.set_value(position_ms / duration_ms * 1000)
            self._progress.handler_unblock_by_func(self._on_seek)
        self._time_curr.set_label(_fmt_ms(position_ms))
        self._time_total.set_label(_fmt_ms(duration_ms))

    def show_message(self, text: str, level: str = "info") -> None:
        toast = Adw.Toast.new(text)
        self.add_toast(toast)
