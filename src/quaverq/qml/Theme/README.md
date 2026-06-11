# src/quaverq/qml/Theme

设计 token 的 QML singleton。组件只绑这里的名字，不写裸 hex / 像素值。换肤、改字号、调间距、调动效——只动这一个目录。

`qmldir` 把五个 singleton 注册成 `import "../Theme" as ThemeTokens` 后的 `ThemeTokens.Theme` / `ThemeTokens.Palette` 等。

| 文件 | 角色 |
| --- | --- |
| `Theme.qml` | **主题入口**。`mode` ∈ `system` / `light` / `dark`，由 `SettingsController.themeMode` 经 [`Main.qml`](../README.md) `Binding` 注入；`systemDark` 默认走 Qt `styleHints.colorScheme` + `SystemPalette` 推断，运行时由 `Main` 用 freedesktop portal `color-scheme` 覆盖。`dark` = `mode === dark \|\| (mode === system && systemDark)`，其他三个 singleton 读它判明暗。 |
| `Palette.qml` | **调色板**。QQ 音乐 PC 风格：品牌绿 `#31C27C`，亮色白底 + 浅灰侧栏 + `#333` / `#999` 文本；深色为同品牌绿 + 中性深灰层级。背景层、文本层、状态层（hover / pressed / focus）、强调色、错误色、轮廓色都按 token 命名，组件只绑名字。封面图上的遮罩组（`imageOverlay` / `imageOverlayHover` / `imageOverlayText` / `softShadow`）**不带 Theme.dark 分支**——图片颜色不随主题变；`primaryContainerHi` 配 `primaryContainer` 做猜你喜欢卡的同色系微渐变。 |
| `TypeScale.qml` | **字号字重**。`display` 32 / `h1` 23 / `h2` 19 / `body` 16 / `bodySm` 14 / `caption` 12（与 bodySm 拉开 2px 字阶）；权重 `regular` / `medium` / `bold` 给字体回退安全名。 |
| `Spacing.qml` | **间距与窗口尺寸**。`s2..s8` 间距阶（4 / 8 / 12 / 16 / 24 / 32 / 48），圆角 `radiusSm..radiusPill`，`windowWidth/Height`、`minWindowWidth/Height`、`headerHeight`、`playerBarHeight`、`toolHitSize` (44 px ≥ 触摸目标) 等结构常量。 |
| `Motion.qml` | **动效**。时长三档 `durFast` 120 / `durMed` 220 / `durSlow` 320 + 缓动三种；`reduceMotion` 总开关（设置项注入）开启后时长归零（过渡瞬时而非放慢），持续性运动（Marquee / 骨架脉动）由消费方绑定停用，Spinner 加载旋转刻意保留。 |
| `qmldir` | singleton 注册：`singleton Theme 1.0 Theme.qml` 等五行。 |

## 约定

- **不写裸值**：组件层禁止 `color: "#ff0000"` / `font.pixelSize: 16`，全部经 `ThemeTokens.Palette.error` / `ThemeTokens.TypeScale.body`。
- **token 名稳定**：`Palette` 的 token 名是与组件层的契约，换肤改值不改名；新增 token 优先复用现有语义层（`surface*` / `outline*` / `state*`）。
- **`pragma Singleton`**：每个 `.qml` 文件顶部都有，配合 `qmldir` 的 `singleton` 关键字注册。导入端用 `import "../Theme" as ThemeTokens` 加 `as` 别名，避免与某些组件类名相撞。
