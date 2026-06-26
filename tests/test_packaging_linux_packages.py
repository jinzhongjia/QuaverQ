"""Linux 原生安装包布局与命令契约。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from quaverq import packaging


def _fake_dist(tmp_path: Path) -> Path:
    dist_dir = tmp_path / "dist" / packaging._NUITKA_DIST_DIRNAME
    dist_dir.mkdir(parents=True)
    exe = dist_dir / "QuaverQ"
    exe.write_bytes(b"#!fake")
    exe.chmod(0o755)
    (dist_dir / "libfake.so").write_bytes(b"so")
    return dist_dir


def test_linux_package_arch_maps_distribution_names():
    assert packaging.linux_package_arch("deb", machine="x86_64") == "amd64"
    assert packaging.linux_package_arch("deb", machine="aarch64") == "arm64"
    assert packaging.linux_package_arch("rpm", machine="x86_64") == "x86_64"
    assert packaging.linux_package_arch("arch", machine="aarch64") == "aarch64"


def test_prepare_linux_package_root_shared_layout(tmp_path):
    dist_dir = _fake_dist(tmp_path)
    package_root = tmp_path / "pkgroot"

    packaging.prepare_linux_package_root(package_root, dist_dir)

    assert (package_root / "opt/quaverq/QuaverQ").is_file()
    assert (package_root / "opt/quaverq/libfake.so").is_file()
    launcher = package_root / "usr/bin/quaverq"
    assert launcher.is_symlink()
    assert launcher.readlink().as_posix() == "/opt/quaverq/QuaverQ"
    desktop = package_root / "usr/share/applications/io.github.jinzhongjia.quaverq.desktop"
    assert "Exec=quaverq\n" in desktop.read_text(encoding="utf-8")
    assert "Exec=QuaverQ\n" not in desktop.read_text(encoding="utf-8")
    assert (
        package_root / "usr/share/icons/hicolor/scalable/apps/io.github.jinzhongjia.quaverq.svg"
    ).is_file()
    assert (
        package_root / "usr/share/metainfo/io.github.jinzhongjia.quaverq.metainfo.xml"
    ).is_file()


def test_build_deb_writes_control_and_invokes_dpkg_deb(tmp_path, monkeypatch):
    _fake_dist(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(packaging.resources, "project_root", lambda: tmp_path)
    monkeypatch.setattr(packaging, "project_version", lambda: "1.2.3")
    monkeypatch.setattr(
        packaging.shutil, "which", lambda name: "/usr/bin/dpkg-deb" if name == "dpkg-deb" else None
    )
    monkeypatch.setattr(packaging.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        packaging.subprocess,
        "run",
        lambda cmd, cwd=None, **kwargs: calls.append(cmd) or SimpleNamespace(returncode=0),
    )

    assert packaging.build_deb(output_dir="dist", rebuild=False) == 0

    control = (tmp_path / "dist/deb-root/DEBIAN/control").read_text(encoding="utf-8")
    assert "Package: quaverq" in control
    assert "Version: 1.2.3" in control
    assert "Architecture: amd64" in control
    assert "Maintainer: jinzhongjia <mail@nvimer.org>" in control
    assert "Depends: libc6" in control
    assert calls == [
        [
            "/usr/bin/dpkg-deb",
            "--root-owner-group",
            "--build",
            str(tmp_path / "dist/deb-root"),
            str(tmp_path / "dist/quaverq_1.2.3_amd64.deb"),
        ]
    ]


def test_rpm_spec_disables_autoreq_and_installs_fixed_paths(tmp_path):
    spec = packaging._rpm_spec_text("1.2.3", tmp_path / "rpm-root")

    assert "Name: quaverq" in spec
    assert "Version: 1.2.3" in spec
    assert "AutoReqProv: no" in spec
    assert "Requires: glibc" in spec
    assert 'cp -a "' in spec
    assert "/opt/quaverq" in spec
    assert "/usr/bin/quaverq" in spec


def test_arch_pkgbuild_uses_project_maintainer_and_package_root(monkeypatch):
    monkeypatch.setattr(packaging.platform, "machine", lambda: "x86_64")

    pkgbuild = packaging._arch_pkgbuild_text("1.2.3")

    assert "# Maintainer: jinzhongjia <mail@nvimer.org>" in pkgbuild
    assert "pkgname=quaverq" in pkgbuild
    assert "pkgver=1.2.3" in pkgbuild
    assert "arch=('x86_64')" in pkgbuild
    assert "depends=('glibc'" in pkgbuild
    assert 'cp -a "$srcdir/package-root/." "$pkgdir/"' in pkgbuild
