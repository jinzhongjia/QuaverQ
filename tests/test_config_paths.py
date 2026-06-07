"""跨平台路径测试.

策略: 测试在当前运行平台上跑 (skipif 跳其他平台). CI matrix 各平台跑自己那段,
覆盖 Linux/Windows/macOS 三套路径. 不试图 mock sys.platform 让 platformdirs
"假装别的平台" —— platformdirs 是按平台静态分发的, 跨平台 mock 不可靠.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _reload_config() -> object:
    """重新 import config 让模块级常量基于当前环境重算."""
    import quaverq.config as cfg

    return importlib.reload(cfg)


# ============================================================== Linux (XDG)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_linux_uses_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    cfg = _reload_config()

    assert tmp_path / "xdg-config" / "quaverq" == cfg.CONFIG_DIR
    assert tmp_path / "xdg-cache" / "quaverq" == cfg.CACHE_DIR


@pytest.mark.skipif(sys.platform != "linux", reason="Linux only")
def test_linux_falls_back_to_dot_config(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    cfg = _reload_config()

    assert tmp_path / "home" / ".config" / "quaverq" == cfg.CONFIG_DIR
    assert tmp_path / "home" / ".cache" / "quaverq" == cfg.CACHE_DIR


# ============================================================== Windows


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_config_dir_in_appdata():
    """Windows: CONFIG_DIR 在 %APPDATA% (Roaming) 下, CACHE_DIR 在 %LOCALAPPDATA% 下,
    路径形如 .../<APPDATA>/quaverq, .../<LOCALAPPDATA>/quaverq/Cache.

    appauthor=False 让路径不带 "<author>" 中间层.
    """
    import os

    cfg = _reload_config()

    appdata = Path(os.environ["APPDATA"])
    localappdata = Path(os.environ["LOCALAPPDATA"])

    assert cfg.CONFIG_DIR.is_absolute()
    assert cfg.CONFIG_DIR.name == "quaverq"
    # CONFIG_DIR 必须在 APPDATA 子树内
    assert appdata in cfg.CONFIG_DIR.parents

    assert cfg.CACHE_DIR.is_absolute()
    assert "quaverq" in cfg.CACHE_DIR.parts
    assert localappdata in cfg.CACHE_DIR.parents


# ============================================================== macOS


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_uses_library_application_support(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    cfg = _reload_config()

    home = tmp_path / "home"
    assert home / "Library" / "Application Support" / "quaverq" == cfg.CONFIG_DIR
    assert home / "Library" / "Caches" / "quaverq" == cfg.CACHE_DIR


# ============================================================== 跨平台回归


def test_module_exposes_constants():
    """所有平台都必须暴露 CONFIG_DIR / CACHE_DIR / CONFIG_FILE 三个 Path 常量."""
    cfg = _reload_config()
    assert isinstance(cfg.CONFIG_DIR, Path)
    assert isinstance(cfg.CACHE_DIR, Path)
    assert cfg.CONFIG_FILE == cfg.CONFIG_DIR / "config.toml"
    # 应用名一定出现在路径里 (避免误落到 home root)
    assert "quaverq" in cfg.CONFIG_DIR.parts
    assert "quaverq" in cfg.CACHE_DIR.parts
