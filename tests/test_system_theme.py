"""系统主题探测测试（freedesktop portal color-scheme）。"""

from __future__ import annotations

from quaverq.bridge import system_theme


def test_color_scheme_dark_for_prefer_dark():
    # freedesktop 约定：1 = prefer dark
    assert system_theme.color_scheme_is_dark(1) is True


def test_color_scheme_not_dark_for_prefer_light():
    assert system_theme.color_scheme_is_dark(2) is False


def test_color_scheme_not_dark_for_no_preference():
    assert system_theme.color_scheme_is_dark(0) is False


def test_unwrap_variant_handles_nesting():
    class _V:
        def __init__(self, value):
            self.value = value

    assert system_theme.unwrap_variant(_V(_V(1))) == 1
    assert system_theme.unwrap_variant(_V(2)) == 2
    assert system_theme.unwrap_variant(0) == 0
