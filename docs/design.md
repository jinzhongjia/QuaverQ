# QuaverQ 设计文档 — PySide6 + Qt Quick

> QQ 音乐桌面客户端 · **Linux 优先（Windows / macOS 后续支持）** · **明暗双主题（默认跟随系统）** · 采用现代音乐应用熟悉的三栏工作区（侧栏导航 + 主内容 + 底部播放栏），但通过 QuaverQ 自有的歌词优先体验、封面处理、动效与 token 系统建立独立视觉识别；所有资源均自研，不复刻任何商标元素。

---

## 1. 目标与边界

### 1.1 V1 目标范围与当前状态

本表区分"设计目标"和"当前落地状态"。验收时以"当前状态"为准推进，不把静态占位、假数据入口或仅有外壳的视图视为完成。

| 能力 | V1 目标 | 当前状态 |
|---|---|---|
| 首页发现 | 默认启动页；每日 30 首推荐 + 今日推荐歌单 + 新歌速递 + 排行榜入口 | **部分完成**：`HomeView` 已有入口结构；当前三个发现板块仍是无效入口，启动还误进搜索页；每日 30 首推荐未实现 |
| 完整搜索 | 综合 + 按类型（歌曲 / 歌手 / 专辑 / 歌单） | **部分完成**：歌曲搜索 + 明确分页已完成；多类型搜索和详情跳转待补 |
| 个人库 | 我喜欢 / 我的歌单 / 收藏专辑 / 关注艺人 | **部分完成**：我喜欢同步已完成；歌单 / 收藏专辑 / 关注艺人 Tab 仍未接真实数据 |
| 详情页 | 专辑 / 歌手 / 歌单真实详情 | **部分完成**：详情路由与壳已完成；真实详情、曲目列表、播放全部待补 |
| 现在播放 | 小封面歌曲信息 + 大面积同步歌词 + 队列按需打开 | **已完成**：Q7 已验收；封面仍依赖后续 CoverImageProvider |
| 播放策略 | 顺序 / 单曲循环 / 列表循环 / 随机 | **已完成**：PlayerController + 队列模式已验收 |
| 登录 | 二维码登录、缓存凭据、过期重登 | **部分完成**：二维码登录与缓存已完成；过期检测和失效重登待 Q9 |
| 音质 | 用户偏好 `standard` / `balanced` / `high`；实际输出显示 MP3_128 / OGG_192 / MP3_320 / FLAC | **待 Q10**：core 支持 preference；设置 UI 和持久化未完成 |
| 桌面集成 | MPRIS2（媒体键 / GNOME / KDE 控件） | **已完成**：Q8 已验收 |
| 会话恢复 | 启动恢复上次队列 / position / 模式 | **已完成**：Q4b 已验收 |
| 设置 | 主题、减弱动效、音质、缓存管理、账号状态 | **待 Q10** |
| 打包 | Linux AppImage + release workflow | **待 Q11** |

### 1.1.1 完成口径

- 真实数据视图必须具备 `loading / empty / error / content` 四态；只展示静态卡片或"暂无"不算完成。
- 任何能触发网络请求的入口必须有可恢复错误：重试、重新登录或返回上一级，不能只写日志。
- 播放链路优先级高于信息浏览：任何新视图不得破坏搜索、点歌、队列、歌词和媒体键。
- UI 验收以截图和真实交互为准：没有明显错位、文本不溢出、滚动边界正确、键盘快捷键不干扰输入框。

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
| 音频 | **`QtMultimedia.MediaPlayer`** (QML 元素) | 由 Qt 多媒体插件处理音频；当前 PySide6/Qt 6 Linux 环境默认走 FFmpeg 后端；不再需要 `core/player.py` 自管 GStreamer |
| 进程模型 | 单进程，Python + QML | 通过 `QQmlApplicationEngine` 暴露 `QObject` |
| MPRIS | 沿用 `core/mpris.py` | dbus-next 挂到 qasync/Qt 主事件循环；不另起 D-Bus 后台线程 |
| API 风控策略 | vkey bypass + **随机 safe `ct`** | 避开库默认 `ct=11` 等热门客户端风控值；每次启动从安全池随机选择并在实例生命周期内固定 |

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
│   │   │     ├── NowPlayingView                             │    │
│   │   │     └── SettingsView                               │    │
│   │   ├── ContextPanel (Queue / Lyrics 单一面板抽屉)      │    │
│   │   └── PlayerBar (底部常驻 transport)                  │    │
│   │   MediaPlayer 元素 (Audio sink)                        │    │
│   └────────────────────────────┬───────────────────────────┘    │
│                                │ Qt meta-object bridge           │
│   ┌────────────────────────────▼───────────────────────────┐    │
│   │ Bridge (src/quaverq/bridge/)                            │    │
│   │   - AppController (QObject)  — 总入口 + 鉴权 + 路由    │    │
│   │   - PlayerController         — 播放/队列/状态           │    │
│   │   - LibraryController        — 喜欢 / 歌单 / 专辑 / 艺人│    │
│   │   - LyricController          — 歌词同步 / 当前行        │    │
│   │   - HomeController           — 每日推荐 / 发现数据      │    │
│   │   - MprisController          — 桌面媒体键 / D-Bus 同步  │    │
│   │   - SettingsController       — 主题 / 音质 / 缓存设置   │    │
│   │   - ServiceController        — 搜索 / 详情 / 取链       │    │
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
                       QtMultimedia（当前环境走 FFmpeg 后端；由 Qt 插件选择）
