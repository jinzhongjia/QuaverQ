"""MPRIS2 D-Bus 集成.

把 QuaverQ 注册为 `org.mpris.MediaPlayer2.quaverq`, 桌面媒体控件/媒体键
能控制播放并显示元数据.

接口规范: https://specifications.freedesktop.org/mpris-spec/latest/

设计:
- 用 dbus-next (pure-python async) 挂在 qasync / Qt 主事件循环
- D-Bus 收到方法调用时, 回调由 bridge.MprisController 注入
- 状态/元数据变化由 controller 主动推
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..resources import APP_ID
from .models import Song

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- 纯函数 helpers


_TRACKID_SANITIZE = re.compile(r"[^A-Za-z0-9_]")


def _sanitize_trackid_segment(mid: str) -> str:
    """把 song mid 转成合法的 D-Bus object path 片段 (只能含 [A-Za-z0-9_])."""
    return _TRACKID_SANITIZE.sub("_", mid or "unknown")


def song_to_metadata(song: Song, *, local_cover_uri: str | None = None) -> dict[str, Any]:
    """把 QuaverQ 的 Song 转成 MPRIS metadata dict.

    artUrl 优先用本地 file:// (桌面媒体控件加载更可靠); 没本地时退到 cover_url.
    """
    meta: dict[str, Any] = {
        "mpris:trackid": f"/org/mpris/MediaPlayer2/quaverq/track/{_sanitize_trackid_segment(song.mid)}",
        "mpris:length": int(song.duration) * 1_000_000 if song.duration else 0,
        "xesam:title": song.name or "",
        "xesam:artist": [s.name for s in song.singers],
        "xesam:album": song.album_name or "",
    }
    if local_cover_uri:
        meta["mpris:artUrl"] = local_cover_uri
    elif song.cover_url:
        meta["mpris:artUrl"] = song.cover_url
    return meta


def normalize_status(state: str | None) -> str:
    """controller 传的状态字符串 → MPRIS 规范的 PlaybackStatus 值."""
    if not state:
        return "Stopped"
    s = state.lower()
    if "play" in s:
        return "Playing"
    if "pause" in s:
        return "Paused"
    return "Stopped"


def normalize_loop_status(mode: str | None) -> str:
    """controller mode → MPRIS LoopStatus."""
    if mode == "repeat_all":
        return "Playlist"
    if mode == "repeat_one":
        return "Track"
    return "None"


def normalize_shuffle(mode: str | None) -> bool:
    """controller mode → MPRIS Shuffle."""
    return mode == "shuffle"


# ---------------------------------------------------------------- 回调容器


@dataclass
class MprisCallbacks:
    """controller 注入给 MPRIS 的回调; 收到 D-Bus 调用时触发."""

    play_pause: Callable[[], None] = field(default=lambda: None)
    play: Callable[[], None] = field(default=lambda: None)
    pause: Callable[[], None] = field(default=lambda: None)
    next: Callable[[], None] = field(default=lambda: None)  # noqa: A003
    prev: Callable[[], None] = field(default=lambda: None)
    stop: Callable[[], None] = field(default=lambda: None)
    seek: Callable[[int], None] = field(default=lambda _position_ms: None)
    quit: Callable[[], None] = field(default=lambda: None)  # noqa: A003
    raise_window: Callable[[], None] = field(default=lambda: None)


# ---------------------------------------------------------------- D-Bus 接口


# dbus-next 必须在使用时 import (避免无 D-Bus 环境时 import 失败)
def _import_dbus():
    from dbus_next import BusType, PropertyAccess, Variant  # noqa: F401
    from dbus_next.aio import MessageBus  # noqa: F401
    from dbus_next.service import (  # noqa: F401
        ServiceInterface,
        dbus_property,
        method,
    )

    return {
        "BusType": BusType,
        "PropertyAccess": PropertyAccess,
        "Variant": Variant,
        "MessageBus": MessageBus,
        "ServiceInterface": ServiceInterface,
        "dbus_property": dbus_property,
        "method": method,
    }


def _build_interfaces(cb: MprisCallbacks):
    """工厂: 用 dbus-next 装饰器构造两个 ServiceInterface 类.

    放函数里是因为装饰器需要 dbus-next 模块, 而模块在 _import_dbus 内.
    """
    d = _import_dbus()
    ServiceInterface = d["ServiceInterface"]
    PropertyAccess = d["PropertyAccess"]
    Variant = d["Variant"]
    method = d["method"]
    dbus_property = d["dbus_property"]

    class _RootInterface(ServiceInterface):
        def __init__(self):
            super().__init__("org.mpris.MediaPlayer2")

        @method()
        def Raise(self):  # noqa: N802
            cb.raise_window()

        @method()
        def Quit(self):  # noqa: N802
            cb.quit()

        @dbus_property(access=PropertyAccess.READ)
        def CanQuit(self) -> b:  # noqa: N802
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanRaise(self) -> b:  # noqa: N802
            return True

        @dbus_property(access=PropertyAccess.READ)
        def HasTrackList(self) -> b:  # noqa: N802
            return False

        @dbus_property(access=PropertyAccess.READ)
        def Identity(self) -> s:  # noqa: N802
            return "QuaverQ"

        @dbus_property(access=PropertyAccess.READ)
        def DesktopEntry(self) -> s:  # noqa: N802
            # 必须是"已安装 .desktop 文件去掉后缀的 basename" (MPRIS 规范). 桌面环境
            # 据此找 .desktop -> 读 Icon= 解析 Now Playing 卡片的应用图标. 必须等于
            # 打包安装的 `{APP_ID}.desktop`, 否则 GNOME 找不到 -> 显示默认图标.
            return APP_ID

        @dbus_property(access=PropertyAccess.READ)
        def SupportedUriSchemes(self) -> "as":  # noqa: N802
            return []

        @dbus_property(access=PropertyAccess.READ)
        def SupportedMimeTypes(self) -> "as":  # noqa: N802
            return []

    class _PlayerInterface(ServiceInterface):
        def __init__(self):
            super().__init__("org.mpris.MediaPlayer2.Player")
            self._status = "Stopped"
            self._metadata: dict[str, Any] = {}
            self._position_us = 0
            self._volume = 1.0
            self._loop_status = "None"
            self._shuffle = False

        # 方法
        @method()
        def PlayPause(self):  # noqa: N802
            cb.play_pause()

        @method()
        def Play(self):  # noqa: N802
            cb.play()

        @method()
        def Pause(self):  # noqa: N802
            cb.pause()

        @method()
        def Stop(self):  # noqa: N802
            cb.stop()

        @method()
        def Next(self):  # noqa: N802
            cb.next()

        @method()
        def Previous(self):  # noqa: N802
            cb.prev()

        @method()
        def Seek(self, offset: x):  # noqa: N802
            next_position_us = max(0, self._position_us + int(offset))
            cb.seek(next_position_us // 1000)

        @method()
        def SetPosition(self, _track_id: o, position: x):  # noqa: N802
            cb.seek(max(0, int(position) // 1000))

        @method()
        def OpenUri(self, _uri: s):  # noqa: N802
            pass

        # 属性
        @dbus_property(access=PropertyAccess.READ)
        def PlaybackStatus(self) -> s:  # noqa: N802
            return self._status

        @dbus_property(access=PropertyAccess.READ)
        def LoopStatus(self) -> s:  # noqa: N802
            return self._loop_status

        @dbus_property(access=PropertyAccess.READ)
        def Rate(self) -> d:  # noqa: N802
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def Shuffle(self) -> b:  # noqa: N802
            return self._shuffle

        @dbus_property(access=PropertyAccess.READ)
        def Metadata(self) -> "a{sv}":  # noqa: N802
            return self._metadata

        @dbus_property(access=PropertyAccess.READ)
        def Volume(self) -> d:  # noqa: N802
            return self._volume

        @dbus_property(access=PropertyAccess.READ)
        def Position(self) -> x:  # noqa: N802
            return self._position_us

        @dbus_property(access=PropertyAccess.READ)
        def MinimumRate(self) -> d:  # noqa: N802
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def MaximumRate(self) -> d:  # noqa: N802
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def CanGoNext(self) -> b:  # noqa: N802
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanGoPrevious(self) -> b:  # noqa: N802
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanPlay(self) -> b:  # noqa: N802
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanPause(self) -> b:  # noqa: N802
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanSeek(self) -> b:  # noqa: N802
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanControl(self) -> b:  # noqa: N802
            return True

        # 外部 push
        def update_metadata(self, song: Song, *, local_cover_uri: str | None = None) -> None:
            raw = song_to_metadata(song, local_cover_uri=local_cover_uri)
            self._metadata = {k: _wrap_variant(v, Variant) for k, v in raw.items()}
            self.emit_properties_changed({"Metadata": self._metadata})

        def update_playback_status(self, state: str | None) -> None:
            new_status = normalize_status(state)
            if new_status == self._status:
                return
            self._status = new_status
            self.emit_properties_changed({"PlaybackStatus": new_status})

        def update_position(self, position_ms: int) -> None:
            self._position_us = max(0, int(position_ms)) * 1000

        def update_volume(self, volume: float) -> None:
            new_volume = min(1.0, max(0.0, float(volume)))
            if self._volume == new_volume:
                return
            self._volume = new_volume
            self.emit_properties_changed({"Volume": new_volume})

        def update_playback_mode(self, mode: str | None) -> None:
            new_loop_status = normalize_loop_status(mode)
            new_shuffle = normalize_shuffle(mode)
            changed: dict[str, Any] = {}
            if self._loop_status != new_loop_status:
                self._loop_status = new_loop_status
                changed["LoopStatus"] = new_loop_status
            if self._shuffle != new_shuffle:
                self._shuffle = new_shuffle
                changed["Shuffle"] = new_shuffle
            if changed:
                self.emit_properties_changed(changed)

    return _RootInterface, _PlayerInterface


def _wrap_variant(value: Any, Variant) -> Any:
    """根据 Python 值类型自动包成 dbus_next.Variant."""
    if isinstance(value, bool):
        return Variant("b", value)
    if isinstance(value, int):
        return Variant("x", value)
    if isinstance(value, float):
        return Variant("d", value)
    if isinstance(value, str):
        # 路径(trackid) 仍走字符串签名 's' — Metadata dict 内允许; spec 不强制 'o'
        return Variant("s", value)
    if isinstance(value, list):
        # 全字符串列表
        return Variant("as", [str(x) for x in value])
    return Variant("s", str(value))


# ---------------------------------------------------------------- 高层 service


class MprisService:
    """启动 / 维持 D-Bus 服务对象; controller 主动 push 元数据."""

    BUS_NAME = "org.mpris.MediaPlayer2.quaverq"
    OBJECT_PATH = "/org/mpris/MediaPlayer2"

    def __init__(self, callbacks: MprisCallbacks):
        self._cb = callbacks
        self._bus = None
        self._root = None
        self._player = None

    async def start(self) -> bool:
        """在当前 asyncio loop 上连接 session bus + 注册接口.

        返回 False 表示 D-Bus 不可用 (session bus 没启或权限不足), 上层应当容忍.
        """
        try:
            d = _import_dbus()
            self._bus = await d["MessageBus"](bus_type=d["BusType"].SESSION).connect()
            Root, Player = _build_interfaces(self._cb)
            self._root = Root()
            self._player = Player()
            self._bus.export(self.OBJECT_PATH, self._root)
            self._bus.export(self.OBJECT_PATH, self._player)
            await self._bus.request_name(self.BUS_NAME)
            logger.info("MPRIS 已注册: %s", self.BUS_NAME)
            return True
        except Exception as exc:
            logger.warning("MPRIS 启动失败 (%s), 桌面媒体集成不可用", exc)
            self._bus = None
            self._root = None
            self._player = None
            return False

    def push_metadata(self, song: Song, *, local_cover_uri: str | None = None) -> None:
        if self._player is not None:
            try:
                self._player.update_metadata(song, local_cover_uri=local_cover_uri)
            except Exception:
                logger.exception("MPRIS 推 metadata 异常")

    def push_playback_status(self, state: str | None) -> None:
        if self._player is not None:
            try:
                self._player.update_playback_status(state)
            except Exception:
                logger.exception("MPRIS 推 status 异常")

    def push_position(self, position_ms: int) -> None:
        if self._player is not None:
            try:
                self._player.update_position(position_ms)
            except Exception:
                logger.exception("MPRIS 推 position 异常")

    def push_volume(self, volume: float) -> None:
        if self._player is not None:
            try:
                self._player.update_volume(volume)
            except Exception:
                logger.exception("MPRIS 推 volume 异常")

    def push_playback_mode(self, mode: str | None) -> None:
        if self._player is not None:
            try:
                self._player.update_playback_mode(mode)
            except Exception:
                logger.exception("MPRIS 推 mode 异常")

    async def stop(self) -> None:
        if self._bus is not None:
            try:
                self._bus.disconnect()
            except Exception:
                logger.exception("MPRIS 关闭异常")
            self._bus = None
            self._root = None
            self._player = None
