"""打包资源定位。

桌面集成资源（``.desktop`` / 图标 / AppStream metainfo）统一放在仓库根
``assets/`` 目录，文件名以 reverse-DNS App ID 为前缀。Q11.2 打包阶段通过
Nuitka ``--include-data-dir`` 把 ``assets/`` 带入 bundle。
"""

from __future__ import annotations

from pathlib import Path

APP_ID = "io.github.jinzhongjia.quaverq"


def project_root() -> Path:
    """仓库根目录（源码布局：``<root>/src/quaverq/resources.py``）。"""
    return Path(__file__).resolve().parents[2]


def assets_dir() -> Path:
    return project_root() / "assets"


def desktop_file() -> Path:
    return assets_dir() / f"{APP_ID}.desktop"


def icon_file() -> Path:
    return assets_dir() / f"{APP_ID}.svg"


def metainfo_file() -> Path:
    return assets_dir() / f"{APP_ID}.metainfo.xml"
