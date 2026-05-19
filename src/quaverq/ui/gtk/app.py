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
from gi.repository import (  # type: ignore[import-untyped]
    Adw,
    Gdk,
    GdkPixbuf,
    Gio,
    GLib,
    Gtk,
    Pango,
)

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

        GLib.unix_signal_add(
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
        # Header: 搜索框放在标题槽, 登录按钮在末尾
        # =================================================================
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("搜索歌曲、歌手、专辑…")
        self._search_entry.set_max_width_chars(36)
        self._search_entry.connect("activate", self._on_search)

        self._login_btn = Gtk.Button(label="登录")
        self._login_btn.add_css_class("suggested-action")
        self._login_btn.connect("clicked", lambda _b: self._ui._emit("login"))

        header = Adw.HeaderBar()
        header.set_title_widget(self._search_entry)
        header.pack_end(self._login_btn)

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
        # ToolbarView 组装
        # =================================================================
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(self._stack)
        toolbar_view.add_bottom_bar(control_box)

        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(toolbar_view)
        self.set_content(self._toast_overlay)

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
        if authed:
            self._welcome_page.set_title("已就绪")
            self._welcome_page.set_description(
                "在顶部搜索框输入关键词查找音乐"
            )
            self._welcome_login_btn.set_visible(False)
            self._login_btn.set_visible(False)
        else:
            self._welcome_page.set_title("欢迎使用 QuaverQ")
            self._welcome_page.set_description(
                "在顶部搜索框输入关键词查找音乐\n"
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
        """搜索结果 — 4 Tabs (歌曲/歌手/专辑/歌单).

        每个 Tab 对应一个 ListView, 数据由 service 并发 fan-out 后填进来.
        Tab 切换用 Adw.ViewSwitcherBar (顶部胶囊样式).
        """
        self._results_view_stack = Adw.ViewStack()

        # 歌曲 Tab — 复用现有的工厂逻辑 (可点击播放)
        self._list_store = Gio.ListStore.new(Gtk.StringObject)
        self._song_data: list[Song] = []
        songs_scroll = self._make_list_tab(
            store=self._list_store,
            factory_bind=self._on_list_bind,
            activate=self._on_play_selected,
        )
        self._results_view_stack.add_titled(songs_scroll, "songs", "歌曲")

        # 歌手 Tab
        self._singer_store = Gio.ListStore.new(Gtk.StringObject)
        self._singer_data: list[Singer] = []
        singers_scroll = self._make_list_tab(
            store=self._singer_store,
            factory_bind=self._on_list_bind,
            activate=self._on_singer_selected,
        )
        self._results_view_stack.add_titled(singers_scroll, "singers", "歌手")

        # 专辑 Tab
        self._album_store = Gio.ListStore.new(Gtk.StringObject)
        self._album_data: list[Album] = []
        albums_scroll = self._make_list_tab(
            store=self._album_store,
            factory_bind=self._on_list_bind,
            activate=self._on_album_selected,
        )
        self._results_view_stack.add_titled(albums_scroll, "albums", "专辑")

        # 歌单 Tab
        self._playlist_store = Gio.ListStore.new(Gtk.StringObject)
        self._playlist_data: list[Playlist] = []
        playlists_scroll = self._make_list_tab(
            store=self._playlist_store,
            factory_bind=self._on_list_bind,
            activate=self._on_playlist_selected,
        )
        self._results_view_stack.add_titled(
            playlists_scroll, "playlists", "歌单"
        )

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self._results_view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.set_margin_top(8)
        switcher.set_margin_bottom(8)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.append(switcher)
        box.append(self._results_view_stack)
        box.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(900)
        clamp.set_child(box)
        return clamp

    def _make_list_tab(
        self,
        *,
        store: Gio.ListStore,
        factory_bind: Callable,
        activate: Callable,
    ) -> Gtk.ScrolledWindow:
        """构造一个标准 ListView + ScrolledWindow (4 Tabs 共用)."""
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_list_setup)
        factory.connect("bind", factory_bind)

        list_view = Gtk.ListView(
            model=Gtk.SingleSelection(model=store),
            factory=factory,
        )
        list_view.connect("activate", activate)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(list_view)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        return scrolled

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

        track_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        track_box.set_size_request(260, -1)
        track_box.append(self._cover)
        track_box.append(now_info)

        # 中：圆形播放按钮
        self._play_btn = Gtk.Button()
        self._play_btn.set_icon_name("media-playback-start-symbolic")
        self._play_btn.add_css_class("circular")
        self._play_btn.add_css_class("suggested-action")
        self._play_btn.set_valign(Gtk.Align.CENTER)
        self._play_btn.connect("clicked", self._on_play_pause)

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

        control_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=16
        )
        control_box.set_margin_start(16)
        control_box.set_margin_end(16)
        control_box.set_margin_top(10)
        control_box.set_margin_bottom(10)
        control_box.append(track_box)
        control_box.append(self._play_btn)
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
    # 列表工厂
    # ------------------------------------------------------------------

    @staticmethod
    def _on_list_setup(_factory, item: Gtk.ListItem) -> None:
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_margin_start(16)
        label.set_margin_end(16)
        label.set_margin_top(10)
        label.set_margin_bottom(10)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        item.set_child(label)

    def _on_list_bind(self, _factory, item: Gtk.ListItem) -> None:
        label = item.get_child()
        obj = item.get_item()
        if label and obj:
            label.set_label(obj.get_string())

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def add_toast(self, toast: Adw.Toast) -> None:
        self._toast_overlay.add_toast(toast)

    def _on_search(self, _widget) -> None:
        keyword = self._search_entry.get_text().strip()
        if keyword:
            self._ui._emit("search", keyword)

    def _on_play_selected(self, _list_view, pos: int) -> None:
        if 0 <= pos < len(self._song_data):
            self._ui._emit("play_song", self._song_data[pos])

    def _on_singer_selected(self, _list_view, pos: int) -> None:
        # P0.3 进 ArtistView; 目前 toast 提示占位
        if 0 <= pos < len(self._singer_data):
            self._ui._emit("open_singer", self._singer_data[pos])

    def _on_album_selected(self, _list_view, pos: int) -> None:
        if 0 <= pos < len(self._album_data):
            self._ui._emit("open_album", self._album_data[pos])

    def _on_playlist_selected(self, _list_view, pos: int) -> None:
        if 0 <= pos < len(self._playlist_data):
            self._ui._emit("open_playlist", self._playlist_data[pos])

    def _on_play_pause(self, _btn) -> None:
        if self._play_btn.get_icon_name() == "media-playback-start-symbolic":
            self._ui._emit("resume")
        else:
            self._ui._emit("pause")

    def _on_seek(self, scale: Gtk.Scale) -> None:
        self._ui._emit("seek", int(scale.get_value()))

    # ------------------------------------------------------------------
    # UI 更新方法
    # ------------------------------------------------------------------

    def show_welcome(self) -> None:
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
        self._stack.set_visible_child_name("login")

    def show_search_results(self, songs: list[Song]) -> None:
        self._list_store.remove_all()
        self._song_data.clear()
        for song in songs:
            text = f"{song.name}  ·  {' / '.join(song.singer_names)}"
            self._list_store.append(Gtk.StringObject.new(text))
            self._song_data.append(song)
        # 切到结果页 + 默认显示歌曲 Tab
        self._stack.set_visible_child_name("results")
        self._results_view_stack.set_visible_child_name("songs")

    def show_singer_results(self, singers: list[Singer]) -> None:
        self._singer_store.remove_all()
        self._singer_data.clear()
        for s in singers:
            self._singer_store.append(Gtk.StringObject.new(s.name))
            self._singer_data.append(s)

    def show_album_results(self, albums: list[Album]) -> None:
        self._album_store.remove_all()
        self._album_data.clear()
        for a in albums:
            singer_text = (
                " / ".join(sg.name for sg in a.singers) if a.singers else ""
            )
            text = (
                f"{a.name}  ·  {singer_text}" if singer_text else a.name
            )
            self._album_store.append(Gtk.StringObject.new(text))
            self._album_data.append(a)

    def show_playlist_results(self, playlists: list[Playlist]) -> None:
        self._playlist_store.remove_all()
        self._playlist_data.clear()
        for p in playlists:
            text = (
                f"{p.name}  ·  {p.creator}  ·  {p.song_count} 首"
                if p.creator
                else f"{p.name}  ·  {p.song_count} 首"
            )
            self._playlist_store.append(Gtk.StringObject.new(text))
            self._playlist_data.append(p)

    def show_playlist(self, playlist: Playlist) -> None:
        # 进入歌单详情 (P0.3 会单独建 PlaylistView; 现在复用 songs Tab)
        self.set_title(f"QuaverQ — {playlist.name}")
        self._list_store.remove_all()
        self._song_data.clear()
        for song in playlist.songs:
            text = f"{song.name}  ·  {' / '.join(song.singer_names)}"
            self._list_store.append(Gtk.StringObject.new(text))
            self._song_data.append(song)
        self._stack.set_visible_child_name("results")
        self._results_view_stack.set_visible_child_name("songs")

    def show_lyric(self, _lyric: Lyric) -> None:
        pass

    def set_now_playing(self, song: Song) -> None:
        self._now_title.set_label(song.name)
        self._now_artist.set_label(" / ".join(song.singer_names))

    def set_play_state(self, playing: bool) -> None:
        if playing:
            self._play_btn.set_icon_name("media-playback-pause-symbolic")
        else:
            self._play_btn.set_icon_name("media-playback-start-symbolic")

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
