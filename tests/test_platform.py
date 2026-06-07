"""PAL (Platform Abstraction Layer) 契约测试.

PAL 是跨平台落地的入口: ``get_platform()`` 按 ``sys.platform`` 派发返回对应适配器,
适配器把"会因平台而异的能力" (单实例 / 系统主题 / 媒体会话) 包装成统一接口,
让 __main__.py 只依赖 PAL 不依赖具体平台.

测试矩阵 (按当前平台 skipif, 各平台 CI 验证自己那段):
- Linux : LinuxPlatform 返回真正的 SingleInstanceGuard / SystemThemeWatcher / MprisController
- Windows / macOS: WindowsPlatform / MacOSPlatform stub, 所有能力返回 None (降级模式)
- 跨平台: get_platform() 永远返回非 None 的 adapter; adapter.name 为已知值;
  没实现的能力返回 None 时调用方应当作功能未启用而非崩溃.
"""

from __future__ import annotations

import sys

import pytest


def test_get_platform_returns_non_none_adapter():
    """任何平台 get_platform() 必须返回 adapter, 不应 raise."""
    from quaverq.platform import get_platform

    adapter = get_platform()
    assert adapter is not None
    # 已知 name: 之后 macos 加进来再扩这个集合.
    assert adapter.name in {"linux", "windows", "macos", "stub"}


def test_get_platform_is_cached():
    """get_platform() 多次调用返回同一实例 (避免重复初始化 / D-Bus 连接)."""
    from quaverq.platform import get_platform

    assert get_platform() is get_platform()


# ============================================================== Linux


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_linux_adapter_provides_single_instance():
    from quaverq.core.single_instance import SingleInstanceGuard
    from quaverq.platform import get_platform

    pal = get_platform()
    assert pal.name == "linux"
    guard = pal.single_instance()
    assert isinstance(guard, SingleInstanceGuard)
    # 应当是有 acquire / notify_existing_raise / release 的协议对象
    assert callable(guard.acquire)
    assert callable(guard.notify_existing_raise)
    assert callable(guard.release)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_linux_adapter_provides_system_theme():
    from PySide6.QtWidgets import QApplication

    from quaverq.bridge.system_theme import SystemThemeWatcher
    from quaverq.platform import get_platform

    _ = QApplication.instance() or QApplication([])
    pal = get_platform()
    watcher = pal.system_theme()
    assert isinstance(watcher, SystemThemeWatcher)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_linux_adapter_provides_media_session():
    """LinuxPlatform.media_session(player, raise_window=, quit_app=) 返回 MprisController."""
    from PySide6.QtWidgets import QApplication

    from quaverq.bridge.mpris_controller import MprisController
    from quaverq.platform import get_platform

    _ = QApplication.instance() or QApplication([])
    pal = get_platform()
    fake_player = _FakePlayerController()
    mpris = pal.media_session(
        fake_player,
        raise_window=lambda: None,
        quit_app=lambda: None,
    )
    assert isinstance(mpris, MprisController)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_linux_adapter_provides_lyric_publisher():
    """LinuxPlatform.lyric_publisher(...) 返回 LyricsDBusController (D-Bus 歌词外发)."""
    from PySide6.QtWidgets import QApplication

    from quaverq.bridge.lyric_dbus_controller import LyricsDBusController
    from quaverq.platform import get_platform

    _ = QApplication.instance() or QApplication([])
    pal = get_platform()
    fake_player = _FakePlayerController()
    fake_lyric = _FakeLyricController()
    pub = pal.lyric_publisher(lyric_controller=fake_lyric, player_controller=fake_player)
    assert isinstance(pub, LyricsDBusController)


# ============================================================== Windows / macOS (stub)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_adapter_capabilities_after_stage3a():
    """Stage 3a 后: single_instance 真实现 (Mutex); 其余仍 None (Stage 3b/3c 填).

    详细单实例契约测试见 test_platform_windows_single_instance.py.
    """
    from quaverq.platform import get_platform
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    pal = get_platform()
    assert pal.name == "windows"
    guard = pal.single_instance()
    assert isinstance(guard, WindowsSingleInstance)
    guard.release()  # cleanup; 不持有 mutex
    assert pal.system_theme() is None
    assert pal.media_session(object(), raise_window=lambda: None, quit_app=lambda: None) is None
    assert pal.lyric_publisher(lyric_controller=object(), player_controller=object()) is None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_adapter_returns_none_for_all_capabilities():
    from quaverq.platform import get_platform

    pal = get_platform()
    assert pal.name == "macos"
    assert pal.single_instance() is None
    assert pal.system_theme() is None
    assert pal.media_session(object(), raise_window=lambda: None, quit_app=lambda: None) is None
    assert pal.lyric_publisher(lyric_controller=object(), player_controller=object()) is None


# ============================================================== Protocol 契约


def test_platform_adapter_protocol_accepts_stub():
    """自己写的 stub adapter 应当满足 PlatformAdapter Protocol (静态结构鸭子)."""
    from quaverq.platform.base import PlatformAdapter

    class StubAdapter:
        name = "stub"

        def single_instance(self):
            return None

        def system_theme(self):
            return None

        def media_session(self, player_controller, *, raise_window=None, quit_app=None):
            return None

        def lyric_publisher(self, *, lyric_controller, player_controller):
            return None

    stub: PlatformAdapter = StubAdapter()  # 类型检查: Protocol 结构鸭子
    assert stub.name == "stub"
    assert stub.single_instance() is None
    assert stub.lyric_publisher(lyric_controller=None, player_controller=None) is None


# ============================================================== helpers


class _FakePlayerController:
    """模拟 PlayerController, 给 MprisController 构造时的最少接口."""

    def __init__(self) -> None:
        from PySide6.QtCore import QObject, Signal

        class _Sig(QObject):
            currentSongChanged = Signal()
            playbackStateChanged = Signal()
            positionMsChanged = Signal()
            volumeChanged = Signal()
            modeChanged = Signal()

        self._holder = _Sig()
        self.currentSongChanged = self._holder.currentSongChanged
        self.playbackStateChanged = self._holder.playbackStateChanged
        self.positionMsChanged = self._holder.positionMsChanged
        self.volumeChanged = self._holder.volumeChanged
        self.modeChanged = self._holder.modeChanged

    def togglePlayPause(self) -> None: ...
    def play(self) -> None: ...
    def pause(self) -> None: ...
    def stop(self) -> None: ...
    def next(self) -> None: ...
    def prev(self) -> None: ...
    def seek(self, _us: int) -> None: ...


class _FakeLyricController:
    """模拟 LyricController, 给 LyricsDBusController 构造时的最少接口."""

    def __init__(self) -> None:
        from PySide6.QtCore import QObject, Signal

        from quaverq.core.models import Lyric

        class _Sig(QObject):
            lyricChanged = Signal()

        self._holder = _Sig()
        self.lyricChanged = self._holder.lyricChanged
        self.current_lyric = Lyric(mid="", lines=[])
