# QuaverQ 设计文档 — PySide6 + Qt Quick

> QQ 音乐桌面客户端 · **Linux 优先（Windows / macOS 后续支持）** · **明暗双主题（默认跟随系统）** · 视觉灵感取自现代流媒体音乐应用的通用三栏布局（侧栏导航 + 主内容 + 底部播放栏），所有 token / 资源均自研，不复刻任何商标元素。

---

## 1. 目标与边界

### 1.1 In-scope

| 能力 | 说明 |
|---|---|
| 首页发现 | 推荐歌单 / 新歌速递 / 排行榜入口 |
| 完整搜索 | 综合 + 按类型（歌曲 / 歌手 / 专辑 / 歌单） |
| 个人库 | 我喜欢 / 我的歌单 / 收藏专辑 / 关注艺人 |
| 详情页 | 专辑 / 歌手 / 歌单 |
| 现在播放 | 大封面 + 同步歌词 + 队列侧栏 |
| 播放策略 | 顺序 / 单曲循环 / 列表循环 / 随机 |
| 音质 | MP3_128 / MP3_320 / FLAC / Master（VIP 自动降级） |
| 桌面集成 | MPRIS2（媒体键 / GNOME / KDE 控件） |
| 会话恢复 | 启动恢复上次队列 / position / 模式 |

### 1.2 Out-of-scope（v1 不做）

云盘、上传、听歌识曲、社交流、DRM 受限内容、动画密集型可视化。

### 1.3 Deferred（后续阶段）

- **Windows / macOS 桌面支持**：v1 仅 Linux。架构上要为这些平台留出抽象——
  - 桌面媒体集成：Linux MPRIS（v1）→ Windows SMTC / macOS `MPNowPlayingInfoCenter`（后续）。`core/mpris.py` 后续抽出 `MediaIntegration` 接口，按平台注入实现。
  - 打包：v1 AppImage（Linux）；后续加 `.msix` / `.dmg`。
  - 字体 / 系统色板：`Theme` 已经走系统 token，可平滑过渡。
  - 任何后续跨平台代码不得把 `dbus` / GStreamer / `XDG_*` 假设散落到业务层；进入 Windows / macOS 阶段前,先引入 `core/platform/` 子模块隔离平台差异。

---

## 2. 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| Python 绑定 | **PySide6 ≥ 6.6** | 官方 Qt for Python（LGPL，与项目 GPL-3.0 兼容） |
| UI | **Qt Quick / QML** | 声明式、动画原生、与暗色现代风格契合 |
| 控件基底 | Qt Quick Controls **Basic** + 自定义主题 | Basic 不带 OS 样式干扰，方便自由布局 |
| 音频 | **`QtMultimedia.MediaPlayer`** (QML 元素) | Linux 下走 GStreamer，与既有 codec 链路一致；不再需要 `core/player.py` 自管 GStreamer |
| 进程模型 | 单进程，Python + QML | 通过 `QQmlApplicationEngine` 暴露 `QObject` |
| MPRIS | 沿用 `core/mpris.py` | 改在 Qt 主事件循环里跑 `asyncio` |

---

