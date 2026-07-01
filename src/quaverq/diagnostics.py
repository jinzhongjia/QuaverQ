"""启动运行时自检。

检测播放与桌面集成的关键依赖是否就绪，缺失时给出明确提示而非静默崩溃：

- ``multimedia``：Qt 多媒体后端（QtMultimedia / FFmpeg 插件）—— 缺失为 ``critical``，播放不可用。
- ``dbus``：D-Bus 会话总线（MPRIS 媒体键 / 单实例 / 歌词外发）—— 缺失为 ``critical``，
  Linux 桌面环境不满足最低运行要求。
  仅 Linux 桌面适用；Windows 走 SMTC、macOS 走 NowPlayingInfoCenter，
  调用方应当通过 ``include_dbus=False`` 跳过此检查 (见 ``__main__.py``)。

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
    """检 ``PySide6.QtMultimedia`` 能 import **且** Qt 实际搜索的插件路径下 ``multimedia/`` 非空.

    Nuitka 打包时如果漏带 ``--include-qt-plugins=multimedia``, 模块本身能 import
    (.pyd 在), 但运行时 ``QMediaPlayer`` 找不到 FFmpeg / WMF 等后端插件, 启动报
    "No QtMultimedia backends found" 不能播放. 仅检 import 会误报 OK, 所以还要确认
    ``<Qt 插件目录>/multimedia/`` 真的有插件文件.

    **不能只查 ``QLibraryInfo.PluginsPath``**: Nuitka standalone 把 Qt 插件从 wheel 的
    ``PySide6/plugins`` 重定位到 ``PySide6/qt-plugins`` 并注入 ``QCoreApplication.
    libraryPaths()`` 供 Qt 运行时检索, 但 ``QLibraryInfo.PluginsPath`` 仍报那个已不
    存在的 ``PySide6/plugins`` —— 只查它会在打包产物里**假阴性**, 把插件其实齐全的
    可用包当成"后端缺失"直接 critical 退出 (现象: 双击 exe / 终端跑都无反应即闪退).
    改为遍历 Qt 真正搜索的所有 library path (覆盖 dev wheel + Nuitka bundle 两种布局),
    任一含非空 ``multimedia/`` 即算后端就绪; 全空才算真缺失.
    """
    import importlib
    from pathlib import Path

    importlib.import_module("PySide6.QtMultimedia")
    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    # PluginsPath (dev wheel 布局正确) + libraryPaths (Nuitka 注入 qt-plugins);
    # 去重后逐个看 multimedia/ 子目录. 至少一个后端插件 (Windows:
    # ffmpegmediaplugin.dll / windowsmediaplugin.dll; Linux: libffmpegmediaplugin.so 等).
    candidates = [
        Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)),
        *(Path(p) for p in QCoreApplication.libraryPaths()),
    ]
    seen: set[Path] = set()
    for base in candidates:
        if base in seen:
            continue
        seen.add(base)
        multimedia_dir = base / "multimedia"
        if multimedia_dir.is_dir() and any(multimedia_dir.iterdir()):
            return True
    return False


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
        CRITICAL,
        "未检测到 D-Bus 会话总线，Linux 桌面集成能力不可用，应用拒绝启动",
    )


def run_diagnostics(
    *,
    multimedia_probe: Probe | None = None,
    dbus_probe: Probe | None = None,
    include_dbus: bool = True,
) -> list[Diagnostic]:
    """跑所有相关自检. ``include_dbus=False`` 时跳过 D-Bus 检查 (Windows / macOS 用),
    避免在没有 D-Bus 概念的平台上误报 warning."""
    results = [check_multimedia(multimedia_probe)]
    if include_dbus:
        results.append(check_dbus(dbus_probe))
    return results


def has_critical(results: list[Diagnostic]) -> bool:
    return any(d.severity == CRITICAL for d in results)


def format_diagnostics(results: list[Diagnostic]) -> str:
    lines = []
    for d in results:
        mark = "OK" if d.ok else d.severity.upper()
        lines.append(f"[{mark}] {d.name}: {d.detail}")
    return "\n".join(lines)
