# src/quaverq/qml/views

顶层视图（"页面"）。每个 `.qml` 对应 [`Main.qml`](../README.md) 的一个路由 (`routeName`)，由路由切换决定挂载哪一个。视图持有控制器引用 + 路由参数，组装 [`components/`](../components/README.md) / [`panels/`](../panels/README.md) 完成具体页面。

## 视图清单

| 文件 | 路由 | 作用 |
| --- | --- | --- |
| `HomeView.qml` | `home` | **发现页**。每日推荐 + 今日歌单 + 新歌速递 + 排行榜四个横向滚动行，绑 `homeController` 的对应 `*Loading` / `Model` 属性。SWR 首帧用 `homeController.prime_*_from_cache` 喂好的快照，加载完成自动覆盖。 |
| `SearchView.qml` | `search` | **搜索页**。综合（默认）/ 歌曲（分页）/ 歌手 / 专辑 / 歌单五分栏 `TabRow`；搜索框输入触发 `serviceController.search*`，结果支持一键进详情或起播。**综合 tab** 复用歌曲列表渲染 `songResults`，并在列表头部（随滚动）显示 `directHit` 直达卡（点击 `detailRequested` 进歌手/专辑详情）+ `relatedWords` 相关词 chips（点击 `searchRequested` → Main.qml `searchAndOpen` 同步搜索框再搜）；综合不翻页。 |
| `LibraryView.qml` | `library` | **资料库**。我喜欢、我的歌单、收藏专辑、关注艺人；从 `libraryController` 的同名 model 读，登录后首帧由 `prime_from_cache(account_key)` 立即填充。 |
| `DetailView.qml` | `detail` | **详情页**（歌单 / 专辑 / 艺人 / 排行榜）。路由参数 `detailKind` + `detailId` 触发 `detailController` 加载，渲染标题 + 封面 + 描述 + 曲目列表，提供「播放全部」+「下载全部」（`downloadController.downloadFromModel(songModel)` 批量入队）与单曲操作。长简介默认 2 行截断，确实截断时出现「展开 ⌄ / 收起 ⌃」链接（`descriptionExpanded`，换详情数据自动收回）。 |
| `NowPlayingView.qml` | （无路由） | **正在播放沉浸页**。**不进导航栈**——由 `Main.qml` 以整宽浮层承载（盖侧栏 + 内容区，z=5，顶栏 / 播放栏保持可见），`Main.openNowPlaying()` 开 / 关，从播放栏上方滑入（durSlow 减速）/ 滑出（durMed 加速）；收起后底下的路由、滚动位置、侧栏选中态原样还原。出口×4：页内左上「收起 ˅」（`backRequested()`）/ Esc / 顶栏返回 / 再点播放栏封面；任何 `navigate()` / `pushDetail()` 自动收起。布局单一断点 920（浮层盖侧栏后自宽 ≈ 窗宽）：**≥920 双栏** = 左栏 ~40%（大封面 200–400 自适应 + `RectangularShadow` 投影 + 1px 描边、歌名 / 歌手 / 专辑、喜欢 + 下载 + 待播列表，整组垂直居中）+ 右栏歌词；**<920 单栏** = 顶行小封面信息 + 歌词。内容块限宽 1280 居中防超宽散架。歌词区是同一个 [`LyricPanel`](../panels/README.md) 实例（`compact: false`，注入 `playerController` 启用点击跳播），断点切换不丢滚动状态。首子项是整层 `MouseArea` 事件屏障，防点击 / 滚轮 / 悬停穿透到底下的页面。 |
| `SettingsView.qml` | `settings` | **设置页**。账号 / 播放音质 / **下载**（播放与下载音质统一为同三档 标准（128K）/ 高品质（320K）/ 无损（FLAC），下载目录——`FolderDialog` 选目录 + 「打开」走 `downloadController.openDownloadDirectory()`、歌词 / 封面 / 嵌入标签开关）/ 主题 / 歌词字体（family、size、weight、italic + 一键重置）/ 封面缓存上限 + 一键清理。分区标题在卡片外（小号灰字 + 紧凑行卡），内容列最大宽 840px。行类型：`ChoiceRow`（下拉，经显式 `Binding` 同步外部重置）/ `SwitchRow`（二元开关，绿色 Switch）/ `SpinRow`（数字输入 + 框外后缀）/ `ColorRow`（色板 + QColorDialog）/ `FontPickerRow`（顶部 TextField 实时子串过滤、delegate 用对应 family 渲染做字形预览）。危险动作（退出登录）按钮文字走 `Palette.error`。「外观」分区含主题与「减少动效」开关（写 `settingsController.reduceMotion` → Main 注入 `Motion.reduceMotion`）。「高级」分区含「重置风控指纹」按钮（`serviceController.resetRiskFingerprint()`，重抽 vkey 用的 ct、立即生效，遇部分歌曲取流被风控时可换）。「关于」分区显示版本号（`appController.appVersion`）+ 开源仓库链接（`Qt.openUrlExternally`）。挂载时主动 `refreshCoverCacheSize()` 拿当前占用。 |
| `DownloadsView.qml` | `downloads` | **下载管理整页**（侧边栏「下载」入口）。绑 `downloadController.downloadModel`：行 = 封面（`AlbumArt`）+ 歌名 + 歌手 · 状态 · 音质（失败显红色错误原因）+ running 进度条；**整行点击 → `playerController.pushAndPlay(song)` 应用内播放**（播放核心本地优先：已下载文件直接放，失效回退在线）；行尾按状态「取消」（进行中）/「重试」（失败/取消）/「重新下载」+「移除」（文件失效 missing：副标题 warning 色「文件已删除」）/「删除」（已完成 done：删本地文件+记录，`ConfirmDialog` 二次确认）；顶部「打开下载目录」；空态引导。重启后由 `DownloadController` 从 `downloads.json` 加载的历史填充。 |

`SettingsView.qml` 的「歌词」分区包含「显示歌词翻译」开关，写入 `settingsController.lyricTranslationVisible`，同时影响应用内歌词、桌面悬浮歌词和 D-Bus 歌词外发。


## 约定

- **路由 + 控制器从外注入**：视图顶部一律是 `property string routeName: ...` + 一组 `property var xxxController`，由 `Main.qml` 在切路由时挂上去；视图内部不直接引用 context property。
- **信号回上层**：`loginRequested()` / `searchRequested(keyword)` / `detailRequested(kind, id, title, subtitle, coverUrl)` / `nowPlayingRequested()` 这类导航意图通过信号抛给 `Main.qml`，由它决定路由切换。`coverUrl` 是入口卡片的封面，经 `pushDetail` 透传给 `DetailView` 作头图初始值（详情接口返回前立即显示，接口没给封面时保留兜底）。
- **`pragma ComponentBehavior: Bound`** 全部开启。
- **派生显示属性**：详情 / 首页这些视图用 `readonly property` 包一层 `xxxController.xxx`，给控制器尚未到位时一个安全默认值，避免初始化期空引用。
