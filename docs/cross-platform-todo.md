# 跨平台改造 —— 后续待办清单

> 状态: 2026-06-08, Stage 0 / 1a / 1b 已落地, Windows 端到端冒烟通过 (登录 / 播放 / 浏览 / 设置 OK,
> 4 项已知功能性降级). 本文件列出之后要做的事, 按优先级排序.

## 已完成 (Done) ✅

| 阶段 | 提交 | 内容 |
| --- | --- | --- |
| Stage 0 | `ed9ff8e` | `platformdirs` 跨平台路径; `dbus-next` / `patchelf` 加 `sys_platform == "linux"` marker; `.gitattributes` 强制 LF; `scripts/lint.py` 用 `shutil.which()` 修 Windows subprocess |
| Stage 1a | `9f547c8` | PAL 骨架 `src/quaverq/platform/{__init__,base,linux,windows}.py` + README; Protocol 定义; LinuxPlatform 包装现有实现; WindowsPlatform stub 返 None |
| Stage 1b | `5794116` | `__main__.py` 切换到 PAL: single_instance / system_theme / media_session / lyric_publisher 四处全走 `pal.x()` + None-guard 降级 |
| 修首帧闪白 | `f43aced` | `system_theme_watcher.start()` 改成 `engine.load()` 之前同步等完; portal 加超时保护 (意外收益, 与跨平台同期发现) |
| 修 Windows GBK | `edb6b39` | `state.py` / `service.py` 凭据 / 会话快照 IO 强制 `encoding="utf-8"`; 加回归测试 |
| 测试 / 文档 | `e8b82d9` `1bbda81` `7a7390b` `5151f1e` `0b5601c` | Linux 验证清单 2 份; 测试同步信号名 / mid 字段; Windows 跳过 D-Bus 专属测试 |

---

## 高优先级 (Should Do Soon)

### A. Stage 3a — Windows 单实例守卫 (Mutex)

**问题**: 现在 Windows 上"打开第二次会真起两个窗口", PAL stub 返回 None.

**方案**:
- 新增 `src/quaverq/platform/_windows_single_instance.py` (实现细节模块, 不放 `windows.py` 主门面避免胀大).
- 用 `win32event.CreateMutex` (经 `pywin32`) 占名 `Global\\QuaverQ-SingleInstance-<sha256(install_path)[:8]>` 或类似. 名字带 install path hash 避免不同安装目录互锁.
- `acquire()`: CreateMutex + GetLastError == ERROR_ALREADY_EXISTS -> False; 否则 True.
- `notify_existing_raise()`: 用命名管道 / `FindWindow` + `BringWindowToTop` / WM_SHOWWINDOW. 最稳是用 `FindWindow("QuaverQ")` 找到第一实例主窗后 `SetForegroundWindow`.
- `release()`: `CloseHandle(mutex)`.
- WindowsPlatform.single_instance() 返回这个实现.
- `pyproject.toml` 加 `'pywin32>=306 ; sys_platform == "win32"'`.

**风险**: SetForegroundWindow 在 Windows 10+ 默认会被前台锁机制拒, 可能需要 `AllowSetForegroundWindow` 协议交接. 真测一下.

**估**: 1-2 h. **影响**: 仅 Windows. Linux 行为不变 (LinuxPlatform 不走这里).

**测试**:
- `tests/test_platform.py` 加 Windows-only case: `pal.single_instance()` 应当返回非 None 的对象, 有 `acquire/notify_existing_raise/release` 三个方法.
- 集成测试在 CI 上不好跑 (要起两个进程), 手测即可.

---

### B. Stage 3b — Windows 系统主题跟随 (注册表)

**问题**: 系统切深 / 浅色时 Windows 上的 QuaverQ 不跟随.

