# src/quaverq/qml/components

可复用原子 QML 组件。各组件只绑定 [`Theme/`](../Theme/README.md) 暴露的 token，不写裸色值/字号；与具体业务的耦合通过 `property var xxxController` / `property var song` 等显式注入，方便复用与测试。

## 导航与外壳

| 组件 | 作用 |
| --- | --- |
| `Sidebar.qml` | **侧栏**。Logo、登录入口、主导航（发现 / 资料库 / 设置）、「我的歌单」列表。`compact` 折叠态收为图标。 |
| `NavItem.qml` | 侧栏的单项导航：图标 + 标签 + 选中态背景；点击发 `activated()`。 |
| `PlayerBar.qml` | **底部播放栏**（最大组件）。封面缩略 + 标题/歌手 + 喜欢、进度条 + 时长、播放模式/上一首/播放暂停/下一首 + 对称第 5 槽（让播放键正压进度条中轴）、音量、队列开关、跳「正在播放」页。**音量图标可点**：切静音/恢复（`muted` 属性 + `muteToggleRequested()` 信号，图标 volume ↔ volume-mute 切换，静音时滑条填充/手柄降权 35%；拖滑条即解除静音）。窗口 <920px 时右区（词/队列/音量）收纳进第 5 槽的 "⋯" 溢出菜单（`OverflowRow` + 音量滑条；队列非空时按钮带绿点），不再整组消失。 |

## 列表与卡片

| 组件 | 作用 |
| --- | --- |
| `Card.qml` | **内容卡片**（歌单 / 专辑 / 艺人 / 排行榜）：方形封面 + 播放量角标 + hover 浮出播放键 + 标题副标题。整卡点击 `activated()`（进详情），浮层 `playRequested()`（直接播放）。`circular` 给艺人卡用圆形。 |
| `SongRow.qml` | 曲目列表行：序号、封面、歌名 + 歌手、专辑、时长、喜欢按钮、单曲操作。 |
| `QueueRow.qml` | 播放队列行：高亮当前播放项，提供「定位到这首」和「从队列移除」。 |
| `AlbumArt.qml` | 通用专辑封面：`active` 时附 hover 播放浮层，`compact` 切小尺寸，`circular` 切圆形（艺人用），失败 / 未加载时显示占位符。封面 URL 通过 `coverController` 间接走 `image://covers/...`。`retainOnSwitch: true` 时换 URL 期间保留旧图直到新图就绪（详情头图"卡片图 → 接口高清图"无缝升级用）；列表行 delegate 复用场景保持默认 false，立即回占位避免串图。双缓冲换层记账用自维护的 `frontSource/backSource` 字符串——**不要**反读 `Image.source` 比较（`image://` URL 会被 QUrl 规范化导致比对失效）。**防 resize 闪烁**：`imageSize` 量化到 64px 桶（桶内拖窗口只拉伸纹理零重载，跨桶才换 provider id），圆角按 `bakeScale`（纹理/显示拉伸比快照）放大烘焙保持视觉半径；同一封面仅切分辨率桶时换层瞬切（`animateSwap` false），真换封面才 120ms 交叉淡入——两层半透明交叉的中间帧合成不透明度 < 1 会透底色闪一下，内容相同时必须瞬切。契约测试见 `tests/test_qml_album_art.py`。 |
| `SongRow.qml` | 歌曲行（64px）：点击播放、右键 / ⋯ 弹同一个操作菜单（播放 / 下一首播放 / 添加到待播列表 / 收藏 / 查看歌手 / 查看专辑 / 歌曲详情），需注入 `playerController`（插队/追加走 `playSongNext`/`appendToQueue`）。 |
| `QueueRow.qml` | 待播列表行（56px）：hover 时时长让位给 × 移除按钮（`removeRequested(row)`）；当前曲带 3px 绿条 + ♪ 标记 + "播放中"徽章。 |

## 输入与反馈

