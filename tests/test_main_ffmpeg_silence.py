"""FFmpeg 日志静音的 libavutil 路径查找契约.

回归: PySide6 在 Linux/macOS 把 Qt 库放 ``Qt/lib`` 子目录, 旧实现只搜顶层
导致 ``av_log_set_level`` 从未命中, FFmpeg 每次切歌仍刷 stderr.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from quaverq.__main__ import _libavutil_candidates


def test_finds_library_in_qt_lib_subdir(tmp_path):
    qtlib = tmp_path / "Qt" / "lib"
    qtlib.mkdir(parents=True)
    lib = qtlib / "libavutil.so.59"
    lib.write_bytes(b"")
    assert lib in _libavutil_candidates(tmp_path, "linux")


def test_finds_top_level_windows_dll(tmp_path):
    dll = tmp_path / "avutil-59.dll"
    dll.write_bytes(b"")
    assert dll in _libavutil_candidates(tmp_path, "win32")


def test_finds_macos_dylib_in_qt_lib(tmp_path):
    qtlib = tmp_path / "Qt" / "lib"
    qtlib.mkdir(parents=True)
    lib = qtlib / "libavutil.58.dylib"
    lib.write_bytes(b"")
    assert lib in _libavutil_candidates(tmp_path, "darwin")


def test_unknown_platform_returns_empty(tmp_path):
    assert _libavutil_candidates(tmp_path, "freebsd") == []


def test_no_match_returns_empty(tmp_path):
    # 目录里没有 libavutil → 空列表 (best-effort, 不抛)
    assert _libavutil_candidates(tmp_path, "linux") == []


@pytest.mark.skipif(sys.platform != "linux", reason="验证真实 Linux PySide6 布局")
def test_real_pyside6_linux_has_libavutil():
    # 修复前此处返回空 (只搜顶层) → 静音失效; 修复后应在 Qt/lib 命中
    import PySide6

    pyside_dir = Path(PySide6.__file__).parent
    assert _libavutil_candidates(pyside_dir, "linux"), "应在 PySide6/Qt/lib 找到 libavutil"