**方案**:
- 新增 `src/quaverq/platform/_windows_system_theme.py` (`QObject` 子类, 暴露 `dark` Property + `darkChanged` Signal, 与 `SystemThemeWatcher` 接口一致).
- 读注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme` (DWORD, 0 = dark, 1 = light), 用 Python 内置 `winreg`.
- 监听变化: 起 `QTimer` 每 2s 轮询 (简单, 不依赖 Win32 消息钩子); 或更专业的 `RegNotifyChangeKeyValue` API. 先轮询版本.
- WindowsPlatform.system_theme() 返回这个实现.

**估**: 2-3 h. **影响**: 仅 Windows. 不需要新依赖 (winreg 是 Python 标准库).

**测试**:
- 单元: monkeypatch `winreg.OpenKey` / `QueryValueEx` 返回 0 / 1 对应值, 断言 `dark` Property.
- 手测: 设置 → 个性化 → 颜色 → 切深色, 看 app 是否跟随.

---

### C. Stage 3c — Windows SMTC 媒体会话

**问题**: Windows 上键盘媒体键 / Now Playing 卡片不工作.

**方案**:
- 新增 `src/quaverq/platform/_windows_media_session.py`. 用 `winrt` 暴露的 `Windows.Media.SystemMediaTransportControls`.
- 接 player_controller 的 signal (currentSongChanged / playbackStateChanged / positionMsChanged) -> 推到 SMTC.
- SMTC 的回调 (ButtonPressed) -> 调 raise_window / quit_app / player.togglePlayPause 等.
- 状态映射: SMTC 不支持 "shuffle/repeat" 全部状态, 做 best-effort.
- WindowsPlatform.media_session() 返回这个实现.
- `pyproject.toml` 加 `'winrt-runtime>=2.0 ; sys_platform == "win32"'` + 相关投影包.

**风险**:
- `winrt` 包名 2024 后改了 (`winsdk` → `winrt-runtime` 拆分多个 namespace 包); 装包时按 namespace 选, 不是一个 monorepo 包. 估装包路径就要花点时间.
- 封面图: SMTC 期望 `RandomAccessStreamReference`; 我们的封面是 disk 路径 -> 要包一层.

**估**: 半天 (4-6 h, 一半时间在 winrt 包 / API 摸索).

**测试**: SMTC 的真实集成测试只能手测. 单元层面 mock 一个 SMTC 接口验证签名.

---

### D. 编码 / 路径 / Locale 项目级审计

**触发**: Windows GBK bug 是漏的, 想必还有其他类似坑.

**清单**:
- [ ] `grep -rn "open(" src/ tests/ scripts/ build.py` 找漏写 `encoding=` 的 (已知 state.py / service.py 已修).
- [ ] `grep -rn "subprocess.run" src/ scripts/ build.py` 找硬编码 `"/bin/bash"` / `"sh"` / `"linux-only-cmd"` 的.
- [ ] `grep -rn "/tmp\b" src/ tests/` 找硬编码 POSIX 路径.
- [ ] `grep -rn "os.uname\|platform.system\|sys.platform" src/` 找业务代码里直接判系统的 (这些应该走 PAL).
- [ ] 检查所有 `Path.read_text` / `Path.write_text` 是否都带 `encoding="utf-8"`.

**估**: 1-2 h. **影响**: 各平台; 找到的具体问题各自 ≤ 半小时修.

**测试**: 找到的每个问题补一个回归测试 (含 Unicode / 含 GBK 不可编字符).

---

## 中优先级 (Plan Next)

### E. Stage 2 — 凭据迁移到 keyring

**问题**: 当前 `credential.json` 明文存盘; 跨平台都不安全.

**方案**:
- PAL 加 `credentials()` 工厂, 返回 `Credentials` 协议对象 (`save(key, blob)` / `load(key)` / `delete(key)`).
- 用 `keyring` 库 + 平台默认 backend:
  - Linux: SecretStorage (gnome-keyring / kwallet); 回退明文 (headless / CI).
  - Windows: Credential Manager (`pywin32 win32cred`).
  - macOS: Keychain (`keyring.backends.macOS.Keyring`).
- 老用户迁移: 启动期检测 `~/.config/quaverq/credential.json` 存在 -> 读出来塞 keyring -> 重命名为 `.migrated` (不删, 留作兜底).
- `service.py` 的 save_credential / load_cached_credential_sync 改走 PAL credentials.

**估**: 1 d. **影响**: 三平台.

**风险**:
- keyring 在 headless Linux / GitHub Actions runner 无 DBus 时会失败, 必须 fallback 明文 (with warning).
- 迁移逻辑错可能导致老用户重登一次; 测试时要 mock 两边都覆盖.

---

### F. Stage 5a — Windows 打包 (Nuitka + Inno Setup → .exe)

**目标**: 出 `QuaverQ-Setup-x64.exe`, 没装 Python 的机器装上也能跑.

**方案**:
- `src/quaverq/packaging.py` 拆出 `build_exe()`, 与现有 `build_appimage()` 平级.
- Nuitka 命令: `--standalone --windows-disable-console --enable-plugin=pyside6 --include-qt-plugins=multimedia,multimediawidgets,qmltooling` + 输出图标 `assets/quaverq.ico` (要先把 SVG 转 ICO).
- Inno Setup 脚本: `packaging/quaverq.iss`, 把 `dist/quaverq.dist/` 整个打进 `QuaverQ-Setup-x64.exe`.
- `build.py --exe` 子命令调上面这个流程.

**估**: 2-3 h (Nuitka 命令调通就 OK; Inno Setup 是声明式不复杂).

**风险**:
- `qqmusic-api-python` / `curl-cffi` 可能有 C 扩展 Nuitka 打不全, 要 `--include-package`.
- 启动慢: standalone bundle 几百兆, 首次解包要等.

**测试**: 装到一台没装 Python 的 VM 上跑一次.

---

### G. Windows CI job

**问题**: 现在 lint / pytest 只在 ubuntu-latest 跑, 下次提"Linux 修一下"PR 又会带 Windows 漏网 (像 `test_start_times_out_when_portal_unresponsive` 那个).

**方案**:
- `.github/workflows/lint.yml` 加 matrix `os: [ubuntu-latest, windows-latest]`.
- 跑 `uv sync --dev` + `uv run pytest` + `uv run python scripts/lint.py`.
- Windows job 上 dbus-next / patchelf 自动跳过 (marker 已就绪).
- 启动期可能要装 `pyside6-essentials` 的 system DLL, 看 CI runner 是否预装.

**估**: 1-2 h.

**红线**: 不能减 Linux job; 不要把 Linux skip 测试在 Windows 上误标 failed.

---

## 低优先级 / 长远 (Eventually)

### H. Stage 4 — macOS 实现

**全套**: 文件锁单实例 + NSAppearance KVO 主题 + MPNowPlayingInfoCenter 媒体 + Keychain 凭据 + DMG 打包.

**估**: 4-5 d (单平台一次性). **风险**: 需要 macOS 实机或 GH macos-13/macos-14 runner; 签名 / 公证另算.

**前置**: A/B/C 都完成, 验证 Windows 模式后再做 macOS, 边际成本最低.

---

### I. Stage 5b — macOS DMG

跟 H 一起做 (Nuitka `--macos-create-app-bundle` + create-dmg).

---

### J. Windows 歌词外发 (替代 D-Bus)

**问题**: Linux 上 `LyricsDBusController` 让外部消费者读歌词; Windows 上无对应机制.

**候选**:
- 本地 HTTP / WebSocket (绑 127.0.0.1, 跟 stream_proxy 同 pattern).
- 命名管道 (`\\.\pipe\QuaverQ-Lyrics1`).
- 写文件 + filewatcher.

**估**: 半天 (实现) + 文档.

**优先级低**: 极少数用户用到这个接口 (歌词桌面浮窗类工具). 没有现成消费者的 Windows 用户群, 可以等需求.

---

### K. D-Bus 测试的 Windows mock

**问题**: `tests/test_mpris.py` / `test_lyric_dbus.py` / `test_single_instance.py` 全套在 Windows 上 SKIPPED, CI 覆盖差.

**方案**:
- 用 `unittest.mock.MagicMock` / fake `dbus_next` 模块在 Windows 上让这些测试也能跑业务逻辑 (不真连 bus).
- 已有的 `_FakePlayerController` / `_FakeLyricController` 模式可以复用.

**估**: 半天.

**优先级低**: 这些路径只在 Linux 上真正执行, Linux CI 已经覆盖. Windows 上的覆盖收益小.

---

## 不在范围

- 移动端 (Android / iOS)
- 自动更新器
- Windows MSIX Store / macOS App Store 上架
- Windows ARM64 (PySide6 wheel 没准备好)

---

## 推荐执行顺序

1. **A** (Mutex 单实例) — 1-2 h, 用户最常踩的坑, 低风险.
2. **B** (注册表主题) — 2-3 h, 不引入新依赖.
3. **D** (编码 / 路径审计) — 1-2 h, 趁热把同类 bug 一锅端.
4. **G** (Windows CI) — 1-2 h, 防回归.
5. **F** (Windows .exe 打包) — 2-3 h, 此时 A+B+CI 已就绪, 出 alpha 安装包给外人试用.
6. **C** (SMTC 媒体键) — 半天, Windows 功能性最后一块拼图.
7. **E** (keyring 凭据) — 1 d, Windows 主功能稳了再动跨平台层.
8. **H+I** (macOS 全套) — 4-5 d, 看是否有 macOS 真用户需求.
9. **J / K** — 长尾, 按需.

按 1-6 走完, Windows 用户体验已经接近 Linux. 7-9 是质量 / 平台扩展.