| 组件 | 作用 |
| --- | --- |
| `SearchField.qml` | 搜索框 `FocusScope`。`searchRequested(text)` / `editingCancelled()` 信号，`loading` 时显示状态。 |
| `TabRow.qml` | **文字 + 2px 品牌绿下划线 tab 行**（QQ 音乐样式），统一收编搜索/资料库/详情三处复制实现。`tabs` 接受字符串或 `{label}` 对象数组，`currentIndex` 受控、点击/Enter/Space 发 `activated(index)` 由调用方决定切换（受控组件，不自持状态）。命中区经 Handler `margin` 外扩（不动布局对齐），键盘焦点环统一。 |
| `AppIcon.qml` | 单色 SVG 图标：白色源图（[`../icons/`](../icons/README.md)）经 `MultiEffect.colorization` 按 `color` 染色，亮暗主题 / 选中 / 禁用态一份资产通吃。`size` 控制渲染尺寸（48px 栅格化保证高 DPI 锐利）。 |
| `IconButton.qml` | 统一的工具按钮：≥44 px 命中区、焦点环（`visualFocus`，仅键盘聚焦显示）、Enter/Space 触发；`text` 同时当无障碍名和 hover ToolTip（经 `AppToolTip`）。图标走 `iconSource`（SVG，经 `AppIcon` 染 `iconColor`），`iconText` 字形作后备。 |
| `AppToolTip.qml` | 统一样式 ToolTip：token 配色 + 600ms 延迟；显示前按 parent 的窗口位置自动选上方 / 下方，避免被窗口顶 / 底边裁掉。供 `IconButton`、`PlayerBar` 歌曲信息等复用。 |
| `LikeButton.qml` | 喜欢按钮。绑 `libraryController.isLiked(mid)` + `likedRevision`，自动随同步状态变化。 |
| `Snackbar.qml` | **轻量状态提示**。`show()` 触发，`autoHideMs` 后自动收起；`kind` ∈ `info` / `error` / `warning` / `success`。 |
| `Banner.qml` | **持久提示**：带恢复动作（`actionText`）、不自动关闭；`message` 非空即显示。用于"凭据过期，点此重登"这类场景。 |
| `MarqueeLabel.qml` | 单行文字标签：超出容器宽度时无缝横向滚动（双拷贝 + Repeater 平移），未溢出时回退为 `elide: ElideRight`，配合固定宽度容器防止布局抖动。**悬停暂停**（`paused` 而非 stop，移开从当前位置继续）；`Motion.reduceMotion` 开启时横滚整体停用、回退静态省略号。用于底部播放栏歌曲名 / 歌手。 |
| `SkeletonRect.qml` | 骨架屏基件：轻脉动灰块（700ms×2 透明度往返），全应用加载占位的统一形态；`reduceMotion` 时脉动停用、静态灰块仍占位。 |
| `SongRowSkeleton.qml` | 歌曲行骨架（64px，几何对齐 `SongRow`）：封面块 + 标题/副标题条 + 时长条；`titleRatio` 按 index 错开宽度防"假"感。用于首页/详情/资料库/搜索的冷启动占位。 |
| `CardSkeleton.qml` | 卡片骨架（几何对齐 `Card`）：方形封面块 + 标题/副标题条。 |
| `Spinner.qml` | 品牌色加载弧（Canvas 3/4 圆 + RotationAnimator），替代 Basic 默认 `BusyIndicator`。用于登录二维码 / 歌曲详情弹窗这类非列表加载。 |

## 约定

- **不引业务模型**：组件不 `import quaverq.core ...`；通过 `property var song` / `property var libraryController` 等显式接收，便于复用。
- **token-only 样式**：色值取自 `ThemeTokens.Palette`，间距取自 `ThemeTokens.Spacing`，字号取自 `ThemeTokens.TypeScale`，动效取自 `ThemeTokens.Motion`。
- **信号优先**：组件不主动跨层调用，把意图通过 `signal activated()` / `signal playRequested()` 抛给父级，父级决定路由 / 起播 / 弹窗。
- **`pragma ComponentBehavior: Bound`** 在含 `delegate` 的复合组件（`Sidebar`）开启，避免动态作用域问题。
