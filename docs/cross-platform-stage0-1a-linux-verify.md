# 跨平台改造 Stage 0 + 1a —— Linux 回归验证清单

> 范围: 已落地 Stage 0 (platformdirs 路径迁移 + 依赖 marker 隔离 + `.gitattributes`) 与
> Stage 1a (PAL 骨架 + LinuxPlatform/WindowsPlatform stub).
> 状态: **`src/quaverq/__main__.py` 一行未改**, Linux 行为预期 100% 不变.
> 验证目的: 证明改造对 Linux 用户无感知, 再做 Stage 1b (改造 __main__.py).

---

## 改动范围速览

仅以下文件被修改 / 新增:

| 路径 | 类型 | 影响面 |
| --- | --- | --- |
| `pyproject.toml` | 改 | `dbus-next` / `patchelf` 加 `sys_platform == "linux"` marker; 新增 `platformdirs>=4.0` |
| `src/quaverq/config.py` | 改 | `_config_dir()` / `_cache_dir()` 走 `platformdirs`; Linux 路径保持不变 |
| `src/quaverq/platform/` | 新增 | PAL 骨架 (`__init__.py` / `base.py` / `linux.py` / `windows.py` / `README.md`) |
| `scripts/lint.py` | 改 | `shutil.which()` 解析 `ruff` / `pyside6-qmllint`; 修 Windows 上的 subprocess 问题 |
| `.gitattributes` | 新增 | `* text=auto eol=lf` 防止 Windows checkout 时 CRLF 转换 |
| `src/quaverq/README.md` | 改 | 子目录列表加 `platform/`; 路径描述同步成 platformdirs |
| `tests/test_config_paths.py` | 新增 | 跨平台路径测试 (按平台 skipif) |
| `tests/test_lint_script.py` | 新增 | lint 脚本工具解析测试 |
| `tests/test_platform.py` | 新增 | PAL 契约测试 (按平台 skipif) |

`src/quaverq/__main__.py` / `core/` / `bridge/` / `qml/` **均未触碰**.

---

## 0. 准备 (拉代码 / 切分支)

```bash
git fetch && git checkout <分支>      # 切到含本次改造的分支
git pull
git status                            # 必须 clean
```

**期望**: `git status` 报 `working tree clean`. 如果有大量"modified" (没有真实 diff), 说明
`.gitattributes` 的 LF 强制没生效, 跑一次 `git add --renormalize .` 看 diff 内容; diff 为空
就 `git update-index --refresh > /dev/null` 刷新 stat cache.

---

## 1. 依赖装得上, Linux-only 包仍在

```bash
uv sync --dev
uv pip list | grep -E 'dbus-next|patchelf|platformdirs'
```

**期望** (三行全有):
```
dbus-next      0.2.3 (或更高)
patchelf       0.17.2.4 (或更高)
platformdirs   4.10.0 (或更高)
```

**红线**: 任一缺失 -> `markers="sys_platform=='linux'"` 写错了, 回 pyproject.toml 检查.

---

## 2. 路径仍是 XDG (绝不能变 `~/Library` / `%APPDATA%`)

```bash
uv run python -c "from quaverq.config import CONFIG_DIR, CACHE_DIR; print('CONFIG_DIR:', CONFIG_DIR); print('CACHE_DIR:', CACHE_DIR)"
```

**期望** (取决于 `$XDG_CONFIG_HOME` / `$XDG_CACHE_HOME` 是否设置):

| 环境变量 | CONFIG_DIR | CACHE_DIR |
| --- | --- | --- |
| 设了 | `$XDG_CONFIG_HOME/quaverq` | `$XDG_CACHE_HOME/quaverq` |
| 没设 | `~/.config/quaverq` | `~/.cache/quaverq` |

**验证旧数据可读**:

```bash
ls -la ~/.config/quaverq/ ~/.cache/quaverq/
```

**期望**: 旧的 `credential.json`、`state.json`、`device_id`、`covers/`、`home.json`、`settings.ini`
都还在原位.

**红线**: 路径多了一层 author 目录 / 大小写不对 / 跑到非 XDG 位置 -> `PlatformDirs(appauthor=False)`
配置错; 回 config.py 检查 `_dirs()`.

---

## 3. PAL 在 Linux 上返回真实对象 (不能是 None)

```bash
uv run python -c "
from quaverq.platform import get_platform
pal = get_platform()
print('name:', pal.name)
print('single_instance:', type(pal.single_instance()).__name__)
print('system_theme:', type(pal.system_theme()).__name__)
print('cached:', get_platform() is pal)
"
```

**期望**:
```
name: linux
single_instance: SingleInstanceGuard
system_theme: SystemThemeWatcher
cached: True
```

**红线**:
- `name` 不是 `linux` -> `sys.platform` 检测错或 `get_platform()` 改写错.
- 任一能力返回 `None` -> `LinuxPlatform` 没正确 import 现有实现.
- `cached: False` -> `lru_cache(1)` 丢了.

(`media_session` 需要真实 `PlayerController`, 这里不测, 测试套件里有覆盖.)

---

## 4. 完整测试套件 + Linux-only 测试这次会真跑

```bash
uv run pytest
```

**期望计数**:
- **0 failed**
- **511 + 7 = 518 passed** (Stage 0 之前 511, 加上 Stage 0/1a 新增 7 个)
- **3 skipped** —— 仅 Windows / macOS 平台的 case, 例如:
  - `test_windows_config_dir_in_appdata` (Windows only)
  - `test_macos_uses_library_application_support` (macOS only)
  - `test_windows_adapter_returns_none_for_all_capabilities` (Windows only)
  - `test_macos_adapter_returns_none_for_all_capabilities` (macOS only)

