"""Qt message filter tests."""

from __future__ import annotations

from quaverq.__main__ import _should_suppress_qt_message


def test_suppresses_qsocketnotifier_invalid_read_socket_noise():
    assert _should_suppress_qt_message(
        "QSocketNotifier: Invalid socket 62 and type 'Read', disabling..."
    )


def test_suppresses_portal_app_id_collision():
    assert _should_suppress_qt_message(
        "Failed to register with host portal QDBusError("
        '"org.freedesktop.portal.Error.Failed", '
        '"Could not register app ID: Connection already associated with an application ID")'
    )


def test_suppresses_ffmpeg_mp3_skipped_samples_warning():
    assert _should_suppress_qt_message(
        "[mp3float @ 0x7fb8080656c0] Could not update timestamps for skipped samples."
    )


def test_does_not_suppress_other_qt_messages():
    assert not _should_suppress_qt_message(
        "QSocketNotifier: Invalid socket 62 and type 'Write', disabling..."
    )
    assert not _should_suppress_qt_message("file:///tmp/Main.qml:1: Error")
