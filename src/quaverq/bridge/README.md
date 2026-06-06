# src/quaverq/bridge

**Python ↔ QML 桥接层**。每个文件导出一个 `QObject` 子类（或 `QAbstractListModel` / `QQuickImageProvider`），通过 `engine.rootContext().setContextProperty(...)` 注入 QML 上下文，把 [`core/`](../core/README.md) 的能力以 `Property` / `Signal` / `Slot` 暴露给 QML 直接绑定。

控制器持有 `core` 的对象、订阅其回调，再把变化以 Qt 信号广播给 QML；反过来，QML 调用 `Slot` / `asyncSlot` 触发业务动作。任何会阻塞或走网络的逻辑都用 `qasync.asyncSlot` 在事件循环里跑，绝不阻塞 UI 线程。

## 控制器

| 文件 | 类 | 作用 |
| --- | --- | --- |
| `app_controller.py` | `AppController` | 应用级状态：登录态、二维码扫码登录流、凭据过期通知、深色模式切换。 |
| `service_controller.py` | `ServiceController` | QQ 音乐服务层（`core.service.QuaverService`）的 QML 包装：搜索、详情、首页 API。账号 key、凭据预热、网络有效性校验都在这里。 |
| `home_controller.py` | `HomeController` | 首页发现：每日推荐 / 今日歌单 / 新歌速递 / 排行榜。SWR：先用 `home_cache` 同步喂首帧，再后台 `refresh_*_async`。 |
| `library_controller.py` | `LibraryController` | 资料库：我喜欢、我的歌单、收藏专辑、关注艺人，登录后从 `home_cache` 私有区块同步首帧再刷新。 |
| `detail_controller.py` | `DetailController` | 歌单 / 专辑 / 艺人 / 排行榜详情页状态：标题、封面、曲目列表、loading / error。 |
| `player_controller.py` | `PlayerController` | 播放器：包装 `QMediaPlayer` + `core.queue.PlayQueue`。控制四种播放模式、音质偏好、进度/音量、退出快照保存（`session_state`）。 |
| `lyric_controller.py` | `LyricController` | 同步歌词：跟随 `player_controller` 的进度更新 `activeIndex`，逐字 karaoke 高亮的进度也在这里算。 |
| `settings_controller.py` | `SettingsController` | `QSettings` 持久化的偏好：主题模式、音质、封面缓存上限 + 一键清理。 |
| `mpris_controller.py` | `MprisController` | 把 `PlayerController` 的状态/元数据推到 `core.mpris.MprisService`，从 D-Bus 收到的方法调用回灌到播放器。 |
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
