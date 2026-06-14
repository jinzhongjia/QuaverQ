"""应用退出序列契约."""

from __future__ import annotations

from quaverq.__main__ import _connect_pre_shutdown_hooks, _save_exit_snapshot


class _Signal:
    def __init__(self) -> None:
        self.slots: list[object] = []

    def connect(self, slot: object) -> None:
        self.slots.append(slot)


class _App:
    def __init__(self) -> None:
        self.aboutToQuit = _Signal()


class _RuntimeHook:
    def __init__(self) -> None:
        self.calls = 0

    def stop(self) -> None:
        self.calls += 1

    def shutdown(self) -> None:
        self.calls += 1


class _Player:
    def __init__(self) -> None:
        self.saves = 0

    def saveSessionSnapshot(self) -> None:  # noqa: N802 - Qt slot 命名跟生产代码一致
        self.saves += 1


def test_about_to_quit_hooks_exclude_session_snapshot() -> None:
    app = _App()
    stream_proxy = _RuntimeHook()
    download_controller = _RuntimeHook()

    _connect_pre_shutdown_hooks(app, stream_proxy, download_controller)

    assert [slot.__name__ for slot in app.aboutToQuit.slots] == ["stop", "shutdown"]


def test_exit_snapshot_is_explicit_single_step() -> None:
    player = _Player()

    _save_exit_snapshot(player)

    assert player.saves == 1
