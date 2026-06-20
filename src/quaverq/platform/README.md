# src/quaverq/platform

平台抽象层 (PAL)。集中收口"会因平台而异"的能力，让业务代码（`bridge/` / `core/` / `__main__.py`）不直接 `import dbus_next` / `winreg` / `pyobjc`，而是统一通过 `get_platform()` 取 adapter。

## 目录结构

| 文件 | 作用 |
| --- | --- |
| `__init__.py` | 入口：`get_platform()` 按 `sys.platform` 派发并 lru_cache，返回 `PlatformAdapter` 单例。 |
| `base.py` | `PlatformAdapter` / `SingleInstance` Protocol 定义（`typing.Protocol`，结构子类型，鸭子接受）。 |
| `linux.py` | `LinuxPlatform`：包装现有 `SingleInstanceGuard` / `SystemThemeWatcher` / `MprisController`，不动现有实现。 |
| `windows.py` | `WindowsPlatform`：Windows 原生能力门面，返回 `LockFileEx` 单实例、Qt 高层系统主题 signal、SMTC、任务栏、阻止睡眠与桌面歌词等实现。 |

## 能力矩阵

| 能力 | Linux | Windows | macOS |
| --- | --- | --- | --- |
| `single_instance()` | D-Bus well-known name (`SingleInstanceGuard`) | ✅ `LockFileEx` byte-range lock (`WindowsSingleInstance`) | ❌ None (TODO Stage 4 文件锁) |
| `system_theme()` | freedesktop portal `color-scheme` (`SystemThemeWatcher`) | ✅ `QGuiApplication.styleHints().colorSchemeChanged` 触发后重读注册表 `AppsUseLightTheme` (`WindowsSystemThemeWatcher`) | ❌ None (TODO Stage 4 NSAppearance) |
| `media_session(player)` | MPRIS2 D-Bus (`MprisController`) | ✅ SMTC via ctypes COM (`WindowsMediaSession`)，本地封面 URI 通过 `StreamProxy` 按需懒启动暴露 | ❌ None (TODO Stage 4 MPNowPlayingInfoCenter) |
| `lyric_publisher(...)` | `org.quaverq.Lyrics1` D-Bus (`LyricsDBusController`) | ❌ None (无对等机制 / Stage 3+ 不打算做) | ❌ None |
| `desktop_lyrics(...)` | ❌ None (Wayland 跨 compositor 不一致, 走 MPRIS 接现成工具) | ✅ Qt frameless + transparent + input-passthrough (`DesktopLyricsController`) | ❌ None |
| `power_saver(player)` | ❌ None (PulseAudio / DE 已自动 inhibit) | ✅ `SetThreadExecutionState` 阻止待机 (`WindowsPowerSaver`) | ❌ None (Stage 4 IOPMAssertion) |

返回 `None` 表示该平台没有对应能力，调用方必须容忍（应用功能降级，不能崩）。Linux 是例外：D-Bus session bus 属于最低运行要求，启动自检缺失时会直接退出，不进入 PAL 初始化阶段。

`lyric_publisher(..., settings_controller=...)` 在 Linux 把设置层的歌词翻译可见性传给 `LyricsDBusController`；Windows / macOS 仍无歌词外发能力。


## 对外接口

```python
from quaverq.platform import get_platform

pal = get_platform()                       # 单例, 多次调用同一对象
guard = pal.single_instance()              # SingleInstance | None
theme = pal.system_theme()                 # QObject | None  (dark: bool Property)
mpris = pal.media_session(player_ctrl)     # QObject | None  (start_async/stop_async)
```

调用约定：

- **必须容忍 None**：每次调用都要 `if x is not None: ...`，不允许 `assert pal.x() is not None`。
- **Linux D-Bus 必需**：Linux 平台的单实例、MPRIS、歌词外发都依赖 D-Bus；`diagnostics.run_diagnostics(include_dbus=True)` 会在缺失时返回 critical，入口拒绝启动。
- **持有引用**：返回的 QObject 必须有 Python 端引用（变量或 attribute），否则 Qt 会 GC 掉它，signal slot 断开。
- **生命周期**：返回的对象的 `start_async()` 由调用方挂到 qasync event loop；`stop_async()` / `release()` 由调用方在 `aboutToQuit` 钩子里清理。

## 依赖关系

- `linux.py` 依赖 `core.single_instance` / `bridge.system_theme` / `bridge.mpris_controller`（不改这些模块的对外 API，纯包装）。
- `windows.py` 按需导入 Windows 专用实现：`ctypes` Win32/COM、注册表读取、Qt Widgets/Multimedia 等；模块级入口保持轻量，非 Windows 平台不会导入这些实现文件。
- `base.py` 只用标准库 (`typing.Protocol`)；不引 Qt / dbus_next，便于纯 Python 单元测试。

## 测试

`tests/test_platform.py`:
- 跨平台：`get_platform()` 返回非 None；`name` 为已知值；多次调用返回同一实例。
- Linux：契约测试，验证 `LinuxPlatform.*()` 返回正确的具体类型。
- Windows：契约测试，验证单实例、系统主题、SMTC、阻止睡眠、任务栏、桌面歌词等能力返回正确具体类型。
- macOS：契约测试，验证当前未实现能力返回 `None`。
- Protocol 结构鸭子：自写 stub adapter 应当满足 `PlatformAdapter` Protocol。

按平台 `skipif` 跳过其他平台的测试，CI matrix 各平台跑自己那段。

## 未来

- macOS 仍为 Stage 4 目标：新增 `macos.py`，用 `pyobjc` 填充单实例、系统主题、媒体会话、阻止睡眠等能力。
- Linux 暂不实现内置桌面悬浮歌词，继续走 MPRIS/Lyrics D-Bus 给外部桌面组件消费。
