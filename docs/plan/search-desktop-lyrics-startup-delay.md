# 悬浮歌词启动晚于主窗口调研

## 任务描述

调研 Windows 桌面悬浮歌词为什么看起来比主窗口晚几秒出现，区分是窗口本身创建 / show 晚，还是歌词内容晚于窗口显示。

## 调研结果

### 启动时间线

当前 `src/quaverq/__main__.py` 的启动顺序是：

1. 创建 `PlayerController`，构造函数内同步恢复 `state.json` 会话队列，并 emit `currentSongChanged`。
2. 创建 `LyricController`，此时才连接 `PlayerController.currentSongChanged`。
3. 预热凭据 / 首页 / 资料库缓存。
4. `engine.load(Main.qml)`，主窗口创建并显示。
5. 创建 Windows SMTC 媒体会话 controller。
6. 创建 `DesktopLyricsController`，构造时读取设置；若 `desktopLyricsEnabled=True`，会调用 `DesktopLyricsWindow.show()`。
7. `loop.run_forever()` 后才启动 `_load_initial_state()` 后台任务：
   - `await service_controller.start()`
   - 并发 `home_controller.refresh_home_async()` 与 `lyric_controller.refresh_current_lyric_async()`

### 关键发现

- `DesktopLyricsController` 明确放在 `engine.load()` 之后创建，所以它不可能早于主窗口显示。
- `PlayerController` 恢复会话时已经 emit 过 `currentSongChanged`，但 `LyricController` 那时还没创建，错过了这次信号。
- 启动时 `LyricController` 没有本地歌词缓存可 prime，当前行通常为空；即使悬浮歌词窗口已经 `show()`，透明窗口没有文字，用户感知上等于“没出现”。
- 首次歌词内容依赖 `_load_initial_state()` 里的网络路径：先 `service_controller.start()` 做 connect / 凭据校验，再 `refresh_current_lyric_async()` 拉歌词。因此网络、登录校验、QQ API 响应都会直接表现为悬浮歌词晚几秒。
- Windows SMTC controller 在 desktop lyrics 之前创建，但它的 `__init__` 只挂 signal，不执行 `start_async()`；真正 SMTC 绑定在 `loop.run_forever()` 后后台执行。因此它不是主要同步阻塞点。

### 结论

主要原因不是 QWidget 创建慢，而是两层时序叠加：

1. 悬浮歌词 controller 在主窗口 QML 加载后才创建 / show。
2. 启动恢复的当前歌曲歌词没有同步首帧数据，必须等 `_load_initial_state()` 网络刷新后才有文字。

其中第 2 点更符合“晚几秒”的体感：窗口可能已经透明显示，但没有文本可绘制。

## 可验证方式

建议临时加以下日志确认时间线：

- `engine.load()` 前后打时间戳。
- `DesktopLyricsController.__init__` / `_on_settings_changed` / `DesktopLyricsWindow.showEvent` 打时间戳。
- `LyricController.refresh_current_lyric_async()` 开始 / 成功设置 lyric 打时间戳。
- `DesktopLyricsController._sync_line()` 打 `currentLineText` 是否为空。

预期会看到：悬浮歌词 show 很快发生在 `engine.load()` 后，但 `currentLineText` 在歌词网络刷新完成前为空。

## 修复建议

### 方案 A：让 LyricController 初始化时主动同步当前歌曲

在 `LyricController.__init__` 连接 `currentSongChanged` 之后，读取一次 `player_controller.currentSong`，若存在 mid，则调用 `_handle_current_song_changed()` 或等价的初始化方法，让 `_current_mid` 立即和会话恢复歌曲对齐。

优点：
- 修复“错过 PlayerController 恢复事件”的时序问题。
- 不改变 `__main__.py` 启动结构。

局限：
- 仍需要网络拉歌词；只是状态更早进入正确 mid。

### 方案 B：增加歌词缓存 / 启动 prime

新增 `LyricCache`（如 `CACHE_DIR / "lyrics"`），歌词加载成功后按 mid 缓存。启动时 `LyricController` 可同步 prime 当前 mid 的歌词，再后台刷新。

优点：
- 真正消除“悬浮歌词无文字等网络”的几秒空窗。
- 与首页 / 资料库 SWR 模式一致。

代价：
- 需要新增缓存格式、过期策略、测试和 README。

### 方案 C：提前创建 DesktopLyricsController

把 `pal.desktop_lyrics(...)` 移到 `engine.load()` 前。

优点：
- 窗口 show 可以更早。

局限：
- 如果歌词仍为空，用户看到的仍是透明窗口；对“有内容晚几秒”的主因帮助有限。
- 可能让主窗口出现前先出现悬浮窗，体验未必更好。

## 预期目标

推荐分两步：

1. 先做方案 A，消除恢复会话时 `LyricController` 错过当前歌曲信号的问题。（已实施：构造期同步 `PlayerController.currentSong`，但不抢跑网络。）
2. 如果还希望启动即显示上次歌词，再做方案 B，引入歌词缓存与同步 prime。
