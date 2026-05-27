"""Qt message filter tests."""

from __future__ import annotations

from quaverq.__main__ import _should_suppress_qt_message


def test_suppresses_qsocketnotifier_invalid_read_socket_noise():
    assert _should_suppress_qt_message(
        "QSocketNotifier: Invalid socket 62 and type 'Read', disabling..."
    )


def test_does_not_suppress_other_qt_messages():
    assert not _should_suppress_qt_message(
        "QSocketNotifier: Invalid socket 62 and type 'Write', disabling..."
    )
    assert not _should_suppress_qt_message("file:///tmp/Main.qml:1: Error")
