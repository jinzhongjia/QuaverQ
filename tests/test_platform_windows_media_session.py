"""WindowsMediaSession 的跨平台纯逻辑回归测试。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from quaverq.platform._windows_media_session import WindowsMediaSession


class _SignalHolder(QObject):
    currentSongChanged = Signal()
    playbackStateChanged = Signal()


class _FakePlayer:
    def __init__(self) -> None:
        self._holder = _SignalHolder()
        self.currentSongChanged = self._holder.currentSongChanged
        self.playbackStateChanged = self._holder.playbackStateChanged
        self.currentSong = {}
        self.playbackState = "stopped"


class _FakeCoverCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.urls: list[str] = []

    def get_path(self, url: str) -> Path | None:
        self.urls.append(url)
        return self.path


class _LazyProxy:
    def __init__(self) -> None:
        self.started = False
        self.start_calls = 0
        self.local_file_calls: list[str] = []

    def start(self) -> None:
        self.started = True
        self.start_calls += 1

    def local_file_url(self, filename: str) -> str | None:
        assert self.started is True
        self.local_file_calls.append(filename)
        return f"http://127.0.0.1:9000/_local/token/{filename}"


def test_resolve_thumbnail_uri_starts_stream_proxy_lazily(tmp_path):
    """SMTC 只有在真正需要本机封面 URI 时才启动 StreamProxy。"""

    _ = QApplication.instance() or QApplication([])
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"jpg")
    proxy = _LazyProxy()
    session = WindowsMediaSession(
        _FakePlayer(),
        cover_cache=_FakeCoverCache(cover),
        stream_proxy=proxy,
    )

    uri = session._resolve_thumbnail_uri("https://y.qq.com/cover.jpg")  # noqa: SLF001

    assert proxy.start_calls == 1
    assert proxy.local_file_calls == ["cover.jpg"]
    assert uri == "http://127.0.0.1:9000/_local/token/cover.jpg"
