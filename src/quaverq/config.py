"""配置管理.

配置文件路径：
    - Linux: $XDG_CONFIG_HOME/quaverq/config.toml
    - 回退: ~/.config/quaverq/config.toml
"""

from __future__ import annotations

import os
import shutil
import sys
import uuid
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


def _cache_dir() -> Path:
    """获取缓存目录."""
    if sys.platform == "linux":
        base = os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
        return Path(base) / "quaverq"
    return Path.home() / ".cache" / "quaverq"


CACHE_DIR = _cache_dir()


# 旧架构 (pywebview/WebKit + 从未接线的 SQLite 元数据缓存) 遗留的孤儿缓存:
# 当前 PySide6/QML app 不再写入它们, 启动时清理一次避免无主磁盘占用.
_ORPHAN_CONFIG_FILES = ("cache.db", "cache.db-wal", "cache.db-shm")
_ORPHAN_CACHE_DIRS = ("CacheStorage", "WebKitCache")


def purge_orphan_caches(
    config_dir: Path | None = None,
    cache_dir: Path | None = None,
) -> list[Path]:
    """删除旧架构遗留的孤儿缓存, 返回实际删除的路径 (幂等, 失败静默跳过).

    只删白名单内的已知孤儿; 现役文件 (credential.json / state.json / device_id /
    covers/) 一律不动.
    """
    config_dir = Path(config_dir) if config_dir is not None else CONFIG_DIR
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    removed: list[Path] = []

    for name in _ORPHAN_CONFIG_FILES:
        path = config_dir / name
        try:
            if path.is_file():
                path.unlink()
                removed.append(path)
        except OSError:
            pass

    for name in _ORPHAN_CACHE_DIRS:
        path = cache_dir / name
        try:
            if path.is_dir():
                shutil.rmtree(path)
                removed.append(path)
        except OSError:
            pass

    return removed


def _device_id_file() -> Path:
    return _config_dir() / "device_id"


def device_guid(path: Path | None = None) -> str:
    """持久设备 guid（反风控 G1）：首次生成 uuid4 落盘，之后复用。

    模拟真实设备——同一账号始终用同一 guid 取链，避免"多设备"异常被风控。
    """
    target = path or _device_id_file()
    try:
        existing = target.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        existing = ""
    if existing:
        return existing
    guid = uuid.uuid4().hex
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(guid, encoding="utf-8")
    return guid


# 默认配置
DEFAULTS: dict[str, Any] = {
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