## 3. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│ Python 进程                                                       │
│                                                                   │
│   ┌────────────────────────────────────────────────────────┐    │
│   │ QML Scene (Qt Quick)                                    │    │
│   │   Main.qml                                              │    │
│   │   ├── Sidebar (Home / Search / Library / 我的歌单)     │    │
│   │   ├── ContentStack (StackView 路由)                    │    │
│   │   │     ├── HomeView / SearchView / LibraryView        │    │
│   │   │     ├── DetailView (Album / Artist / Playlist)     │    │
│   │   │     └── SettingsView                               │    │
│   │   ├── ContextPanel (Queue / Lyrics 抽屉)              │    │
│   │   └── PlayerBar (底部常驻 transport)                  │    │
│   │   MediaPlayer 元素 (Audio sink)                        │    │
│   └────────────────────────────┬───────────────────────────┘    │
│                                │ Qt meta-object bridge           │
│   ┌────────────────────────────▼───────────────────────────┐    │
│   │ Bridge (src/quaverq/bridge/)                            │    │
│   │   - AppController (QObject)  — 总入口 + 鉴权 + 路由    │    │
│   │   - PlayerController         — 播放/队列/状态           │    │
│   │   - LibraryController        — 喜欢 / 我的             │    │
│   │   - ServiceController        — 搜索 / 详情 / 推荐       │    │
│   │   - SongListModel (QAbstractListModel) — 歌曲列表       │    │
│   │   - CardListModel            — 歌单 / 专辑 / 艺人卡片  │    │
│   │   - LyricModel               — LRC 同步行              │    │
│   │   - CoverImageProvider (QQuickImageProvider) — 封面    │    │
│   └────────────────────────────┬───────────────────────────┘    │
│                                │                                 │
│   ┌────────────────────────────▼───────────────────────────┐    │
│   │ Core (既有，无改动)                                      │    │
│   │   service / library / queue / cache / cover_cache /     │    │
│   │   state / lyric / mpris / models                        │    │
│   └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                       系统 D-Bus（MPRIS）
                       QtMultimedia（Linux 后端走 GStreamer）
