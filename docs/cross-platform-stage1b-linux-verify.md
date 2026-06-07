# 跨平台改造 Stage 1b —— Linux 回归验证清单

> 范围: 本阶段唯一动作 = **把 `__main__.py` 切换到走 PAL** (single_instance / system_theme /
> media_session / lyric_publisher 四处). Linux 行为应当 100% 不变, 因为 PAL 在 Linux 上
> 返回的就是原来的 `SingleInstanceGuard` / `SystemThemeWatcher` / `MprisController` /
> `LyricsDBusController` 实例.
> 风险: 启动顺序变了 (新增 `pal = get_platform()` 一行), None-guard 分支多了; 任何一项
> "本应在 Linux 上工作的功能"挂掉 = 改造引入了回归, **回滚不合并**.

> 前置: Stage 0 + 1a 已通过 [`cross-platform-stage0-1a-linux-verify.md`](cross-platform-stage0-1a-linux-verify.md)
> 全部验收 (依赖装得上 / XDG 路径不变 / PAL 单测全过 / 应用 6 项手测全过). 本阶段在那之上.

---

## 本次改动范围

| 路径 | 类型 | 改动内容 |
| --- | --- | --- |
| `src/quaverq/platform/base.py` | 改 | Protocol 加 `lyric_publisher(*, lyric_controller, player_controller)`; `media_session` 加 `raise_window` / `quit_app` kwargs |
| `src/quaverq/platform/linux.py` | 改 | `media_session` 透传 kwargs; 新增 `lyric_publisher` 工厂方法包装 `LyricsDBusController` |
| `src/quaverq/platform/windows.py` | 改 | 同上, stub 返回 None |
| `src/quaverq/platform/__init__.py` | 改 | `_NullPlatform` (macOS 兜底) 同步新签名 |
| `src/quaverq/__main__.py` | 改 | **唯一真正改启动顺序的文件**: 去掉 `from .core.single_instance import SingleInstanceGuard` / `from .bridge.system_theme import SystemThemeWatcher` / `from .bridge import LyricsDBusController, MprisController`; 改成 `from .platform import get_platform` + `pal = get_platform()` + 四处 `pal.x()` + None-guard 降级 |
| `tests/test_platform.py` | 改 | 加 `test_linux_adapter_provides_lyric_publisher`; Windows/macOS/stub case 同步新 API |

`core/` / `bridge/` / `qml/` **均未触碰** —— Linux 上 `pal.single_instance()` 仍然 new 出原来的 `SingleInstanceGuard`, `pal.media_session(p, raise_window=, quit_app=)` 仍然 new 出原来的 `MprisController`, 内部实现一行没动.

---

## 一、自动预检 (跑命令)

### 1. 拉代码 + 装依赖

```bash
git pull
git status                            # clean
uv sync --dev
```

**红线**: `dbus-next` / `patchelf` / `platformdirs` 应当装上 (Stage 0 marker 修正过).

### 2. 测试套件: Linux 段必须真跑且全过

```bash
uv run pytest
```

**期望**:
- **0 failed**
- **518 + 1 = 519 passed** (新增 `test_linux_adapter_provides_lyric_publisher`)
- **5 skipped** (仅 Windows / macOS case)

**红线**: 任一 Linux 测试 SKIPPED -> 平台检测错; 任一 FAILED -> PAL 包装错.

针对性确认 PAL 这几个测试都被执行:

```bash
uv run pytest -v tests/test_platform.py 2>&1 | grep -E 'PASSED|SKIPPED|FAILED'
```

应当看到这 5 个 **PASSED** (Windows 上是 SKIPPED 的):
- `test_linux_adapter_provides_single_instance`
- `test_linux_adapter_provides_system_theme`
- `test_linux_adapter_provides_media_session`
- `test_linux_adapter_provides_lyric_publisher` ← **新增**
- `test_get_platform_returns_non_none_adapter` (跨平台)

### 3. Lint 全绿

```bash
uv run python scripts/lint.py
```

**期望**: `[lint] OK 全部通过`, exit=0.

### 4. PAL 在 Linux 上仍返回真实对象 (回归检查)

```bash
uv run python -c "
from quaverq.platform import get_platform
pal = get_platform()
print('name:', pal.name)
print('single_instance:', type(pal.single_instance()).__name__)
print('system_theme:', type(pal.system_theme()).__name__)
"
```

**期望**:
```
name: linux
single_instance: SingleInstanceGuard
system_theme: SystemThemeWatcher
```

**红线**: 任一 `None` / `NoneType` -> LinuxPlatform 没正确包装现有实现, 回 `platform/linux.py` 检查惰性 import.

### 5. __main__.py 仍能 import 且 main 可调

