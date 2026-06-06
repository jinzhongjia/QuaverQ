# QuaverQ

一款对齐 **QQ 音乐 PC 端**视觉与体验的桌面客户端，**Linux 优先**（Windows / macOS 后续）。
三栏布局（侧栏导航 + 主内容 + 底部播放栏），品牌绿 `#31C27C`，明暗双主题、默认跟随系统。

## 功能

### 浏览与发现

- **首页发现** — 每日推荐、今日推荐歌单、新歌速递、排行榜一屏到位；冷启动**秒开**，上次内容即刻显示，网络在后台静默刷新。
- **搜索** — 歌曲（分页）、歌手、专辑、歌单四个分栏，结果可一键跳详情。
- **资料库** — 我喜欢、我的歌单、收藏专辑、关注艺人,登录后自动同步。
- **详情页** — 歌单 / 专辑 / 艺人 / 排行榜均可深入查看,曲目列表 + 一键「播放全部」。
- **侧栏「我的歌单」** — 自动列出账号下歌单,点击即进详情。

### 播放体验

- **完整播放队列** — 顺序 / 单曲循环 / 列表循环 / 随机四种模式自由切换。
- **音质选择** — 标准 / 均衡 / 高品质,自动匹配到 MP3 128 / OGG 192 / MP3 320 / FLAC。
- **专属播放栏** — 进度、音量、上下首、喜欢一键操作。
- **正在播放页** — 超大封面 + 沉浸式同步歌词,版权信息行自动淡化。
- **逐字卡拉 OK 高亮** — 按字着色,歌词跟唱;无逐字数据时自动回退逐行。
- **重启即续播** — 上次队列、进度、模式、音量全部恢复,关闭→重开无缝衔接。

### 桌面集成

- **无边框窗口** — 自绘标题栏,可拖拽、缩放、最大化,圆角与阴影一致。
- **系统托盘** — 关闭窗口默认隐藏到托盘,托盘菜单可直接「显示 / 播放暂停 / 上下首 / 退出」。
- **MPRIS2** — 媒体键、GNOME 媒体控件、KDE 通知面板原生支持。
- **二维码登录** — 扫码即登;启动同步加载凭据,首帧已是登录态;凭据过期自动提示重登。
- **跟随系统主题** — 浅色 / 深色随桌面切换,也可手动锁定。

### 设置与缓存

- 主题:跟随系统 / 浅色 / 深色。
- 音质偏好:标准 / 均衡 / 高品质。
- 封面缓存上限:128 MB / 256 MB / 512 MB / 1 GB / 2 GB / 无限制,**一键清理**。

测试覆盖核心模块(搜索、详情、推荐、排行榜、喜欢同步、歌词、队列、MPRIS、会话快照、封面缓存),`uv run pytest` 全绿。

## 运行

```bash
uv sync --dev
uv run pytest                          # 单元测试
uv run python scripts/lint.py          # 跑 lint (ruff + pyside6-qmllint)
uv run python scripts/lint.py --fix    # ruff 自动修复 + 格式化
uv run quaverq                         # 启动应用
```

环境要求:Linux、Python ≥ 3.10、桌面基础库(libEGL / libGL / libxkbcommon / libxcb-* / dbus)。播放需先扫码登录 QQ 音乐。

## 打包(AppImage)

```bash
uv run python build.py --appimage          # -> dist/QuaverQ-x86_64.AppImage
uv run python -m quaverq.packaging --smoke dist/quaverq.dist/QuaverQ
```

打 `v*` tag 触发 GitHub Actions 自动构建并发布 AppImage(见 `.github/workflows/release.yml`)。

## 配置与数据

- `~/.config/quaverq/`:`config.toml`、登录凭据、会话快照、设备 ID。
- `~/.cache/quaverq/`:封面磁盘缓存、首屏快照。

```toml
# ~/.config/quaverq/config.toml
[player]
quality = "balanced"   # high | balanced | standard
```

## 技术栈

PySide6 + Qt Quick (QML) · QtMultimedia · qqmusic-api-python · qasync · dbus-next

## 许可证

GPL-3.0-or-later
