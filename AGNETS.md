# Project Memory

**除非明确要求使用英文交流，否则所有的交流和文档均使用中文**。

LLM 约定：

<AGNET-TODO> 表示需要 AGNET 进行补充的内容，AGNET 需要根据上下文进行合理的补充，确保内容完整且符合项目需求。

## 项目使用的库

### 运行时依赖 (`[project] dependencies`)

- **`PySide6>=6.6`** — Qt for Python 官方绑定, 提供 QML (Qt Quick) UI + `QtMultimedia` (`QMediaPlayer`) 播放后端 + `QSystemTrayIcon` / `QMenu` 托盘 + `QQuickStyle` / `QQuickImageProvider` 等. 整个 GUI / 播放器 / 自绘标题栏的基石.
- **`qasync>=0.27`** — `asyncio` ↔ Qt 事件循环桥. 启动期建 `qasync.QEventLoop`, QML 槽用 `@asyncSlot` 暴露异步函数. 不能换成 `asyncio.run`, 否则 Qt 信号 / GUI 线程会卡死 (见"asyncio 经 qasync 跑").
- **`qqmusic-api-python>=0.6.1,<0.7`** — 第三方 QQ 音乐 API 封装 (搜索 / 歌单 / 歌手 / 歌词 / 排行榜 / 二维码登录 / 播放 URL 等). 暴露 `Client` / `Credential` / `SearchType` / `TabType` / `QRCodeLoginEvents` 等. 版本锁 `<0.7` 因 0.7 系列有破坏性变更.
- **`curl-cffi>=0.15.0`** — 带浏览器 TLS 指纹的 HTTP 客户端 (`from curl_cffi import requests`), `qqmusic-api-python` 内部用它绕开 QQ 服务端的 JA3 指纹校验. 必须经 `ServiceController.start()` (含 `_start_lock`) 统一启停, 否则会泄漏后台线程导致退出卡死 (见"禁止重复 `start()`").
- **`dbus-next>=0.2.3`** — 纯 Python 异步 D-Bus 实现, 用于 MPRIS2 (媒体键 / GNOME 媒体控件 / KDE 通知面板). 服务端通过 `__annotations__` 读取 D-Bus 签名字符串 (`"b"` / `"s"` / `"a{sv}"` 等), 不是 Python 类型注解, 不要"修正" (见 `src/quaverq/core/mpris.py` 与"禁止动 MPRIS D-Bus 注解形式").
- **`tomli-w>=1.0`** — TOML 写入. 读侧用 Python 3.11+ 内置 `tomllib` (3.10 fallback 到 `tomli`), 写 `~/.config/quaverq/config.toml` 用 `tomli_w.dump`.

### 开发依赖 (`[dependency-groups] dev`)

- **`pytest>=8.0`** + **`pytest-asyncio>=0.24`** — 单元 / 契约测试框架, `asyncio_mode=auto` 让 `async def test_*` 自动跑. QQ API 调用统一用 `types.SimpleNamespace` mock 而非真请求; 文件 I/O 一律 `tmp_path` fixture, 不污染 `~/.config/quaverq/` 真实目录.
- **`ruff>=0.6.0`** — Python lint + formatter 一体工具 (替代 flake8 + isort + black). 配置见 `pyproject.toml [tool.ruff]`, 规则集 F/E/W/I/B/UP/C4/SIM/RET/PIE, `line-length=100`, `target-version=py310`. 对 `src/quaverq/core/mpris.py` 有 per-file ignore (`F821`/`F722`/`UP037`) 放过 D-Bus 签名字符串.
- **`nuitka>=4.1.2`** — Python → C 编译器, `standalone` 模式产出可独立分发的二进制 (见 `[tool.quaverq] nuitka_module_mode = "standalone"`). `build.py --appimage` 再套 linuxdeploy 打成 AppImage.
- **`patchelf>=0.17.2.4`** — ELF `rpath` / interpreter 修补工具, Nuitka standalone 产物动态库依赖处理依赖它.

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
- **禁止往 `dist/` / `.venv/` / `~/.config/quaverq/` / `~/.cache/quaverq/` 写测试夹具**: 测试只用 `tmp_path` fixture, 不污染用户真实配置 / 缓存目录.

## Readme 维护

每个 src 下的目录都需要一个 README.md 文件，内容包括：

- 目录介绍
- 结构说明
- 业务逻辑
- 对外暴露的接口或者方法
- 接口定义说明
- 与其他目录之间依赖的关系

每次更新 src 下目录的代码时，检查 README.md 是否需要更新，保持文档与代码一致。
