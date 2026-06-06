# QuaverQ

QQ 音乐桌面客户端 — **PySide6 + Qt Quick (QML)**，**Linux 优先**（Windows / macOS 后续）。

后端封装 [qqmusic-api-python](https://github.com/luren-dc/qqmusic-api-python) 0.6 系列，前端 Qt Quick 自绘，**视觉对齐 QQ 音乐 PC**（三栏：侧栏导航 + 主内容 + 底部播放栏，品牌绿 `#31C27C`），**明暗双主题，默认跟随系统**。

## 功能

- **首页发现** — 猜你喜欢（每日推荐）+ 今日推荐歌单 + 新歌速递 + 排行榜；**SWR 首屏缓存**：冷启动先显示上次内容（封面秒出），网络在后台静默刷新。
- **搜索** — 歌曲（分页）+ 歌手 / 专辑 / 歌单分栏，结果可跳对应详情。
- **资料库** — 我喜欢、我的歌单、收藏专辑、关注艺人。
- **详情页** — 歌单 / 专辑 / 艺人 / 排行榜真实详情，曲目列表 + 播放全部。
- **播放** — QtMultimedia（Qt6 FFmpeg 后端）；队列 + 顺序 / 单曲循环 / 列表循环 / 随机；进度、音量；取链偶发 401 自动重取新 vkey 重试。
- **现在播放页** — 封面 + 大面积**同步歌词**，支持**卡拉OK 逐字高亮**（QRC，按字着色）；无逐字的歌自动回退逐行。
- **登录** — 二维码扫码；凭据缓存 + 启动乐观登录（首帧即登录态）+ 过期自动重登。
- **音质** — `standard` / `balanced` / `high` 偏好，实际输出 MP3_128 / OGG_192 / MP3_320 / FLAC。
- **桌面集成** — MPRIS2 媒体键 + GNOME / KDE 媒体控件；**系统托盘 + 关闭到托盘**（点关闭仅隐藏，托盘「退出」才真正退出）。
- **会话恢复** — 重启恢复上次队列 / 进度 / 播放模式 / 音量。
- **设置** — 跟随系统 / 浅色 / 深色、音质偏好、封面缓存上限（LRU，默认 256 MB）与清理。

后端核心（搜索 / 详情 / 推荐 / 排行榜 / 喜欢同步 / 歌词 / 队列 / MPRIS / 会话快照 / 封面缓存）均有单元测试覆盖，`uv run pytest` 全绿。

## 技术栈

| 层 | 选型 |
|---|---|
| UI | Qt Quick / QML（Controls **Basic** + 自定义 Theme token） |
| Python 绑定 | PySide6 ≥ 6.6 |
| 音频 | `QtMultimedia.MediaPlayer`（Qt6 Linux 默认 FFmpeg 后端） |
| 异步 | `qasync`（asyncio ↔ Qt 事件循环） |
| API | qqmusic-api 0.6.1 + 自实现 vkey 取链、**随机 safe `ct` 反风控**、QRC 逐字解密 |
| 拉流 | 本机回环代理（curl_cffi 官方 TLS 指纹出网，规避 CDN 风控） |
| 媒体键 | `dbus-next` MPRIS2，挂在 Qt 主事件循环 |

## 运行

```bash
uv sync --dev
uv run pytest        # core + bridge 测试
uv run quaverq       # 启动应用
```

环境要求：Linux、Python ≥ 3.10、Qt 6.6+（PySide6 wheel 自带 Qt 与 QtMultimedia）。系统需有桌面基础库（libEGL / libGL / libxkbcommon / libxcb-\* / dbus）；播放取链需先扫码登录 QQ 音乐。

## 打包（AppImage）

```bash
uv run python build.py --appimage          # Nuitka standalone + linuxdeploy -> dist/QuaverQ-x86_64.AppImage
uv run python -m quaverq.packaging --smoke dist/quaverq.dist/QuaverQ   # 产物自检
```

打 `v*` tag 触发 GitHub Actions 构建并发布 AppImage（见 `.github/workflows/release.yml`）。

## 配置与数据

- `~/.config/quaverq/`：`config.toml`（音质等）、`credential.json`（登录凭据）、`state.json`（会话快照）、`device_id`。
- `~/.cache/quaverq/`：`covers/`（封面磁盘缓存，LRU）、`home.json`（首屏 SWR 快照）。

```toml
# ~/.config/quaverq/config.toml
[player]
quality = "balanced"   # high | balanced | standard
```

## 许可证

GPL-3.0-or-later
