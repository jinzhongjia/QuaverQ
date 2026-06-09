"""Crash logger (sys.excepthook -> CACHE_DIR/crash.log) 测试."""

from __future__ import annotations

import sys

import pytest


@pytest.fixture
def restore_excepthook():
    saved = sys.excepthook
    yield
    sys.excepthook = saved


def test_install_crash_logger_writes_traceback(tmp_path, monkeypatch, restore_excepthook):
    """安装后, unhandled exception 应当被写到 crash.log + 链给默认 hook (stderr 还能看)."""
    from quaverq import diagnostics_crash

    monkeypatch.setattr(diagnostics_crash, "CACHE_DIR", tmp_path)
    diagnostics_crash.install_crash_logger()
    try:
        raise ValueError("simulated crash")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    log_file = tmp_path / "crash.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "ValueError" in content
    assert "simulated crash" in content
    # traceback frame 包含本文件文件名
    assert __file__.split("\\")[-1].split("/")[-1] in content or "test_diagnostics_crash" in content


def test_install_crash_logger_appends_multiple_crashes(tmp_path, monkeypatch, restore_excepthook):
    """多次崩溃应当追加, 不覆盖. 便于回看历史."""
    from quaverq import diagnostics_crash

    monkeypatch.setattr(diagnostics_crash, "CACHE_DIR", tmp_path)
    diagnostics_crash.install_crash_logger()
    for marker in ("first", "second"):
        try:
            raise RuntimeError(marker)
        except RuntimeError:
            sys.excepthook(*sys.exc_info())

    content = (tmp_path / "crash.log").read_text(encoding="utf-8")
    assert "first" in content
    assert "second" in content


def test_install_crash_logger_does_not_swallow_default_behavior(
    tmp_path, monkeypatch, restore_excepthook, capsys
):
    """新 excepthook 必须把异常也链给原 hook (默认 hook 输出到 stderr), 不然控制台调试体验回退."""
    from quaverq import diagnostics_crash

    monkeypatch.setattr(diagnostics_crash, "CACHE_DIR", tmp_path)
    diagnostics_crash.install_crash_logger()
    try:
        raise KeyError("chained")
    except KeyError:
        sys.excepthook(*sys.exc_info())

    captured = capsys.readouterr()
    assert "KeyError" in captured.err or "chained" in captured.err
