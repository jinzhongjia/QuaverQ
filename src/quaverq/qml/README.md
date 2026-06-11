# src/quaverq/qml

Qt Quick UI 根目录。`Main.qml` 是应用主窗口，五个子目录按职责分层组织 QML：tokens → 原子组件 → 抽屉面板 → 弹窗 → 顶层视图。

## Main.qml

主窗口（`ApplicationWindow`）。`pragma ComponentBehavior: Bound`，无边框 + 自绘标题栏 + 圆角阴影 + 拖拽缩放。

- **三栏布局**：左 [`Sidebar`](components/README.md) + 中视图栈 + 底 [`PlayerBar`](components/README.md)。
- **路由切换**：`currentRoute` 在 `home` / `library` / `search` / `detail` / `settings` 之间切，对应加载 [`views/`](views/README.md) 的 QML 文件。
- **正在播放浮层**：`NowPlayingView` **不走路由**——`nowPlayingOpen` 控制的整宽沉浸浮层（盖侧栏 + 内容区，z=5 介于内容与 QueuePanel 之间，顶栏 / 播放栏保持可见），从播放栏上方滑入 / 滑出；`Loader` 首开后常驻（`everOpened` 闩锁，否则收起的滑出动画没有宿主、页内滚动状态也会丢）。`navigate()` / `pushDetail()` 自动收起；Esc 优先级 = 搜索框退焦 → 关 QueuePanel → 收浮层 → `goBack()`；收起时焦点强制还给 `shortcutFocusSink` 防键盘陷阱。
- **状态绑定**：所有 controller 通过 `setContextProperty` 由 Python 注入（`AppController` / `HomeController` / `PlayerController` ...），在窗口顶部当 `readonly property` 转发给视图。
- **主题协调**：把 `settingsController.themeMode`（用户偏好）和 `systemTheme.dark`（freedesktop portal 探测的系统色）绑给 [`Theme/Theme.qml`](Theme/README.md) singleton，决定明暗。
- **关闭到托盘**：`closeToTray` 由 Python 在托盘可用时置 `true`，`onClosing` 拦截后隐藏窗口而非退出。
- **`QtMultimedia`**：嵌入 `MediaPlayer` + `AudioOutput`，由 `PlayerController` 控制。
- **挂载 [`LoginDialog`](dialogs/README.md) + [`LyricPanel`](panels/README.md) + [`QueuePanel`](panels/README.md)** 作为右侧抽屉 / 模态弹窗。

## 子目录

| 目录 | 角色 |
| --- | --- |
| [`Theme/`](Theme/README.md) | **设计 token singleton**：调色板、字号、间距、动效时长/缓动。换肤只动 `Palette.qml`。`qmldir` 在这里声明 singleton 导出。 |
| [`components/`](components/README.md) | **可复用原子组件**：侧栏、播放栏、卡片、歌曲行、队列行、图标按钮、搜索框、喜欢按钮、横幅 / Snackbar、专辑封面。 |
| [`views/`](views/README.md) | **顶层视图（"页面"）**：发现 / 搜索 / 资料库 / 详情 / 设置 / 正在播放。每个视图自包含路由名 + 控制器引用。 |
| [`panels/`](panels/README.md) | **右侧抽屉式面板**：歌词面板、播放队列面板。覆盖在视图之上、由 `Main.qml` 管理开合。 |
| [`dialogs/`](dialogs/README.md) | **模态弹窗**：二维码登录对话框。 |

## 约定

- **导入别名**：`import "../Theme" as ThemeTokens` / `import "../components" as Components`——所有相对路径都用别名导入，避免组件名撞名 `Theme.Theme` 这种重复。
- **token 而非 hex**：组件只绑 `ThemeTokens.Palette.xxx` / `ThemeTokens.Spacing.xxx`，不写裸 `#31C27C` 这种值；换肤只动 `Theme/`。
- **`pragma ComponentBehavior: Bound`** 默认开启，避免动态作用域引发的 binding 陷阱。
- **控制器通过 property 传**：父组件把 `xxxController` 当 `property var` 传给子组件，组件内不直接引用全局 context property，方便单测/复用。
- **`required property`**：列表 `delegate` 内部用 `required property var song` 等强制 model role 绑定，让 ListView 模型变更时不会留下脏值。
