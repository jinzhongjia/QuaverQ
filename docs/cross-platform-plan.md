# QuaverQ 跨平台支持规划 (Windows / macOS)

> 状态: 草案 (2026-06-07)
> 范围: 把当前 Linux-only v1 扩展为支持 Windows 10+ 与 macOS 12+ 的桌面客户端
> 原则: 平台抽象层 (PAL) 集中收口, Linux 路径保持不变, Win/Mac 走"功能降级 + 平台原生 API"

---

## 1. 现状盘点 (阻塞点)

| 模块 | 文件 | Linux 依赖 | 跨平台严重程度 |
|------|------|-----------|---------------|
| MPRIS 媒体键 / Now Playing | `src/quaverq/core/mpris.py` (424 行) | `dbus-next`, `org.mpris.MediaPlayer2` | **Blocking** |
| 单实例守护 | `src/quaverq/core/single_instance.py` (121 行) | D-Bus well-known name `org.quaverq.SingleInstance` | **Blocking** |
| 系统主题跟随 | `src/quaverq/bridge/system_theme.py` (119 行) | freedesktop portal `color-scheme` | **Blocking** |
| 主依赖 `dbus-next` | `pyproject.toml:29` | 无条件依赖 | **Blocking** (Win/Mac 装不上易出问题) |
| 配置 / 缓存路径 | `src/quaverq/config.py:20-35` | 硬编码 `~/.config`, `~/.cache` 回退 | Medium |
| 凭据存储 | `src/quaverq/core/service.py:1675-1690` | 明文 JSON (`credential.json`) | Medium (跨平台都不安全, 顺带改) |
| 系统托盘 / 桌面集成 | `src/quaverq/__main__.py:91-120`, `assets/io.github.*.{desktop,metainfo.xml}` | `.desktop` 文件, AppStream metainfo | Medium |
| 打包流水线 | `build.py`, `src/quaverq/packaging.py`, `.github/workflows/release.yml` | Nuitka + linuxdeploy + AppImage, CI 只跑 `ubuntu-latest` | **Blocking** (打不出包) |
| 音频后端 | `PySide6.QtMultimedia` | FFmpeg 插件; Qt 自带跨平台抽象 | Low (验证即可) |
| QML / Qt 资源 | `src/quaverq/qml/**`, `resources.py` | 字体 / 路径基本干净 | Low |

> CLAUDE.md 中有"v1 仅 Linux, 禁止跨平台假设"硬规则。本次跨平台为**显式专项分支**, 主线不要先动 PAL 抽象, 否则会和 v1 文档 / 测试夹具打架。先开 `feat/cross-platform` 长期分支, 分阶段合并。

---

## 2. 平台抽象层 (PAL) 设计

新增 `src/quaverq/platform/` 目录, 统一收口"会因平台而异"的能力:

```
src/quaverq/platform/
├── __init__.py            # 入口: get_platform() 返回当前平台实现
├── base.py                # Protocol 接口定义
├── linux.py               # 现有实现迁移过来 (mpris + dbus single instance + portal theme)
├── windows.py             # 新增
├── macos.py               # 新增
└── README.md              # 目录说明 (按项目规范)
```

### 抽象出的能力 (PlatformAdapter Protocol)

1. `media_session()` — 媒体键 / Now Playing
   - Linux: 现有 MPRIS
   - Windows: `Windows.Media.SystemMediaTransportControls` (经 `winrt` Python 绑定)
   - macOS: `MPNowPlayingInfoCenter` + `MPRemoteCommandCenter` (经 `pyobjc`)
   - 降级: 不支持时返回 no-op, 应用功能不受影响

2. `single_instance(app_id)` — 单实例
   - Linux: 现有 D-Bus
   - Windows: 命名 Mutex (`win32event.CreateMutex`) + 命名管道唤起前台
   - macOS: 文件锁 (`fcntl.flock` on `~/Library/Application Support/quaverq/.lock`) + LaunchServices 唤起
   - 降级: 锁拿不到直接退出(已是目前行为)

