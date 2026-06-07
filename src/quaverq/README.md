# src/quaverq

QuaverQ 的 Python 包根目录。包含应用入口、配置/资源/诊断/打包等顶层模块，以及业务核心层、Qt 桥接层与 QML 三个子目录。

## 顶层模块

| 文件 | 作用 |
| --- | --- |
| `__init__.py` | 包元数据 (`__version__` / `__author__`)。 |
| `__main__.py` | **应用入口** (`uv run quaverq` / `python -m quaverq`)。装配 `QApplication` + `qasync` 事件循环，实例化所有 `bridge` 控制器，加载 `qml/Main.qml`，挂上系统托盘、MPRIS、stream 代理，并在退出时按顺序清理。 |
| `config.py` | 解析 `config.toml`，给出 `CONFIG_DIR` / `CACHE_DIR` 等路径常量（通过 `platformdirs` 跨平台：Linux 走 XDG / `~/.config`、`~/.cache`，Windows 走 `%APPDATA%` / `%LOCALAPPDATA%`，macOS 走 `~/Library/...`）；负责旧架构遗留缓存的清理。 |
| `diagnostics.py` | 启动自检：QtMultimedia/FFmpeg 后端、D-Bus 会话总线等关键依赖是否就绪，缺失给出 `info/warning/critical` 三级提示。 |
| `resources.py` | 定位 `assets/`（`.desktop` / 图标 / metainfo），同时兼容源码布局与 Nuitka bundle 布局；`APP_ID` 常量在这里。 |
| `packaging.py` | Nuitka standalone 构建 + AppImage 封装的纯函数命令组装 + 实际调用（`uv run python build.py --appimage` / `python -m quaverq.packaging --smoke ...`）。 |

## 子目录

| 目录 | 角色 |
| --- | --- |
| [`core/`](core/README.md) | **业务核心层**——无 Qt 依赖的纯 Python。数据模型、QQ 音乐 API 封装、播放队列、LRC/QRC 歌词、MPRIS2 服务、磁盘缓存、会话快照。可在没有 GUI 的情况下被 pytest 直接覆盖。 |
| [`bridge/`](bridge/README.md) | **Python ↔ QML 桥接层**——`QObject` 控制器、`QAbstractListModel` 适配器、`QQuickImageProvider`，把 `core/` 的能力翻译成 QML 能直接绑定的 `Property` / `Signal` / `Slot`。 |
| [`qml/`](qml/README.md) | **Qt Quick UI**——`Main.qml` 主窗口 + 三栏布局，加上 `Theme/`（设计 token singleton）、`components/`（可复用组件）、`views/`（页面）、`panels/`（抽屉式面板）、`dialogs/`（弹窗）。 |

## 启动流程速览

```
config.load() → diagnostics.run_diagnostics() → QApplication →
qasync.QEventLoop → 实例化 bridge.* 控制器 → setContextProperty 注入 QML →
service.prime_credential_sync() + home_cache/library 预热 (SWR 首帧) →
engine.load(Main.qml) → tray + MPRIS → loop.run_forever() →
关窗后 _shutdown(): close 下载 session / 停 MPRIS / 排空挂起任务
```
