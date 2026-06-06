# src/quaverq/qml/panels

右侧抽屉式面板。比 [`dialogs/`](../dialogs/README.md) 更轻：不模态、贴边出现，能跟主内容并存。由 [`Main.qml`](../README.md) 拥有并通过状态属性（`queuePanelOpen` 等）控制开合动效。

| 组件 | 作用 |
| --- | --- |
| `LyricPanel.qml` | **同步歌词面板**。绑 `lyricController` 的 `lines` / `activeIndex` / `positionMs`：当前行居中高亮，已过 / 未到的行用 `mutedLineColor` 弱化；版权信息行（"作词/作曲/编曲..."）淡到 `creditLineColor`。逐字 karaoke：从 `LyricLine.words` 拼 `RichText` 的 `<font color>` 段，`sungCount` 只在跨字时变以避免每帧重排。`compact` 用于嵌入侧栏抽屉、非 compact 用于「正在播放」全屏页。 |
| `QueuePanel.qml` | **播放队列面板**。绑 `queueModel`（`SongListModel`）+ `currentIndex`，逐项渲染 [`QueueRow`](../components/README.md)；提供「定位到当前」、「清空队列」、「从队列移除」操作；行点击跳转该首播放。 |

## 约定

- **`pragma ComponentBehavior: Bound`**：强制显式作用域，列表 `delegate` 内部用 `required property` 绑 model role。
- **不持有业务状态**：面板是 controller 的视图层投射；自身只管展示/滚动/动效，业务动作通过 `lyricController` / `playerController` 的方法回调。
- **token-only 配色**：高亮用 `Palette.primary`（品牌绿），弱化用 `mutedLineColor` 之类按主题切的色阶。
