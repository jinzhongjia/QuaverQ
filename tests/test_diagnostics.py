"""Q11.1 启动运行时自检测试。"""

from __future__ import annotations

from quaverq import diagnostics


def test_multimedia_ok_when_probe_succeeds() -> None:
    d = diagnostics.check_multimedia(probe=lambda: True)
    assert d.ok
    assert d.name == "multimedia"
    assert d.severity == diagnostics.INFO


def test_multimedia_critical_when_probe_fails() -> None:
    d = diagnostics.check_multimedia(probe=lambda: False)
    assert not d.ok
    assert d.severity == diagnostics.CRITICAL
    assert d.detail


def test_multimedia_critical_when_probe_raises() -> None:
    def boom() -> bool:
        raise ImportError("no QtMultimedia")

    d = diagnostics.check_multimedia(probe=boom)
    assert not d.ok
    assert d.severity == diagnostics.CRITICAL


def test_dbus_warning_when_unavailable() -> None:
    d = diagnostics.check_dbus(probe=lambda: False)
    assert not d.ok
    assert d.severity == diagnostics.WARNING  # 非致命，可降级


def test_dbus_ok_when_available() -> None:
    d = diagnostics.check_dbus(probe=lambda: True)
    assert d.ok
    assert d.name == "dbus"


def test_run_diagnostics_returns_all_checks() -> None:
    results = diagnostics.run_diagnostics(
        multimedia_probe=lambda: True,
        dbus_probe=lambda: True,
    )
    names = {d.name for d in results}
    assert {"multimedia", "dbus"} <= names


def test_has_critical_detects_multimedia_failure() -> None:
    results = diagnostics.run_diagnostics(
        multimedia_probe=lambda: False,
        dbus_probe=lambda: True,
    )
    assert diagnostics.has_critical(results)


def test_has_critical_false_when_only_warnings() -> None:
    results = diagnostics.run_diagnostics(
        multimedia_probe=lambda: True,
        dbus_probe=lambda: False,
    )
    assert not diagnostics.has_critical(results)


def test_format_diagnostics_includes_each_check() -> None:
    results = diagnostics.run_diagnostics(
        multimedia_probe=lambda: True,
        dbus_probe=lambda: False,
    )
    text = diagnostics.format_diagnostics(results)
    assert "multimedia" in text
    assert "dbus" in text


def test_default_probes_run_without_qapplication() -> None:
    # 默认 probe 只做 import / env 探测，不能要求 QApplication 实例存在。
    results = diagnostics.run_diagnostics()
    assert len(results) >= 2
    assert all(isinstance(d, diagnostics.Diagnostic) for d in results)


def test_include_dbus_false_skips_dbus_check() -> None:
    """Windows / macOS 调用方传 include_dbus=False 时不该跑 dbus check (D-Bus 在这些平台不适用)."""
    results = diagnostics.run_diagnostics(
        multimedia_probe=lambda: True,
        include_dbus=False,
    )
    names = {d.name for d in results}
    assert "multimedia" in names
    assert "dbus" not in names
