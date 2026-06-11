"""W10: 启动期按平台设默认字体的纯函数契约."""

from __future__ import annotations

from quaverq.__main__ import _platform_default_font_family


def test_windows_uses_yahei_ui():
    # Windows 默认 Segoe UI 无 CJK 字形, 中英混排逐字 fallback 基线/字重不一致
    assert _platform_default_font_family("win32") == "Microsoft YaHei UI"


def test_linux_and_macos_leave_fontconfig_alone():
    assert _platform_default_font_family("linux") is None
    assert _platform_default_font_family("darwin") is None
