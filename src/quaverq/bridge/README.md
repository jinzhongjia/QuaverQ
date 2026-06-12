# src/quaverq/bridge

**Python ↔ QML 桥接层**。每个文件导出一个 `QObject` 子类（或 `QAbstractListModel` / `QQuickImageProvider`），通过 `engine.rootContext().setContextProperty(...)` 注入 QML 上下文，把 [`core/`](../core/README.md) 的能力以 `Property` / `Signal` / `Slot` 暴露给 QML 直接绑定。

控制器持有 `core` 的对象、订阅其回调，再把变化以 Qt 信号广播给 QML；反过来，QML 调用 `Slot` / `asyncSlot` 触发业务动作。任何会阻塞或走网络的逻辑都用 `qasync.asyncSlot` 在事件循环里跑，绝不阻塞 UI 线程。

## 控制器

| 文件 | 类 | 作用 |
| --- | --- | --- |
| `app_controller.py` | `AppController` | 应用级状态：登录态、二维码扫码登录流、凭据过期通知、深色模式切换、`appVersion` 常量属性（`application_version()` 读包元数据，读不到回退 "dev"）。账号画像（C4 侧栏身份区）：`nickname` / `avatarUrl` / `vipKind`（""/vip/hugevip/svip）/ `vipIconUrl` 四属性 + `profileChanged` 信号；`_set_authed` 变 true（login / cached prime）时 fire-and-forget 拉 `ServiceController.get_user_profile()`，变 false（登出/过期）同步清空并取消在途任务，迟到结果按当前 authed 丢弃（竞态保护）；拉取失败仅 log warning，身份区静默缺席不挡登录主流程。 |
| `service_controller.py` | `ServiceController` | QQ 音乐服务层（`core.service.QuaverService`）的 QML 包装：搜索、详情、首页 API。账号 key、凭据预热、网络有效性校验都在这里。`get_user_profile()` 走 `call_service` 统一凭据过期处理。 |
| `home_controller.py` | `HomeController` | 首页发现：每日推荐 / 今日歌单 / 新歌速递 / 排行榜。SWR：先用 `home_cache` 同步喂首帧，再后台 `refresh_*_async`。猜你喜欢 (`daily`) 走 `DAILY_TTL_SECONDS = 6h` 门：启动 / 登录态变化触发的自动刷新若缓存还新鲜则跳过网络；只有用户主动从 QML 调 `refreshHome()` / `refreshDailyThirty()` 才 `force=True` 穿透 TTL。注入 `PlayerController` 后联动：`dailyPreviewSong` 跟随播放中曲目；监听 `queueExhausted("daily")` 自动 `extend_daily_async()` 续取下一批并 `append_to_queue` 续播。 |
| `library_controller.py` | `LibraryController` | 资料库：我喜欢、我的歌单、收藏歌单、收藏专辑、关注艺人，登录后从 `home_cache` 私有区块同步首帧再刷新。 |
| `detail_controller.py` | `DetailController` + `DetailControllerFactory` | 歌单 / 专辑 / 艺人 / 排行榜详情页状态：标题、封面、曲目列表、loading / error。歌手详情页扩展：`similarSingersModel` / `singerSongsModel` / `singerAlbumsModel` 三个懒加载 model（`loadSimilarSingers` / `loadSingerSongs` / `loadSingerAlbums` slots），切歌手时自动 reset；用 `*Loaded` 标志保证幂等。**Controller 走 factory 模式**：每个 `DetailView` push 入栈时 `factory.create(view)` 拿到独立实例（Qt parent=view, GC 自动），避免栈式 view 共享 singleton 导致 pop 后 state 错乱（见 [AGENTS.md](../../../AGENTS.md) 契约 1）。 |
| `song_detail_controller.py` | `SongDetailController` | 歌曲详情 popup 状态：currentSong + similarSongsModel + relatedPlaylistsModel + **songInfo (dict, 2.4 加入)** + visible，由 SongRow 右键 / 菜单键触发 `open(song)` 异步并发拉相似/相关/歌曲附加信息。`load_generation` 防 race，关闭时保留旧 model 内容不闪空。 |
| `player_controller.py` | `PlayerController` | 播放器：包装 `QMediaPlayer` + `core.queue.PlayQueue`。控制四种播放模式、音质偏好、进度/音量/静音（`muted` 独立标志不动音量值，`toggleMute()` 切换；`setVolume`/`nudgeVolume(delta)` 任何主动调音量自动解除静音；静音不入会话快照）、退出快照保存（`session_state`）。服务端明确拒发的曲目（vkey `result=104003` 无版权等灰色歌曲）**自动跳下一首** + `noticeRaised` 轻提示（连跳上限 5 防全队列不可播时绕圈空转；传输层异常仍停住报错，断网不会把队列"跳"光）。待播队列的单点变动（追加/插队挪位/单行移除）走 `SongListModel` 的**粒度信号**（insert/move/remove rows），整表 reset 仅用于整队列替换——reset 会让待播面板的 ListView 重建并滚回顶部（真机验收反馈）。`play_songs_async(songs, idx, source=...)` 可给队列打来源标签 (e.g. `"daily"`)；队列自然耗尽时发 `queueExhausted(source)`，外部 `append_to_queue(songs)` 追加后自动续播。 |
| `lyric_controller.py` | `LyricController` | 同步歌词：跟随 `player_controller` 的进度更新 `activeIndex`，逐字 karaoke 高亮的进度也在这里算。 |
| `settings_controller.py` | `SettingsController` | `QSettings` 持久化的偏好：主题模式、减少动效（`reduceMotion`，注入 `Motion` singleton 后全应用过渡瞬时化）、音质、封面缓存上限 + 一键清理、歌词字体（family / size / weight / italic）+ `resetLyricFont()` 一键复位；**桌面悬浮歌词**（Windows-only：锁定 / 字体 / 字号 14-72 / 粗体 / 斜体 / 方向 横竖 / 未唱 + 已唱颜色）+ `pickDesktopLyricsColor(role)` 弹 `QColorDialog` + `resetDesktopLyrics()`；`availableLyricFonts` 用 `QFontDatabase.WritingSystem.SimplifiedChinese` 枚举系统中支持 CJK / UTF-8 的字体族。QSettings 文件落 `CONFIG_DIR/settings.ini`（与 `state.json` 同目录）。 |
| `desktop_lyrics.py` | `DesktopLyricsWindow` + `DesktopLyricsController` | **桌面悬浮歌词（仅 Windows）**：frameless + 透明 + WindowStaysOnTop + Tool + WindowTransparentForInput 的 QQ 音乐风格桌面 OSD。逐字高亮：`set_line(text, words)` + `set_progress_ms(ms)`，用 `ms >= startMs` 算 sung_count（与 `LyricPanel.qml` 一致）；无 `words` 数据时整句视为已唱用 highlight 色。`QPainterPath.addText` 描边 + 分段填色。Controller 接 `LyricController.currentLineChanged` / `positionMsChanged` + `SettingsController.settingsChanged`，每次全量 pull 状态。Linux / macOS 不接（PAL 返 None；见 [platform/README.md](../platform/README.md)）。 |
| `mpris_controller.py` | `MprisController` | 把 `PlayerController` 的状态/元数据推到 `core.mpris.MprisService`，从 D-Bus 收到的方法调用回灌到播放器。 |
| `lyric_dbus_controller.py` | `LyricsDBusController` | 把 `LyricController` 当前歌词 + `PlayerController.positionMs` 推到 `core.lyric_dbus.LyricsService`（`org.quaverq.Lyrics1`）。`active_word` 由 controller 内部用 `compute_active_word` + 当前行 words + 实时 position 算出；用 `_last_active` 去重避免 PositionMs tick 内字未变也重复 push。纯输出, 不接收 D-Bus 入站调用。 |
| `cover_provider.py` | `CoverController` + `CoverImageProvider` | `image://covers/<url>\|<size>\|<radius>` 的图片提供者；圆角裁剪、并发上限 6、磁盘命中秒级返回、未命中异步下载。 |

