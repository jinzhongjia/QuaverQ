"""portable 归档格式契约: Linux 用 tar.gz (保 +x 位), Windows 用 zip."""

from __future__ import annotations

import tarfile

from quaverq import packaging


def test_portable_archive_name_by_platform():
    # zip 不保留 Unix 可执行位, Linux/macOS 解出来二进制没 +x; tar.gz 原生保留
    assert (
        packaging.portable_archive_name("1.2.3", platform="win32") == "QuaverQ-1.2.3-portable.zip"
    )
    assert (
        packaging.portable_archive_name("1.2.3", platform="linux")
        == "QuaverQ-1.2.3-portable.tar.gz"
    )
    assert (
        packaging.portable_archive_name("1.2.3", platform="darwin")
        == "QuaverQ-1.2.3-portable.tar.gz"
    )


def test_portable_targz_preserves_executable_bit_and_layout(tmp_path, monkeypatch):
    # 假 Nuitka 产物: 可执行主程序 + 普通数据文件
    dist_dir = tmp_path / "dist" / packaging._NUITKA_DIST_DIRNAME
    dist_dir.mkdir(parents=True)
    exe = dist_dir / "QuaverQ"
    exe.write_bytes(b"#!fake")
    exe.chmod(0o755)
    (dist_dir / "data.txt").write_text("x", encoding="utf-8")
    (dist_dir / "sub").mkdir()
    (dist_dir / "sub" / "lib.so").write_bytes(b"so")

    monkeypatch.setattr(packaging.resources, "project_root", lambda: tmp_path)
    monkeypatch.setattr(packaging, "project_version", lambda: "0.0.test")

    rc = packaging.build_portable(rebuild=False)
    assert rc == 0

    archive = tmp_path / "dist" / "QuaverQ-0.0.test-portable.tar.gz"
    assert archive.exists()

    with tarfile.open(archive, "r:gz") as tf:
        names = tf.getnames()
        # 顶层目录包一层, 防"解压到这里"喷一地
        assert all(n.startswith("QuaverQ-0.0.test/") for n in names)
        assert "QuaverQ-0.0.test/QuaverQ" in names
        assert "QuaverQ-0.0.test/sub/lib.so" in names
        exe_member = tf.getmember("QuaverQ-0.0.test/QuaverQ")
        # 可执行位必须保留 (zip 会丢, 这是 Linux 改 tar.gz 的全部理由)
        assert exe_member.mode & 0o111
