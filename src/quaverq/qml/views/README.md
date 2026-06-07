# src/quaverq/qml/views

顶层视图（"页面"）。每个 `.qml` 对应 [`Main.qml`](../README.md) 的一个路由 (`routeName`)，由路由切换决定挂载哪一个。视图持有控制器引用 + 路由参数，组装 [`components/`](../components/README.md) / [`panels/`](../panels/README.md) 完成具体页面。

## 视图清单

| 文件 | 路由 | 作用 |
| --- | --- | --- |
| `HomeView.qml` | `home` | **发现页**。每日推荐 + 今日歌单 + 新歌速递 + 排行榜四个横向滚动行，绑 `homeController` 的对应 `*Loading` / `Model` 属性。SWR 首帧用 `homeController.prime_*_from_cache` 喂好的快照，加载完成自动覆盖。 |
| `SearchView.qml` | `search` | **搜索页**。歌曲（分页）/ 歌手 / 专辑 / 歌单四分栏 `TabBar`；搜索框输入触发 `serviceController.search*`，结果支持一键进详情或起播。 |
| `LibraryView.qml` | `library` | **资料库**。我喜欢、我的歌单、收藏专辑、关注艺人；从 `libraryController` 的同名 model 读，登录后首帧由 `prime_from_cache(account_key)` 立即填充。 |
| `DetailView.qml` | `detail` | **详情页**（歌单 / 专辑 / 艺人 / 排行榜）。路由参数 `detailKind` + `detailId` 触发 `detailController` 加载，渲染标题 + 封面 + 描述 + 曲目列表，提供「播放全部」与单曲操作。 |
| `NowPlayingView.qml` | `now-playing` | **正在播放页**。顶部 `AlbumArt` + 歌名 / 歌手 + 喜欢 + 队列按钮，主区域全屏挂 [`LyricPanel`](../panels/README.md)（`compact: false`）做沉浸式同步歌词；把 `settingsController` 透传给面板让歌词字体跟随用户偏好。 |
| `SettingsView.qml` | `settings` | **设置页**。账号 / 播放音质 / 主题 / 歌词字体（family、size、weight、italic + 一键重置）/ 封面缓存上限 + 一键清理。歌词字体行用自定义 `FontPickerRow`：顶部 TextField 实时子串过滤、列表 delegate 用对应 family 渲染做字形预览。挂载时主动 `refreshCoverCacheSize()` 拿当前占用。 |

## 约定

- **路由 + 控制器从外注入**：视图顶部一律是 `property string routeName: ...` + 一组 `property var xxxController`，由 `Main.qml` 在切路由时挂上去；视图内部不直接引用 context property。
- **信号回上层**：`loginRequested()` / `searchRequested(keyword)` / `detailRequested(kind, id, title, subtitle)` / `nowPlayingRequested()` 这类导航意图通过信号抛给 `Main.qml`，由它决定路由切换。
- **`pragma ComponentBehavior: Bound`** 全部开启。
- **派生显示属性**：详情 / 首页这些视图用 `readonly property` 包一层 `xxxController.xxx`，给控制器尚未到位时一个安全默认值，避免初始化期空引用。