```

### 3.1 关键约束

- **状态权威在 Python**：队列、喜欢、会话快照、当前曲都由 controller 持有；QML 只 render + 提交意图（signal/slot）
- **`asyncio` 与 Qt 事件循环并存**：用 `qasync` 把 async core 调用桥到 Qt 主线程；全局只维护一个 Qt 主事件循环
- **封面走 image provider**：QML 用 `image://covers/<url-sha1>`，provider 内部命中 `core/cover_cache`
- **MediaPlayer 控制权**：QML 端持有 `MediaPlayer` 实例，但 source/position/playbackState 双向绑定到 `PlayerController`，让 MPRIS 也能读写
- **无任何"Spotify"商标资产**：图标全用 [Qt 自带](https://doc.qt.io/qt-6/qtquickcontrols-icons.html) + Material Icons 字体（Apache-2.0）；强调色为自定义 token，不复用任何品牌色

---

## 4. 视觉系统

### 4.1 设计 token 总览

全部以 QML singleton 形式暴露在 `qml/Theme/`，禁止在组件里出现裸 hex / 裸像素。**明暗两套主题等权一等公民**：`Palette` 内部维持两份 token 字典，由 `Theme.dark: bool` 选当前。

```
qml/Theme/
├── qmldir
├── Theme.qml        总入口（dark / reducedMotion / 跟随系统开关）
├── Palette.qml      色板（暗 / 亮两套等权）
├── TypeScale.qml    字号阶梯
├── Spacing.qml      间距 / 圆角 / elevation
└── Motion.qml       动画时长 / 缓动
```

**模式选择**：`Theme.dark` 默认绑定 `Application.styleHints.colorScheme === Qt.Dark`（Qt 6.5+ 跟随系统），用户也可在设置里强制 `Light / Dark / System` 三档，写入 `QSettings`。切换时只动 token，**不重建组件**——所有组件用 `Palette.background` 这种 binding 自动重绘。

### 4.2 调色板（角色令牌）

按 Material 3 角色命名，不出现 `blue1`/`green2` 这种"长相"名字。两套主题在 `Palette.qml` 里同表对齐，所有角色都成对存在。

**暗色主题**

| Token | 值 | 用途 |
|---|---|---|
| `background` | `#0d0d10` | 页面底色（最暗层） |
| `surface` | `#161618` | 卡片 / 侧栏 / 播放栏 |
| `surfaceVariant` | `#1f2024` | 悬浮 / 选中行 / 输入框 |
| `surfaceContainerHigh` | `#26272c` | 弹出面板 / 抽屉 |
| `onSurface` | `#ececf1` | 主文本 |
| `onSurfaceVariant` | `#a3a3ad` | 次文本 / 元数据 / 图标默认 |
| `outline` | `#34353c` | 分割线 / 边框 |
| `primary` | `#22c55e` | 强调色（CTA / 进度 / 喜欢激活） |
| `onPrimary` | `#0a0f0c` | primary 上的文字 / 图标 |
| `primaryContainer` | `#143524` | primary tint 背景（按钮 hover） |
| `error` | `#ef4444` | 错误 / 不可用 |
| `warning` | `#f59e0b` | 凭据过期 / 降级提示 |

**亮色主题**

| Token | 值 | 用途 |
|---|---|---|
| `background` | `#ffffff` | 页面底色 |
| `surface` | `#f7f7f9` | 卡片 / 侧栏 / 播放栏 |
| `surfaceVariant` | `#ececf0` | 悬浮 / 选中行 / 输入框 |
| `surfaceContainerHigh` | `#e2e2e7` | 弹出面板 / 抽屉 |
| `onSurface` | `#1a1a1f` | 主文本 |
| `onSurfaceVariant` | `#5e5e68` | 次文本 / 元数据 / 图标默认 |
| `outline` | `#d4d4d8` | 分割线 / 边框 |
| `primary` | `#15803d` | 强调色（CTA / 进度 / 喜欢激活） |
| `onPrimary` | `#ffffff` | primary 上的文字 / 图标 |
| `primaryContainer` | `#dcfce7` | primary tint 背景（按钮 hover） |
| `error` | `#b91c1c` | 错误 / 不可用 |
| `warning` | `#b45309` | 凭据过期 / 降级提示 |

> **强调色策略**：暗色用 `#22c55e`、亮色用更深的 `#15803d`，都是开源调色板里常见的中性绿；都是项目自有 token，**不与任何流媒体应用的注册商标色相同**。两值由 `Palette.qml` 集中维护，换肤改一处即生效。
>
> **状态色（error / warning）也要分主题**：直接照搬暗色版本贴到亮色背景上对比度会跌破 3:1，亮色版用对应色相的更深一档。

### 4.3 字号 — 模数比 1.200（Minor Third）

base 16 px，给密集列表 + 清晰层级。每屏 ≤ 4 个层级。

| 角色 | px | 用途 |
|---|---|---|
| `display` | 32 | 详情页 hero 标题（专辑 / 歌单名） |
| `h1` | 23 | 页头（"发现"、"资料库"） |
| `h2` | 19 | 区块标题（"为你推荐"、"新歌速递"） |
| `body` | 16 | 歌名 / 卡片标题 / 主文案 |
| `bodySm` | 14 | 歌手 / 专辑名 / 二级文案 |
| `caption` | 13 | 时长 / 元数据 / 状态行 |

字重：常规 400 / Medium 500（标题）。**禁用 700 在正文里**。字体走系统（`Inter`/`Noto Sans SC` 优先，PySide 自动 fallback）。

行高：正文 1.5，标题 1.2。

### 4.4 间距 / 圆角 / 阴影

8 px 基线，硬约束。

| Token | 值 |
|---|---|
| `s2` | 4 |
| `s3` | 8 |
| `s4` | 12 |
| `s5` | 16 |
| `s6` | 24 |
| `s7` | 32 |
| `s8` | 48 |
| `radiusSm` | 4（输入框 / 小标签） |
| `radiusMd` | 8（按钮 / 卡片） |
| `radiusLg` | 12（大卡 / 封面） |
| `radiusXl` | 16（弹窗 / 抽屉） |
| `elev1` | 0 1px 2px rgba(0,0,0,0.32) |
| `elev2` | 0 4px 12px rgba(0,0,0,0.48) |

### 4.5 动效 token（`Motion.qml`）

只动 `opacity` / `scale` / `transform`，禁动 `width`/`height`/`anchors`（避免 relayout 抖）。

| Token | 值 | 用途 |
|---|---|---|
| `durFast` | 120 ms | 小元素：图标、徽章 hover |
| `durMed` | 220 ms | 卡片 / 面板进出 |
| `durSlow` | 320 ms | 全屏页面切换 |
| `easeOut` | `Easing.OutCubic` | 入场 |
| `easeIn` | `Easing.InCubic` | 退场 |
| `easeStd` | `Easing.InOutCubic` | 双向 |

**任何动画 ≤ 400 ms**。`Theme.reducedMotion` 全局开关绑 `QSettings`，开启时所有 NumberAnimation `duration` 强制 0。

---

## 5. 视图与导航

### 5.1 视图清单

| 视图 | 路由 | 内容 |
|---|---|---|
| Home | `home` | 推荐歌单 + 新歌速递 + 排行榜入口（卡片栅格） |
| Search | `search` | 输入栏 + 4 类型 tab 结果列表 |
| Library | `library` | 4 Tabs：我喜欢 / 我的歌单 / 收藏专辑 / 关注艺人 |
| AlbumDetail | `detail/album/:mid` | Hero（封面 + 元信息 + 播放全部） + 曲目列表 |
| ArtistDetail | `detail/artist/:mid` | Hero（头像 + 简介） + 热门曲目 + 专辑 |
| PlaylistDetail | `detail/playlist/:pid` | Hero + 曲目 + "全部播放" |
| Settings | `settings` | 音质 / 缓存 / 凭据状态 / 退出登录 |
| Login | overlay | 二维码登录弹窗 |

侧栏内置：**Home / Search / Library**，下方动态列出"我的歌单"（点击直跳 PlaylistDetail）。

### 5.2 导航模型

- **StackView** 管理主区域的前进 / 后退（详情页可以连跳，支持回退按钮）
- 侧栏切顶级路由 = `StackView.replace`（清栈）
- 详情页跳详情 = `StackView.push`
- 顶部 `Breadcrumb` 显示当前位置（"资料库 / 我喜欢的"）
- 全局快捷键：
  - `Ctrl+F` 聚焦搜索
  - `Space` 播 / 暂停
  - `Ctrl+→` / `Ctrl+←` 下一首 / 上一首
  - `Ctrl+L` 喜欢当前
  - `Esc` 关闭抽屉 / 弹窗

---

## 6. 主窗口布局

```
┌────────────────────────────────────────────────────────────────────┐
│  ◀ ▶   ⌕ 搜索...                              ⚙ user      _ □ ✕   │  ← HeaderBar (40)
├──────────┬──────────────────────────────────────────┬──────────────┤
│          │                                          │              │
│  Sidebar │        ContentStack                      │ ContextPanel │
│  (240)   │        (StackView)                       │ (可折叠 320)  │
│          │                                          │              │
│  ▶ 发现  │        ...具体视图...                     │  ┌─Queue─┐   │
│  ▶ 搜索  │                                          │  │  ...  │   │
│  ▶ 资料库│                                          │  └───────┘   │
│  ──────  │                                          │              │
│  我的歌单│                                          │  ┌─Lyric─┐   │
│   · 列表1│                                          │  │  ...  │   │
│   · 列表2│                                          │  └───────┘   │
│          │                                          │              │
├──────────┴──────────────────────────────────────────┴──────────────┤
│  ◯ 封面  歌名             ⏮ ⏯ ⏭  ────●────  03:21/04:12  ♥ 🔀 ⇄ ♪│  ← PlayerBar (88)
│  小      歌手 · 专辑                                       音量 列表│
└────────────────────────────────────────────────────────────────────┘
```

- **最小窗口**：1080 × 720（侧栏折叠为图标条 64 px，ContextPanel 默认隐藏）
- **断点**：宽 < 1280 时 ContextPanel 自动收起；宽 < 920 时侧栏图标化
- **HiDPI**：所有尺寸用 `Theme.spacing.*` + `font.pointSize`；Qt 6 默认启用 high-DPI scaling，不再手动设置 Qt 5 的 `AA_EnableHighDpiScaling`

---

## 7. 组件层级（关键件）

```
ApplicationWindow (Main.qml)
├── HeaderBar
│   ├── NavHistoryButtons (◀ ▶)
│   ├── SearchField
│   └── UserMenu
├── SplitView (orientation: Horizontal)
│   ├── Sidebar
│   │   ├── NavItem × 3  (Home / Search / Library)
│   │   └── PlaylistList  (我的歌单)
│   ├── StackView (id: contentStack)
│   │   ├── HomeView
│   │   │   ├── SectionRow ("为你推荐", CardListModel)
│   │   │   ├── SectionRow ("新歌速递", CardListModel)
│   │   │   └── SectionRow ("排行榜")
│   │   ├── SearchView
│   │   │   ├── ResultTabs (TabBar + StackLayout)
│   │   │   └── SongList / CardGrid
│   │   ├── LibraryView (TabBar 4 项)
│   │   ├── DetailView
│   │   │   ├── DetailHero (cover + 元信息 + PlayAllButton)
│   │   │   └── SongList
│   │   └── SettingsView
│   └── ContextPanel (Drawer | 嵌入)
│       ├── QueuePanel (SongList + DraggableReorder)
│       └── LyricPanel (LyricView)
└── PlayerBar
    ├── NowPlayingMini (cover + 标题 + 喜欢)
    ├── TransportControls (⏮ ⏯ ⏭)
    ├── ProgressBar (Slider + 时间)
    └── SideControls (queue / lyric / 模式 / 音量)
```

**可复用原子件**

| 组件 | 入参 | 用途 |
|---|---|---|
| `SongRow` | song, index, selected | 一行歌曲（图、标题、歌手、专辑、时长、♥） |
| `Card` | title, subtitle, cover, kind | 歌单 / 专辑 / 艺人卡片 |
| `CoverImage` | url, size | 走 image provider + placeholder |
| `LikeButton` | mid, liked | 切换 + 状态绑 LibraryController |
| `IconButton` | iconName, action, tooltip | 工具按钮（焦点环 + 4.5:1 对比度） |
| `LoadingSkeleton` | shape | AI / 网络等待占位（见 §10） |

---

## 8. Python ↔ QML 桥接契约

### 8.1 注册方式（`bridge/__init__.py`）

```python
from PySide6.QtQml import QmlElement, QmlSingleton

QML_IMPORT_NAME = "QuaverQ.Bridge"
QML_IMPORT_MAJOR_VERSION = 1
```

每个 controller 用 `@QmlElement` 暴露；singleton（`AppController`）用 `@QmlSingleton`。

### 8.2 控制器矩阵

| Controller | 关键 property / slot | signal |
|---|---|---|
| **AppController** (singleton) | `authed: bool`, `vipInfo`, `darkMode: bool`<br>slot `loginByQrCode()`, `logout()` | `qrcodeChanged(bytes, kind)`, `authChanged(bool, reason)`, `credExpired()` |
| **ServiceController** | slot `search(kw, types) -> Future`, `getAlbumDetail(mid)`, `getArtistDetail(mid)`, `getPlaylistDetail(pid)`, `getSongUrl(mid, quality) -> {url, quality, expiresAt}`, `getLyric(mid)`, `getHomeFeed()`, `getTopDetail(topId, limit)` | `errorRaised(str)` |
| **LibraryController** | `likedCount: int`, slot `listLiked()`, `isLiked(mid)`, `toggleLike(songJson)`, `myPlaylists()`, `favAlbums()`, `followedSingers()` | `likedChanged(mid, liked)`, `synced(count)` |
| **PlayerController** | `currentSong`, `currentIndex`, `positionMs`, `durationMs`, `playbackState` (`stopped/playing/paused`), `volume`, `mode` (`sequence/repeat_all/repeat_one/shuffle`)<br>slot `pushAndPlay(songs)`, `next()`, `prev()`, `jumpTo(idx)`, `setMode(m)`, `clear()`, `seek(ms)`, `play()`, `pause()`, `setVolume(v)` | `nowPlayingChanged(song)`, `queueChanged()`, `mediaCommandReceived(cmd)` (来自 MPRIS) |

### 8.3 列表模型（`QAbstractListModel`）

避免每次 `dataclasses.asdict` 全表，QML 只走 role：

```python
class SongListModel(QAbstractListModel):
    MidRole = Qt.UserRole + 1
    NameRole = Qt.UserRole + 2
    SingersRole = ...
    DurationRole = ...
    CoverRole = ...
    LikedRole = ...
```

模型实例：
- `PlayerController.queueModel` — 队列
- `LibraryController.likedModel` — 我喜欢
- 详情页临时实例（VM 持有）

### 8.4 异步桥（`bridge/async_bridge.py`）

用 **qasync** 把 `asyncio` 跑进 Qt event loop：

```python
import qasync, asyncio
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
loop = qasync.QEventLoop(app)
asyncio.set_event_loop(loop)
with loop:
    loop.run_forever()
```

Controller slot 返回 `Future` 时通过 `QFuture` 模式或 `asyncSlot` 装饰器把 awaitable 暴露给 QML（QML 端 `await ServiceController.search(...)` 用 ES2017 async/await）。

### 8.5 图片管线

```python
class CoverImageProvider(QQuickImageProvider):
    # id 形如 "abc123def...|512"  (sha1|size)
    def requestPixmap(self, id, size, requested):
        url_hash, size_hint = id.split("|")
        path = self._cover_cache.get_path(url_hash)
        if not path: trigger async fetch, 返回 placeholder
        return QPixmap(str(path)).scaled(...)
```

QML：

```qml
CoverImage { source: "image://covers/" + song.coverHash + "|512" }
```

### 8.6 MPRIS 与 QML 协作

MPRIS 命令（媒体键）→ `core/mpris.py` → 经 `QMetaObject.invokeMethod(...Qt.QueuedConnection)` 投递到 `PlayerController.handleMprisCommand(...)` → controller 改 state → QML 通过绑定刷新。**严禁** 从 D-Bus 回调线程直接动 QML。

---

## 9. 关键流程

### 9.1 启动

```
main() → QApplication + qasync loop
     → AppController.__init__:
         · cache.open()
         · service.connect()
         · service._get_cached_credential() → 验证有效
         · 有效: emit authChanged(True); library.sync_from_remote() (背景)
         · 无效: emit credExpired
     → QQmlApplicationEngine.load("Main.qml")
     → state.restore() → 注入 PlayerController.queue (但不自动播)
     → loop.run_forever()
```

### 9.2 点歌播放

```
QML: SongRow.clicked → PlayerController.pushAndPlay([song])
     PlayerController: queue.push + emit queueChanged
                     ServiceController.getSongUrl(mid)
                     MediaPlayer.source = url
                     MediaPlayer.play()
                     emit nowPlayingChanged(song)
                     mpris.push_metadata(song)
```

### 9.3 自动下一首

```
MediaPlayer.onMediaStatusChanged(EndOfMedia)
  → PlayerController.next() → 取 queue.next() → 若有：拉 url 续播
                            → 若无：emit playbackState=stopped
```

### 9.4 媒体键

```
D-Bus MPRIS Play/Pause/Next/Previous
  → core/mpris.py callback (D-Bus 线程)
  → QMetaObject.invokeMethod(PlayerController, "handleMprisCommand",
        Qt.QueuedConnection, Q_ARG(str, cmd))
  → PlayerController 主线程消化
```

---

## 10. 可访问性 / 键盘 / 国际化

### 10.1 WCAG 2.2

- 文本对比度 ≥ 4.5:1（两套主题都过）：
  - **暗**：`onSurface` (#ececf1) on `background` (#0d0d10) = **17.3:1** ✅；`onSurfaceVariant` (#a3a3ad) on `surface` (#161618) = **6.8:1** ✅；`primary` (#22c55e) on `background` = **8.4:1** ✅
  - **亮**：`onSurface` (#1a1a1f) on `background` (#ffffff) = **17.1:1** ✅；`onSurfaceVariant` (#5e5e68) on `surface` (#f7f7f9) = **6.7:1** ✅；`primary` (#15803d) on `background` = **5.6:1** ✅
- 大文本（≥ 18 px / 14 px Bold）≥ 3:1
- **颜色不是唯一指示**：喜欢 = 实心♥ + 颜色；播放中 = 跳动条 + 颜色
- **焦点环**：所有交互件 `activeFocus` 时画 2 px `primary` 描边 + 2 px offset
- 切换主题后必须重跑一遍对比度校验脚本（建议 Q1 阶段写个 `tests/test_theme_contrast.py` 跑 WCAG 阈值）

### 10.2 键盘

- Tab 顺序 = 视觉读序（左上 → 右下）
- 任何对话框 / 抽屉可用 `Esc` 关闭，无键盘陷阱
- 全局快捷键见 §5.2

### 10.3 国际化

- 主 locale `zh_CN`；所有字符串走 `qsTr()` + Qt Linguist
- `QLocale` 格式化时长 / 日期（不要硬写 `%02d:%02d`）
- 列表容器允许 30% 文本膨胀（英译通常更长）
- 暂不支持 RTL（计划之外，但 `LayoutMirroring.enabled` 钩子留好）

### 10.4 减弱动效

`Settings → 减少动画` 开关写 `QSettings`，绑 `Motion.reducedMotion`。所有 `NumberAnimation` `duration: Motion.reducedMotion ? 0 : Motion.durMed`。

---

## 11. 等待 / 加载 / 失败

- 网络请求 < 1 s：不显 spinner
- 1 ~ 3 s：列表 skeleton（灰条 + opacity 脉动）
- > 3 s：skeleton + 文案"正在加载..."
- 失败：`Snackbar` 顶部出（`error` color + 文本 + 重试按钮），4 s 自动收
- 凭据过期：触发 `LoginDialog` 模态（非阻塞性提醒，主界面不锁）

---

## 12. 文件布局（落地后）

```
src/quaverq/
├── __init__.py
├── __main__.py             改成 PySide6 启动
├── config.py
├── bridge/                 新增：QObject 桥层
│   ├── __init__.py
│   ├── app_controller.py
│   ├── service_controller.py
│   ├── library_controller.py
│   ├── player_controller.py
│   ├── models.py           QAbstractListModel 族
│   ├── image_provider.py
│   └── async_bridge.py     qasync 接入
├── core/                   保持
│   ├── service / library / queue / cache / cover_cache /
│   │   state / lyric / mpris / models
│   └── platform/           deferred：Windows / macOS 支持前引入
└── qml/                    新增
    ├── Main.qml
    ├── Theme/
    │   ├── qmldir
    │   ├── Palette.qml
    │   ├── TypeScale.qml
    │   ├── Spacing.qml
    │   └── Motion.qml
    ├── components/
    │   ├── SongRow.qml
    │   ├── Card.qml
    │   ├── CoverImage.qml
    │   ├── LikeButton.qml
    │   ├── IconButton.qml
    │   ├── LoadingSkeleton.qml
    │   └── Snackbar.qml
    ├── views/
    │   ├── HomeView.qml
    │   ├── SearchView.qml
    │   ├── LibraryView.qml
    │   ├── DetailView.qml
    │   └── SettingsView.qml
    ├── panels/
    │   ├── Sidebar.qml
    │   ├── PlayerBar.qml
    │   ├── QueuePanel.qml
    │   └── LyricPanel.qml
    └── dialogs/
        └── LoginDialog.qml
```

清理：删 `src/quaverq/api.py`、`src/quaverq/events.py`、`src/quaverq/core/player.py`、`tests/test_player.py`（player 改由 QtMultimedia 接管）。

---

## 13. 打包

v1 仅 Linux。Windows / macOS 分发在 §1.3 已列为 deferred，对应工具链见末行注释。

| 阶段 | 工具 | 输出 |
|---|---|---|
| 本地 dev | `uv run quaverq` | 直接跑 |
| Bundle | **Nuitka** (`--standalone --enable-plugin=pyside6`) | `dist/quaverq/` 目录 |
| 分发（Linux）| **AppImage** (`linuxdeploy` + `linuxdeploy-plugin-qt`) | 单文件 |
| 分发（Windows，后续） | Nuitka `--onefile` + `--mingw64` 或 `pyinstaller` + Inno Setup / MSIX | `.exe` / `.msix` |
| 分发（macOS，后续） | `pyinstaller` `.app` bundle + `create-dmg` + Apple notarization | `.dmg` |

`pyproject.toml` 当前依赖应与本节保持一致：
- 不再包含 `pywebview` / `PyGObject`
- 包含 `PySide6 >= 6.6`、`qasync >= 0.27`
- 保留 `dbus-next`（MPRIS）

---

## 14. 分期落地（TDD + 用户验收）

每期 ≤ 300 行变更（不含测试 / QML），每步交 "测试 + 实现 + 手动验证清单"，用户回 "过了" 才推进下一期。

| # | 步骤 | 关键文件 | 验证 |
|---|---|---|---|
| **Q0** | 依赖切换 + 最小 Hello window | `pyproject.toml`、`__main__.py`、`qml/Main.qml` | `uv run quaverq` 出空窗口；pytest 既有 229 测试不掉 |
| **Q1** | Theme singleton (Palette / TypeScale / Spacing / Motion) + 验收用 demo 组件 | `qml/Theme/*` | QML 端 import 走通；Palette 切换暗 / 亮可见 |
| **Q2** | `AppController` + `ServiceController` 骨架 + qasync 接入；QML 搜索框 → SongList 渲染 | `bridge/app_controller.py`、`bridge/service_controller.py`、`bridge/models.py`、`qml/views/SearchView.qml` | 输入 "周杰伦"，列表回填 |
| **Q3** | `PlayerController` + `MediaPlayer` 绑定 + PlayerBar；点歌出声 | `bridge/player_controller.py`、`qml/panels/PlayerBar.qml` | 点歌播；transport 全功能；模式切换 |
| **Q4** | 队列面板 + 自动续播 + 会话恢复 | `qml/panels/QueuePanel.qml`、`state.py` 接入 | 续播 / 重启恢复 |
| **Q5** | Sidebar 导航 + StackView 路由 + Home / Library / Detail 视图 | `qml/Main.qml`、`qml/views/*` | 全视图可达；详情页能跳能回 |
| **Q6** | 喜欢同步 + LibraryController 接入 + LikeButton | `bridge/library_controller.py`、`qml/components/LikeButton.qml` | 双向同步、断网降级 |
| **Q7** | 歌词 + LyricPanel 同步滚动 + LRC 翻译 | `qml/panels/LyricPanel.qml`、`bridge/lyric_model.py` | 行同步精度 < 200 ms |
| **Q8** | MPRIS 集成（QtMultimedia metadata 推 D-Bus）+ 媒体键 | `core/mpris.py`（小改）+ `PlayerController` | 媒体键 / GNOME / KDE 显示正常 |
| **Q9** | 登录弹窗 + 二维码登录 + 凭据过期处理 | `qml/dialogs/LoginDialog.qml`、`AppController` | 全新设备扫码登录 |
| **Q10** | 设置页 + 减弱动效 / 音质 / 缓存清理 | `qml/views/SettingsView.qml` | 设置生效；persistent |
| **Q11** | 打包：Nuitka + AppImage + GH Actions | `build.py`、`.github/workflows/release.yml` | AppImage 双击能跑 |

### 14.1 工作模式（与既有约定一致）

1. 写测试（`tests/test_*.py` 或 `tests/qml/tst_*.qml` via `qmltest`）
2. 跑红
3. 写实现（必要时再写 QML）
4. 跑绿
5. 给用户**手动验证清单**
6. 等"过了"再推 next

### 14.2 风险登记

| 风险 | 缓解 |
|---|---|
| QtMultimedia codec 缺失（无 GStreamer plugins-good） | AppImage 内嵌核心 codec；启动检测缺失 codec 给提示 |
| qasync 与 `asyncio.run_coroutine_threadsafe` 冲突 | 全局只一个 loop = Qt 主 loop；core 内部不再 `asyncio.run` |
| MediaPlayer 进度回调频率高 | 用 `PositionInterval` 200 ms；MPRIS 推送同源去抖 |
| Nuitka × PySide6 QML 资源 | 用 `qt_add_qml_module` 或 `qrc:/` 打包；走 `--include-data-dir` |
| 凭据过期 race | `AppController.checkCredentialExpired` 启动跑一次 + 失败拦截重试 |

---

## 15. 验收看板（按期勾选）

- [ ] Q0 依赖与最小窗口
- [ ] Q1 Theme tokens
- [ ] Q2 Service + 搜索
- [ ] Q3 播放器
- [ ] Q4 队列 + 会话恢复
- [ ] Q5 导航 + 全视图
- [ ] Q6 喜欢同步
- [ ] Q7 歌词
- [ ] Q8 MPRIS
- [ ] Q9 登录
- [ ] Q10 设置
- [ ] Q11 打包

---

*文档维护：设计 token / 视图 / 桥接契约变动时同步对应章节；进度仅在第 15 节勾选。*
