"""issue #11 排查: Linux 上 ffmpeg 日志静音失效的纯函数契约.

`_silence_ffmpeg_logs` 旧实现只在 PySide6 顶层 glob libavutil, 但 Linux/macOS 的
ffmpeg 库实际在 `PySide6/Qt/lib/` 子目录 -> candidates 为空 -> av_log_set_level
从未被调到 -> ffmpeg 一直刷 invalid sync code / Input #0 元数据到 stderr.
"""

from __future__ import annotations

from quaverq.__main__ import _libavutil_candidates


def test_linux_searches_qt_lib_subdir(tmp_path):
    # Linux: 库在 PySide6/Qt/lib/, 必须搜到子目录 (旧实现漏了 -> 静音全失效)
    pyside = tmp_path / "PySide6"
    qtlib = pyside / "Qt" / "lib"
    qtlib.mkdir(parents=True)
    (qtlib / "libavutil.so").touch()  # ld-script / symlink 占位, 应跳过
    (qtlib / "libavutil.so.59").touch()
    (qtlib / "libavutil.so.59.39.100").touch()

    names = [c.name for c in _libavutil_candidates("linux", pyside)]

    assert "libavutil.so.59" in names
    # 只取带版本号的, 不取裸 libavutil.so (可能是链接器专用 ld script, 不可 dlopen)
    assert "libavutil.so" not in names


def test_linux_empty_when_no_qt_lib(tmp_path):
    pyside = tmp_path / "PySide6"
    pyside.mkdir()
    assert _libavutil_candidates("linux", pyside) == []


def test_windows_searches_top_level_and_qt_bin(tmp_path):
    pyside = tmp_path / "PySide6"
    (pyside / "Qt" / "bin").mkdir(parents=True)
    (pyside / "avutil-59.dll").touch()
    (pyside / "Qt" / "bin" / "avutil-58.dll").touch()

    names = [c.name for c in _libavutil_candidates("win32", pyside)]

    assert "avutil-59.dll" in names
    assert "avutil-58.dll" in names


def test_macos_searches_qt_lib(tmp_path):
    pyside = tmp_path / "PySide6"
    qtlib = pyside / "Qt" / "lib"
    qtlib.mkdir(parents=True)
    (qtlib / "libavutil.59.dylib").touch()

    names = [c.name for c in _libavutil_candidates("darwin", pyside)]
    assert "libavutil.59.dylib" in names


def test_unknown_platform_returns_empty(tmp_path):
    assert _libavutil_candidates("sunos", tmp_path) == []
