# src/quaverq/platform

平台抽象层 (PAL)。集中收口"会因平台而异"的能力，让业务代码（`bridge/` / `core/` / `__main__.py`）不直接 `import dbus_next` / `winreg` / `pyobjc`，而是统一通过 `get_platform()` 取 adapter。

## 目录结构

| 文件 | 作用 |
| --- | --- |
| `__init__.py` | 入口：`get_platform()` 按 `sys.platform` 派发并 lru_cache，返回 `PlatformAdapter` 单例。 |
| `base.py` | `PlatformAdapter` / `SingleInstance` Protocol 定义（`typing.Protocol`，结构子类型，鸭子接受）。 |
| `linux.py` | `LinuxPlatform`：包装现有 `SingleInstanceGuard` / `SystemThemeWatcher` / `MprisController`，不动现有实现。 |
| `windows.py` | `WindowsPlatform`：Stage 1 stub，所有能力返回 `None`（降级），Stage 3 替换为 Mutex / 注册表 / SMTC 真实现。 |

## 能力矩阵

| 能力 | Linux | Windows | macOS |
| --- | --- | --- | --- |
| `single_instance()` | D-Bus well-known name (`SingleInstanceGuard`) | ❌ None (TODO Stage 3 命名 Mutex) | ❌ None (TODO Stage 4 文件锁) |
| `system_theme()` | freedesktop portal `color-scheme` (`SystemThemeWatcher`) | ❌ None (TODO Stage 3 注册表 + WM_SETTINGCHANGE) | ❌ None (TODO Stage 4 NSAppearance) |
| `media_session(player)` | MPRIS2 D-Bus (`MprisController`) | ❌ None (TODO Stage 3 SMTC via winrt) | ❌ None (TODO Stage 4 MPNowPlayingInfoCenter) |

返回 `None` 表示能力不可用，调用方必须容忍（应用功能降级，不能崩）。

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
- **持有引用**：返回的 QObject 必须有 Python 端引用（变量或 attribute），否则 Qt 会 GC 掉它，signal slot 断开。
- **生命周期**：返回的对象的 `start_async()` 由调用方挂到 qasync event loop；`stop_async()` / `release()` 由调用方在 `aboutToQuit` 钩子里清理。

## 依赖关系

- `linux.py` 依赖 `core.single_instance` / `bridge.system_theme` / `bridge.mpris_controller`（不改这些模块的对外 API，纯包装）。
- `windows.py` Stage 1 无依赖；Stage 3 后会 `import winreg` / `pywin32` / `winrt-runtime`，且都用 `sys_platform == "win32"` marker 隔离。
- `base.py` 只用标准库 (`typing.Protocol`)；不引 Qt / dbus_next，便于纯 Python 单元测试。

## 测试

`tests/test_platform.py`:
- 跨平台：`get_platform()` 返回非 None；`name` 为已知值；多次调用返回同一实例。
- Linux：契约测试，验证 `LinuxPlatform.*()` 返回正确的具体类型。
- Windows：契约测试，验证 stub 所有能力返回 `None`。
- macOS：契约测试（同 Windows）。
- Protocol 结构鸭子：自写 stub adapter 应当满足 `PlatformAdapter` Protocol。

按平台 `skipif` 跳过其他平台的测试，CI matrix 各平台跑自己那段。

## 未来 (Stage 2+)

- **Stage 2**：Protocol 加 `credentials() -> Credentials | None`，统一走 `keyring` 库。
- **Stage 3**：`windows.py` 用 `pywin32` / `winrt` 填充三项能力。
- **Stage 4**：新增 `macos.py`，用 `pyobjc` 填充。
- **Stage 1b**：`__main__.py` 从直接 import `SingleInstanceGuard` 等改成走 `pal.single_instance()`，所有 None 分支降级。需在 Linux 上手动回归再合并。
