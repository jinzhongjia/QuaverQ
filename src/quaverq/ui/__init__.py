"""桌面环境检测与 UI 后端选择."""

from __future__ import annotations

import logging
import os
import sys

from .base import UIBase

logger = logging.getLogger(__name__)

# DE → 推荐后端映射
_DE_BACKEND: dict[str, str] = {
    "kde": "qt",
    "plasma": "qt",
    "lxqt": "qt",
    "razor": "qt",
    "gnome": "gtk",
    "gnome-xorg": "gtk",
    "gnome-wayland": "gtk",
    "ubuntu:gnome": "gtk",
    "unity": "gtk",
    "xfce": "gtk",
    "mate": "gtk",
    "cinnamon": "gtk",
    "budgie": "gtk",
    "pantheon": "gtk",
    "deepin": "gtk",
}


def _detect_de() -> str | None:
    """检测当前桌面环境."""
    xdg = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if xdg:
        # 可能包含多个值（分号分隔），取第一个匹配的
        for de in xdg.split(":"):
            de = de.strip()
            if de in _DE_BACKEND:
                return _DE_BACKEND[de]
        # 模糊匹配
        for name, backend in _DE_BACKEND.items():
            if name in xdg:
                return backend

    # 兜底：检查 DESKTOP_SESSION
    session = os.environ.get("DESKTOP_SESSION", "").lower()
    for name, backend in _DE_BACKEND.items():
        if name in session:
            return backend

    # 检查 GDMSESSION
    gdm = os.environ.get("GDMSESSION", "").lower()
    for name, backend in _DE_BACKEND.items():
        if name in gdm:
            return backend

    return None


def resolve_backend(explicit: str = "auto") -> str:
    """解析最终使用的 UI 后端.

    Args:
        explicit: 明确指定的后端名 (auto / qt / gtk)

    Returns:
        后端名 (qt / gtk)
    """
    if explicit in ("qt", "gtk"):
        return explicit

    detected = _detect_de()
    if detected:
        logger.info("检测到桌面环境 → %s 后端", detected)
        return detected

    logger.warning("无法检测桌面环境，回退到 GTK")
    return "gtk"


def create_ui(backend: str) -> UIBase:
    """根据后端名创建 UI 实例.

    Args:
        backend: "qt" 或 "gtk"

    Returns:
        UIBase 子类实例

    Raises:
        ImportError: 所需的 UI 库未安装
        RuntimeError: 不支持的后端名
    """
    if backend == "qt":
        from .qt.app import QtUI

        return QtUI()

    if backend == "gtk":
        from .gtk.app import GtkUI

        return GtkUI()

    raise RuntimeError(f"不支持的 UI 后端: {backend}")


def check_availability(backend: str) -> bool:
    """检查指定后端的依赖是否可用."""
    try:
        if backend == "qt":
            from PySide6 import QtWidgets  # noqa: F401
        elif backend == "gtk":
            import gi  # noqa: F401
            gi.require_version("Gtk", "4.0")
            from gi.repository import Gtk  # noqa: F401
        else:
            return False
        return True
    except (ImportError, ValueError):
        return False
