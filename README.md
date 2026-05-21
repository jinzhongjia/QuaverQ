# QuaverQ 🎵

QQ 音乐桌面客户端 — **GTK 4 + Libadwaita** (GNOME/XFCE/Cinnamon/KDE 均可)。

基于 [QQMusicApi](https://github.com/L-1124/QQMusicApi) 封装，使用 Python 编写，支持 Nuitka 编译为原生二进制。

## ✨ 特性

- 🔍 歌曲 / 歌手 / 专辑 / 歌单搜索
- 🎧 在线播放 (GStreamer 后端)
- 🖥️ GTK 4 + Libadwaita 现代界面
- 📦 Nuitka 原生编译为二进制，无运行时解压
- ⚙️ TOML 配置文件

## 🚀 快速开始

### 安装依赖

```bash
uv sync
```

需要系统装好 GTK 4 / libadwaita / PyGObject 运行时 (各发行版包名不同, 如 Arch: `gtk4 libadwaita python-gobject`).

### 运行

```bash
uv run quaverq
```

### 编译为二进制

```bash
# 安装 Nuitka
uv add --dev nuitka

# standalone 编译 (输出到 dist/)
python build.py

# 单文件编译
python build.py --onefile
```

## 📁 项目结构

```
quaverq/
├── src/quaverq/
│   ├── __init__.py          # 包信息
│   ├── __main__.py          # 入口 + Controller
│   ├── config.py            # 配置管理
│   ├── core/
│   │   ├── service.py       # QQMusicApi 封装
│   │   ├── player.py        # 播放器抽象 (GStreamer)
│   │   └── models.py        # 数据模型
│   └── ui/
│       ├── __init__.py      # GTK 后端入口
│       ├── base.py          # UI 抽象接口
│       └── gtk/app.py       # GTK 4 + Libadwaita 实现
├── build.py                 # Nuitka 编译脚本
└── pyproject.toml
```

## ⚙️ 配置

配置文件位于 `~/.config/quaverq/config.toml`：

```toml
[api]
cookie_file = ""  # QQ 音乐 cookie 文件路径 (可选)

[player]
volume = 0.8
quality = "balanced"  # high | balanced | standard
```

## 📄 许可证

GPL-3.0-or-later