3. `system_theme()` — 跟随系统深浅色
   - Linux: 现有 portal
   - Windows: 读注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme`, 监听 `WM_SETTINGCHANGE`
   - macOS: `NSApp.effectiveAppearance` + KVO, 或简单的 `defaults read -g AppleInterfaceStyle`
   - 降级: 跟随 Qt palette, 不做主动监听

4. `paths()` — 配置 / 缓存目录
   - 改用 `platformdirs` 库 (跨平台标准)
   - Linux: 保持 XDG (`~/.config/quaverq`, `~/.cache/quaverq`)
   - Windows: `%APPDATA%\quaverq\`, `%LOCALAPPDATA%\quaverq\Cache\`
   - macOS: `~/Library/Application Support/quaverq/`, `~/Library/Caches/quaverq/`
   - 迁移: 检测旧路径存在时一次性搬迁 + log warning

5. `credentials()` — Cookie / token 安全存储
   - 抽象成 `save(key, blob)` / `load(key)`, 底层选择:
     - Linux: Secret Service (`secretstorage`) > 回退明文 JSON (现状)
     - Windows: Credential Manager (`pywin32` `win32cred`)
     - macOS: Keychain (`keyring` + `keyring.backends.macOS.Keyring`)
   - 统一用 `keyring` 库 + 平台默认 backend, 减少自己写 FFI

6. `notifications()` (可选) — 桌面通知
   - 现状: 项目没用; 占位接口预留

### 入口改造

`src/quaverq/__main__.py` 把硬调 `MprisController` / `SingleInstanceGuard` / `SystemThemeWatcher` 改成:

```python
from quaverq.platform import get_platform
pal = get_platform()
guard = pal.single_instance("io.github.jinzhongjia.quaverq")
media = pal.media_session(player_controller)   # 可能返回 None
theme = pal.system_theme()                     # 可能返回 None
```

调用点都要容忍 `None` (降级)。

---

## 3. 打包 / 分发

### Windows

- 工具: Nuitka `--standalone --windows-disable-console` + Inno Setup 或 MSIX
- 产出: `QuaverQ-Setup-x64.exe` (Inno) 或 `quaverq.msix`
- 图标: `assets/quaverq.ico` (从现有 SVG 用 `pillow` 转)
- 自启动 / 关联: 不做 (v1 范围外)

### macOS

- 工具: Nuitka `--standalone --macos-create-app-bundle --macos-signed-app-name` + `create-dmg`
- 产出: `QuaverQ.app` 包进 `QuaverQ-arm64.dmg` / `QuaverQ-x64.dmg`
- 签名 / 公证: 先做 ad-hoc 签名跑通, 正式发布再申请 Apple Developer ID
- Info.plist: `LSUIElement=NO`, `NSAppleMusicUsageDescription` 等先不需要

### CI (`.github/workflows/release.yml`)

新增 matrix:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-13, macos-14]   # 13=x64, 14=arm64
```

每个 job 调对应的 `build.py --{appimage|exe|dmg}` 子命令。`packaging.py` 拆出 `build_exe()` / `build_dmg()`, 与 `build_appimage()` 平级。

### `pyproject.toml`

```toml
dependencies = [
    ...,
    "platformdirs>=4.0",
    "keyring>=24.0",
    'dbus-next>=0.2.3 ; sys_platform == "linux"',
    'pywin32>=306    ; sys_platform == "win32"',
    'winrt-runtime>=2.0 ; sys_platform == "win32"',
    'pyobjc-framework-Cocoa>=10.0 ; sys_platform == "darwin"',
    'pyobjc-framework-MediaPlayer>=10.0 ; sys_platform == "darwin"',
]
```

---

## 4. 测试策略

- **PAL 单测**: `tests/platform/test_*.py` 用 fake adapter, 验证降级路径 (`media_session() is None` 不崩)。
- **平台单测**: Linux 现有测试不动; Windows/macOS 测试用 `pytest.mark.skipif(sys.platform != "win32")` 等门控。
- **CI**: 三平台都跑 `pytest` (skipif 自动跳无关测试) + lint。GUI 集成测试只在 Linux 跑 (省 CI 资源)。
- **手测清单**: 每阶段 PR 附"在 X 平台手动验证 Y" checklist (项目规范要求)。

---

## 5. 分阶段实施计划 (TDD + 阶段 ≤ 300 行)

### 阶段 0: 准备 (1 天)
- [ ] 开 `feat/cross-platform` 分支
- [ ] 引入 `platformdirs`, 把 `config.py` 路径函数改成 `platformdirs.user_config_dir("quaverq")` / `user_cache_dir`
- [ ] **保持 Linux 路径不变** (`platformdirs` 在 Linux 默认就是 XDG), 加迁移钩子
- [ ] 测试: `tests/test_config_paths.py` 三平台 mock `sys.platform` 验证返回路径
- 手测: Linux 启动应用, 确认 `~/.config/quaverq/credential.json` 仍能读到

### 阶段 1: PAL 骨架 (2 天)
- [ ] 新建 `src/quaverq/platform/{__init__.py,base.py,linux.py,README.md}`
- [ ] 定义 `PlatformAdapter` Protocol (`media_session`, `single_instance`, `system_theme`, `paths`, `credentials`)
- [ ] `linux.py` 把 `core/mpris.py` / `core/single_instance.py` / `bridge/system_theme.py` 包装进来 (不动现有实现, 只加 adapter 类)
- [ ] `__main__.py` 改成走 PAL, 但 Linux 行为 100% 不变
- [ ] 测试: PAL 接口契约测试 (fake adapter / Linux adapter)
- 手测: Linux 全功能回归 (登录 / 播放 / 媒体键 / 单实例 / 主题切换)

