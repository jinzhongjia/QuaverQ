# src/quaverq/qml/icons

单色 SVG 图标集。替代 Unicode 字形图标（字形会落到不同回退字体，视觉大小/单色性完全不可控，
`⚙` 在部分系统甚至渲染成彩色 emoji）。

## 约定

- **画布 24×24**，描边风格 `stroke-width=1.8`、圆头圆角（`round` cap/join）；实心元素（播放三角、音符头、点）用 `fill`。
- **统一画成白色** `#ffffff`：运行时由 [`components/AppIcon.qml`](../components/README.md) 经 `MultiEffect.colorization`
  按 token 色染色——选中绿（`Palette.primaryFg`）/ 常规灰（`surfaceVariantText`）/ 禁用（`stateDisabled`）、
  亮暗主题全部一份资产通吃。**不要**为颜色状态复制 SVG 变体。
- 命名小写连字符（`skip-back.svg`），语义命名不绑业务（`queue` 而非 `playlist-panel`）。

## 清单

| 文件 | 用途 |
| --- | --- |
| `home.svg` / `search.svg` / `library.svg` / `settings.svg` | 侧栏导航（`NavItem.iconSource`） |
| `play.svg` / `pause.svg` | 播放/暂停（播放栏主键、猜你喜欢卡、Card 悬停、播放全部） |
| `skip-back.svg` / `skip-forward.svg` | 上一首 / 下一首 |
| `sequence.svg` / `repeat.svg` / `repeat-one.svg` / `shuffle.svg` | 播放模式四态 |
| `heart.svg` / `heart-filled.svg` | 喜欢（描边 = 未喜欢，实心 = 已喜欢 / 侧栏「我喜欢」） |
| `queue.svg` | 待播列表 |
| `download.svg` | 下载（播放栏 / 正在播放页「下载当前歌曲」） |
| `volume.svg` | 音量 |
| `volume-mute.svg` | 静音（扬声器 + 叉，播放栏静音切换态） |
| `more-horizontal.svg` | 更多操作（歌曲行 ⋯ / 播放栏窄窗溢出） |
| `arrow-left.svg` | 顶栏返回 |
| `chevron-down.svg` | 正在播放页「收起」 |
| `user.svg` | 侧栏身份区未登录占位头像（人形剪影） |

## 使用

```qml
import "../components" as Components

Components.AppIcon {
    size: 18
    source: "../icons/queue.svg"
    color: ThemeTokens.Palette.surfaceVariantText
}
```

按钮场景直接走 `IconButton.iconSource` / `NavItem.iconSource`（内部已接 AppIcon）。

### ⚠️ 相对路径解析陷阱（实测踩过）

字符串相对路径经 `url` 属性链传递时**不会**在书写处解析——它一路保持相对，直到
`AppIcon` 内部的 `Image` 才按 **AppIcon 所在目录（`components/`）** 解析。因此：

- `components/` 与 `views/` 下统一写 `"../icons/<name>.svg"`（两个目录与 `icons/` 同层，
  无论按书写处还是按 AppIcon 解析结果一致，二义皆安全）；
- **qml 根目录（`Main.qml`）必须用 `Qt.resolvedUrl("icons/<name>.svg")`** 立即解析成绝对
  URL——裸写 `"icons/..."` 会被解析成 `components/icons/` 而静默加载失败（图标隐形）。
仍保留字形的位置：`词`（CJK 字符渲染稳定且为 QQ 正统）、`×` 关闭、列表行 `♪` 状态标记、
`AlbumArt` 占位符、设置页 `⌄/⌃` 下拉指示。

## 打包

随 `--include-package-data=quaverq` 进 Nuitka bundle；着色依赖 `QtQuick.Effects`（在
`packaging.py` 的保留名单内）、SVG 解码依赖 `imageformats/qsvg`（`sensible` 插件集自带）。