**验证 Linux 测试真的被执行** (而不是被错跳):

```bash
uv run pytest -v tests/test_config_paths.py tests/test_platform.py 2>&1 | grep -E 'PASSED|SKIPPED|FAILED'
```

应当看到这些 **PASSED** (在 Windows 上是 SKIPPED 的):
- `test_linux_uses_xdg_config_home`
- `test_linux_falls_back_to_dot_config`
- `test_linux_adapter_provides_single_instance`
- `test_linux_adapter_provides_system_theme`
- `test_linux_adapter_provides_media_session`

**红线**: 任一上面应当 PASSED 的项是 SKIPPED -> `sys.platform != "linux"` 误判, 或 import 失败.

---

## 5. Lint 全绿

```bash
uv run python scripts/lint.py
```

**期望**: `[lint] OK 全部通过`, 退出码 0.

```bash
git status
```

**期望**: clean. **不能**有任何"line-ending only" 的虚假 modified —— `.gitattributes` 应当让
Linux 拉下来的 working tree 与索引位元一致.

**红线**: 有 modified 但 `git diff` 为空 -> stat cache 老旧, 跑 `git update-index --refresh`;
如果有 diff 而且是 `\r\n -> \n` 之类, 说明 `.gitattributes` 没生效, 检查文件是否在 git 跟踪范围.

---

## 6. 应用实测 (手测, 6 项)

```bash
uv run quaverq
```

按顺序验. 任一项坏 = Stage 0 / 1a 真的破了什么, **回滚不合并**.

### 6.1 启动

- 主窗口出现, 三栏布局 (侧栏 + 内容 + 底栏播放器) 完整.
- 终端**没有 critical / error 级别**日志. (warning 可以接受, 比如 portal 不可用之类降级提示.)

### 6.2 登录

- 设置 → 扫码登录 (或已登录则跳过).
- 扫完后 "我喜欢" / 自建歌单 / 收藏歌单等私有区填上.
- **退出 app 再启动**: 凭据仍在 (`~/.config/quaverq/credential.json` 还能被读到), 首帧直接登录态.

**红线**: 凭据丢了 / 首帧不是登录态 -> SWR 首帧契约破了, 看 `prime_credential_sync()` 路径.

### 6.3 播放

- 搜索一首歌 → 双击播放.
- 出声 + 底栏进度条走 + 封面显示.
- 切下一首 (`Ctrl+→` 或底栏按钮) 能工作.

### 6.4 媒体键 / Now Playing

- 键盘媒体键 `XF86AudioPlay` / `XF86AudioNext` / `XF86AudioPrev` 能控制播放.
- (GNOME) 顶栏下拉看 Now Playing 控件: 标题 + 艺人 + 封面 + play/pause/next/prev 都对.
- (KDE) Plasma 通知面板里的 Media Player 同上.

**红线**: 媒体键无反应 / Now Playing 显示空 -> MPRIS 服务没起来 (本次未动 MPRIS 代码, 不应该坏);
看启动日志 `MprisController.start_async` 是否报错.

### 6.5 单实例

- 留着第一个 app 开着.
- **再跑一次 `uv run quaverq`** (或从应用菜单再点一次).
- 期望: 第二个进程秒退 (终端打印 "QuaverQ 已在运行, 已请求现有窗口前置, 本实例退出"),
  第一个 app 的主窗口前置 / 浮上来.

**红线**: 第二个窗口也起来了 -> D-Bus name 没占住, 看 `SingleInstanceGuard.acquire` 是否报错;
或 `org.quaverq.SingleInstance` name 改了名字.

### 6.6 主题跟随

- 系统设置切换深 / 浅色:
  - GNOME: 设置 → 外观 → 风格 (浅色 / 深色).
  - KDE: 系统设置 → 外观 → 全局主题.
- 期望: QuaverQ 窗口配色立即跟随切换, **无需重启 app**.

**红线**: 切换后窗口不变 -> portal `color-scheme` 监听没起来, 看
`SystemThemeWatcher.start` 是否报错 / portal 是否可达 (`busctl --user list | grep portal`).

---

## 7. 一键预检 (1 - 5 串联)

```bash
uv sync --dev && \
  echo "--- paths ---" && \
  uv run python -c "from quaverq.config import CONFIG_DIR, CACHE_DIR; print(CONFIG_DIR); print(CACHE_DIR)" && \
  echo "--- pal ---" && \
  uv run python -c "from quaverq.platform import get_platform; p = get_platform(); print(p.name, type(p.single_instance()).__name__, type(p.system_theme()).__name__)" && \
  echo "--- pytest ---" && \
  uv run pytest && \
  echo "--- lint ---" && \
  uv run python scripts/lint.py && \
  echo "=== 自动预检全过, 接下来手测 uv run quaverq 6 项 ==="
```

任何一步红 -> 停下记录具体输出, 回头排查.

---

## 验证完之后

- **全过** -> 可以开始做 Stage 1b (`__main__.py` 切到 PAL); 该改动需要 Linux 上**再跑一遍**
  6.1-6.6, 因为这是真改了启动顺序.
- **有失败** -> 把失败项 + 终端输出贴回来, 决定是 forward fix 还是回滚到 main.
