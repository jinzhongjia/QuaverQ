# src/quaverq

QuaverQ 的 Python 包根目录。包含应用入口、配置/资源/诊断/打包等顶层模块，以及业务核心层、Qt 桥接层与 QML 三个子目录。

## 顶层模块

| 文件 | 作用 |
| --- | --- |
| `__init__.py` | 包元数据 (`__version__` / `__author__`)。 |
| `__main__.py` | **应用入口** (`uv run quaverq` / `python -m quaverq`)。装配 `QApplication` + `qasync` 事件循环，实例化所有 `bridge` 控制器，加载 `qml/Main.qml`，挂上系统托盘、MPRIS/SMTC 等平台能力，并在退出时按顺序清理。`StreamProxy` 只构造不立即启动，等在线播放或 Windows SMTC 本地封面真正需要回环 HTTP 时懒启动，避免未播放用户启动期多占一个 server 线程和 curl session。启动关键段（系统主题、SWR prime、QML load）会记录 `perf ... elapsed_ms=...` 耗时日志。 |
| `config.py` | 解析 `config.toml`，给出 `CONFIG_DIR` / `CACHE_DIR` 等路径常量（通过 `platformdirs` 跨平台：Linux 走 XDG / `~/.config`、`~/.cache`，Windows 走 `%APPDATA%` / `%LOCALAPPDATA%`，macOS 走 `~/Library/...`）。反风控持久标识：`device_guid()`（设备 GUID，落盘 `device_id`）与 `risk_ct(allowed)` / `reset_risk_ct(allowed)`（vkey 用的 ct 风控指纹，落盘 `risk_ct`、值失效自动重抽）。 |
| `diagnostics.py` | 启动自检：QtMultimedia/FFmpeg 后端、Linux D-Bus 会话总线等关键依赖是否就绪；critical 项会让应用拒绝启动。 |
| `perf.py` | 轻量性能日志 helper：`log_elapsed(logger, event, **fields)` 统一输出 `perf event=<name> status=<ok/error> elapsed_ms=<n> key=value`，供启动与刷新路径定位真实耗时。源码运行默认开启，Nuitka 打包产物默认关闭；可用 `QUAVERQ_PERF_LOG=1/0` 强制覆盖。 |
| `resources.py` | 定位 `assets/`（`.desktop` / 图标 / metainfo），同时兼容源码布局与 Nuitka bundle 布局；`APP_ID` 常量在这里。 |
| `runtime.py` | 运行时环境判断，例如 `is_packaged()` 用于区分源码运行与 PyInstaller / Nuitka 打包产物。 |
| `packaging.py` | Nuitka standalone 构建 + AppImage / deb / rpm / Arch Linux pacman 包 / portable / MSI 封装的纯函数命令组装 + 实际调用（`uv run python build.py --appimage` / `--deb` / `--rpm` / `--archlinux` / `--portable` / `--msi` / `python -m quaverq.packaging --smoke ...`）。Linux 原生包共用 `/opt/quaverq` 安装树、`/usr/bin/quaverq` 启动器与 freedesktop desktop/icon/metainfo 文件；portable 的 `--no-rebuild` 会复用已有 Nuitka dist，并按其中的 `QuaverQ.exe` / `QuaverQ` 推断 zip 或 tar.gz。 |

## 子目录

| 目录 | 角色 |
| --- | --- |
| [`core/`](core/README.md) | **业务核心层**——无 Qt 依赖的纯 Python。数据模型、QQ 音乐 API 封装、播放队列、LRC/QRC 歌词、MPRIS2 服务、磁盘缓存、会话快照。可在没有 GUI 的情况下被 pytest 直接覆盖。 |
| [`bridge/`](bridge/README.md) | **Python ↔ QML 桥接层**——`QObject` 控制器、`QAbstractListModel` 适配器、`QQuickImageProvider`，把 `core/` 的能力翻译成 QML 能直接绑定的 `Property` / `Signal` / `Slot`。 |
| [`platform/`](platform/README.md) | **平台抽象层 (PAL)**——`get_platform()` 按 `sys.platform` 派发，统一暴露单实例守卫、系统主题、媒体会话三项跨平台能力的工厂；不支持的能力返回 `None`（降级），让 `__main__.py` 不直接 import `dbus_next` / `winreg` / `pyobjc`。 |
| [`qml/`](qml/README.md) | **Qt Quick UI**——`Main.qml` 主窗口 + 三栏布局，加上 `Theme/`（设计 token singleton）、`components/`（可复用组件）、`views/`（页面）、`panels/`（抽屉式面板）、`dialogs/`（弹窗）。 |

## 启动流程速览

```
config.load() → diagnostics.run_diagnostics() → QApplication →
qasync.QEventLoop → 实例化 bridge.* 控制器 → setContextProperty 注入 QML →
service.prime_credential_sync() + home_cache/library 预热 (SWR 首帧) →
engine.load(Main.qml) → tray + MPRIS/SMTC → loop.run_forever() →
显式保存会话快照 → _shutdown(): close 下载 session / 停 MPRIS / 排空挂起任务
```

`StreamProxy` 不在这条启动链路里同步 `start()`；第一次在线挂源由 `PlayerController`
启动，Windows SMTC 第一次把缓存封面转成本机 `http://127.0.0.1` URI 时也会启动。
