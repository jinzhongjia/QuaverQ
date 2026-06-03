"""启动运行时自检。

检测播放与桌面集成的关键依赖是否就绪，缺失时给出明确提示而非静默崩溃：

- ``multimedia``：Qt 多媒体后端（QtMultimedia / FFmpeg 插件）—— 缺失为 ``critical``，播放不可用。
- ``dbus``：D-Bus 会话总线（MPRIS 媒体键）—— 缺失为 ``warning``，可降级运行。

探测函数可注入，便于测试覆盖各分支；默认探测只做 import / 环境变量检查，
不要求 ``QApplication`` 实例存在。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

INFO = "info"
WARNING = "warning"
CRITICAL = "critical"

Probe = Callable[[], bool]


@dataclass(frozen=True)
class Diagnostic:
    """单项自检结果。"""

    name: str
    ok: bool
    severity: str
    detail: str


def _safe(probe: Probe) -> bool:
    try:
        return bool(probe())
    except Exception:
        return False


def _default_multimedia_probe() -> bool:
    import importlib

    importlib.import_module("PySide6.QtMultimedia")
    return True


def _default_dbus_probe() -> bool:
    import importlib
    import os

    importlib.import_module("dbus_next")
    return bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))


def check_multimedia(probe: Probe | None = None) -> Diagnostic:
    if _safe(probe or _default_multimedia_probe):
        return Diagnostic("multimedia", True, INFO, "Qt 多媒体后端可用")
    return Diagnostic(
        "multimedia",
        False,
        CRITICAL,
        "未检测到 Qt 多媒体后端（QtMultimedia / FFmpeg 插件缺失），播放将不可用",
    )


def check_dbus(probe: Probe | None = None) -> Diagnostic:
    if _safe(probe or _default_dbus_probe):
        return Diagnostic("dbus", True, INFO, "D-Bus 会话可用，MPRIS 媒体键已启用")
    return Diagnostic(
        "dbus",
        False,
        WARNING,
        "未检测到 D-Bus 会话总线，桌面媒体键 / MPRIS 不可用（不影响播放）",
    )


def run_diagnostics(
    *,
    multimedia_probe: Probe | None = None,
    dbus_probe: Probe | None = None,
) -> list[Diagnostic]:
    return [check_multimedia(multimedia_probe), check_dbus(dbus_probe)]


def has_critical(results: list[Diagnostic]) -> bool:
    return any(d.severity == CRITICAL for d in results)


def format_diagnostics(results: list[Diagnostic]) -> str:
    lines = []
    for d in results:
        mark = "OK" if d.ok else d.severity.upper()
        lines.append(f"[{mark}] {d.name}: {d.detail}")
    return "\n".join(lines)
