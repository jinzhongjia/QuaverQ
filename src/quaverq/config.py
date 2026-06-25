"""配置管理.

配置 / 缓存路径走 platformdirs, 跨平台规则:
    - Linux:   $XDG_CONFIG_HOME/quaverq, $XDG_CACHE_HOME/quaverq
               (XDG 未设时回退 ~/.config / ~/.cache, 与历史行为一致)
    - Windows: %APPDATA%\\quaverq, %LOCALAPPDATA%\\quaverq\\Cache
    - macOS:   ~/Library/Application Support/quaverq, ~/Library/Caches/quaverq
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from platformdirs import PlatformDirs

_APP_NAME = "quaverq"


def _dirs() -> PlatformDirs:
    """构造 PlatformDirs.

    - ``appauthor=False``: Windows 不塞 ``<author>\\`` 中间层.
    - ``roaming=True``: Windows config 走 ``%APPDATA%`` (Roaming) 而非 Local, 跟用户漫游.
    - ``opinion=False``: 关掉 platformdirs 的"opinionated" 后缀 —— 它默认在 Windows
      cache dir 末尾加 ``\\Cache``, 跟 Qt 自动管理的 ``cache\\`` 子目录大小写撞车,
      且 cache 子目录又有 ``Cache``/``cache`` 看着乱. 关掉后 CACHE_DIR 就是
      ``%LOCALAPPDATA%\\quaverq`` 顶层 (单目录, 小写), Qt 内部 QML / 渲染管线缓存
      自动落到 ``%LOCALAPPDATA%\\quaverq\\cache\\`` 子目录里 (Qt 默认 CacheLocation),
      跟我们的 ``covers/`` / ``home.json`` 干净分开.
    """
    return PlatformDirs(appname=_APP_NAME, appauthor=False, roaming=True, opinion=False)


def _config_dir() -> Path:
    return Path(_dirs().user_config_dir)


def _cache_dir() -> Path:
    return Path(_dirs().user_cache_dir)


CONFIG_DIR = _config_dir()
CONFIG_FILE = CONFIG_DIR / "config.toml"
CACHE_DIR = _cache_dir()


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


def _risk_ct_file() -> Path:
    return _config_dir() / "risk_ct"


def risk_ct(allowed: Sequence[int], path: Path | None = None) -> int:
    """持久"风控指纹"(vkey 接口 ct 值): 首次从 allowed 随机落盘, 之后复用。

    像固定设备一样——真实客户端不会每次启动换 ct。落盘值若已不在 allowed
    (池子缩小/某 ct 被加黑剔除) 或文件损坏, 自动重抽, 不把用户钉死在失效值上。
    """
    target = path or _risk_ct_file()
    try:
        existing = int(target.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        existing = None
    if existing is not None and existing in allowed:
        return existing
    return reset_risk_ct(allowed, target)


def reset_risk_ct(allowed: Sequence[int], path: Path | None = None) -> int:
    """强制重抽一个 ct 并落盘 (设置页"重置风控指纹"); 返回新值。"""
    target = path or _risk_ct_file()
    value = random.choice(list(allowed))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(value), encoding="utf-8")
    return value


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
    if not CONFIG_FILE.exists():
        return deepcopy(DEFAULTS)

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    with open(CONFIG_FILE, "rb") as f:
        user = tomllib.load(f)
    return _deep_merge(DEFAULTS, user)


def save(config: dict[str, Any]) -> None:
    """保存配置到文件."""
    import tomli_w

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(config, f)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并两个 dict，override 优先."""
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