```bash
uv run python -c "from quaverq.__main__ import main; print('main:', main)"
```

**期望**: 打印 `main: <function main at 0x...>`, 不 raise.

**红线**: ImportError -> 重构丢了 import 链; 看具体报错回去补.

---

## 二、应用启动日志 (关键)

```bash
uv run quaverq 2>&1 | tee /tmp/quaverq-stage1b.log
```

启动到主界面后, 看终端 / log 文件**前 5 秒**内必须出现这些行 (不一定连续):

| 关键日志 | 说明 | 缺了的话 |
| --- | --- | --- |
| `单实例守卫: 占用 org.quaverq.SingleInstance 成功` | `SingleInstanceGuard.acquire` 成功 | PAL single_instance 接错; 检查 `pal.single_instance()` 在 Linux 上不是 None |
| `系统主题跟随 portal color-scheme: dark=...` | `SystemThemeWatcher.start` 成功连 portal | portal 不可达 (老 desktop) 或 PAL system_theme 没接好 |
| `QuaverQ started with QML: .../Main.qml` | QML 加载成功 | QML rootObjects 为空; QML 端坏了 |
| (无) `QML load failed` / `MPRIS 退出清理失败` / `Lyrics D-Bus 退出清理失败` | 启动期不应该出现 | 看具体堆栈 |

**反向红线** (这些**不应该**出现, 出现就是 PAL 接错):
- `当前平台 (linux) 暂无单实例守卫, 允许多开`  ← 这是 Windows / macOS 才该走的降级路径, **Linux 出这行说明 PAL 接错了**.
- 任何 `pal.x()` 返回 None 导致跳过 `loop.create_task(...)` 的静默行为 (不会有日志, 但功能会缺).

---

## 三、6 项功能手测 (与 Stage 0+1a 验收清单一致, 但重点放在"启动顺序敏感"的项)

依次跑, 任一失败 = 回滚.

### 3.1 启动 + QML 加载

- `uv run quaverq` 主窗口正常出现, 三栏布局完整.
- 终端没有 critical / error 级别日志 (warning 可以接受, 比如 stylehints 之类).

### 3.2 登录 (SWR 首帧契约不能破)

- 已登录 (有 `~/.config/quaverq/credential.json`): **重启 app** -> 主界面**首帧立刻就是登录态**, "我喜欢" / 自建歌单同步可见.
- 未登录: 设置 -> 扫码登录 -> 私有区填上.

**重点红线**: 重启后首帧不是登录态 -> SWR 契约破了. 本次没动 `prime_credential_sync()` / `prime_public_from_cache()` / `prime_private_from_cache()`, 出问题极不应该, 但仍要确认.

### 3.3 播放 (核心功能, 不能坏)

- 搜歌 -> 双击播放 -> 出声, 进度走, 封面显示.
- `Ctrl+→` / `Ctrl+←` 切下一首 / 上一首.
- 暂停 / 继续.

### 3.4 媒体键 + Now Playing (MPRIS 集成 — Stage 1b 的核心风险点)

**最容易在本次改造中坏的项**, 因为 `MprisController` 的构造从 `__main__.py` 直接调改成走 `pal.media_session(player_controller, raise_window=..., quit_app=...)`.

- 键盘媒体键: `XF86AudioPlay` (Fn + 对应键) 能 play/pause; `XF86AudioNext` / `XF86AudioPrev` 能切.
- GNOME 顶栏下拉 -> Now Playing 控件:
  - 显示当前歌名 + 艺人 + 封面
  - 控件能 play/pause/next/prev
  - 点击控件 (Raise) **能把 QuaverQ 主窗口前置** ← 验证 `raise_window=lambda: _raise_main_window(engine)` 正确透传
- KDE / Wayland: 同上, Plasma 通知面板里的 Media Player.

**红线诊断**:

```bash
# MPRIS D-Bus 名字应当注册
busctl --user list | grep mpris.MediaPlayer2.quaverq

# 应该能查到 metadata
busctl --user introspect org.mpris.MediaPlayer2.quaverq /org/mpris/MediaPlayer2
```

如果 `busctl` 查不到 `org.mpris.MediaPlayer2.quaverq` -> `MprisController.start_async` 没跑或失败. 启动日志应有具体异常.

### 3.5 单实例 (启动顺序敏感)

- 已经开着 QuaverQ.
- 再跑一次 `uv run quaverq` (或从应用菜单再点一次).
- **期望**:
  - 第二个进程几秒内退出.
  - 终端打印 `QuaverQ 已在运行, 已请求现有窗口前置, 本实例退出`.
  - **第一个 app 的主窗口前置 / 浮上来** (MPRIS Raise 触发).

