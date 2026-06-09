# Project Memory

**除非明确要求使用英文交流，否则所有的交流和文档均使用中文**。

LLM 约定：

<AGNET-TODO> 表示需要 AGNET 进行补充的内容，AGNET 需要根据上下文进行合理的补充，确保内容完整且符合项目需求。

## 调研类或者计划类任务处理

保存到 `docs/` 目录下的 Markdown 文件中，命名格式为 `plan/search-<简短描述>.md`，内容包括：

- 任务描述
- 调研的结果或计划的具体步骤
- 预期的结果或目标

## 支持的平台

跨平台改造经 Stage 0 / 1 / 2 / 3 完成，但**对运行环境有最低假设**——非主流桌面环境不支持，也不会为它们写兜底代码。

- **Linux**：要求**标准 freedesktop 桌面环境**（GNOME / KDE / Plasma / 其他符合 freedesktop 规范的 DE）。具体依赖：
  - **D-Bus session bus**：MPRIS2 媒体键 / GNOME Now Playing 控件 / 单实例守卫（`org.quaverq.SingleInstance`）/ 歌词外发（`org.quaverq.Lyrics1`）。
  - **Secret Service**（`gnome-keyring` / `kwallet` / `keepassxc` 等任一）：凭据存储（`keyring` 库自动选）。
  - **xdg-desktop-portal**：系统亮/暗色主题跟随（`org.freedesktop.appearance/color-scheme`）。
  - **不支持的场景**：tty / headless / 无 D-Bus 的最小化 WM（i3、dwm 等需自行启 D-Bus session + Secret Service backend），keyring / MPRIS / 单实例守卫都会 log warning 后**降级到 no-op**，但**不会**回退到明文文件存储。
- **Windows**：Windows 10+ x64。自动使用平台原生：凭证管理器（凭据存储）/ SMTC（Now Playing 卡片 + 键盘媒体键）/ 注册表 `AppsUseLightTheme`（主题跟随）/ 文件锁 `LockFileEx`（单实例）/ **QQ 音乐风格桌面悬浮歌词**（`DesktopLyricsController`，Qt frameless + 透明 + 鼠标穿透）。详见 `src/quaverq/platform/_windows_*.py` 及 `src/quaverq/bridge/desktop_lyrics.py`。
- **macOS**：计划支持 macOS 12+（Stage 4），当前 `darwin` 走 `_NullPlatform` stub，所有平台能力返 None。

平台抽象层入口：`from quaverq.platform import get_platform`；调用方**必须容忍 None**（降级），不能 `assert pal.x() is not None`。详见 `src/quaverq/platform/README.md`。

## 缓存 / 配置目录约定

跨平台路径走 `from quaverq.config import CONFIG_DIR, CACHE_DIR`（由 `platformdirs` 解析）。**目录命名 + 层级必须遵守**以下规则，否则会在 Windows 上看到 `%LOCALAPPDATA%\QuaverQ\QuaverQ\` 这类重复嵌套，在 Linux 上分裂出大小写不同的两个目录：

### 命名规则

- **app 名称一律小写 `quaverq`**：`platformdirs(appname="quaverq")` + `QApplication.setApplicationName("quaverq")` 必须**完全一致**（含大小写）。Linux 是 case-sensitive，混用 `quaverq` / `QuaverQ` 会出现两个目录；Windows 虽然 case-insensitive 但首创者大小写会"污染"所有后续路径显示。用户可见的"QuaverQ"是 QML 端的 `Window.title` 属性，不走 `setApplicationName`。
- **不设 `QApplication.setOrganizationName`**：留空让 Qt 的 `QStandardPaths` 用单层 `<base>/<appname>` 路径布局；设了 orgname 就嵌套成 `<base>/<orgname>/<appname>` 与 `CACHE_DIR` 分裂。

### 目录结构

```
%APPDATA%\quaverq\               (Linux: ~/.config/quaverq, macOS: ~/Library/Application Support/quaverq)
├── settings.ini                 ← QSettings (主题模式 / 音质 / 歌词字体偏好)
├── state.json                   ← SessionState 会话快照 (队列 + 进度 + mode)
├── device_id                    ← 持久设备 GUID (反风控)
└── config.toml                  ← 按需写入的用户配置 (可能没生成)

%LOCALAPPDATA%\quaverq\          (Linux: ~/.cache/quaverq, macOS: ~/Library/Caches/quaverq)
├── covers/                      ← 封面图磁盘缓存 (CoverCache, ~200 张)
├── home.json                    ← 首页 SWR 缓存 (HomeCache)
└── cache/                       ← Qt 自动管理 (不要往里写自定义文件!)
    ├── qmlcache/                ← QML 字节码缓存 (.qmlc 文件)
    └── qtpipelinecache-...      ← 渲染管线缓存
