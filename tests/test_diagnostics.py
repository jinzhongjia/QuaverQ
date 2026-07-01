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


def test_dbus_critical_when_unavailable() -> None:
    d = diagnostics.check_dbus(probe=lambda: False)
    assert not d.ok
    assert d.severity == diagnostics.CRITICAL


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


def test_has_critical_detects_dbus_failure() -> None:
    results = diagnostics.run_diagnostics(
        multimedia_probe=lambda: True,
        dbus_probe=lambda: False,
    )
    assert diagnostics.has_critical(results)


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


def test_default_multimedia_probe_validates_plugin_dir(tmp_path, monkeypatch) -> None:
    """默认 multimedia probe 必须验证后端插件目录真有插件; 仅 import 不算数.

    模拟 Nuitka 漏带 multimedia 插件场景: PySide6.QtMultimedia 能 import, 但
    Qt 搜索的插件目录下没 ``multimedia/`` 子目录 -> probe 返 False -> 报 critical.
    必须同时清空 PluginsPath **和** libraryPaths, 否则进程里真实 PySide6 wheel 的
    plugins/multimedia 会漏进来让"没部署"模拟失效。
    """
    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    # 把 Qt 搜索的两处插件来源都换成新建的空目录, 模拟"插件没部署"
    monkeypatch.setattr(
        QLibraryInfo,
        "path",
        staticmethod(lambda _kind: str(tmp_path)),
    )
    monkeypatch.setattr(
        QCoreApplication,
        "libraryPaths",
        staticmethod(lambda: [str(tmp_path)]),
    )
    assert diagnostics._default_multimedia_probe() is False

    # 创建空 multimedia/ 目录: 还是 False (空目录 = 没 backend)
    (tmp_path / "multimedia").mkdir()
    assert diagnostics._default_multimedia_probe() is False

    # 放一个假后端插件文件: True
    (tmp_path / "multimedia" / "ffmpegmediaplugin.dll").write_bytes(b"placeholder")
    assert diagnostics._default_multimedia_probe() is True


def test_default_multimedia_probe_finds_plugins_via_library_paths(tmp_path, monkeypatch) -> None:
    """回归 (打包后闪退): Nuitka 把插件重定位到 qt-plugins, ``QLibraryInfo.PluginsPath``
    指向已不存在的 ``PySide6/plugins`` 而插件实际在 ``libraryPaths()`` 里. 只查 PluginsPath
    会假阴性 critical 退出整个 app —— probe 必须遍历 libraryPaths 才能找到后端.
    """
    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    missing = tmp_path / "PySide6" / "plugins"  # PluginsPath 报这里, 但不存在
    relocated = tmp_path / "PySide6" / "qt-plugins"  # Nuitka 实际放这里
    (relocated / "multimedia").mkdir(parents=True)
    (relocated / "multimedia" / "ffmpegmediaplugin.dll").write_bytes(b"placeholder")

    monkeypatch.setattr(QLibraryInfo, "path", staticmethod(lambda _kind: str(missing)))
    monkeypatch.setattr(QCoreApplication, "libraryPaths", staticmethod(lambda: [str(relocated)]))

    assert diagnostics._default_multimedia_probe() is True


def test_default_multimedia_probe_skips_inaccessible_candidate(tmp_path, monkeypatch) -> None:
    """一个候选路径访问抛 OSError (受限 / 系统目录) 不该拖垮整个 probe: 跳过它继续查
    后面的候选, 只有全部候选都无有效 multimedia 才算缺失 (PR #37 review: 单坏路径
    否则会被 _safe 吞成 False -> 误判后端缺失 critical 退出).
    """
    import pathlib

    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    bad = tmp_path / "restricted"  # is_dir() 抛 PermissionError
    good = tmp_path / "ok"
    (good / "multimedia").mkdir(parents=True)
    (good / "multimedia" / "ffmpegmediaplugin.dll").write_bytes(b"placeholder")

    real_is_dir = pathlib.Path.is_dir

    def flaky_is_dir(self: pathlib.Path) -> bool:
        if str(self).startswith(str(bad)):
            raise PermissionError("access denied")
        return real_is_dir(self)

    monkeypatch.setattr(pathlib.Path, "is_dir", flaky_is_dir)
    monkeypatch.setattr(QLibraryInfo, "path", staticmethod(lambda _kind: str(tmp_path / "none")))
    monkeypatch.setattr(
        QCoreApplication, "libraryPaths", staticmethod(lambda: [str(bad), str(good)])
    )

    # bad 在前且会抛 -> 必须被跳过, good 里的插件仍要被找到
    assert diagnostics._default_multimedia_probe() is True


def test_include_dbus_false_skips_dbus_check() -> None:
    """Windows / macOS 调用方传 include_dbus=False 时不该跑 dbus check (D-Bus 在这些平台不适用)."""
    results = diagnostics.run_diagnostics(
        multimedia_probe=lambda: True,
        include_dbus=False,
    )
    names = {d.name for d in results}
    assert "multimedia" in names
    assert "dbus" not in names
