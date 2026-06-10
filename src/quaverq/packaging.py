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

# Nuitka standalone 产物目录名 = 入口脚本 basename + ".dist". 我们入口是
# ``src/quaverq_entry.py`` (包外 shim, 见 nuitka_command 注释), 因此 dist 子目录
# 名是 ``quaverq_entry.dist``. 不要改, 改了得同步改 packaging.py 里所有引用.
_NUITKA_DIST_DIRNAME = "quaverq_entry.dist"

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
)

# Linux-only 包: 仅在 Linux 上 install (pyproject sys_platform marker 控制),
# Windows / macOS 上压根没装, --include-package=dbus_next 会让 Nuitka 找不到包而崩.
_LINUX_ONLY_PACKAGES = ("dbus_next",)

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


def render_ico_from_svg(svg_path: Path, ico_path: Path, *, size: int = 256) -> None:
    """把 SVG 光栅化成 ``size x size`` 的 ICO. 没 ``QGuiApplication`` 时启个 offscreen 的.

    用于打包 (Nuitka --windows-icon-from-ico + MSI ARPPRODUCTICON 都需要 .ico).
    Windows Shell 会自动缩放单尺寸 ICO 到 16/32/48/256 各尺寸, 视觉损失可接受;
    需要多分辨率 ICO 的话再升级 (例如用 Pillow 写多帧 ICO).
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication(["build"])
    del app  # 仅用其副作用 (初始化 Qt 字体 / image plugin)
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise ValueError(f"SVG 加载失败: {svg_path}")
    img = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    if not img.save(str(ico_path), "ICO"):
        raise ValueError(f"ICO 写入失败: {ico_path}")


def project_version() -> str:
    data = tomllib.loads((resources.project_root() / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def nuitka_command(
    mode: str = "standalone",
    *,
    version: str | None = None,
    output_dir: str = "dist",
    python: str | None = None,
    icon_path: Path | None = None,
) -> list[str]:
    """组装 Nuitka 编译命令（不执行）。

    Nuitka 4 默认生成的 Windows manifest 已经包含: DPI awareness ``PerMonitorV2`` /
    supportedOS Win 7-11 / ``requestedExecutionLevel asInvoker`` (无 UAC 弹窗) /
    ``longPathAware`` —— 我们不再自定义 manifest, 默认值都符合 QuaverQ 需求.
    若额外传 ``icon_path`` 则用 ``--windows-icon-from-ico`` 嵌入到 exe 资源段
    (任务栏 / 资源管理器都按这个图标显示).
    """
    root = resources.project_root()
    version = version or project_version()
    python = python or sys.executable
    # Linux 才追加 dbus_next 等 Linux-only 包; Windows / macOS 上没装 -> Nuitka 报
    # "failed to locate package" 直接 FATAL.
    force_packages = list(_FORCE_INCLUDE_PACKAGES)
    if sys.platform == "linux":
        force_packages.extend(_LINUX_ONLY_PACKAGES)
    cmd = [
        python,
        "-m",
        "nuitka",
        f"--{mode}",
        "--assume-yes-for-downloads",
        f"--output-dir={output_dir}",
        "--enable-plugin=pyside6",
        # sensible (platforms/styles/imageformats) + qml (Qt Quick 模块) +
        # multimedia (QMediaPlayer ffmpeg backend 插件; 不加 Windows 上启动会报
        # "No QtMultimedia backends found" 不能播放).
        "--include-qt-plugins=sensible,qml,multimedia",
        *(f"--noinclude-dlls={pattern}" for pattern in _EXCLUDE_QT_DLL_PATTERNS),
        "--include-package-data=quaverq",  # qml / Theme / qmldir
        "--include-package-data=curl_cffi",  # native _wrapper.so + libcurl
        f"--include-data-dir={root / 'assets'}=assets",
        # WiX 模板是 MSI 构建时给 build_msi() 用的, 不需要进运行时 bundle.
        # --include-data-dir 会把 assets/ 整目录拉进来, 这里挑出来踢掉.
        "--noinclude-data-files=assets/quaverq.wxs.tmpl",
        *(f"--include-package={pkg}" for pkg in force_packages),
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
        # 编译成功后清掉 .build 中间目录 (.o 文件等约 500MB-1GB), 只留 .dist 产物.
        "--remove-output",
    ]
    if sys.platform == "win32":
        # GUI 应用: 双击启动不弹黑色 cmd 窗口. attach (默认) 会跟父 console
        # 关联打印 logging, 但用户从资源管理器 / 开始菜单启动时凭空蹦个终端,
        # 极差体验. CI 调试用 onefile 想看日志就改回 force.
        cmd.append("--windows-console-mode=disable")
        # 显式声明带 VC++ runtime (vcruntime140 / msvcp140), 让没装 VC++ Redist
        # 的用户也能跑 portable. Nuitka 默认就这么干, 显式声明只是消掉提醒.
        cmd.append("--include-windows-runtime-dlls=yes")
    if icon_path is not None:
        cmd.append(f"--windows-icon-from-ico={icon_path}")
    # 入口走包**外** shim (``src/quaverq_entry.py`` -> ``quaverq.__main__.main``);
    # 不能直接 ``-m src/quaverq`` 因为会让 ``__main__`` 同时是 "主程序" 又是
    # "--include-package=quaverq 列表里的子模块", Nuitka 去重时刷一条 INFO 警告.
    # 用包外 shim 后 ``__main__`` 只通过正常 import 链进, 警告消失.
    cmd.append(str(root / "src" / "quaverq_entry.py"))
    return cmd


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


def build(mode: str = "standalone", *, output_dir: str = "dist") -> int:
    clean_stray_qt_objects()
    root = resources.project_root()
    # 渲染 ICO 嵌入 exe 资源段 (任务栏 / 资源管理器图标). Linux 上 Nuitka 仍接受
    # --windows-icon-from-ico 但忽略, 兼容性 OK.
    ico_path = root / output_dir / "quaverq.ico"
    try:
        render_ico_from_svg(resources.icon_file(), ico_path)
    except Exception as exc:
        print(f"[build] WARN: ICO 渲染失败, 跳过图标嵌入: {exc}", file=sys.stderr)
        ico_path = None
    cmd = nuitka_command(mode, output_dir=output_dir, icon_path=ico_path)
    print("[build]", " ".join(shlex.quote(c) for c in cmd))
    return subprocess.run(cmd, cwd=root).returncode


# UpgradeCode 固定 GUID: 跨版本保持不变, 让 MSI 的 MajorUpgrade 机制识别"同一个产品"
# 自动卸载旧版后装新版. 改这个 GUID = 新产品, 用户机器上会并存出现两套, 不要动!
_MSI_UPGRADE_CODE = "B8F3A1C2-5D9E-4F87-A3C1-D6E2F1B0A9F4"


def _find_wix_cli() -> str | None:
    """探测 WiX 5 CLI. 优先用 ``wix.exe`` (dotnet tool install --global wix), 否则返 None."""
    return shutil.which("wix")


def _ensure_wix_extension(wix: str, extension: str) -> bool:
    """确保 WiX 扩展在用户级 (-g) 缓存里. 第一次跑会联网拉, 之后命中本地缓存.

    WiX 5 的 UI / Bal / Util 等扩展不再随 CLI 安装, 需要 ``wix extension add -g`` 显式加.
    幂等: 已加过会输出 "already added" / 类似消息, 我们容忍 returncode != 0 但带这关键词.
    """
    result = subprocess.run(
        [wix, "extension", "add", "-g", extension],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0:
        return True
    if "already added" in output.lower() or "已添加" in output:
        return True
    print(f"[msi] WiX extension '{extension}' 添加失败:\n{output}", file=sys.stderr)
    return False


def _render_wxs(
    template: Path,
    output: Path,
    *,
    version: str,
    upgrade_code: str,
    icon_path: Path,
    dist_dir: Path,
) -> None:
    """``string.Template`` 把 ``.wxs.tmpl`` 里的 ``$VAR`` 占位替换成实际值, 写到 ``output``."""
    from string import Template

    text = template.read_text(encoding="utf-8")
    rendered = Template(text).substitute(
        VERSION=version,
        UPGRADE_CODE=upgrade_code,
        ICON_PATH=str(icon_path),
        DIST_DIR=str(dist_dir),
    )
    output.write_text(rendered, encoding="utf-8")


def build_msi(output_dir: str = "dist", *, rebuild: bool = True) -> int:
    """Nuitka standalone -> SVG/ICO + WiX 5 -> ``QuaverQ-{version}.msi``.

    依赖: WiX 5 CLI (``dotnet tool install --global wix``), .NET 6+ runtime.
    不装 WiX 时给清晰错误 + 安装命令, 不静默失败.

    ``rebuild=False`` (CLI ``--no-rebuild``): 复用已存在的 ``dist/quaverq_entry.dist/``,
    只跑 WiX 那段. 调 .wxs 模板 / 改 UI extension 这类 packaging 改动迭代时用,
    避免每次重跑 5 分钟 Nuitka 链接 + 250MB 复制. Python 代码改了就别用这个.
    """
    if sys.platform != "win32":
        print("[msi] 仅 Windows 支持 MSI 打包", file=sys.stderr)
        return 1
    wix = _find_wix_cli()
    if wix is None:
        print(
            "[msi] 未找到 WiX 5 CLI. 安装方式:\n"
            "    dotnet tool install --global wix\n"
            "  (需要 .NET 6+ runtime; 安装后重开 shell 让 PATH 生效)",
            file=sys.stderr,
        )
        return 1

    root = resources.project_root()
    version = project_version()
    dist_dir = root / output_dir / _NUITKA_DIST_DIRNAME

    # 1) Nuitka standalone (build() 内部已经渲染 ICO + 嵌入 exe).
    # rebuild=False 时跳过 (用于调 WiX 模板迭代, 不动 Python 代码)
    if rebuild or not (dist_dir / "QuaverQ.exe").exists():
        rc = build("standalone", output_dir=output_dir)
        if rc != 0:
            return rc
    else:
        print(f"[msi] 复用已有 Nuitka 产物: {dist_dir} (--no-rebuild)")
    if not dist_dir.is_dir():
        print(f"[msi] 期望的产物目录不存在: {dist_dir}", file=sys.stderr)
        return 1

    # 2) ICO 复用 build() 已渲染的 (build() 走了 render_ico_from_svg)
    ico_path = root / output_dir / "quaverq.ico"
    if not ico_path.is_file():
        print(f"[msi] ICO 不存在 (build() 应当已经渲染): {ico_path}", file=sys.stderr)
        return 1

    # 3) 渲染 WiX template
    template = root / "assets" / "quaverq.wxs.tmpl"
    wxs_out = root / output_dir / "quaverq.wxs"
    _render_wxs(
        template,
        wxs_out,
        version=version,
        upgrade_code=_MSI_UPGRADE_CODE,
        icon_path=ico_path,
        dist_dir=dist_dir,
    )

    # 4) 确保 UI extension 已在 ``wix extension`` 缓存; WiX 5 默认不带, 用户首次构建拉一次
    if not _ensure_wix_extension(wix, "WixToolset.UI.wixext"):
        return 1

    # 5) wix build (含 UI extension 让安装界面带选目录)
    msi_path = root / output_dir / f"QuaverQ-{version}.msi"
    cmd = [
        wix,
        "build",
        "-arch",
        "x64",
        "-ext",
        "WixToolset.UI.wixext",
        str(wxs_out),
        "-o",
        str(msi_path),
    ]
    print("[msi]", " ".join(shlex.quote(c) for c in cmd))
    rc = subprocess.run(cmd, cwd=root).returncode
    if rc == 0:
        print(f"[msi] OK -> {msi_path}")
    return rc


def build_portable_zip(output_dir: str = "dist", *, rebuild: bool = True) -> int:
    """Nuitka standalone 产物 ``dist/quaverq_entry.dist/`` -> ``dist/QuaverQ-{version}-portable.zip``.

    用户解压后双击 ``QuaverQ.exe`` 即跑, 不需要安装 / admin 权限. 适合 U 盘携带 /
    禁止 IT 装软件 / 临时试用场景.

    zip 内部顶层目录命名为 ``QuaverQ-{version}/``, 解压不会污染当前目录 (避免
    "解压到这里" 把上百个 dll 喷一地).

    ``rebuild=False`` (CLI ``--no-rebuild``): 复用已存在的 Nuitka 产物, 只跑 zip
    那段; CI 里 ``--msi`` 已经把 Nuitka 跑过一遍, 紧接着 ``--portable --no-rebuild``
    复用即可, 省 5 分钟链接 + 250MB 复制.
    """
    import zipfile

    root = resources.project_root()
    version = project_version()
    dist_dir = root / output_dir / _NUITKA_DIST_DIRNAME
    exe_name = "QuaverQ.exe" if sys.platform == "win32" else "QuaverQ"

    if rebuild or not (dist_dir / exe_name).exists():
        rc = build("standalone", output_dir=output_dir)
        if rc != 0:
            return rc
    else:
        print(f"[portable] 复用已有 Nuitka 产物: {dist_dir} (--no-rebuild)")
    if not dist_dir.is_dir():
        print(f"[portable] 期望的产物目录不存在: {dist_dir}", file=sys.stderr)
        return 1

    zip_path = root / output_dir / f"QuaverQ-{version}-portable.zip"
    top_dir = f"QuaverQ-{version}"  # zip 内顶层目录名
    print(f"[portable] 打包 {dist_dir} -> {zip_path}")
    # ZIP_DEFLATED + compresslevel=6: 压缩比 vs 速度的常见权衡; bundle 几百 MB,
    # level=9 多 5% 压缩比但慢 3 倍, 不值得.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in dist_dir.rglob("*"):
            if path.is_file():
                arcname = f"{top_dir}/{path.relative_to(dist_dir).as_posix()}"
                zf.write(path, arcname)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[portable] OK -> {zip_path} ({size_mb:.1f} MB)")
    return 0


def build_appimage(output_dir: str = "dist") -> int:
    """standalone 编译 → 组装 AppDir → linuxdeploy 产出 AppImage。"""
    root = resources.project_root()
    rc = build("standalone")
    if rc != 0:
        return rc
    dist = root / output_dir / _NUITKA_DIST_DIRNAME
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
    parser.add_argument(
        "--msi", action="store_true", help="standalone + WiX 5 -> Windows MSI 安装包 (仅 Windows)"
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="standalone -> portable .zip (解压即跑, 不需要安装)",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="跟 --msi / --portable 一起用: 复用已存在的 Nuitka 产物, 只跑后续打包步骤 (省时间)",
    )
    parser.add_argument("--smoke", metavar="BINARY", help="对产物跑 smoke 启动自检")
    args = parser.parse_args()

    if args.smoke:
        ok = smoke_test(args.smoke)
        print("SMOKE", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    if args.appimage:
        sys.exit(build_appimage())
    if args.msi:
        sys.exit(build_msi(rebuild=not args.no_rebuild))
    if args.portable:
        sys.exit(build_portable_zip(rebuild=not args.no_rebuild))
    sys.exit(build("onefile" if args.onefile else "standalone"))


if __name__ == "__main__":
    main()
