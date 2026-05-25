# QuaverQ

QQ 音乐桌面客户端 — **PySide6 + Qt Quick (QML)**，**Linux 优先（Windows / macOS 后续支持，见 [design §1.3](docs/design.md)）**。

后端基于 [qqmusic-api-python](https://github.com/luren-dc/qqmusic-api-python) 0.6 系列封装，前端用 Qt Quick 写，**明暗双主题（默认跟随系统）**，整体风格参考主流流媒体音乐应用的三栏布局。

## 状态

- **后端核心已完成**：搜索 / 详情 / 推荐 / 排行榜 / 喜欢同步 / 歌词 / 播放队列 / MPRIS / 会话快照 / 封面磁盘缓存 / SQLite TTL cache（`uv run pytest` 全绿）
- **UI 待重建**：旧实现已清理；PySide6 + Qt Quick 方案分期 Q0–Q11 落地，见 [`docs/design.md`](docs/design.md) §14
- 目前 `uv run quaverq` 入口尚未接 PySide6 启动（Q0 计划项），仅 core 层可用、测试可跑

## 环境

- Linux（Arch / Fedora / Ubuntu 22.04+ 均测）
- Python ≥ 3.10
- Qt 6.6+、PySide6 6.6+
- 系统包：Qt Quick / QtMultimedia / GStreamer codecs（QtMultimedia 在 Linux 走 GStreamer 后端）

```bash
uv sync
uv run pytest        # core 层测试
# uv run quaverq     # Q0 落地后再可用
```

## 配置

`~/.config/quaverq/config.toml`

```toml
[player]
quality = "balanced"   # high | balanced | standard
```

凭据 / 会话快照 / SQLite cache 也都放在 `~/.config/quaverq/`，封面缓存在 `~/.cache/quaverq/covers/`。

## 设计与路线

见 [`docs/design.md`](docs/design.md)。

## 许可证

GPL-3.0-or-later