## 适配器与基础设施

| 文件 | 作用 |
| --- | --- |
| `models.py` | `QAbstractListModel` 适配器：`SongListModel` / `CardListModel` / `LyricLineListModel`，把 `core` 的 dataclass 列表喂给 QML `ListView` / `Repeater`。附带 `song_to_map` / `song_from_map` / `card_to_map` 的字典互转。 |
| `error_utils.py` | 桥接错误处理共享工具：识别网络类异常（aiohttp/httpx/requests/urllib3 + `Connection` / `Timeout` 等），让 controller 用统一日志级别和文案展示。 |
| `stream_proxy.py` | **本机回环流代理（反风控 U2）**：`MediaPlayer(FFmpeg) → 127.0.0.1 → curl_cffi (官方 JA3) → CDN`。token + host 白名单防 SSRF，未启动时降级为 http 直连。 |
| `system_theme.py` | 系统亮/暗主题探测：直接读 freedesktop portal `org.freedesktop.appearance/color-scheme`，绕开 PySide6 `styleHints.colorScheme` 在 GNOME/Wayland 上的错映射。 |
| `__init__.py` | 统一导出所有控制器 + 模型适配器，供 `__main__.py` 一次性 `from .bridge import ...`。 |

## 与 QML 的契约

- 所有控制器都以 **context property** 形式注入（`AppController` / `HomeController` / `PlayerController` ...），QML 端按驼峰名直接访问。
- 长耗时操作用 `@asyncSlot` 装饰，QML 调用立即返回；状态变化经 `Signal` 通知 QML 重绑定。
- 列表绑定一律走 `QAbstractListModel` 子类，role 名（`name` / `singers` / `coverUrl` ...）就是 QML `delegate` 里读到的属性名。
- 封面通过 `image://covers/...` URL 间接拉取，绝不让 QML 直接发网络。
