# src/quaverq/qml/panels

右侧抽屉式面板。比 [`dialogs/`](../dialogs/README.md) 更轻：不模态、贴边出现，能跟主内容并存。由 [`Main.qml`](../README.md) 拥有并通过状态属性（`queuePanelOpen` 等）控制开合动效。

| 组件 | 作用 |
| --- | --- |
| `LyricPanel.qml` | **同步歌词面板**。绑 `lyricController` 的 `lines` / `activeIndex` / `positionMs`：当前行居中高亮，已过 / 未到的行用 `Palette.lyricMuted` 弱化；版权信息行（"作词/作曲/编曲..."）淡到 `Palette.lyricCredit`（本地 readonly 别名 `mutedLineColor` / `creditLineColor` 绑这些 token）。逐字 karaoke：full 模式当前行交给 [`KaraokeLine`](../components/README.md)（逐词双层 + clip wipe，字内从左到右渐进扫亮；`wipeDurationMs` 传 `Motion.durFast`，reduceMotion 时归零退化为瞬时）。`compact` 用于嵌入侧栏抽屉、非 compact 用于「正在播放」沉浸页（full 模式**不渲染「歌词」标题行**，滚动区直接顶满）。**点击跳播**：注入可选 `playerController` 后，full 模式下普通歌词行可点（hover 背景条 + 手型光标）→ `seek(timestampMs)`；credit 行与 compact 模式不可点；不注入则整体只读。可选 `settingsController` 注入后，主歌词 / karaoke / 翻译三类行的 `font.family / pixelSize / weight / italic` 都从 SettingsController.lyricFont* 读取并按视觉层次比例缩放；不注入时回退到默认值。⚠️ 滚动钳位 `clampedContentY` 必须从 `originY` 起算（delegate 高度变化会让 ListView 内容原点漂移非零）：按 `[0, contentHeight-height]` 钳出的值相对真实边界越界，Flickable 会在下一次按压时回弹并**吃掉那次点击**。列表 `onHeightChanged` 重跑 reveal 用新边界重新钳位。 |
| `QueuePanel.qml` | **播放队列面板**。绑 `queueModel`（`SongListModel`）+ `currentIndex`，逐项渲染 [`QueueRow`](../components/README.md)；提供「定位到当前」、「清空队列」、「从队列移除」操作；行点击跳转该首播放。首子项是整层 `MouseArea` 事件屏障：面板盖在内容区上，无处理器区域的点击 / 滚轮 / 悬停会穿透到底下的页面。承载方式为 Main.qml 的**首开常驻 Loader**（滑入/出动画需要 item 存活），「打开时定位到当前曲」由 `onVisibleChanged` 触发（不 hook currentIndex，避免播放器切歌强拉用户滚开的视图）。 |

## 约定

- **`pragma ComponentBehavior: Bound`**：强制显式作用域，列表 `delegate` 内部用 `required property` 绑 model role。
- **不持有业务状态**：面板是 controller 的视图层投射；自身只管展示/滚动/动效，业务动作通过 `lyricController` / `playerController` 的方法回调。
- **token-only 配色**：高亮用 `Palette.primary`（品牌绿），弱化用 `mutedLineColor` 之类按主题切的色阶。