```

### 写新缓存文件的规则

- **app 数据**放 `CACHE_DIR` 顶层（如 `covers/`、`home.json`），或语义清晰的子目录（如未来加 `lyrics/`）。
- **绝对不要**往 `CACHE_DIR / "cache"` 写——那是 Qt 的内部 cache 目录，混进自定义文件会被 Qt 当成它的 QML 字节码误删 / 误改。
- **凭据不落盘**（走 `keyring`，见上文）；调试脚本读凭据用 `QuaverService.load_cached_credential_sync()`，**不要**自己 `open(CONFIG_DIR / "credential.json")`。

### platformdirs 配置

`config.py` 的 `_dirs()` 必须：
- `appauthor=False`（不塞 `<author>\` 中间层）
- `roaming=True`（Windows config 走 Roaming，可跨机器漫游）
- `opinion=False`（**关掉 platformdirs 的 Windows `\Cache` 后缀**，否则 CACHE_DIR 就成了 `%LOCALAPPDATA%\quaverq\Cache\`，跟 Qt 的 `cache\` 子目录大小写撞车 + 视觉上别扭）

## 跨平台已踩过的雷 (don't repeat)

下面这些坑都是实测过 + 排查到根因的, 写下来防 LLM / 后人再踩。

### Windows 单实例守卫: 必须用 `LockFileEx`, 不要碰 mutex / msvcrt

- ❌ **`CreateMutexW` 命名 mutex**: 现代 Windows + Python 3.14 上, 不同 `python.exe` 进程的 named kernel object 走 isolated namespace, 第二个 ``CreateMutexW`` 同名也不会返 ``ERROR_ALREADY_EXISTS``。表面成功, 实际**两个进程都"占用成功"**, 互斥失效。
- ❌ **`msvcrt.locking`**: 基于 CRT `_locking()` 抽象层, 实测不真正调 OS-level byte-range lock, 跨进程也"都成功"。
- ✅ **Win32 `LockFileEx`**: 直接 ctypes 调, 真正 OS-level byte-range lock, 跨进程一致互斥 (`ERROR_LOCK_VIOLATION=33`)。进程退出时 OS 自动 close handle 释放锁。详见 `src/quaverq/platform/_windows_single_instance.py`。

附加规则:
- **绝对不 `os.unlink` 锁文件** —— 删了后下次 `CreateFileW(OPEN_ALWAYS)` 会创建**新 inode**, 多进程锁到不同的文件 → 互斥失效。锁文件就 1 byte, 留着不删。
- **不要把 release 接到 `app.aboutToQuit`** —— qasync 的 `loop.run_until_complete(...)` 内部用 `app.exit()` 退出当前 event loop level, 会**意外触发 aboutToQuit 信号** (app 实际并未退出)。把 `instance_guard.release()` 放在 `with loop:` 块**外** (真正退出后) 调用。

### Windows 凭据 (keyring)

- 凭据**只**走 `keyring` (Windows Credential Manager backend); 失败时静默 log warning, 不回退明文文件 —— 软件未发布无历史用户, 不写迁移逻辑 (见上面 [Stage 2 keyring 实现](src/quaverq/core/service.py) 的 `_save_credential_blob` / `_load_credential_blob`)。
- `tests/conftest.py` 的 autouse `fake_keyring` fixture 强制把 keyring backend 替成进程内 dict, **测试绝不能往真实 Credential Manager 写**。

### Windows 编码 (GBK 隐患)

- Python `open()` 默认用 `locale.getpreferredencoding()`, Windows 中文 locale 是 `cp936` (GBK)。**所有文本 IO 必须显式 `encoding="utf-8"`**, 否则保存含 Ø / 中文 nickname / Unicode cookie 的 JSON 会 `UnicodeEncodeError`。
- 已修过的实例: `core/state.py` 会话快照 + `core/service.py` 凭据 (现已迁 keyring)。grep `\bopen\(` 找新引入的漏网。

### Windows 系统主题事件: 用 Qt 高层 signal, 不要自己钩 `WM_SETTINGCHANGE`

实测过的失败路径 (don't repeat):

- ❌ **`QAbstractNativeEventFilter` + `installNativeEventFilter` 自己解 `WM_SETTINGCHANGE`**:
  PySide6 6.x 在 frameless QML 窗口 (我们这套 chrome) 下, Python 子类的
  ``nativeEventFilter`` 方法**完全不被 Qt 调到** —— 加日志确认是真的 0 次调用,
  不是 lParam 解码错. 应该跟 Qt 派发逻辑 + PySide6 绑定有关, 深挖成本太高.
- ❌ **`QTimer` 2s 轮询注册表**: 能用, 但有 1-2s 延迟 + 静止期空转 CPU + 违反
  ["禁止轮询" 规则](#开发禁止做的事).
- ✅ **订阅 `QGuiApplication.styleHints().colorSchemeChanged` 信号 + 回调里重读注册表**:
  Qt 自己内部已经钩了 ``WM_SETTINGCHANGE`` / ``WM_THEMECHANGED``, 系统主题变时它
  emit 此信号. 我们**只把它当 trigger** —— 回调里 ``_read_registry()`` 拿
  ``AppsUseLightTheme`` 准确值, 因为 Qt 自身的 ``colorScheme()`` 在某些环境上
  会把值错映射 (我们也只信任 SIGNAL 的 fire 时机, 不信任它的值). 实现见
  ``src/quaverq/platform/_windows_system_theme.py``.

教训: 遇到 "Windows 上需要事件驱动" 的需求, **先看 Qt 有没有包好的高层 signal**
(``QStyleHints`` / ``QGuiApplication`` / ``QSystemTrayIcon`` 等), 不要上来就 ctypes
解 WM 消息. Qt 内部多半已经替你接好了, 暴露成 Python-friendly signal.

### Qt `QApplication` 配置 (Windows 路径双层 / 大小写一致)

- `setApplicationName("quaverq")` (**小写, 与 platformdirs appname 完全一致**); Linux case-sensitive, 大小写不一致会分裂出两个目录。
- **故意不设 `setOrganizationName`** —— Qt 的 `QStandardPaths` 用 `<base>/<orgname>/<appname>` 布局, 设了 orgname 就嵌套出 `%LOCALAPPDATA%\quaverq\quaverq\`。留空后单层 `%LOCALAPPDATA%\quaverq\`, 跟我们 CACHE_DIR 合并。

### 桌面悬浮歌词: 仅 Windows, 不接 Linux / macOS

- **Linux 故意不实现** —— Wayland 多家 compositor (Mutter / KWin / Hyprland 等) 下
  `FramelessWindowHint + WA_TranslucentBackground + WindowTransparentForInput` 组合行为
  不一致 (焦点抢占 / z-order 错位 / 透明合成怪异); 不写跨 compositor 兜底.
- **Linux 用户走 MPRIS** 接现成桌面歌词工具 (kde-mpris-osd / gnome-mpris-applet 等),
  我们已经暴露 `org.quaverq.Lyrics1` D-Bus 接口, 不重复造轮子.
- **macOS 同理不接** —— Spaces / Mission Control 下浮窗交互复杂, Stage 4 也不打算做.
- 实现 (`src/quaverq/bridge/desktop_lyrics.py`) 本身是**纯 Qt, 跨平台 import 不崩**, 但
  `PAL.desktop_lyrics()` 只在 Windows 实例化 ( `platform/windows.py` 返实例, 其他平台返 None).
- **不要往 Linux / macOS 路径加 fallback** —— 见 [Wayland 已知坑文档](https://wayland.app/protocols/wlr-layer-shell-unstable-v1) 之类的工程权衡, 别又造一份 X11 / Wayland 分支.

### Qt SMTC interop (Win32 媒体会话)

- 不要用 `winrt-Windows.Media` Python 包做 SMTC 集成 —— `winrt._winrt.SystemMediaTransportControls._from(ptr)` 不接受裸 `IUnknown*` (来自 `ISystemMediaTransportControlsInterop::GetForWindow`)。
- **走纯 ctypes COM vtable 直调**, 见 `src/quaverq/platform/_windows_media_session.py`。关键 IID (实测得到, 部分文档抄错的):
  - `IRandomAccessStreamReferenceStatics = {857309DC-3FBF-4E7D-986F-EF3B1A07A964}`
  - `IUriRuntimeClassFactory = {44A9796F-723E-4FDF-A218-033E75B0C084}`
  - `IRandomAccessStreamReferenceStatics::CreateFromUri` 在 vtable[7] (不是 [6])
- **`RandomAccessStreamReference.CreateFromUri` 不支持 `file://`** (只支持 `ms-appx://` / `ms-appdata://` / `http(s)://`); 本地图片走 `StreamProxy.local_file_url()` 包成 `http://127.0.0.1:port/_local/<token>/<file>` 才能塞给 SMTC Thumbnail。
- **按钮事件 handler COM 对象**: `QueryInterface` 对 `INoMarshal` 必须返 `E_NOINTERFACE` (不是 `S_OK`), 否则 SMTC 视我们为 non-agile, 拒绝注册回调。

## 项目使用的库

### 运行时依赖 (`[project] dependencies`)

- **`PySide6>=6.6`** — Qt for Python 官方绑定, 提供 QML (Qt Quick) UI + `QtMultimedia` (`QMediaPlayer`) 播放后端 + `QSystemTrayIcon` / `QMenu` 托盘 + `QQuickStyle` / `QQuickImageProvider` 等. 整个 GUI / 播放器 / 自绘标题栏的基石.
- **`qasync>=0.27`** — `asyncio` ↔ Qt 事件循环桥. 启动期建 `qasync.QEventLoop`, QML 槽用 `@asyncSlot` 暴露异步函数. 不能换成 `asyncio.run`, 否则 Qt 信号 / GUI 线程会卡死 (见"asyncio 经 qasync 跑").
- **`qqmusic-api-python>=0.6.1,<0.7`** — 第三方 QQ 音乐 API 封装 (搜索 / 歌单 / 歌手 / 歌词 / 排行榜 / 二维码登录 / 播放 URL 等). 暴露 `Client` / `Credential` / `SearchType` / `TabType` / `QRCodeLoginEvents` 等. 版本锁 `<0.7` 因 0.7 系列有破坏性变更.
- **`curl-cffi>=0.15.0`** — 带浏览器 TLS 指纹的 HTTP 客户端 (`from curl_cffi import requests`), `qqmusic-api-python` 内部用它绕开 QQ 服务端的 JA3 指纹校验. 必须经 `ServiceController.start()` (含 `_start_lock`) 统一启停, 否则会泄漏后台线程导致退出卡死 (见"禁止重复 `start()`").
- **`dbus-next>=0.2.3`** (**仅 Linux**, `sys_platform == "linux"` marker) — 纯 Python 异步 D-Bus 实现, 用于 MPRIS2 (媒体键 / GNOME 媒体控件 / KDE 通知面板). 服务端通过 `__annotations__` 读取 D-Bus 签名字符串 (`"b"` / `"s"` / `"a{sv}"` 等), 不是 Python 类型注解, 不要"修正" (见 `src/quaverq/core/mpris.py` 与"禁止动 MPRIS D-Bus 注解形式"). Windows / macOS 走各自原生 API, 不依赖此包.
- **`platformdirs>=4.0`** — 跨平台 config / cache 目录解析. Linux 走 XDG (`~/.config/quaverq`, `~/.cache/quaverq`), Windows 走 `%APPDATA%\quaverq` + `%LOCALAPPDATA%\quaverq\Cache`, macOS 走 `~/Library/Application Support/quaverq` + `~/Library/Caches/quaverq`. **业务代码只用 `from quaverq.config import CONFIG_DIR, CACHE_DIR`**, 不直接 `os.path.expanduser("~/.config/...")`.
- **`keyring>=24.0`** — 跨平台凭据存储. 自动选平台后端: Linux Secret Service (gnome-keyring / kwallet) / Windows Credential Manager / macOS Keychain. 服务名 `QuaverQ`, 用户名 `credential`, 内容为 JSON blob. 不再有文件兜底——keyring 不可用 (headless / 无 D-Bus) 时凭据不持久化, 用户重启需重新扫码.
- **`tomli-w>=1.0`** — TOML 写入. 读侧用 Python 3.11+ 内置 `tomllib` (3.10 fallback 到 `tomli`), 写 `config.toml` 用 `tomli_w.dump` (路径走 `CONFIG_DIR`).

### 开发依赖 (`[dependency-groups] dev`)

- **`pytest>=8.0`** + **`pytest-asyncio>=0.24`** — 单元 / 契约测试框架, `asyncio_mode=auto` 让 `async def test_*` 自动跑. QQ API 调用统一用 `types.SimpleNamespace` mock 而非真请求; 文件 I/O 一律 `tmp_path` fixture, 不污染真实 `CONFIG_DIR` / `CACHE_DIR`. `tests/conftest.py` 的 autouse `fake_keyring` fixture 把 keyring 后端替成进程内 dict, 防测试污染用户真实凭据存储.
- **`ruff>=0.6.0`** — Python lint + formatter 一体工具 (替代 flake8 + isort + black). 配置见 `pyproject.toml [tool.ruff]`, 规则集 F/E/W/I/B/UP/C4/SIM/RET/PIE, `line-length=100`, `target-version=py310`. 对 `src/quaverq/core/mpris.py` / `core/lyric_dbus.py` 有 per-file ignore (`F821`/`F722`/`UP037`) 放过 D-Bus 签名字符串.
- **`nuitka>=4.1.2`** — Python → C 编译器, `standalone` 模式产出可独立分发的二进制 (见 `[tool.quaverq] nuitka_module_mode = "standalone"`). `build.py --appimage` 再套 linuxdeploy 打成 AppImage.
- **`patchelf>=0.17.2.4`** (**仅 Linux**, `sys_platform == "linux"` marker) — ELF `rpath` / interpreter 修补工具, Nuitka standalone 产物动态库依赖处理依赖它. Windows / macOS 装包时自动跳过.

### 构建与依赖管理

- **`uv`** — 包 + 虚拟环境管理 (替代 `pip` + `venv` + `pip-tools`). 锁定文件 `uv.lock`, `[tool.uv] package = true` 表示本仓库自身亦作可安装包. 所有命令统一 `uv run ...` 进虚拟环境.
- **`hatchling`** — PEP 517 构建后端, 配合 `[tool.hatch.build.targets.wheel] packages = ["src/quaverq"]` 指定 wheel 源.

### Qt 自带工具 (随 PySide6 提供)

- **`pyside6-qmllint`** — QML 静态检查器, lint 阶段强制 `--max-warnings=0`, 配置见 `.qmllint.ini`. ContextProperty 等已知合法用法用 inline `// qmllint disable <rule>` 精确抑制.
- **Qt 模块**: `QtCore` / `QtGui` / `QtWidgets` / `QtQml` / `QtQuick` / `QtQuickControls2` / `QtMultimedia` / `QtSvg` 通过 PySide6 暴露, 无需单独依赖. QML 侧 `import QtQuick`, `QtQuick.Controls.Basic`, `QtQuick.Layouts`, `QtMultimedia`.

## 开发可用命令

- `uv sync --dev` — 安装运行 + 开发依赖 (含 ruff / pytest / nuitka)
- `uv run pytest` — 跑所有单元测试 (testpaths=tests, asyncio_mode=auto)
- `uv run quaverq` — 启动应用 (等价 `python -m quaverq`)
- `uv run python scripts/lint.py` — 跑 lint (ruff check + ruff format --check + pyside6-qmllint)
- `uv run python scripts/lint.py --fix` — 自动修复可修的 ruff 问题并执行 `ruff format`
- `uv run python scripts/lint.py --py` / `--qml` — 只跑其中一项
- `uv run python build.py --appimage` — 打 AppImage (Nuitka standalone + linuxdeploy)

## 项目使用的 Lint

- **Python**: `ruff check` + `ruff format`, 配置在 `pyproject.toml [tool.ruff]`. 规则集 F/E/W/I/B/UP/C4/SIM/RET/PIE, line-length 100, target-version py310.
- **QML**: `pyside6-qmllint` (随 PySide6 自带), 默认配置在 `.qmllint.ini` (由 `pyside6-qmllint --write-defaults` 生成). `--max-warnings=0` 严格模式: ContextProperty 等已知合法用法用 inline `// qmllint disable <rule>` 注释精确抑制, 不放水整条规则.
- **CI**: 见 `.github/workflows/lint.yml`, push/PR 自动触发.

## commit 消息生成规范

**使用 `git diff` 生成符合 Conventional Commit 格式的提交消息，格式为 `type(scope): 简短描述` + 空行 + 多个带 `-` 的描述点。必须直接输出提交消息内容，不要包含任何 markdown 格式或额外解释。如果提供了提交历史，参考其风格保持一致。**

默认使用中文!
强制要求：commit message 不要带有任何和 LLM 相关的 Co-Authored-By

## 开发必须做的事

- **TDD 驱动**: 先写 `tests/test_*.py` 覆盖契约 → 跑红 → 写实现 → 跑绿. 任何代码改动 (含 bug 修复) 都要配套回归或契约测试. 测试框架 pytest + pytest-asyncio (`asyncio_mode=auto`), QQ API 用 `types.SimpleNamespace` mock. 提交前 `uv run pytest` 必须全绿.
- **分阶段实施**: 多文件 / 多模块改造拆成 ≤ 300 行 / 步, 单步完成后给"如何手动验证"清单 (具体命令 / 点哪个按钮 / 看哪个日志), 等用户"过了"再继续.
- **提交前过 lint**: `uv run python scripts/lint.py` 必须绿 (ruff + pyside6-qmllint). 能 `--fix` 修的先修, 改不掉的要么用 inline `# noqa: <code>` / `// qmllint disable <rule>` 精确抑制并写明原因, 要么在 `pyproject.toml` / `.qmllint.ini` 加 per-file-ignore 并注释解释.
- **持有 QObject 引用**: PySide6 controller / `QSystemTrayIcon` / `QMenu` 等通过 signal 订阅或 `setProperty` 注入的 QObject, 必须有 Python 端引用 (变量名以 `_` 开头表"持有但不读"即可), 否则 GC 立即回收 → signal slot 断开 / 菜单消失 / 测试随机失败.
- **ContextProperty 收拢到 root**: Python 通过 `engine.rootContext().setContextProperty()` 注入的 controller, 必须在 `Main.qml` 顶层声明 `readonly property var <name>: <PascalName>` 别名 (块内 `// qmllint disable unqualified`); 子组件统一走 `root.<name>` qualified 访问.
- **asyncio 经 qasync 跑**: 所有异步代码挂在 `qasync.QEventLoop` 上, QML 槽用 `@asyncSlot` 暴露; 网络 / 磁盘等耗时操作放 `asyncio.to_thread`. 启动同步预载 (`prime_*`) + 后台 `start()` 真正 connect 的 SWR 模式不可破坏.
- **更新 src/ 子目录的 README**: 任何 `src/quaverq/<dir>/` 下代码改动后, 检查并同步对应 README.md (目录介绍 / 结构 / 业务逻辑 / 对外接口 / 依赖关系).

## 开发禁止做的事

- **禁止跳过 / 弱化测试**: 不允许只改实现不补测试; 不允许加 `@pytest.mark.skip` / `xfail` 绕过坏测试; 不允许把失败断言改弱 (`assert x == []` → `assert x or not x`).
- **禁止跳过 / 放水 lint**: 不允许整条规则全局 disable; 不允许 `--no-verify` 跳过 pre-commit; 不允许 `git commit --amend` 改已发布的 commit. lint 失败先找根因, 不直接加 `# noqa` 压掉.
- **禁止动 MPRIS D-Bus 注解形式**: `src/quaverq/core/mpris.py` 中的 `-> "b"` / `-> "s"` / `-> "a{sv}"` 是 dbus-next 通过 `__annotations__` 读的 D-Bus 签名, 不是 Python 类型注解, 不要"修正"成 `bool` / `str` / `dict`, 也不要去引号.
- **禁止破坏 SWR 首帧契约**: 不要把 `__main__.py` 启动顺序里的 `prime_credential_sync()` / `prime_public_from_cache()` / `prime_private_from_cache(account_key)` 挪到 `engine.load()` 之后, 也不要改成异步; 否则首帧登录态 / 公共区 / 私有区会闪一下空再填.
- **禁止重复 `start()`**: `ServiceController.start()` 已用 `_start_lock` 串行化, 不要绕开锁; 也不要在多处并发显式 `await sc.start()` —— 用 `call_service()` / `_ensure_started()` 走统一入口, 否则会泄漏第二个 curl_cffi 客户端线程 → 退出卡死.
- **禁止 `tray._menu = menu` 这类引用绑定改成局部变量**: 见上"持有 QObject 引用"; 任何"看起来没用的赋值"删除前先确认它不是为防 GC.
- **禁止往 `dist/` / `.venv/` / 真实 `CONFIG_DIR` / `CACHE_DIR` 写测试夹具**: 测试只用 `tmp_path` fixture, 不污染用户真实配置 / 缓存目录 (Linux `~/.config/quaverq` + `~/.cache/quaverq`, Windows `%APPDATA%\quaverq` + `%LOCALAPPDATA%\quaverq\Cache`, macOS `~/Library/...`).
- **禁止往用户真实 keyring 写凭据**: `tests/conftest.py` 的 `fake_keyring` autouse fixture 已把后端替成进程内 dict; 测试不要主动 `keyring.set_keyring(real_backend)` 绕开它, 否则会污染 Windows Credential Manager / Secret Service / Keychain.
- **禁止假设非标准 Linux DE**: 不要为 headless Linux / 无 D-Bus 的最小化 WM 写"明文文件兜底"; keyring / MPRIS / 单实例 失败时降级到 no-op + log warning 即可. 软件未发布无历史用户, 无需写迁移逻辑.
- **禁止用轮询监听外部变化**: 任何"等 X 变化"的场景**先找事件 / 信号 / 通知**, 不要默认 `QTimer` / `while True: sleep()` 轮询.
  - 系统主题变化 -> Windows 走 `WM_SETTINGCHANGE` (`QAbstractNativeEventFilter` 钩); Linux 走 freedesktop portal `Settings.SettingChanged` D-Bus signal. **不轮询注册表 / `gsettings`**.
  - 注册表 / 文件变化 -> Windows 用 `RegNotifyChangeKeyValue` / `ReadDirectoryChangesW`; Linux 用 `inotify` / `QFileSystemWatcher`.
  - 进程内状态变化 -> `Signal` / `asyncio.Event` / 回调. 不要在 slot 里设标志位然后另起 timer 检查.
  - 唯一合法的轮询场景: **被监听方主动不暴露事件且无 OS 级通知**, 且经过文档明确取舍 (例如 SMTC 某些 winrt 属性). 这种地方注释里必须写"为什么不能事件化".
  - **Why**: 轮询 = 用户感知延迟 (1-5s 起) + 静止期空转 CPU + 测试要 sleep 拖时间. 事件驱动 = 0 延迟 + 0 空转 + 测试用 mock signal 触发, 又快又准.
  - **How to apply**: 加任何"周期性检查外部状态"的代码前, 先 grep 该状态在 OS / 库里是否暴露 signal / D-Bus / WM / fd; 找不到再考虑轮询, 并在 PR 里说明.

## Readme 维护

每个 src 下的目录都需要一个 README.md 文件，内容包括：

- 目录介绍
- 结构说明
- 业务逻辑
- 对外暴露的接口或者方法
- 接口定义说明
- 与其他目录之间依赖的关系

每次更新 src 下目录的代码时，检查 README.md 是否需要更新，保持文档与代码一致。

## 项目 UI 风格

### 设计参考

- **QQ 音乐 PC 端**: 整体克隆 QQ 音乐桌面版视觉语言. 参考规范 / Token 详见 `.claude/skills/qq-music-design` (作为外部 skill 维护, 不复制到本仓库). 任何配色 / 间距 / 圆角拿捏不准时先翻这个 skill, 不要凭感觉填裸 hex.

### 整体布局 (三段式)

- **顶栏 (`headerBar`, height = `Spacing.headerHeight = 56`)**: 自绘无边框标题栏. 从左到右: 返回键 → 品牌 logo (28x28 圆角矩形 + ♪) + 标题 (≥920px 才显示文字) → `SearchField` (`maxWidth=500`, `fillWidth`) → 最小化 / 最大化 / 关闭按钮. 拖动靠 `DragHandler` + `startSystemMove()`, 不接系统装饰. 见 `qml/Main.qml`.
- **主体 (RowLayout, `spacing=0`)**: 左 `Sidebar` (展开 240px / 紧凑 64px) + 右 `StackView contentStack` (路由切换走 push / clear, 不用 Loader); `StackView` 装 `views/HomeView`, `SearchView`, `LibraryView`, `DetailView`, `NowPlayingView`, `SettingsView`.
- **底栏 (`PlayerBar`, height = `Spacing.playerBarHeight = 104`)**: 全宽常驻播放器, 封面 + 元信息 + 控件 + 进度 + 音量 + 队列 / 正在播放入口. 底部圆角与窗口圆角联动 (`bottomCornerRadius`).
- **浮层**: `QueuePanel` (`Loader` 懒加载, 右抽屉 z=10, 宽 `min(360, root.width - 96)`), `LoginDialog` (二维码登录, z 默认), `Banner` (顶栏下警告条, z=970), `Snackbar` (居中提示, z=980), 窗口边框 / resize handle 分别 z=990 / z=1000.

### 窗口 chrome (自绘 + 无系统装饰)

- `flags: Qt.Window | Qt.FramelessWindowHint`, `color: "transparent"`: 整窗自绘. 默认尺寸 `1080x720` (`Spacing.windowWidth` / `windowHeight`), 最小 `760x640`.
- **圆角 + 阴影边距**: 普通态 `windowShadowMarginBase=2` + `radius=Spacing.radiusSm=4`; 最大化 / 全屏 (`Window.Maximized` / `Window.FullScreen`) 自动归零去圆角. 边距区供未来加投影, 当前作"透明气垫"避免顶角硬切.
- **边框层 (`windowBorderLayer`, z=990)**: `border.width=1`, 激活态 `Palette.windowBorder` / 失焦 `windowBorderInactive`, 仅描线不填色.
- **Resize 八向**: `resizeLayer` (z=1000) 8 个 `MouseArea` (四角 + 四边), `resizeHandleSize=8`, 调 `root.startSystemResize(Qt.LeftEdge | ...)`. 最大化时整层 `enabled: false`.

### 主题系统 (Theme singleton + Token 文件)

`qml/Theme/` 下 5 个 `pragma Singleton`, 子组件只绑 token 名, 不写裸 hex / 裸数字:

- **`Theme.qml`** — 模式开关. `mode` ∈ `{"system", "light", "dark"}`, `dark` 派生属性. 系统模式以 `SystemTheme` (`bridge/system_theme.py`, 走 xdg-desktop-portal `color-scheme`) 为准, Qt 自带 `styleHints.colorScheme` 在 GNOME/Wayland 上把 portal `prefer-dark` 错映射成 `Light`, 不可靠. `Main.qml` 用两个 `Binding` 把 `settingsController.themeMode` + `systemTheme.dark` 灌进来.
- **`Palette.qml`** — 全部颜色 token. 亮色: 品牌 `#31c27c` + 白底 `#ffffff` + 侧栏 `#f5f5f7` + 文本 `#333333` / `#767676`; 深色: `#1b1c1f` 底 + `#1f2024` 侧栏 + `#f0f1f3` / `#9a9ca2` 文本. 分层 token 含 `background` / `surface` / `surfaceElevated` / `surfaceVariant` / `surfaceContainerHigh`, 交互态 `stateHover` / `statePressed` / `stateSelected` / `stateDisabled` / `focusRing` / `scrim`, 品牌色 `primary` / `primaryHover` / `primaryActive` / `primaryContainer` / `primaryText`, 次级 `accent` (空间音频蓝), 状态 `error` / `warning`. 换肤只动这一个文件.
- **`Spacing.qml`** — 间距 + 圆角 + 命中区. 间距 4 阶幂级数: `s2=4`, `s3=8`, `s4=12`, `s5=16`, `s6=24`, `s7=32`, `s8=48`. 圆角五档: `radiusSm=4`, `radiusMd=8`, `radiusLg=12`, `radiusXl=16`, `radiusPill=20`. 命中区 `toolHitSize=44` (WCAG 触控目标).
- **`TypeScale.qml`** — 字号 + 字重. 字号: `display=32` / `h1=23` / `h2=19` / `body=16` / `bodySm=14` / `caption=13`. 字重: `regular=Font.Normal` / `medium=Font.Medium` / `bold=Font.DemiBold` (用 DemiBold 而非 Bold, 避免在 Linux 默认字体上糊).
- **`Motion.qml`** — 动效时长 + 缓动. 时长三档: `durFast=120` / `durMed=220` / `durSlow=320` ms. 缓动: `easeOut=OutCubic` / `easeIn=InCubic` / `easeStd=InOutCubic`.

### 组件 / 视图分层

- **`qml/components/`** — 通用复用组件: `Sidebar` / `PlayerBar` / `SearchField` / `SongRow` / `QueueRow` / `Card` / `AlbumArt` / `NavItem` / `IconButton` / `LikeButton` / `Snackbar` / `Banner`. 一律自定义 `background` / `contentItem`, 不依赖 Qt 默认 style 主题.
- **`qml/views/`** — 整页视图: `HomeView` / `SearchView` / `LibraryView` / `DetailView` / `NowPlayingView` / `SettingsView`. 通过 `StackView` 切换, 走 `StackView.Immediate` (无切换动画, 避免延迟感).
- **`qml/panels/`** — 抽屉式浮层: `QueuePanel` / `LyricPanel`.
- **`qml/dialogs/`** — 模态对话框: `LoginDialog`.
- **`qml/Theme/`** — 上述 5 个 singleton, 不放业务组件.

### 交互 / 无障碍

- **键盘**: 全局快捷键 — `Ctrl+F` 聚焦搜索, `Space` 播放 / 暂停, `Ctrl+←` / `Ctrl+→` 上 / 下首, `Esc` 退焦 / 关队列面板 / 返回上一级. 焦点搁 `shortcutFocusSink`, 不抢输入框焦点.
- **焦点环**: 所有可聚焦组件 `activeFocus` 时套 2px `Palette.focusRing` (= `primary`) 描边, 配合 `Keys.onReturnPressed` / `onSpacePressed` 触发. 不依赖鼠标 hover.
- **无障碍名**: 图标按钮 `Accessible.role: Button` + `Accessible.name: text`, 即 `IconButton.text` 不显示在视觉上但读屏会读. `Card` 的 name 拼 `title + 副标题`.
- **命中区**: 工具按钮统一 `toolHitSize=44`, 即便视觉图标只有 16~20px. 列表行 ≥ 40px.

### 控件库选择

- **使用 `QtQuick.Controls.Basic`**, 不用 `Material` / `Fusion` / `Universal`. 原因: Basic 是无主题"光板", 子样式全靠自绘 `background` / `contentItem` 接管, 不会被系统 style 串色, 跨发行版表现一致. 由 `QQuickStyle.setStyle("Basic")` 在 `__main__.py` 启动期强制锁死.
- **`pragma ComponentBehavior: Bound`** 写在 QML 文件首行, 配合 `Repeater` 的 `required property` 收紧绑定作用域, 让 qmllint 能查出错误的隐式 `id` 引用.

### 响应式 (单一断点 920px)

- 唯一断点 `width >= 920`: 顶栏品牌文字隐藏 / 显示; 侧栏 `compact: width < 920`, 240→64 px 折叠且只保留图标. 不做更细的栅格, 因 v1 仅桌面.

### 国际化

- 所有用户可见字符串走 `qsTr()`. 默认中文 (项目优先中文), 未来加 `.ts` / `.qm` 翻译时可直出. 视图路由 / 标题字典统一在 `Main.qml routeTitle()` 一处管理.

### 图标 / 字符

- v1 不引入字体图标库 (避免再带一份字体资产 / Nuitka 打包额外路径). 用 Unicode 符号代替: `←` 返回, `⌂` 发现, `⌕` 搜索, `♬` 资料库, `⚙` 设置, `▶` 播放, `♥` 我喜欢, `♪` 品牌 logo 占位. 字体级渲染保证清晰. 若未来切到矢量图标, 在 `IconButton.iconText` 替换或新增 `iconSource` 即可, 不影响命中区 / 焦点环.

### 1. 栈式视图必须自持状态

任何会被 `push` 到导航栈（`StackView`、navigation history 等）的 view，**必须**自己持有它依赖的可变 controller。多个相同类型的 view 实例**禁止**共享同一个 controller singleton。

#### Why

视图栈生命周期 ≠ 单例 controller 生命周期：
- View 是 push / pop 多实例的，同一时刻多个实例可能共存于栈中
- Singleton controller 的 state 只有一份，后 push 的会覆写前 push 的

后果：用户 pop 回上一层时，视图渲染的还是被覆写后的 state，表面上像"返回键没反应"。

#### How to apply

1. **新增可栈页面时**：给它配套写一个 `XxxController(QObject)` + `XxxControllerFactory(QObject)`。Factory 自己是单例（持有 `ServiceController` 引用），通过 `setContextProperty("XxxControllerFactory", factory)` 注入 QML。
2. **View 端持有**：View 的 `Component.onCompleted` 里调 `factory.create(root)` 拿到新 controller，存到自己的 property 上。**必须** `parent=root` 让 Qt parent-child 接管销毁——StackView pop 时 view 销毁，controller 自动 GC，所有 signal slot 自动断开。
3. **不要在 `Main.qml` 顶层做 `readonly property var xxxController: XxxController`**——这是单例模式的入口，跟"per-view 实例"原则冲突。
4. **不可栈的单例 controller 不受影响**：`AppController` / `HomeController` / `LibraryController` / `PlayerController` / `LyricController` / `MprisController` / `SongDetailController` / `ServiceController` / `SettingsController` / `CoverController` 都是全局唯一（同时只有一个实例显示），继续走 `setContextProperty` 单例注入即可。

#### 反例（修复前）

- `DetailController` 曾是 singleton，push 到 detail stack 时只有一份。复现：搜歌手 → 进艺人页 → 切"全部专辑" tab → 点专辑卡片 → 按返回 → 看到仍是专辑内容（因为底层 artist View 共享同一个 controller，状态被覆写）。**2026-06-08 修复**：改成 `DetailControllerFactory` 模式（PR feat/qqmusic-api-integration-2）。

#### 自检 checklist

新增 detail-like 视图前先问：
- [ ] 这个 view 是放到 `contentStack.push(...)` 进栈的吗？
- [ ] 它的 controller 有可变 state 吗（model / loading flag / current entity ID）？

如果两个都是 yes → **必须**走 factory 模式，不能 singleton。
