"""打包：Nuitka standalone 构建 + AppImage 封装。

命令组装与 AppDir 布局是纯函数，便于测试；真正的编译 / linuxdeploy 调用在
:func:`build` / :func:`build_appimage` 内执行（依赖 nuitka、linuxdeploy，通常在 CI 跑）。

要点：
- ``--enable-plugin=pyside6`` 让 Nuitka 正确带 Qt/QML 运行时。
- ``--include-package-data=quaverq`` 把包内 ``qml/`` ``Theme/`` 等数据文件带进 bundle。
- **curl_cffi 必须显式 include**：它在 service/stream_proxy 里是函数内动态 import，
  且带 native ``_wrapper.abi3.so``（libcurl-impersonate）；漏掉会导致取链 / 回环代理失效。
- ``assets/`` 经 ``--include-data-dir`` 进 bundle，供 AppImage 的 .desktop / 图标 / metainfo。
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import tomllib

from . import resources

APP_ID = resources.APP_ID

# 这些包有大量运行时动态 import（niquests/urllib3-future 的 DNS resolver、
# HTTP/2/3 后端 jh2/qh3、wassima CA、curl_cffi native、qqmusic_api 动态模块），
# nuitka 静态分析会漏，必须整包显式包含。
_FORCE_INCLUDE_PACKAGES = (
    "quaverq",
    "curl_cffi",
    "niquests",
    "urllib3",
    "urllib3_future",
    "charset_normalizer",
    "wassima",
    "jh2",
    "qh3",
    "qqmusic_api",
    "dbus_next",
)

# PySide6 的 qml 插件会把整套 Qt 库都打进来；这些模块音乐播放器用不到，显式排除以瘦身
# （仅 WebEngineCore 单个就 ~195MB）。只排"明确没用且重"的，不碰运行时真依赖：
# Quick / QuickControls2* / Qml* / Multimedia / Svg / Network / DBus / OpenGL /
# ShaderTools / WaylandClient / Quick(Layouts|Templates2|Shapes|Effects) 等。
_EXCLUDE_QT_DLL_PATTERNS = (
    "*WebEngine*",
    "*WebView*",
    "*WebChannel*",
    "*Quick3D*",
    "*Qt63D*",
    "*Qt6Pdf*",
    "*Charts*",
    "*DataVisualization*",
    "*Qt6Graphs*",
    "*VirtualKeyboard*",
    "*Qt6Location*",
    "*Qt6Positioning*",
    "*Qt6Scxml*",
    "*RemoteObjects*",
    "*Qt6Sensors*",
    "*TextToSpeech*",
    "*SpatialAudio*",
    "*WaylandCompositor*",
)


def project_version() -> str:
    data = tomllib.loads((resources.project_root() / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def nuitka_command(
    mode: str = "standalone",
    *,
    version: str | None = None,
    output_dir: str = "dist",
    python: str | None = None,
) -> list[str]:
    """组装 Nuitka 编译命令（不执行）。"""
    root = resources.project_root()
    version = version or project_version()
    python = python or sys.executable
    return [
        python,
        "-m",
        "nuitka",
        f"--{mode}",
        "--assume-yes-for-downloads",
        f"--output-dir={output_dir}",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=sensible,qml",  # QtQuick / QtMultimedia / Layouts 运行时
        *(f"--noinclude-dlls={pattern}" for pattern in _EXCLUDE_QT_DLL_PATTERNS),
        "--include-package-data=quaverq",  # qml / Theme / qmldir
        "--include-package-data=curl_cffi",  # native _wrapper.so + libcurl
        f"--include-data-dir={root / 'assets'}=assets",
        *(f"--include-package={pkg}" for pkg in _FORCE_INCLUDE_PACKAGES),
        "--product-name=QuaverQ",
        f"--product-version={version}",
        f"--file-version={version}",
        # 可执行名不能等于包名 quaverq，否则与包数据目录 quaverq/(qml) 冲突
        "--output-filename=QuaverQ",
        "--noinclude-pytest-mode=nofollow",
        "--noinclude-unittest-mode=nofollow",
        # 不用 LTO：LTO 让 nuitka 编译 PySide6 慢数倍，在 CI 2 核 runner 上不实际
        # （实测 >35min 未完）；no-LTO 产物功能一致、体积略大，本地已验证可启动。
        f"--jobs={os.cpu_count() or 4}",
        # 以包目录为入口 + -m：让 __main__ 有 quaverq 包上下文，relative import 才有效
        "--python-flag=-m",
        str(root / "src" / "quaverq"),
    ]


def appimage_appdir_layout(appdir: str | Path) -> dict[Path, Path]:
    """AppDir 内桌面集成文件的 目标路径 → 源文件 映射。"""
    base = Path(appdir)
    return {
        base / "usr/share/applications" / f"{APP_ID}.desktop": resources.desktop_file(),
        base / "usr/share/icons/hicolor/scalable/apps" / f"{APP_ID}.svg": resources.icon_file(),
        base / "usr/share/metainfo" / f"{APP_ID}.metainfo.xml": resources.metainfo_file(),
    }


def linuxdeploy_command(
    appdir: str | Path,
    *,
    linuxdeploy: str = "linuxdeploy",
) -> list[str]:
    """组装 linuxdeploy 命令（不执行）。"""
    base = Path(appdir)
    # 不用 linuxdeploy-plugin-qt：Nuitka 的 pyside6 插件已把 PySide6 自带的整套 Qt
    # （平台插件 libqxcb、qml 模块、imageformats 等）打进 bundle 且 standalone 可跑；
    # qt 插件会再去部署「系统」Qt（/usr/lib/qt6），引入多余的 sqldrivers 等并因系统缺
    # libfbclient 之类依赖而整体失败。linuxdeploy 只负责部署非 Qt 系统库 + 封装 AppImage。
    return [
        linuxdeploy,
        "--appdir",
        str(base),
        f"--desktop-file={base / 'usr/share/applications' / (APP_ID + '.desktop')}",
        f"--icon-file={resources.icon_file()}",
        "--output",
        "appimage",
    ]


def clean_stray_qt_objects() -> int:
    """删除 PySide6 wheel 误带的 .o 构建中间产物。

    PySide6 的 ``Qt/qml/**/objects-*/`` 里有 ``.cpp.o`` 文件（不该分发），nuitka 复制后
    会对其调用 patchelf 设置 rpath，但 .o 是可重定位目标文件，patchelf 报 'wrong ELF type'
    导致打包中断。运行时用不到这些 .o，编译前删掉即可。
    """
    import PySide6

    qml = Path(PySide6.__file__).resolve().parent / "Qt" / "qml"
    removed = 0
    if qml.is_dir():
        for obj in qml.rglob("*.o"):
            obj.unlink()
            removed += 1
    return removed


def build(mode: str = "standalone") -> int:
    clean_stray_qt_objects()
    cmd = nuitka_command(mode)
    print("[build]", " ".join(shlex.quote(c) for c in cmd))
    return subprocess.run(cmd, cwd=resources.project_root()).returncode


def build_appimage(output_dir: str = "dist") -> int:
    """standalone 编译 → 组装 AppDir → linuxdeploy 产出 AppImage。"""
    root = resources.project_root()
    rc = build("standalone")
    if rc != 0:
        return rc
    dist = root / output_dir / "quaverq.dist"
    appdir = root / output_dir / "AppDir"
    bindir = appdir / "usr/bin"
    bindir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(dist, bindir, dirs_exist_ok=True)
    for target, src in appimage_appdir_layout(appdir).items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    cmd = linuxdeploy_command(appdir)
    print("[appimage]", " ".join(shlex.quote(c) for c in cmd))
    # NO_STRIP: 新系统库 (Arch 等) 带 .relr.dyn 段, linuxdeploy 自带的旧 strip 不识别会报
    # 'unknown type [0x13]' 而整体失败; 跳过 strip, 体积由 appimagetool 的 zstd 压缩兜底。
    env = {**os.environ, "NO_STRIP": "1"}
    return subprocess.run(cmd, cwd=root / output_dir, env=env).returncode


_SMOKE_OK_MARKER = "QuaverQ started with QML"
_SMOKE_FAIL_MARKERS = ("QML load failed", "is not installed", "Traceback", "FATAL:")


def smoke_output_ok(output: str) -> bool:
    """判定产物启动输出：QML 加载 + 窗口创建，且无致命错误。"""
    return _SMOKE_OK_MARKER in output and not any(
        marker in output for marker in _SMOKE_FAIL_MARKERS
    )


def smoke_test(binary: str | Path, *, timeout: float = 20.0) -> bool:
    """offscreen 启动产物，确认能加载 QML 并创建窗口（不依赖登录 / 网络成功）。"""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    try:
        proc = subprocess.run(
            [str(binary)], env=env, timeout=timeout, capture_output=True, text=True
        )
        output = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        # app 是常驻事件循环，超时被 kill 是预期；用已捕获输出判定
        def _text(value: object) -> str:
            if isinstance(value, bytes):
                return value.decode("utf-8", "replace")
            return value or ""

        output = _text(exc.stdout) + _text(exc.stderr)
    return smoke_output_ok(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="QuaverQ 打包")
    parser.add_argument("--onefile", action="store_true", help="编译为单文件")
    parser.add_argument("--appimage", action="store_true", help="standalone + AppImage")
    parser.add_argument("--smoke", metavar="BINARY", help="对产物跑 smoke 启动自检")
    args = parser.parse_args()

    if args.smoke:
        ok = smoke_test(args.smoke)
        print("SMOKE", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    if args.appimage:
        sys.exit(build_appimage())
    sys.exit(build("onefile" if args.onefile else "standalone"))


if __name__ == "__main__":
    main()