### 阶段 2: Credentials 迁移到 keyring (1 天)
- [ ] 引入 `keyring`, 把 `service.py` 凭据读写抽到 `pal.credentials()`
- [ ] Linux backend 优先 SecretStorage, 失败回退现有明文 JSON (避免 headless / CI 崩)
- [ ] 测试: mock `keyring` 验证 fallback
- 手测: Linux 重新登录 → 重启 → 凭据恢复

### 阶段 3: Windows 实现 (4-5 天)
- [ ] `platform/windows.py`:
  - 单实例: 命名 Mutex
  - 主题: 注册表读取 + 简易轮询 (1Hz, 后续上消息钩子)
  - 媒体: SMTC via `winrt`
  - 凭据: `keyring` 自动选 Windows Credential Manager backend
- [ ] `packaging.py::build_exe()`: Nuitka standalone + Inno Setup 脚本
- [ ] CI: 加 `windows-latest` job, 跑 lint + pytest + build_exe (产出 artifact)
- [ ] 测试: Windows skipif 单测 + smoke "应用能启动到主界面"
- 手测 (远程 Windows 机器 / VM): 安装包能装, 登录, 放歌, 媒体键, 关闭重开走单实例

### 阶段 4: macOS 实现 (4-5 天)
- [ ] `platform/macos.py`:
  - 单实例: 文件锁
  - 主题: NSAppearance KVO 或 `defaults` 轮询
  - 媒体: MPNowPlayingInfoCenter via `pyobjc`
  - 凭据: keyring 自动选 macOS Keychain backend
- [ ] `packaging.py::build_dmg()`: Nuitka `--macos-create-app-bundle` + `create-dmg`
- [ ] CI: 加 `macos-13` + `macos-14` job
- 手测 (实机 / GH Actions runner): DMG 能挂载拖入, Gatekeeper 警告可绕开 (右键打开), 全功能

### 阶段 5: 资源 / 元数据收尾 (1-2 天)
- [ ] 生成 `.ico` (Win) / `.icns` (macOS) 图标
- [ ] Win Inno Setup 脚本 / macOS Info.plist 模板加入 `packaging/`
- [ ] README / docs 更新, 加 Windows / macOS 安装说明
- [ ] 各 `src/quaverq/platform/README.md` 写齐
- [ ] 删 / 改 CLAUDE.md "禁止跨平台假设" 条目, 改成"通过 PAL 抽象, 不要在业务代码硬编码 sys.platform"

---

## 6. 风险 / 待定

- **MPRIS ↔ SMTC ↔ MPNowPlayingInfoCenter** 三个 API 的能力对齐: 例如 SMTC 不支持 "shuffle/repeat" 全部状态, 需做 best-effort 映射。
- **音频后端**: QtMultimedia 在 Windows 默认走 Media Foundation, macOS 走 AVFoundation; **FFmpeg 插件**在 PySide6 wheel 内是否带齐需要在三平台跑 `diagnostics.py` 实测。如果缺, 可能要切到 `python-mpv`。
- **macOS 签名 / 公证**: 没 Apple Developer ID 时只能 ad-hoc 签名, 用户需手动放行, v1 可接受。
- **Windows ARM64**: 暂不支持 (PySide6 wheel 还没有 win-arm64); 只发 x64。
- **macOS x64 vs arm64**: 用两条 CI line 各打一份, 不做 universal binary (Nuitka 不直接支持)。
- **凭据迁移**: 老用户从明文 JSON → keyring 要有一次性迁移逻辑, 失败保留旧文件 (不删)。
- **测试 CI 成本**: macOS runner 慢且贵, 考虑只在 release tag 才跑完整 build, PR 只跑 lint + unit。

---

## 7. 验收标准

发布 v1.1 (跨平台版本) 时必须满足:

- [ ] Linux: AppImage 体验 0 回归 (与 v1.0 完全一致, 单测 + 手测全过)
- [ ] Windows 10+ x64: 安装包能装, 登录 / 播放 / 媒体键 / 单实例 / 系统主题跟随 5 项全过
- [ ] macOS 12+ (x64 + arm64): DMG 能装, 同上 5 项全过 (媒体键允许不接 Touch Bar)
- [ ] CI 三平台 lint + unit 全绿
- [ ] 业务代码 (bridge/, core/ 除 platform/ 外) 不出现 `sys.platform` / `dbus` / `winreg` / `pyobjc` 直接调用
- [ ] `src/quaverq/platform/README.md` 描述每个 adapter 的能力矩阵

---

## 8. 不在本期范围

- 移动端 (Android/iOS)
- 跨平台自动更新器
- Windows MSIX Store 上架 / macOS App Store 上架
- ARM Windows 支持
- Snap / Flatpak 打包
