"""Q11.2 构建命令组装测试（不真正编译）。"""

from __future__ import annotations

import tomllib

from quaverq import packaging, resources


def test_nuitka_command_enables_pyside6_plugin():
    assert "--enable-plugin=pyside6" in packaging.nuitka_command()


def test_nuitka_command_bundles_package_data():
    cmd = packaging.nuitka_command()
    assert "--include-package=quaverq" in cmd
    assert "--include-package-data=quaverq" in cmd  # qml / Theme / qmldir


def test_nuitka_command_bundles_curl_cffi():
    # 反风控 native 依赖必须进 bundle，否则取链 / 回环代理失效
    cmd = packaging.nuitka_command()
    assert "--include-package=curl_cffi" in cmd
    assert "--include-package-data=curl_cffi" in cmd


def test_nuitka_command_force_includes_dynamic_import_packages():
    # niquests/urllib3-future 系列运行时动态 import，nuitka 静态分析会漏
    cmd = packaging.nuitka_command()
    for pkg in ("niquests", "urllib3", "qqmusic_api"):
        assert f"--include-package={pkg}" in cmd


def test_nuitka_command_includes_qml_qt_plugins():
    # QtQuick / QtMultimedia / Layouts 运行时模块（QML 加载需要）
    assert "--include-qt-plugins=sensible,qml" in packaging.nuitka_command()


def test_nuitka_command_includes_assets_dir():
    cmd = packaging.nuitka_command()
    assert any(
        c.startswith("--include-data-dir=") and c.endswith("=assets") for c in cmd
    )


def test_nuitka_command_injects_version():
    cmd = packaging.nuitka_command(version="9.9.9")
    assert "--product-version=9.9.9" in cmd
    assert "--file-version=9.9.9" in cmd


def test_nuitka_command_modes_and_entrypoint():
    assert "--standalone" in packaging.nuitka_command("standalone")
    assert "--onefile" in packaging.nuitka_command("onefile")
    # 以包目录为入口 + -m flag（relative import 需要包上下文）
    assert "--python-flag=-m" in packaging.nuitka_command()
    assert packaging.nuitka_command()[-1].endswith("quaverq")


def test_project_version_matches_pyproject():
    data = tomllib.loads(
        (resources.project_root() / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert packaging.project_version() == data["project"]["version"]


def test_appdir_layout_maps_desktop_icon_metainfo():
    layout = packaging.appimage_appdir_layout("/tmp/AppDir")
    targets = {p.as_posix() for p in layout}
    assert any(t.endswith(".desktop") and "usr/share/applications" in t for t in targets)
    assert any(t.endswith(".svg") and "icons/hicolor/scalable/apps" in t for t in targets)
    assert any(t.endswith(".metainfo.xml") and "usr/share/metainfo" in t for t in targets)
    for src in layout.values():  # 源文件都存在
        assert src.is_file()


def test_linuxdeploy_command_skips_qt_plugin():
    # Nuitka 的 pyside6 插件已把整套 Qt 打进 bundle（standalone 可跑），不再用
    # linuxdeploy-plugin-qt（它会去部署系统 Qt 而引入 sqldrivers 等缺失依赖导致失败）。
    cmd = packaging.linuxdeploy_command("/tmp/AppDir")
    assert "--plugin" not in cmd
    assert "appimage" in cmd
