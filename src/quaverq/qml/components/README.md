# src/quaverq/qml/components

可复用原子 QML 组件。各组件只绑定 [`Theme/`](../Theme/README.md) 暴露的 token，不写裸色值/字号；与具体业务的耦合通过 `property var xxxController` / `property var song` 等显式注入，方便复用与测试。

## 导航与外壳

| 组件 | 作用 |
| --- | --- |
| `Sidebar.qml` | **侧栏**。Logo、登录入口、主导航（发现 / 资料库 / 设置）、「我的歌单」列表。`compact` 折叠态收为图标。 |
| `NavItem.qml` | 侧栏的单项导航：图标 + 标签 + 选中态背景；点击发 `activated()`。 |
| `PlayerBar.qml` | **底部播放栏**（~465 行最大组件）。封面缩略 + 标题/歌手 + 喜欢、进度条 + 时长、上一首/播放暂停/下一首、音量、播放模式、队列开关、跳「正在播放」页。 |

## 列表与卡片

| 组件 | 作用 |
| --- | --- |
| `Card.qml` | **内容卡片**（歌单 / 专辑 / 艺人 / 排行榜）：方形封面 + 播放量角标 + hover 浮出播放键 + 标题副标题。整卡点击 `activated()`（进详情），浮层 `playRequested()`（直接播放）。`circular` 给艺人卡用圆形。 |
| `SongRow.qml` | 曲目列表行：序号、封面、歌名 + 歌手、专辑、时长、喜欢按钮、单曲操作。 |
| `QueueRow.qml` | 播放队列行：高亮当前播放项，提供「定位到这首」和「从队列移除」。 |
| `AlbumArt.qml` | 通用专辑封面：`active` 时附 hover 播放浮层，`compact` 切小尺寸，`circular` 切圆形（艺人用），失败 / 未加载时显示占位符。封面 URL 通过 `coverController` 间接走 `image://covers/...`。 |

## 输入与反馈

| 组件 | 作用 |
| --- | --- |
| `SearchField.qml` | 搜索框 `FocusScope`。`searchRequested(text)` / `editingCancelled()` 信号，`loading` 时显示状态。 |
| `IconButton.qml` | 统一的工具按钮：≥44 px 命中区、焦点环（`visualFocus`，仅键盘聚焦显示）、Enter/Space 触发；`text` 同时当无障碍名和 hover ToolTip（经 `AppToolTip`），`iconText` 当字形。 |
| `AppToolTip.qml` | 统一样式 ToolTip：token 配色 + 600ms 延迟；显示前按 parent 的窗口位置自动选上方 / 下方，避免被窗口顶 / 底边裁掉。供 `IconButton`、`PlayerBar` 歌曲信息等复用。 |
| `LikeButton.qml` | 喜欢按钮。绑 `libraryController.isLiked(mid)` + `likedRevision`，自动随同步状态变化。 |
| `Snackbar.qml` | **轻量状态提示**。`show()` 触发，`autoHideMs` 后自动收起；`kind` ∈ `info` / `error` / `warning` / `success`。 |
| `Banner.qml` | **持久提示**：带恢复动作（`actionText`）、不自动关闭；`message` 非空即显示。用于"凭据过期，点此重登"这类场景。 |
| `MarqueeLabel.qml` | 单行文字标签：超出容器宽度时无缝横向滚动（双拷贝 + Repeater 平移），未溢出时回退为 `elide: ElideRight`，配合固定宽度容器防止布局抖动。用于底部播放栏歌曲名 / 歌手。 |

## 约定

- **不引业务模型**：组件不 `import quaverq.core ...`；通过 `property var song` / `property var libraryController` 等显式接收，便于复用。
- **token-only 样式**：色值取自 `ThemeTokens.Palette`，间距取自 `ThemeTokens.Spacing`，字号取自 `ThemeTokens.TypeScale`，动效取自 `ThemeTokens.Motion`。
- **信号优先**：组件不主动跨层调用，把意图通过 `signal activated()` / `signal playRequested()` 抛给父级，父级决定路由 / 起播 / 弹窗。
- **`pragma ComponentBehavior: Bound`** 在含 `delegate` 的复合组件（`Sidebar`）开启，避免动态作用域问题。