```

### 3.1 关键约束

- **状态权威在 Python**：队列、喜欢、会话快照、当前曲都由 controller 持有；QML 只 render + 提交意图（signal/slot）
- **`asyncio` 与 Qt 事件循环并存**：用 `qasync` 把 async core 调用桥到 Qt 主线程；全局只维护一个 Qt 主事件循环
- **封面走 image provider**：QML 用 `image://covers/<percent-encoded-url>|<size>`，provider 内部用原始 URL 命中 `core/cover_cache`
- **MediaPlayer 控制权**：QML 端持有 `MediaPlayer` 实例，但 source/position/playbackState 双向绑定到 `PlayerController`，让 MPRIS 也能读写
- **QQ 音乐 vkey 风控策略**：`core/service.py` 不走 `qqmusic-api-python` 默认 `ct=11` 取链路，而是启动时从 `_SAFE_CT_VALUES` 随机选择一个 safe `ct`，本进程内固定使用。这样避免单一固定指纹，也避开已知高风险客户端值；除非重新完成稳定性矩阵验证，不要退回库默认取链路。
- **无任何竞品商标资产**：图标全用 [Qt 自带](https://doc.qt.io/qt-6/qtquickcontrols-icons.html) + Material Icons 字体（Apache-2.0）；强调色为自定义 token，不复用任何品牌色

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

当前源码按目录 singleton 导入：

```qml
import "Theme" as ThemeTokens
```

组件内通过 `ThemeTokens.Palette.background` / `ThemeTokens.TypeScale.body` / `ThemeTokens.Spacing.s5` 访问 token。后续若改成正式 QML module URI，需要同步调整 import path 与打包配置。

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

**交互状态 token**

所有交互状态也必须走 role token，避免组件各自手写透明度或裸色值。

| Token | 用途 |
|---|---|
| `stateHover` | 鼠标悬停底色，仅用于可交互元素 |
| `statePressed` | 按下 / active 底色 |
| `stateSelected` | 当前导航项、当前 tab、播放中行 |
| `stateDisabled` | 禁用内容与控件，必须同时降低可点击 affordance |
| `focusRing` | 键盘焦点描边，默认等于 `primary` |
| `scrim` | 模态遮罩 / drawer 背景 |

**品牌差异化策略**

绿色只承担交互和播放进度，不做大面积装饰背景。QuaverQ 的视觉签名放在：
- 歌词优先的 Now Playing 展开页（封面 + 同步歌词并重，而不是只放大封面）
- 播放中行的节拍条 / waveform 式状态指示，颜色 + 形状双提示
- 封面占位与加载骨架使用音符网格纹理，不使用任何竞品式渐变大背景

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
| Home | `home` | 每日 30 首推荐 + 今日推荐歌单 + 新歌速递 + 排行榜入口 |
| Search | `search` | 输入栏 + 4 类型 tab 结果列表 |
| Library | `library` | 4 Tabs：我喜欢 / 我的歌单 / 收藏专辑 / 关注艺人 |
| AlbumDetail | `detail/album/:mid` | Hero（封面 + 元信息 + 播放全部） + 曲目列表 |
| ArtistDetail | `detail/artist/:mid` | Hero（头像 + 简介） + 热门曲目 + 专辑 |
| PlaylistDetail | `detail/playlist/:pid` | Hero + 曲目 + "全部播放" |
| NowPlaying | `now-playing` | 小封面歌曲信息 + 大面积同步歌词 + 待播抽屉入口 |
| Settings | `settings` | 音质 / 缓存 / 凭据状态 / 退出登录 |
| Login | overlay | 二维码登录弹窗 |

侧栏内置：**Home / Search / Library**，下方动态列出"我的歌单"（点击直跳 PlaylistDetail）。NowPlaying 不占侧栏主导航位置，由 PlayerBar 的封面 / 歌名区域或歌词按钮进入。

### 5.1.1 启动默认页

应用启动后的默认顶级路由必须是 `home`，不是 `search`。

- 首次启动、已登录启动、未登录启动都进入 Home。
- `Ctrl+F`、顶部搜索框聚焦、侧栏搜索项才进入 Search。
- 会话恢复只恢复队列 / 当前曲 / position / 模式，不改变默认内容页；后续可单独设计"恢复上次页面"设置，但 v1 不做。
- 如果 Home 数据加载失败，仍停留在 Home 并显示局部错误，不自动跳到 Search。

### 5.1.2 Home 信息架构

Home 是发现页，不是搜索页。内容优先级从上到下：

1. **每日 30 首推荐**：首页主功能。登录后展示 30 首个性化推荐歌曲，提供"播放全部"和单曲点播；未登录时显示登录入口，不用热门歌伪装成每日推荐。
2. **今日推荐**：推荐歌单横向卡片，数据来自 `QuaverService.get_recommend_playlists(limit=...)`，点击进入 PlaylistDetail。
3. **新歌速递**：歌曲列表或横向紧凑列表，数据来自 `QuaverService.get_recommend_new_songs(limit=...)`，点击直接播放或加入队列。
4. **排行榜**：排行榜入口卡片，数据来自 `QuaverService.get_top_categories(limit_per_group=...)`，点击后用 `get_top_detail(top_id)` 进入 PlaylistDetail。

Home 完成口径：
- 四个板块都不能是静态假入口；每个板块都要有真实数据、loading、empty、error 状态。
- 每日 30 首推荐必须严格显示 30 首；服务端不足时展示实际数量和原因，不补假数据。
- 推荐歌单、排行榜卡片必须可点击进入详情；新歌和每日推荐必须可播放。
- 每个板块局部失败不影响其他板块显示。

### 5.1.3 Library 信息架构

Library 的四个 Tab 都必须接真实数据：

| Tab | 数据源 | 交互 |
|---|---|---|
| 我喜欢 | `LibraryController.likedModel` / `QuaverService.get_liked_songs()` | 点击播放；喜欢状态可切换 |
| 歌单 | `QuaverService.get_my_playlists()`，排除"我喜欢"虚拟歌单 | 点击进入 PlaylistDetail；支持播放全部 |
| 专辑 | `QuaverService.get_fav_albums()` | 点击进入 AlbumDetail |
| 艺人 | `QuaverService.get_followed_singers()` | 点击进入 ArtistDetail |

Library 完成口径：
- 未登录时四个 Tab 显示同一套登录引导，不发无意义请求。
- 已登录时每个 Tab 独立 loading / empty / error；某个 Tab 失败不清空其他 Tab。
- 资料库数据刷新后要保持当前 Tab，不强制跳回"我喜欢"。
- 歌单 / 专辑 / 艺人不是只显示名称，至少要展示封面或头像占位、标题、二级信息和可点击 affordance。

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
- **快捷键作用域**：
  - 文本输入、搜索框、可编辑字段聚焦时，输入控件优先消费 `Space`、方向键、`Ctrl+←/→` 等编辑快捷键
  - 播放器全局快捷键仅在非编辑上下文生效；媒体键不受此限制
  - 弹窗 / 抽屉打开时，`Esc` 先关闭最上层 overlay，再回到主界面

---

## 6. 主窗口布局

```
┌────────────────────────────────────────────────────────────────────┐
│  ◀ ▶   ⌕ 搜索...                              ⚙ user      _ □ ✕   │  ← HeaderBar (48)
├──────────┬──────────────────────────────────────────┬──────────────┤
│          │                                          │              │
│  Sidebar │        ContentStack                      │ ContextPanel │
│  (240)   │        (StackView)                       │ (可折叠 320)  │
│          │                                          │              │
│  ▶ 发现  │        ...具体视图...                     │ Queue | Lyric│
│  ▶ 搜索  │                                          │  ┌────────┐  │
│  ▶ 资料库│                                          │  │ 当前面板│  │
│  ──────  │                                          │  │  ...   │  │
│  我的歌单│                                          │  └────────┘  │
│   · 列表1│                                          │              │
│   · 列表2│                                          │              │
│          │                                          │              │
├──────────┴──────────────────────────────────────────┴──────────────┤
│  ◯ 封面  歌名             ⏮ ⏯ ⏭  ────●────  03:21/04:12  ♥ 🔀 ⇄ ♪│  ← PlayerBar (88)
│  小      歌手 · 专辑                                       音量 列表│
└────────────────────────────────────────────────────────────────────┘
```

- **设计基准窗口**：1080 × 720
- **最小可用窗口**：760 × 640（侧栏折叠为图标条 64 px，ContextPanel 隐藏，PlayerBar 允许两行布局）
- **断点**：宽 < 1280 时 ContextPanel 自动收起；宽 < 920 时侧栏图标化
- **HiDPI**：所有尺寸用 `Theme.spacing.*` + `font.pointSize`；Qt 6 默认启用 high-DPI scaling，不再手动设置 Qt 5 的 `AA_EnableHighDpiScaling`
- **命中区**：HeaderBar / PlayerBar 的工具按钮交互区域不小于 44 × 44 px；视觉图标可保持 20–24 px

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
│   │   │   ├── DailyThirtySection (SongListModel)
│   │   │   ├── SectionRow ("今日推荐", CardListModel)
│   │   │   ├── SectionRow ("新歌速递", SongListModel)
│   │   │   └── SectionRow ("排行榜", CardListModel)
│   │   ├── SearchView
│   │   │   ├── ResultTabs (TabBar + StackLayout)
│   │   │   └── SongList / CardGrid
│   │   ├── LibraryView (TabBar 4 项)
│   │   ├── DetailView
│   │   │   ├── DetailHero (cover + 元信息 + PlayAllButton)
│   │   │   └── SongList
│   │   ├── NowPlayingView
│   │   │   ├── NowPlayingHeader (small cover + title + like + queue button)
│   │   │   └── SyncedLyrics (primary content)
│   │   └── SettingsView
│   └── ContextPanel (Drawer | 嵌入)
│       ├── SegmentedControl (Queue / Lyrics)
│       ├── QueuePanel (SongList + DraggableReorder)
│       └── LyricPanel (compact LyricView)
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
| `IconButton` | iconName, action, tooltip, accessibleName | 工具按钮（焦点环 + ≥44 px 命中区 + Enter/Space 触发 + `Accessible.name`） |
| `LoadingSkeleton` | shape | 网络等待占位（见 §11） |
| `Snackbar` | message, kind | 无操作轻量状态提示，可自动关闭 |
| `Banner` | message, kind, actions | 带恢复动作或阻断任务的持久提示，不自动关闭 |

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
| **AppController** (singleton) | `authed: bool`, `loginState: str`, `loginMessage: str`, `qrcodeDataUrl: str`, `qrcodeKind: str`<br>slot `loginByQrCode()`, `logout()`, `refreshAuthState()` | `authChanged(bool, reason)`, `credExpired()`, `qrcodeChanged()`, `loginStateChanged()` |
| **ServiceController** | slot `search(kw, types) -> Future`, `getAlbumDetail(mid)`, `getArtistDetail(mid)`, `getPlaylistDetail(pid)`, `getSongUrl(song, qualityPreference) -> {url, quality, expiresAt}`, `getLyric(mid)` | `errorRaised(str)` |
| **HomeController** | `dailyModel: SongListModel`, `playlistModel: CardListModel`, `newSongModel: SongListModel`, `topModel: CardListModel`, `loadingSections: QStringList`<br>slot `refreshHome()`, `refreshDailyThirty()`, `playDailyThirty()` | `sectionChanged(str)`, `errorRaised(str)` |
| **LibraryController** | `likedCount: int`, `likedModel: SongListModel`, `playlistModel: CardListModel`, `albumModel: CardListModel`, `artistModel: CardListModel`<br>slot `refreshLiked()`, `refreshMyPlaylists()`, `refreshFavAlbums()`, `refreshFollowedSingers()`, `isLiked(mid)`, `toggleLike(songJson)` | `likedChanged(mid, liked)`, `sectionChanged(str)`, `errorRaised(str)` |
| **PlayerController** | `currentSong`, `currentIndex`, `positionMs`, `durationMs`, `playbackState` (`stopped/playing/paused`), `volume`, `mode` (`sequence/repeat_all/repeat_one/shuffle`)<br>slot `pushAndPlay(songs)`, `next()`, `prev()`, `jumpTo(idx)`, `setMode(m)`, `clear()`, `seek(ms)`, `play()`, `pause()`, `setVolume(v)` | `nowPlayingChanged(song)`, `queueChanged()` |
| **MprisController** | 监听 PlayerController 的曲目 / 状态 / 进度 / 音量 / 模式并推送到 `core/mpris.py` | D-Bus Play/Pause/Next/Previous/Seek 回调直接调用 PlayerController slot |
| **SettingsController** | `themeMode: "system"|"light"|"dark"`, `reducedMotion: bool`, `qualityPreference: "standard"|"balanced"|"high"`, `coverCacheSizeText: str`<br>slot `setThemeMode(mode)`, `setReducedMotion(enabled)`, `setQualityPreference(value)`, `clearCoverCache()` | `settingsChanged()`, `cacheChanged()`, `errorRaised(str)` |

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
- `HomeController.dailyModel` — 每日 30 首推荐
- `HomeController.newSongModel` — 首页新歌速递
- `HomeController.playlistModel` / `topModel` — 首页歌单 / 排行榜卡片
- `LibraryController.playlistModel` / `albumModel` / `artistModel` — 资料库非歌曲卡片
- 详情页临时实例（VM 持有）

Card role 契约：
- `kind`: `playlist` / `album` / `artist` / `top`
- `id`: 详情请求用的稳定 ID（playlist pid、album mid、artist mid、top_id 字符串）
- `title`, `subtitle`, `coverUrl`, `meta`
- QML 点击 `kind=top` 时先走 `get_top_detail(top_id)` 并进入 PlaylistDetail；不要把排行榜只当外部链接。

Song 结构契约：
- QML 行点击 / 播放动作优先传完整 `song` QVariantMap，而不是只传 `mid`
- `ServiceController.getSongUrl(song, qualityPreference)` 内部把 QVariantMap 转回 `core.models.Song`，再调用 `QuaverService.get_song_url(song_obj, quality_preference=...)`
- 仅有 `mid` 的场景必须先从当前 `SongListModel` / `queueModel` / cache 解析出完整 `Song`；不要新增只靠 `mid` 的取链主路径

音质命名契约：
- 用户设置保存为 preference：`standard` / `balanced` / `high`，与 `core.service.QuaverService._QUALITY_PROFILES` 对齐
- 播放 URL 返回的 `quality` 是实际命中的文件档位：`MP3_128` / `OGG_192` / `MP3_320` / `FLAC`
- UI 设置页展示偏好文案（标准 / 均衡 / 高品质），PlayerBar / NowPlaying 可展示实际档位
- Master 不作为 v1 设置项；若后续支持，先在 core 的 `_QUALITY_FILE` / `_QUALITY_PROFILES` 加入对应 prefix 并补测试，再开放 UI

发现 / 资料库数据契约：

| 功能 | core 方法 | bridge model | 备注 |
|---|---|---|---|
| 每日 30 首推荐 | `get_daily_recommend_songs(limit=30)` | `HomeController.dailyModel` | 新增 core 方法；优先评估 `recommend.get_guess_recommend()`，必要时 fallback 到 `get_radar_recommend()`，但不能伪造个性化推荐 |
| 今日推荐歌单 | `get_recommend_playlists(limit=...)` | `HomeController.playlistModel` | 已有 core 方法，接 UI |
| 新歌速递 | `get_recommend_new_songs(limit=...)` | `HomeController.newSongModel` | 已有 core 方法，接 UI |
| 排行榜入口 | `get_top_categories(limit_per_group=...)` | `HomeController.topModel` | 已有 core 方法，点击后拉 `get_top_detail(top_id)` |
| 我的歌单 | `get_my_playlists()` | `LibraryController.playlistModel` | 已有 core 方法，排除"我喜欢" |
| 收藏专辑 | `get_fav_albums()` | `LibraryController.albumModel` | 已有 core 方法 |
| 关注艺人 | `get_followed_singers()` | `LibraryController.artistModel` | 已有 core 方法 |

每日 30 首推荐需要登录态。未登录时 `HomeController.dailyModel` 保持空，并通过 section state 暴露 `requires_login`；QML 显示登录 CTA，不自动搜索或填充热门歌曲。

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
    # id 形如 "<percent-encoded-url>|512"
    def requestPixmap(self, id, size, requested):
        encoded_url, size_hint = id.split("|", 1)
        url = urllib.parse.unquote(encoded_url)
        path = self._cover_cache.get_path(url)
        if not path: schedule self._cover_cache.fetch(url), 返回 placeholder
        return QPixmap(str(path)).scaled(...)
```

QML：

```qml
CoverImage { source: "image://covers/" + encodeURIComponent(song.coverUrl) + "|512" }
```

说明：`core/cover_cache.py` 的权威接口是原始 URL，不是 hash。Provider 不维护第二套 hash → URL registry；hash 仅作为磁盘文件名内部细节。

### 8.6 MPRIS 与 QML 协作

MPRIS 命令（媒体键）→ `core/mpris.py`（dbus-next async service，挂在 qasync/Qt 主事件循环）→ `MprisCallbacks` 直接调用 `PlayerController` slot → controller 改 state → QML 通过绑定刷新。

默认不保留单独 D-Bus 后台线程，因此不需要 `QMetaObject.invokeMethod` 作为主路径。若后续为了隔离 D-Bus 改回后台 loop，必须用 `QMetaObject.invokeMethod(...Qt.QueuedConnection)` 或等价队列投递回 Qt 主线程，严禁从非主线程直接动 QML。

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
                     ServiceController.getSongUrl(song, qualityPreference)
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
  → core/mpris.py callback (qasync / Qt 主事件循环)
  → MprisController 回调
  → PlayerController slot
  → controller 改 state + QML binding 刷新
```

### 9.5 凭据过期与重新登录（Q9）

```
启动 / 播放 / 同步喜欢
  → ServiceController.ensureAuthenticated()
  → 有缓存凭据：先注入 service，再跑轻量鉴权探测
  → 探测成功：authChanged(True, "cached")
  → 探测失败或业务接口返回登录失效：
       · 清内存凭据；保留队列、歌词、当前页面和会话快照
       · authChanged(False, "expired")
       · credExpired()
       · LoginDialog 以"登录已过期，请重新扫码"状态打开
  → 登录成功：
       · 保存 credential.json
       · authChanged(True, "login")
       · 恢复可恢复任务（例如刷新喜欢）；播放任务由用户重新触发，避免误自动播放
```

过期判断规则：
- 优先用 QQ 音乐账号态 / 资料库轻量接口做主动探测，避免等到点歌才失败。
- `get_song_url`、`get_liked_songs`、`toggleLike` 等用户态接口遇到登录失效时必须统一转成 `CredentialExpiredError` 或等价错误码，再由 controller 触发 `credExpired()`。
- 退出登录是显式用户动作：必须写日志、清内存凭据、删除 `credential.json`，并广播 `authChanged(False, "logout")`。
- 登录弹窗状态枚举固定为 `idle / loading / waiting / scanned / confirming / authenticated / expired / error`，QML 不解析任意中文文案做逻辑判断。

### 9.6 设置持久化（Q10）

```
SettingsView 控件
  → SettingsController slot
  → QSettings 写入
  → Theme / PlayerController / ServiceController 通过绑定或 signal 接收变更
```

设置键：
- `ui/themeMode`: `system` / `light` / `dark`
- `ui/reducedMotion`: `true` / `false`
- `playback/qualityPreference`: `standard` / `balanced` / `high`
- `cache/coverMaxBytes`: v1 可先只读默认值；清理动作必须二次确认

Q10 应把设置逻辑集中到 `SettingsController`。当前 `AppController.darkMode` 可保留为兼容别名，但不再作为设置主入口。

### 9.7 首页发现与资料库加载（Q8.5）

```
启动
  → AppController.route = "home"
  → HomeController.refreshHome()
       · daily: 需要登录；未登录只暴露 requires_login 状态
       · playlists / newSongs / topLists: 可并发加载
  → QML 按 section 独立渲染 loading / error / content

进入 Library
  → 当前 Tab 触发对应 refresh
  → 登录失效: credExpired() + 保留当前 Tab
  → 成功: 更新对应 model，不重置其他 Tab
```

Home 和 Library 的网络请求可以并发，但 model 更新必须回到 Qt 主事件循环。每个 section 维护自己的 `loading/error/empty`，不要用一个全局 loading 覆盖整页。

---

## 10. 可访问性 / 键盘 / 国际化

### 10.1 WCAG 2.2

- 文本对比度 ≥ 4.5:1（两套主题都过）：
  - **暗**：`onSurface` (#ececf1) on `background` (#0d0d10) = **17.3:1** ✅；`onSurfaceVariant` (#a3a3ad) on `surface` (#161618) = **6.8:1** ✅；`primary` (#22c55e) on `background` = **8.4:1** ✅
  - **亮**：`onSurface` (#1a1a1f) on `background` (#ffffff) = **17.1:1** ✅；`onSurfaceVariant` (#5e5e68) on `surface` (#f7f7f9) = **6.7:1** ✅；`primary` (#15803d) on `background` = **5.6:1** ✅
- 大文本（≥ 18 px / 14 px Bold）≥ 3:1
- **颜色不是唯一指示**：喜欢 = 实心♥ + 颜色；播放中 = 跳动条 + 颜色
- **焦点环**：所有交互件 `activeFocus` 时画 2 px `primary` 描边 + 2 px offset
- **无障碍名称**：所有纯图标按钮必须设置 `Accessible.role: Accessible.Button` 与稳定的 `Accessible.name`；tooltip 只是鼠标辅助，不能替代无障碍名称
- **键盘触发**：自定义按钮必须支持 `Enter` / `Space` 激活；带菜单按钮必须支持 `Down` 展开
- **命中区**：桌面工具按钮交互区域默认 ≥ 44 × 44 px；小于此尺寸必须只用于非关键、重复列表内操作，并保证键盘可达
- 切换主题后必须重跑一遍对比度校验脚本（建议 Q1 阶段写个 `tests/test_theme_contrast.py` 跑 WCAG 阈值）

### 10.2 键盘

- Tab 顺序 = 视觉读序（左上 → 右下）
- 任何对话框 / 抽屉可用 `Esc` 关闭，无键盘陷阱
- 全局快捷键见 §5.2
- 列表内行操作（喜欢、更多、播放）必须可通过键盘到达；不要只在 hover 时显示唯一入口

### 10.3 国际化

- 主 locale `zh_CN`；所有字符串走 `qsTr()` + Qt Linguist
- `QLocale` 格式化时长 / 日期（不要硬写 `%02d:%02d`）
- 列表容器允许 30% 文本膨胀（英译通常更长）
- 文本溢出策略：
  - 歌名 / 专辑名：默认单行省略，详情页 hero 最多两行
  - 歌手列表：单行省略，完整内容放到可访问名称和 tooltip
  - 按钮文字：不固定宽度；最小宽度 + 内容驱动，必要时换行
- 暂不支持 RTL（计划之外，但 `LayoutMirroring.enabled` 钩子留好）

### 10.4 减弱动效

`Settings → 减少动画` 开关写 `QSettings`，绑 `Motion.reducedMotion`。所有 `NumberAnimation` `duration: Motion.reducedMotion ? 0 : Motion.durMed`。

---

## 11. 等待 / 加载 / 失败

- 网络请求 < 1 s：不显 spinner
- 1 ~ 3 s：列表 skeleton（灰条 + opacity 脉动）
- > 3 s：skeleton + 文案"正在加载..."
- 失败：
  - 无操作的轻量错误：`Snackbar` 顶部出（`error` color + 图标 + 文本），4 s 自动收
  - 带"重试"、"重新登录"等操作的错误：持久 `Banner`，不自动关闭；用户点击操作、关闭按钮或问题恢复后移除
  - 阻断当前任务的错误：保留在当前内容区域内，给出明确恢复动作，不只依赖顶部提示
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
│   ├── home_controller.py
│   ├── library_controller.py
│   ├── player_controller.py
│   ├── lyric_controller.py
│   ├── mpris_controller.py
│   ├── settings_controller.py   Q10 新增：QSettings / 音质 / 主题 / 缓存
│   ├── models.py                QAbstractListModel 族
│   └── image_provider.py        后续：CoverImageProvider
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
    │   ├── AlbumArt.qml
    │   ├── LikeButton.qml
    │   ├── NavItem.qml
    │   ├── PlayerBar.qml
    │   ├── QueueRow.qml
    │   ├── SearchField.qml
    │   ├── Sidebar.qml
    │   ├── SongRow.qml
    │   ├── Card.qml             后续：歌单 / 专辑 / 艺人统一卡片
    │   ├── CoverImage.qml       后续：封面 image provider 入口
    │   ├── IconButton.qml       后续：统一工具按钮
    │   ├── LoadingSkeleton.qml  后续：加载骨架
    │   ├── Snackbar.qml         后续：轻量反馈
    │   └── Banner.qml           后续：持久错误 / 重登提示
    ├── views/
    │   ├── HomeView.qml
    │   ├── SearchView.qml
    │   ├── LibraryView.qml
    │   ├── DetailView.qml
    │   ├── NowPlayingView.qml
    │   └── SettingsView.qml
    ├── panels/
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
| **Q0** | 依赖切换 + 最小 Hello window | `pyproject.toml`、`__main__.py`、`qml/Main.qml` | `uv run quaverq` 出空窗口；pytest 全绿 |
| **Q1** | Theme singleton (Palette / TypeScale / Spacing / Motion) + 验收用 demo 组件 | `qml/Theme/*` | QML 端 import 走通；Palette 切换暗 / 亮可见 |
| **Q2** | `AppController` + `ServiceController` 骨架 + qasync 接入；QML 搜索框 → SongList 渲染 | `bridge/app_controller.py`、`bridge/service_controller.py`、`bridge/models.py`、`qml/views/SearchView.qml` | 输入 "周杰伦"，列表回填 |
| **Q2.5** | 基础视觉组件 polish：SearchField / NavItem / SongRow / PlayerBar shell | `qml/components/*`、`qml/Main.qml`、`qml/views/SearchView.qml` | 去除 Qt Basic 默认表单感；搜索页和底栏具备可继续扩展的组件基线 |
| **Q3** | `PlayerController` + `MediaPlayer` 绑定 + PlayerBar；点歌出声 | `bridge/player_controller.py`、`qml/components/PlayerBar.qml` | 点歌播；transport 全功能；模式切换 |
| **Q3.1** | 登录前置兜底：启动加载缓存凭据；无凭据时 PlayerBar 显示需要登录 | `bridge/service_controller.py`、`bridge/player_controller.py`、`qml/components/PlayerBar.qml` | 无 `credential.json` 时错误明确；有缓存凭据时可直接验收 Q3 播放 |
| **Q3.2** | 提前落地二维码登录：侧栏入口 + 登录弹窗 + 凭据保存 | `bridge/app_controller.py`、`bridge/service_controller.py`、`qml/dialogs/LoginDialog.qml`、`qml/components/Sidebar.qml` | 全新设备可扫码生成 `credential.json`，登录后点歌可取链 |
| **Q4a** | 队列面板 + 当前项跳播 | `bridge/player_controller.py`、`qml/panels/QueuePanel.qml`、`qml/components/PlayerBar.qml` | 底栏可打开队列；当前项高亮；点击队列项可跳播 |
| **Q4a.1** | 搜索结果明确分页 | `bridge/service_controller.py`、`qml/views/SearchView.qml` | 首屏 30 条；上一页 / 下一页切换；无下一页时按钮禁用 |
| **Q4b** | 自动续播完善 + 会话恢复 | `state.py`、`PlayerController` 接入 | 播放结束自动进入下一首；重启恢复队列 / 当前曲 / position / 模式 |
| **Q5** | Sidebar 导航 + StackView 路由 + Home / Library / Detail / NowPlaying 视图 | `qml/Main.qml`、`qml/views/*` | 全视图可达；详情页能跳能回；PlayerBar 可进入 NowPlaying |
| **Q5.5** | 视觉基线重构：轻量 chrome、音乐列表、专辑封面占位、播放器强化 | `qml/Theme/*`、`qml/components/*`、`qml/views/*` | 界面从工具感转向现代音乐客户端；截图验收无明显错位 |
| **Q6** | 喜欢同步 + LibraryController 接入 + LikeButton | `bridge/library_controller.py`、`qml/components/LikeButton.qml` | 双向同步、断网降级 |
| **Q7** | 歌词 + LyricPanel 紧凑同步 + NowPlaying 大歌词 + LRC 翻译 | `qml/panels/LyricPanel.qml`、`qml/views/NowPlayingView.qml`、`bridge/lyric_controller.py`、`bridge/models.py` | 行同步精度 < 200 ms |
| **Q8** | MPRIS 集成（QtMultimedia metadata 推 D-Bus）+ 媒体键 | `core/mpris.py`、`bridge/mpris_controller.py`、`PlayerController` | 媒体键 / GNOME / KDE 显示正常 |
| **Q8.5** | 信息架构补齐：默认 Home + 每日 30 首推荐 + 发现真实数据 + 资料库非喜欢 Tab | `bridge/home_controller.py`、`bridge/library_controller.py`、`bridge/models.py`、`qml/views/HomeView.qml`、`qml/views/LibraryView.qml` | 启动进 Home；首页四板块有效；资料库歌单 / 专辑 / 艺人可点进详情 |
| **Q9** | 登录完善：凭据过期检测 + 失效重登 + 登录 UX polish | `bridge/app_controller.py`、`bridge/service_controller.py`、`qml/dialogs/LoginDialog.qml` | 凭据过期可提示并重新扫码 |
| **Q10** | 设置页 + 减弱动效 / 音质 / 缓存清理 | `bridge/settings_controller.py`、`qml/views/SettingsView.qml`、`qml/Theme/*` | 设置生效；persistent |
| **Q11** | 打包：Nuitka + AppImage + GH Actions | `build.py`、`.github/workflows/release.yml` | AppImage 双击能跑 |

### 14.1 工作模式（与既有约定一致）

1. 写测试（`tests/test_*.py` 或 `tests/qml/tst_*.qml` via `qmltest`）
2. 跑红
3. 写实现（必要时再写 QML）
4. 跑绿
5. 对 UI 改动跑 offscreen 截图检查（见 §14.3）
6. 给用户**手动验证清单**
7. 等"过了"再推 next

### 14.2 风险登记

| 风险 | 缓解 |
|---|---|
| QtMultimedia / FFmpeg 插件或系统 codec 缺失 | AppImage 内嵌 Qt 多媒体插件和核心 codec；启动检测缺失 codec 给提示 |
| qasync 与 `asyncio.run_coroutine_threadsafe` 冲突 | 全局只一个 loop = Qt 主 loop；core 内部不再 `asyncio.run` |
| MediaPlayer 进度回调频率高 | 用 `PositionInterval` 200 ms；MPRIS 推送同源去抖 |
| Nuitka × PySide6 QML 资源 | 用 `qt_add_qml_module` 或 `qrc:/` 打包；走 `--include-data-dir` |
| 凭据过期 race | `AppController.checkCredentialExpired` 启动跑一次 + 失败拦截重试 |
| QQ 音乐扩大 `ct` 风控范围 | 保持 `_SAFE_CT_VALUES` 黑名单测试；监控取链失败码，必要时重新跑稳定性矩阵并更新 safe 池 |

### 14.3 UI 截图验证

每个 UI 阶段至少跑一次 headless QML 截图，确认窗口能加载、关键区域非空、布局没有明显错位。默认输出到 `/tmp/quaverq-ui.png`，必要时填充 fake model 数据。

```bash
QT_QPA_PLATFORM=offscreen uv run python - <<'PY'
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from quaverq.__main__ import _qml_main_path, _qml_root_path
from quaverq.bridge import AppController, LibraryController, LyricController, PlayerController, ServiceController
from quaverq.core.models import Singer, Song

out = Path("/tmp/quaverq-ui.png")

QQuickStyle.setStyle("Basic")
app = QApplication([])
service_controller = ServiceController()
app_controller = AppController(service_controller)
library_controller = LibraryController(service_controller)
player_controller = PlayerController(service_controller)
lyric_controller = LyricController(service_controller, player_controller)
service_controller.songResults.set_songs([
    Song(mid="m1", name="晴天", singers=[Singer(mid="s1", name="周杰伦")], album_name="叶惠美", duration=269),
    Song(mid="m2", name="七里香", singers=[Singer(mid="s1", name="周杰伦")], album_name="七里香", duration=299),
    Song(mid="m3", name="搁浅", singers=[Singer(mid="s1", name="周杰伦")], album_name="七里香", duration=240),
])
player_controller._queue.push(service_controller.songResults.songs(), play_now=True, start_index=1)
player_controller._sync_queue_model()
player_controller._emit_current_changed()

engine = QQmlApplicationEngine()
engine.addImportPath(str(_qml_root_path()))
engine.rootContext().setContextProperty("AppController", app_controller)
engine.rootContext().setContextProperty("ServiceController", service_controller)
engine.rootContext().setContextProperty("LibraryController", library_controller)
engine.rootContext().setContextProperty("LyricController", lyric_controller)
engine.rootContext().setContextProperty("PlayerController", player_controller)
engine.load(QUrl.fromLocalFile(str(_qml_main_path())))
root = engine.rootObjects()[0]
root.setProperty("queuePanelOpen", True)
root.show()

def grab():
    image = app.primaryScreen().grabWindow(root.winId())
    ok = image.save(str(out))
    print("saved", out, ok, image.size())
    app.quit()

QTimer.singleShot(250, grab)
app.exec()
PY
```

辅助启动检查：

```bash
QT_QPA_PLATFORM=offscreen timeout 2s uv run quaverq
```

### 14.4 剩余里程碑细化

**Q8.5 信息架构补齐**

目标：把当前无效的发现 / 资料库入口补成真实产品主路径，并修正启动默认页。

必须交付：
- 启动默认路由改为 `home`，Search 只由侧栏、顶部搜索框或 `Ctrl+F` 进入。
- 新增 `HomeController`，接每日 30 首推荐、今日推荐歌单、新歌速递、排行榜四个 section。
- `QuaverService` 新增 `get_daily_recommend_songs(limit=30)`；优先对接 QQ 音乐猜你喜欢 / 雷达推荐类接口，失败时展示可恢复错误，不用假数据。
- `LibraryController` 扩展 `playlistModel / albumModel / artistModel`，接 `get_my_playlists()`、`get_fav_albums()`、`get_followed_singers()`。
- Home / Library 的卡片点击进入对应 Detail；每日推荐和新歌可直接播放。
- 每个 section 独立 loading / empty / error，不用整页空白替代局部失败。
- 测试覆盖：默认 route、HomeController section 映射、LibraryController 三个非喜欢模型、点击路由目标。

验收：
- `uv run quaverq` 启动后第一屏是发现页，不是搜索页。
- 首页能看到每日 30 首推荐；今日推荐 / 新歌速递 / 排行榜都能点击或播放。
- 资料库的歌单、专辑、艺人 Tab 不再是占位，能进入详情页。
- 未登录时每日推荐和资料库展示登录引导；公共发现板块仍可加载。

**Q9 登录完善**

目标：登录态从"能扫码"升级为"可诊断、可恢复、不会误导用户"。

必须交付：
- 缓存凭据启动探测：有效才显示"已同步账号"，失效触发 `credExpired()`。
- 登录失效统一错误：播放、喜欢同步、资料库刷新遇到失效时走同一条重登路径。
- `LoginDialog` 状态 polish：获取二维码、等待扫码、已扫码、确认中、过期、取消、失败、成功都可区分。
- 退出登录日志完整：请求、清内存、删缓存文件、状态广播都要有日志。
- 测试覆盖：缓存凭据有效 / 失效、登录超时、拒绝登录、退出登录、业务接口触发过期。

验收：
- 删除或伪造 `~/.config/quaverq/credential.json` 后启动，不误显示已登录。
- 二维码过期 / 手机取消后能重新获取。
- 凭据失效后队列和当前页面不丢，重新登录后资料库可刷新。

**Q10 设置页**

目标：让用户可控的偏好真正生效并持久化。

必须交付：
- `SettingsController`：集中管理 QSettings，不继续把设置逻辑散落在 AppController / QML。
- 音质偏好：标准 / 均衡 / 高品质，对应 `standard / balanced / high`，影响后续取链。
- 外观：跟随系统 / 浅色 / 深色，切换只更新 token，不重建主界面。
- 减弱动效：关闭非必要动画；歌词滚动保留功能但不做平滑动画。
- 缓存：显示封面缓存大小；清理前二次确认；清理后刷新大小。
- 测试覆盖：设置读写、非法值回退默认值、音质 preference 传入播放链路。

验收：
- 重启后设置保持。
- 切换主题、音质、减弱动效后立即生效。
- 清理缓存不会影响正在播放。

**Q11 打包**

目标：交付 Linux 用户能直接运行的 AppImage。

必须交付：
- Nuitka standalone 构建脚本。
- QML / Theme / 图标 / metadata 正确进入 bundle。
- `.desktop`、应用图标、AppImage 文件名与版本号。
- CI release workflow：tag 触发构建并产出 artifact。
- smoke test：AppImage 启动、搜索页渲染、登录弹窗可打开、播放链路依赖检查有明确提示。

验收：
- 干净 Linux 环境双击 AppImage 能启动。
- `QT_DEBUG_PLUGINS=1` 不出现缺失 Qt platform plugin 的阻断错误。
- 没有本地源码目录时 QML 仍能加载。

### 14.5 产品完整度 Backlog（不阻塞 Q9-Q11，但阻塞 1.0 完整体验）

| 优先级 | 项目 | 完成口径 |
|---|---|---|
| P1 | CoverImageProvider + `CoverImage` | 搜索、队列、NowPlaying、详情页都能显示真实封面；失败有统一占位 |
| P1 | 首页真实数据 | Q8.5 处理：每日 30 首推荐 / 推荐歌单 / 新歌 / 排行榜接 core 数据；支持 loading / empty / error |
| P1 | 详情页真实数据 | Q8.5 依赖：歌单 / 专辑 / 艺人详情能显示封面、元信息、曲目，并支持播放全部 |
| P1 | 资料库非喜欢 Tab | Q8.5 处理：我的歌单 / 收藏专辑 / 关注艺人接远端数据；点击能进入详情 |
| P1 | 多类型搜索 | 歌曲 / 歌手 / 专辑 / 歌单分栏或 segmented control；结果能跳详情 |
| P2 | 统一反馈组件 | `Snackbar` / `Banner` 替代散落错误文案 |
| P2 | 统一 IconButton | 工具按钮无障碍、焦点环、hover/pressed 状态统一 |
| P2 | 离线和缓存策略 | 封面缓存大小上限、LRU、后续音频缓存预留 |

---

## 15. 验收看板（按期勾选）

- [x] Q0 依赖与最小窗口
- [x] Q1 Theme tokens
- [x] Q2 Service + 搜索
- [x] Q2.5 基础视觉组件 polish
- [x] Q3 播放器
- [x] Q3.1 登录前置兜底
- [x] Q3.2 二维码登录
- [x] Q4a 队列面板
- [x] Q4a.1 搜索结果分页
- [x] Q4b 自动续播 + 会话恢复
- [x] Q5 导航 + 全视图
- [x] Q5.5 视觉基线重构
- [x] Q6 喜欢同步
- [x] Q7 歌词
- [x] Q8 MPRIS
- [ ] Q8.5 信息架构补齐
- [ ] Q9 登录
- [ ] Q10 设置
- [ ] Q11 打包

---

*文档维护：设计 token / 视图 / 桥接契约变动时同步对应章节；进度仅在第 15 节勾选。*