**红线**:
- 第二个 app 也起来了 -> `instance_guard.acquire()` 返回 True 应当返回 False; 看 `org.quaverq.SingleInstance` 是否真占住:
  ```bash
  busctl --user list | grep org.quaverq.SingleInstance
  ```
- 第二个进程退了但第一个窗口没前置 -> `instance_guard.notify_existing_raise()` 没成功 (MPRIS Raise 失败), 看日志.

### 3.6 主题跟随

- 系统设置切换深 / 浅色:
  - GNOME: 设置 -> 外观 -> 风格.
  - KDE: 系统设置 -> 外观 -> 全局主题.
- **期望**: QuaverQ 窗口配色立即跟随切换, **无需重启**.

**红线诊断**:
- 不跟随 -> `SystemThemeWatcher.start` 没起来. 启动日志看是否出现:
  - 正常: `系统主题跟随 portal color-scheme: dark=...`
  - 失败: `portal color-scheme 不可用，跟随系统回退默认浅色: <异常>`
- portal 检查:
  ```bash
  busctl --user introspect org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop org.freedesktop.portal.Settings
  ```

### 3.7 歌词外发 D-Bus (Stage 1b 新增 PAL 包装, 必须验)

`LyricsDBusController` 从 `__main__.py` 直接 new 改成走 `pal.lyric_publisher(lyric_controller=..., player_controller=...)`.

- 播放任意一首歌 (有歌词的).
- 另一个终端跑:

  ```bash
  busctl --user list | grep quaverq.Lyrics
  # 应当看到 org.quaverq.Lyrics1 (具体名字以代码为准)

  busctl --user introspect org.quaverq.Lyrics1 /org/quaverq/Lyrics1
  ```

- 或跑仓库自带的 example consumer (前提是它能用):

  ```bash
  uv run python examples/lyrics_consumer.py
  ```

  期望: 打印当前歌词 + active line / word 随播放实时更新.

**红线**: D-Bus name 注册不上 -> `LyricsDBusController.start_async()` 失败; 看启动日志.

### 3.8 退出清理 (新加的 None-guard 路径不能误杀)

- 关闭 app 主窗口 (托盘可用时点托盘"退出 QuaverQ").
- 进程应当**几秒内干净退出**, 不卡住.
- 终端日志**不应有** `Task was destroyed but it is pending!` / `MPRIS 退出清理失败` / `Lyrics D-Bus 退出清理失败`.

**红线**: 进程卡住 / 报 Task pending -> `_shutdown()` 里 None-guard 加错位置, 看 `mpris_controller.stop_async()` 是否被 await.

---

## 四、对照 git diff 做最终 review

```bash
git diff main -- src/quaverq/__main__.py
```

**审查点**:
1. 是不是只多了 4 处 `pal.x()` 调用 + 对应 None-guard, 没动其他启动顺序 (尤其 `prime_credential_sync` / `prime_public_from_cache` / `prime_private_from_cache` 这 3 个 SWR 首帧契约调用必须**保持原位置**)?
2. `app.aboutToQuit.connect(instance_guard.release)` 是不是仍然在 acquire 成功后才 connect (不是无条件 connect None)?
3. `_shutdown()` 里 mpris / lyrics 的 None-guard 是不是只跳过 stop_async, **没跳过 `cover_cache.close()` / `pending task cancel`** (这俩跟平台无关, 任何时候都得跑)?

---

## 五、验证完之后

- **全过** -> 可以开始 Stage 2 (凭据迁移到 keyring), 那时会动 `core/service.py` 的 credential 读写, **不动 __main__.py 启动顺序**.
- **任一手测红** -> 把:
  - 失败项编号 (3.1 - 3.8)
  - 终端日志 (尤其启动期前 10 行 + 失败前后 5 行)
  - `git diff main -- src/quaverq/__main__.py` 输出
  贴回来, 决定 forward fix 还是 `git revert` 这一个 commit (Stage 0 / 1a 保留).

---

## 一键自动预检 (1-5 串联)

```bash
git pull && uv sync --dev && \
  uv run pytest && \
  uv run python scripts/lint.py && \
  uv run python -c "from quaverq.platform import get_platform; p = get_platform(); assert p.name == 'linux'; assert p.single_instance().__class__.__name__ == 'SingleInstanceGuard'; assert p.system_theme().__class__.__name__ == 'SystemThemeWatcher'; print('PAL ok')" && \
  uv run python -c "from quaverq.__main__ import main; print('main:', main)" && \
  echo "=== 自动预检全过, 接下来手测 3.1 - 3.8 ==="
```

任何一步红 -> 停下, 不要进入手测.
