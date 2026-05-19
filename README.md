# QuaverQ 🎵

QQ 音乐桌面客户端，自适应 **Qt** (KDE/LXQt) 和 **GTK** (GNOME/XFCE/Cinnamon/...) 环境。

基于 [QQMusicApi](https://github.com/L-1124/QQMusicApi) 封装，使用 Python 编写，支持 Nuitka 编译为原生二进制。

## ✨ 特性

- 🔍 歌曲 / 歌手 / 专辑 / 歌单搜索
- 🎧 在线播放 (GStreamer 后端)
- 🖥️ 智能检测桌面环境，自动选择 Qt 或 GTK 界面
- 📦 Nuitka 原生编译为二进制，无运行时解压
- ⚙️ TOML 配置文件

## 🚀 快速开始

### 安装依赖

```bash
# 基础依赖 (API)
uv sync

# Qt 后端 (KDE 用户)
uv sync --extra qt

# GTK 后端 (GNOME 用户)
uv sync --extra gtk
```

### 运行

```bash
# 自动检测桌面环境
uv run quaverq

# 强制 Qt
uv run quaverq --ui qt

# 强制 GTK
uv run quaverq --ui gtk
```

### 编译为二进制

```bash
# 安装 Nuitka
uv add --dev nuitka

# standalone 编译 (输出到 dist/)
python build.py

# 单文件编译
python build.py --onefile

# 仅编译 Qt 后端 (减小体积)
python build.py --qt
```

## 📁 项目结构

```
quaverq/
├── src/quaverq/
│   ├── __init__.py          # 包信息
│   ├── __main__.py          # 入口 + Controller
│   ├── config.py            # 配置管理
│   ├── core/
│   │   ├── api.py           # QQMusicApi 封装
│   │   ├── player.py        # 播放器抽象 (GStreamer)
│   │   └── models.py        # 数据模型
│   └── ui/
│       ├── __init__.py      # DE 检测 + 后端选择
│       ├── base.py          # UI 抽象接口
│       ├── qt/app.py        # PySide6 实现
│       └── gtk/app.py       # GTK 4 + Libadwaita 实现
├── build.py                 # Nuitka 编译脚本
└── pyproject.toml
```

## ⚙️ 配置

配置文件位于 `~/.config/quaverq/config.toml`：

```toml
[ui]
backend = "auto"  # auto | qt | gtk

[api]
cookie_file = ""  # QQ 音乐 cookie 文件路径 (可选)

[player]
volume = 0.8
```

## 📄 许可证

GPL-3.0-or-later
