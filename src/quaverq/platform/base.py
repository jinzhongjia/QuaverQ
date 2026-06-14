"""平台抽象层 (PAL) 类型契约.

只放 Protocol 定义, 不放任何实现 / 平台门面. 实现走 linux.py / windows.py / macos.py,
__main__.py 通过 ``get_platform()`` 拿到 ``PlatformAdapter`` 实例后只调下面这俩 Protocol.

设计要点:
- 用 ``typing.Protocol`` (结构子类型), 适配器不需要显式继承, 鸭子类型即可满足.
- 所有能力工厂方法**都允许返回 None** —— 这是降级契约: 平台不支持时返回 None,
  调用方 (__main__.py) 必须容忍 None, 不能 ``assert pal.x() is not None``.
- 返回 QObject 的能力 (system_theme / media_session): 调用方负责持有引用 (避免 GC),
  并通过 ``setContextProperty`` 暴露给 QML / 通过 signal 连接生命周期.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SingleInstance(Protocol):
    """单实例守卫契约.

    Linux 实现走 D-Bus well-known name (org.quaverq.SingleInstance).
    Windows 实现走命名 Mutex (Stage 3 加入).
    macOS 实现走文件锁 (Stage 4 加入).
    """

    async def acquire(self) -> bool:
        """抢占名字; True = 占到 (本进程为首实例); False = 已被占 / 不可用."""
        ...

    async def notify_existing_raise(self) -> None:
        """通知已有实例把主窗口前置 (本进程将随即退出)."""
        ...

    def release(self) -> None:
        """释放占用; 多次调用应幂等."""
        ...


@runtime_checkable
class PlatformAdapter(Protocol):
    """平台门面: 工厂方法返回各项能力的实现实例 (或 None 表示不支持).

    实现类应当是无状态的轻对象 —— ``get_platform()`` 缓存一份即可.
    各 ``*()`` 方法被调用时才真正构造底层对象 (惰性, 避免 Linux 上提前连 D-Bus).
    """

    name: str  # "linux" / "windows" / "macos"

    def single_instance(self) -> SingleInstance | None:
        """返回单实例守卫; 不支持时返回 None (调用方退化到"不做守卫, 允许多开")."""
        ...

    def system_theme(self) -> Any | None:
        """返回系统主题监听器 (QObject, 暴露 dark: bool Property + darkChanged Signal).

        返回 ``Any`` 是因为 Protocol 不便约束 QObject; 调用方按 QObject 用即可.
        不支持时返回 None, 调用方退化到"跟随 Qt palette".
        """
        ...

    def media_session(
        self,
        player_controller: Any,
        *,
        raise_window: Any = None,
        quit_app: Any = None,
        cover_cache: Any = None,
        stream_proxy: Any = None,
    ) -> Any | None:
        """返回媒体会话控制器 (Linux: MprisController; Windows: SMTC; macOS: NowPlayingInfoCenter).

        实现负责把 player_controller 的 signal 接到平台 API 上, 暴露
        ``async start_async() / stop_async()`` 方法给 __main__.py 的启动 / 退出钩子.
        ``raise_window`` / ``quit_app`` 是无参回调, 用于平台层"前置窗口" / "退出应用"
        语义的本地反馈 (例如 MPRIS Raise / Quit 接口转回主窗口).
        ``cover_cache`` 让 Windows SMTC 把已下载的封面 (磁盘 file:// URI) 设为
        Now Playing 卡片 Thumbnail; Linux MPRIS 当前不需要 (artUrl 走 URL 即可).

        不支持时返回 None, 调用方退化到"无媒体键 / Now Playing 集成".
        """
        ...

    def lyric_publisher(
        self,
        *,
        lyric_controller: Any,
        player_controller: Any,
        settings_controller: Any = None,
    ) -> Any | None:
        """返回歌词外发控制器 (Linux: LyricsDBusController, org.quaverq.Lyrics1 D-Bus).

        ``settings_controller`` 用来同步歌词翻译可见性；不传时默认外发翻译。
        Windows / macOS 暂无对等机制, 返回 None.
        """
        ...

    def taskbar(
        self,
        player_controller: Any,
        hwnd_provider: Any,
        cover_cache: Any = None,
    ) -> Any | None:
        """返回任务栏深度集成 controller (进度条 + 缩略图按钮 + DWM 自定义缩略图).

        ``hwnd_provider`` 是 ``Callable[[], int]``: 调用方传一个延迟返回主窗口 HWND
        的回调 (engine.load 后 ``rootObjects()[0].winId()`` 可拿到). PAL 自己不知道
        QML 窗口, 所以走回调.
        ``cover_cache`` 可选: 传入后会把当前歌封面替换成任务栏悬停缩略图 (DWM
        iconic representation), 否则保留默认窗口快照.

        - Windows: ``WindowsTaskbar`` 走 ``ITaskbarList3``.
        - Linux / macOS: 返 None.
        """
        ...

    def power_saver(self, player_controller: Any) -> Any | None:
        """返回防睡眠 controller (QObject); 实现需订阅 player_controller.playbackStateChanged
        播放时阻止 OS 进入待机, 暂停时撤销.

        - Windows: ``WindowsPowerSaver`` 走 ``SetThreadExecutionState``.
        - Linux: 返 None (PulseAudio / DE 已经自动管理 idle inhibit).
        - macOS: 暂返 None (Stage 4 可实现 IOPMAssertion).

        返 None 时调用方什么也不做, 应用不崩.
        """
        ...

    def desktop_lyrics(
        self,
        lyric_controller: Any,
        settings_controller: Any = None,
        player_controller: Any = None,
    ) -> Any | None:
        """返回桌面悬浮歌词窗 controller (类似 QQ 音乐桌面歌词).

        ``settings_controller`` 用来同步锁定 / 字体 / 方向; 传 None 时窗口走默认值.
        ``player_controller`` 用来同步播放状态 (是否真正在播放, 控制 wipe 插值是否启动);
        不传的话窗口认为"始终未在播放", 永远不做 30fps 插值 (功能降级但不出 wall-clock 鬼影).

        - Windows: 唯一支持平台. 返 ``DesktopLyricsController``.
        - Linux: **不支持** —— Wayland 下 frameless + transparent + input-passthrough
          组合在不同 compositor (Mutter / KWin / Hyprland 等) 行为不一致, 焦点抢占 /
          z-order 问题难定位. Linux 用户走 MPRIS 接现成桌面歌词工具
          (kde-mpris-osd, gnome-mpris-applet 等). 返 None.
        - macOS: 不在范围内. 返 None.
        """
        ...
