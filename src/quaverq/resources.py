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
    """定位 ``assets/``，兼容源码与 Nuitka bundle 两种布局。

    - 源码: ``<root>/src/quaverq/resources.py`` → ``<root>/assets``（parents[2]）。
    - Nuitka bundle: ``<dist>/quaverq/resources.py`` → ``<dist>/assets``（parents[1]，
      assets 与 quaverq/ 同级，由 ``--include-data-dir=assets=assets`` 放置）。
    """
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1]):
        candidate = base / "assets"
        if candidate.is_dir():
            return candidate
    return project_root() / "assets"


def desktop_file() -> Path:
    return assets_dir() / f"{APP_ID}.desktop"


def icon_file() -> Path:
    return assets_dir() / f"{APP_ID}.svg"


def metainfo_file() -> Path:
    return assets_dir() / f"{APP_ID}.metainfo.xml"
