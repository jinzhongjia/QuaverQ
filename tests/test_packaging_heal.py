"""bundle 自愈契约: 解析到包外的 libQt6 依赖要从 wheel 补拷进 bundle (含传递依赖)."""

from __future__ import annotations

from pathlib import Path

from quaverq import packaging


def test_parse_ldd_outside_deps():
    bundle = Path("/bundle")
    output = """
\tlinux-vdso.so.1 (0x00007fff0)
\tlibQt6QmlModels.so.6 => /usr/lib/libQt6QmlModels.so.6 (0x00007f1)
\tlibQt6Qml.so.6 => /bundle/libQt6Qml.so.6 (0x00007f2)
\tlibQt6QmlMeta.so.6 => not found
\tlibicuuc.so.76 => /usr/lib/libicuuc.so.76 (0x00007f3)
\tlibc.so.6 => /usr/lib/libc.so.6 (0x00007f4)
"""
    missing = packaging.parse_ldd_outside_qt_deps(output, bundle)
    # 包内已解析的不算; 非 libQt6 前缀的系统库不算; "not found" 与解析到 /usr/lib 的都算
    assert missing == {"libQt6QmlModels.so.6", "libQt6QmlMeta.so.6"}


def test_heal_copies_missing_and_transitive(tmp_path):
    bundle = tmp_path / "bundle"
    wheel = tmp_path / "wheel"
    bundle.mkdir()
    wheel.mkdir()
    (bundle / "libQt6Quick.so.6").write_bytes(b"A")
    (wheel / "libQt6QmlModels.so.6").write_bytes(b"B")
    (wheel / "libQt6QmlMeta.so.6").write_bytes(b"C")

    # 假依赖图: Quick 缺 QmlModels; QmlModels 拷入后又缺 QmlMeta (传递依赖)
    graph = {
        "libQt6Quick.so.6": {"libQt6QmlModels.so.6"},
        "libQt6QmlModels.so.6": {"libQt6QmlMeta.so.6"},
        "libQt6QmlMeta.so.6": set(),
    }

    def fake_outside_deps(lib_path: Path, bundle_dir: Path) -> set[str]:
        return {
            name for name in graph.get(lib_path.name, set()) if not (bundle_dir / name).exists()
        }

    copied = packaging.heal_qt_bundle(bundle, wheel_lib_dir=wheel, outside_deps=fake_outside_deps)

    assert (bundle / "libQt6QmlModels.so.6").read_bytes() == b"B"
    assert (bundle / "libQt6QmlMeta.so.6").read_bytes() == b"C"
    assert copied == ["libQt6QmlMeta.so.6", "libQt6QmlModels.so.6"]


def test_heal_reports_unfixable(tmp_path):
    bundle = tmp_path / "bundle"
    wheel = tmp_path / "wheel"
    bundle.mkdir()
    wheel.mkdir()
    (bundle / "libQt6Quick.so.6").write_bytes(b"A")
    # wheel 里没有这个库 -> 自愈无能为力, 返回 unfixable 而不是静默

    def fake_outside_deps(lib_path: Path, bundle_dir: Path) -> set[str]:
        if lib_path.name == "libQt6Quick.so.6":
            return {"libQt6Mystery.so.6"}
        return set()

    copied = packaging.heal_qt_bundle(bundle, wheel_lib_dir=wheel, outside_deps=fake_outside_deps)
    assert copied == []
