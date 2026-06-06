"""Q11.1 打包资源（.desktop / 图标 / AppStream metainfo）测试。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import tomllib

from quaverq import __version__, resources

APP_ID = "io.github.jinzhongjia.quaverq"


def test_app_id_constant() -> None:
    assert resources.APP_ID == APP_ID


def test_assets_dir_exists() -> None:
    assert resources.assets_dir().is_dir()


def test_desktop_file_present_and_valid() -> None:
    path = resources.desktop_file()
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("[Desktop Entry]")
    for key in (
        "Type=Application",
        "Name=QuaverQ",
        "Exec=QuaverQ",
        f"Icon={APP_ID}",
        "Categories=",
    ):
        assert key in text, f"缺少 {key}"


def test_icon_is_valid_svg() -> None:
    path = resources.icon_file()
    assert path.is_file()
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    assert root.get("viewBox")


def test_metainfo_valid_appstream() -> None:
    path = resources.metainfo_file()
    assert path.is_file()
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    assert root.tag == "component"
    assert root.get("type") == "desktop-application"
    assert root.findtext("id") == APP_ID
    assert root.findtext("project_license") == "GPL-3.0-or-later"
    launch = root.find("launchable")
    assert launch is not None
    assert launch.text == f"{APP_ID}.desktop"


def test_metainfo_release_matches_version() -> None:
    root = ET.fromstring(resources.metainfo_file().read_text(encoding="utf-8"))
    versions = {r.get("version") for r in root.iter("release")}
    assert __version__ in versions


def test_metainfo_maintainer_email() -> None:
    # 公开元数据 maintainer 用 mail@nvimer.org（见用户全局约定）。
    text = resources.metainfo_file().read_text(encoding="utf-8")
    assert "mail@nvimer.org" in text


def test_version_matches_pyproject() -> None:
    data = tomllib.loads((resources.project_root() / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


def test_icon_renders_with_qt_svg() -> None:
    # Qt 的 SVG 图标插件必须能解析该图标，否则桌面/任务栏会回退默认图标。
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(resources.icon_file()))
    assert renderer.isValid()
