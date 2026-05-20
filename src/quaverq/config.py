"""配置管理.

配置文件路径：
    - Linux: $XDG_CONFIG_HOME/quaverq/config.toml
    - 回退: ~/.config/quaverq/config.toml
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """获取配置目录."""
    if sys.platform == "linux":
        base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        return Path(base) / "quaverq"
    return Path.home() / ".config" / "quaverq"


CONFIG_DIR = _config_dir()
CONFIG_FILE = CONFIG_DIR / "config.toml"


# 默认配置
DEFAULTS: dict[str, Any] = {
    "ui": {
        "backend": "auto",  # auto | qt | gtk
    },
    "api": {
        "cookie_file": "",  # QQ 音乐 cookie 文件路径
    },
    "player": {
        "volume": 0.8,
        "quality": "balanced",  # high / balanced / standard
    },
}


def load() -> dict[str, Any]:
    """加载并合并配置（默认 + 文件）."""
    config = _deep_merge(DEFAULTS.copy(), {})

    if CONFIG_FILE.exists():
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        with open(CONFIG_FILE, "rb") as f:
            user = tomllib.load(f)
        config = _deep_merge(config, user)

    return config


def save(config: dict[str, Any]) -> None:
    """保存配置到文件."""
    import tomli_w

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(config, f)


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个 dict，override 优先."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
