"""播放器抽象层.

提供统一的播放控制接口，底层默认使用 GStreamer (Linux 桌面最通用)。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable

logger = logging.getLogger(__name__)


class PlayState(Enum):
    """播放状态."""

    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()
    BUFFERING = auto()


@dataclass
class PlayerBackend(ABC):
    """播放器后端抽象基类."""

    volume: float = 1.0  # 0.0 - 1.0
    state: PlayState = field(default=PlayState.STOPPED, init=False)
    # 控制器注册的回调 (任意线程触发, UI 后端内部 marshalling)
    on_error: Callable[[str], None] | None = field(default=None, init=False)
    on_eos: Callable[[], None] | None = field(default=None, init=False)

    @abstractmethod
    async def play(self, url: str) -> None:
        """播放指定 URL."""
        ...

    @abstractmethod
    async def pause(self) -> None:
        """暂停."""
        ...

    @abstractmethod
    async def resume(self) -> None:
        """继续."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """停止."""
        ...

    @abstractmethod
    async def seek(self, position_ms: int) -> None:
        """跳转到指定位置 (毫秒)."""
        ...

    @abstractmethod
    async def set_volume(self, volume: float) -> None:
        """设置音量 0.0-1.0."""
        ...

    @abstractmethod
    async def get_position(self) -> int:
        """获取当前播放位置 (毫秒)."""
        ...

    @abstractmethod
    async def get_duration(self) -> int:
        """获取总时长 (毫秒)."""
        ...


class GStreamerBackend(PlayerBackend):
    """GStreamer 播放后端.

    需要系统安装 GStreamer 及其插件 (gst-plugins-base, gst-plugins-good).
    """

    def __init__(self) -> None:
        super().__init__()
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst  # type: ignore[import-untyped]

        Gst.init(None)
        self._Gst = Gst
        self._pipeline: object | None = None  # Gst.Pipeline

    async def play(self, url: str) -> None:
        Gst = self._Gst
        # 切歌时先释放旧 pipeline
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None

        pipeline_str = f"playbin uri={url} audio-sink=autoaudiosink"
        self._pipeline = Gst.parse_launch(pipeline_str)
        self._pipeline.set_property("volume", self.volume)

        # 监听 bus 消息: error/eos 转给回调
        # 注意: add_signal_watch 把 watch 挂到当前线程的 default MainContext;
        # GTK 后端共用 default context, Qt 后端目前没 GLib loop 会丢消息 (P0.4 修).
        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_bus_error)
        bus.connect("message::eos", self._on_bus_eos)

        self._pipeline.set_state(Gst.State.PLAYING)
        self.state = PlayState.PLAYING
        logger.info("GStreamer: 开始播放 %s", url)

    def _on_bus_error(self, _bus, message) -> None:
        err, debug = message.parse_error()
        logger.error("GStreamer 错误: %s | %s", err, debug or "")
        if self.on_error is not None:
            try:
                self.on_error(str(err))
            except Exception:
                logger.exception("on_error 回调异常")

    def _on_bus_eos(self, _bus, _message) -> None:
        logger.info("GStreamer: 播放结束 (EOS)")
        if self.on_eos is not None:
            try:
                self.on_eos()
            except Exception:
                logger.exception("on_eos 回调异常")

    async def pause(self) -> None:
        if self._pipeline:
            self._pipeline.set_state(self._Gst.State.PAUSED)
            self.state = PlayState.PAUSED

    async def resume(self) -> None:
        if self._pipeline:
            self._pipeline.set_state(self._Gst.State.PLAYING)
            self.state = PlayState.PLAYING

    async def stop(self) -> None:
        if self._pipeline:
            self._pipeline.set_state(self._Gst.State.NULL)
            self._pipeline = None
            self.state = PlayState.STOPPED

    async def seek(self, position_ms: int) -> None:
        if self._pipeline:
            Gst = self._Gst
            self._pipeline.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                position_ms * 1_000_000,  # ms → ns
            )

    async def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        if self._pipeline:
            self._pipeline.set_property("volume", self.volume)

    async def get_position(self) -> int:
        if self._pipeline:
            ok, pos = self._pipeline.query_position(self._Gst.Format.TIME)
            return int(pos / 1_000_000) if ok else 0
        return 0

    async def get_duration(self) -> int:
        if self._pipeline:
            ok, dur = self._pipeline.query_duration(self._Gst.Format.TIME)
            return int(dur / 1_000_000) if ok else 0
        return 0


def create_player() -> PlayerBackend:
    """工厂方法：创建播放器后端.

    优先尝试 GStreamer，不可用时降级为 stub。
    """
    try:
        backend = GStreamerBackend()
    except (ImportError, ValueError) as exc:
        logger.warning("GStreamer 不可用 (%s)，使用 stub 后端", exc)
        return _StubBackend()
    logger.info("播放器后端: GStreamer")
    return backend


class _StubBackend(PlayerBackend):
    """Stub 后端：无实际播放能力，用于测试或降级."""

    async def play(self, url: str) -> None:
        logger.info("[stub] play: %s", url)

    async def pause(self) -> None:
        logger.info("[stub] pause")

    async def resume(self) -> None:
        logger.info("[stub] resume")

    async def stop(self) -> None:
        logger.info("[stub] stop")

    async def seek(self, position_ms: int) -> None:
        logger.info("[stub] seek %dms", position_ms)

    async def set_volume(self, volume: float) -> None:
        self.volume = volume

    async def get_position(self) -> int:
        return 0

    async def get_duration(self) -> int:
        return 0
