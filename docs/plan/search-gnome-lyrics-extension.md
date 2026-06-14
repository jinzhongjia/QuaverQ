# GNOME Shell 歌词扩展规划

## 任务描述

为 QuaverQ 编写一个 GNOME Shell 扩展，消费 `org.quaverq.Lyrics1` D-Bus 接口，在桌面上实时展示歌词。两种展示模式：

1. **OSD 悬浮歌词** — 屏幕底部半透明浮层，逐字高亮 + 翻译
2. **顶栏歌词** — GNOME 顶部面板注入歌词文本，点击展开上下文

## 技术约束

- **仅 GNOME 50**（`shell-version: ["50"]`），Wayland only（X11 已在 50 中移除）
- ESM 模块格式（`import`/`export`），`export default class extends Extension`
- 可用 GNOME 50 全部新 API：`easeAsync()`、`GLib.timeout_add_once()`、`getLogger()`、`-st-accent-color` CSS 变量、async `fillPreferencesWindow`
- 扩展运行在 gnome-shell 进程内；`disable()` 必须撤销 `enable()` 的一切（锁屏触发 `disable()`）
- `prefs.js` 运行在独立 GTK4 + Adw 进程，不能 import St / Clutter / Main

## D-Bus 接口

```
Bus Name:    org.quaverq.Lyrics1
Object Path: /org/quaverq/Lyrics
Interface:   org.quaverq.Lyrics1

Properties (readonly):
  s Mid, o TrackId, x PositionMs,
  i ActiveLine (-1=未开始), i ActiveWord (-1=无逐字),
  b HasWordTiming, b HasTranslation, i LineCount

Methods:
  GetLyric() → (s mid, b has_word_timing, a(xssa(xxs)) lines)
  GetWindow(i before, i after) → (a(xss) window, i active_in_window)

Signals:
  LyricChanged(s mid)         // 切歌
  LineEntered(i line, x ts_ms) // 进入新行
```

## 目录结构

```
gnome-extension/
├── quaverq-lyrics@quaverq/
│   ├── metadata.json
│   ├── extension.js          # 入口
│   ├── dbusClient.js         # D-Bus 代理 + 服务监听
│   ├── osdOverlay.js         # OSD 悬浮歌词
│   ├── panelIndicator.js     # 顶栏指示器
│   ├── prefs.js              # 偏好设置
│   ├── stylesheet.css
│   └── schemas/
│       └── org.gnome.shell.extensions.quaverq-lyrics.gschema.xml
├── install.sh
└── README.md
```

## 实施步骤

### Step 1: 骨架 + D-Bus 客户端

**文件**: `metadata.json`, `extension.js`, `dbusClient.js`, `stylesheet.css`(空), `schemas/*.gschema.xml`

#### metadata.json

```json
{
    "uuid": "quaverq-lyrics@quaverq",
    "name": "QuaverQ Lyrics",
    "description": "Display lyrics from QuaverQ music player on GNOME desktop.\nOSD overlay and top bar modes.",
    "shell-version": ["50"],
    "url": "https://github.com/jinzhongjia/quaverq",
    "settings-schema": "org.gnome.shell.extensions.quaverq-lyrics"
}
```

#### dbusClient.js

```javascript
import Gio from 'gi://Gio';

const BUS_NAME = 'org.quaverq.Lyrics1';
const OBJECT_PATH = '/org/quaverq/Lyrics';

const LYRICS_IFACE_XML = `<node>
  <interface name="org.quaverq.Lyrics1">
    <method name="GetLyric">
      <arg type="s" direction="out" name="mid"/>
      <arg type="b" direction="out" name="has_word_timing"/>
      <arg type="a(xssa(xxs))" direction="out" name="lines"/>
    </method>
    <method name="GetWindow">
      <arg type="i" direction="in" name="before"/>
      <arg type="i" direction="in" name="after"/>
      <arg type="a(xss)" direction="out" name="window"/>
      <arg type="i" direction="out" name="active_in_window"/>
    </method>
    <property name="Mid" type="s" access="read"/>
    <property name="TrackId" type="o" access="read"/>
    <property name="PositionMs" type="x" access="read"/>
    <property name="ActiveLine" type="i" access="read"/>
    <property name="ActiveWord" type="i" access="read"/>
    <property name="HasWordTiming" type="b" access="read"/>
    <property name="HasTranslation" type="b" access="read"/>
    <property name="LineCount" type="i" access="read"/>
    <signal name="LyricChanged"><arg name="mid" type="s"/></signal>
    <signal name="LineEntered"><arg name="line" type="i"/><arg name="ts_ms" type="x"/></signal>
  </interface>
</node>`;

const LyricsProxy = Gio.DBusProxy.makeProxyWrapper(LYRICS_IFACE_XML);
```

核心机制：

1. **`Gio.bus_watch_name(SESSION)`** 监听服务上下线
   - appeared → 异步创建 `LyricsProxy` → `connectSignal('LyricChanged')` + `connect('g-properties-changed')` → `GetLyricAsync()` 拉全量
   - vanished → 清理代理 → 回调 `onDisconnected()`
2. **属性变更** 只关注 `ActiveLine` / `ActiveWord` → 回调 `onActiveChanged(line, word)`
3. **`LyricChanged` 信号** → 重新 `GetLyricAsync()` 缓存 → 回调 `onLyricLoaded()`
4. D-Bus interface 信号用 `proxy.connectSignal()`（非 GObject `connect()`）
5. `destroy()` 中 `Gio.bus_unwatch_name()` + `proxy.disconnectSignal()` + `proxy.disconnectObject()`

#### extension.js

```javascript
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {LyricsDBusClient} from './dbusClient.js';

export default class QuaverQLyricsExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._log = this.getLogger();
        this._client = new LyricsDBusClient({
            onLyricLoaded: (...args) => this._onLyric(...args),
            onActiveChanged: (line, word) => this._onActive(line, word),
            onDisconnected: () => this._onDisconnected(),
        });
        this._client.start();
        // Step 2/3: 根据 display-mode 创建 OSD / Panel
    }

    disable() {
        this._client?.destroy();
        this._client = null;
        this._settings?.disconnectObject(this);
        this._settings = null;
        // Step 2/3: 销毁 OSD / Panel
    }
}
```

#### 验证清单

- [ ] `glib-compile-schemas schemas/` 成功
- [ ] 符号链接到 `~/.local/share/gnome-shell/extensions/`
- [ ] `gnome-extensions enable quaverq-lyrics@quaverq`
- [ ] `journalctl -f -o cat /usr/bin/gnome-shell` 无报错
- [ ] QuaverQ 启动/退出触发 connect/disconnect 日志

---

### Step 2: OSD 悬浮歌词

**文件**: `osdOverlay.js`, `stylesheet.css`

#### 层级

```javascript
Main.layoutManager.addTopChrome(this._overlay, {
    affectsInputRegion: false, // 鼠标穿透
});
// disable 中:
Main.layoutManager.removeChrome(this._overlay);
this._overlay.destroy();
```

#### 组件

```
LyricOverlay (St.BoxLayout, orientation: VERTICAL, reactive: false)
├── _mainLine (St.Label)         ← 逐字 Pango markup
├── _translationLine (St.Label)  ← 翻译 (可隐藏)
└── _nextLine (St.Label)         ← 下一行预览
```

#### 定位

- 主显示器底部居中，距底 `osd-bottom-margin` px
- 监听 `Main.layoutManager` 的 `monitors-changed` 重定位
- 文本变化后重算 x 居中

#### 逐字高亮

`HasWordTiming=true` 时用 Pango markup：
- 已唱字: `#ffffff`
- 当前字: `#31c27c`（品牌色）
- 未唱字: `rgba(255,255,255,0.4)`

```javascript
this._mainLine.clutter_text.set_markup(markup);
```

无逐字 timing 时整行白色。

#### 动画

GNOME 50 直接用 `easeAsync()`：

```javascript
await this._mainLine.easeAsync({
    opacity: 255, duration: 150,
    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
});
```

#### stylesheet.css

```css
.quaverq-osd {
    background-color: rgba(0, 0, 0, 0.70);
    border-radius: 12px;
    padding: 16px 32px;
}
.quaverq-osd-main {
    color: white;
    font-size: 22px;
    font-weight: 500;
    text-align: center;
}
.quaverq-osd-translation {
    color: rgba(255, 255, 255, 0.65);
    font-size: 16px;
    text-align: center;
    margin-top: 4px;
}
.quaverq-osd-next {
    color: rgba(255, 255, 255, 0.35);
    font-size: 16px;
    text-align: center;
    margin-top: 8px;
}
```

#### 验证清单

- [ ] OSD 出现在屏幕底部居中
- [ ] 逐字高亮颜色正确
- [ ] 翻译行跟随 HasTranslation 显隐
- [ ] 鼠标穿透可点下层窗口
- [ ] 切歌有淡入淡出
- [ ] QuaverQ 退出后 OSD 隐藏

---

### Step 3: 顶栏歌词指示器

**文件**: `panelIndicator.js`, `stylesheet.css` 追加

#### 设计

- `PanelMenu.Button` 放顶栏 `'center'`
- 正常态: `♪ 歌词文本` (ellipsize)
- 点击: `PopupMenu` 展开 7 行上下文 (`GetWindowRemote(3, 3)`)
- 无歌词: `visible: false`

#### 组件

```
LyricPanelIndicator (PanelMenu.Button)
├── _box (St.BoxLayout)
│   ├── _icon (St.Label '♪')
│   └── _label (St.Label, ellipsize)
└── menu (PopupMenu)
    └── PopupMenuItem × N (当前行加粗)
```

顶栏只跟踪 `ActiveLine`，不做逐字。菜单打开时拉 `GetWindow`。

#### stylesheet.css

```css
.quaverq-panel-icon {
    color: #31c27c;
    font-size: 14px;
    margin-right: 4px;
}
.quaverq-panel-label {
    max-width: 300px;
    font-size: 13px;
}
.quaverq-menu-active {
    font-weight: bold;
}
```

#### 验证清单

- [ ] 顶栏中央出现歌词
- [ ] ellipsize 截断正确
- [ ] popup 显示上下文，当前行加粗
- [ ] 无歌曲时隐藏
- [ ] 不影响其他扩展

---

### Step 4: GSettings + 偏好设置

**文件**: `schemas/*.gschema.xml`, `prefs.js`

#### Schema

```xml
<?xml version="1.0" encoding="UTF-8"?>
<schemalist>
  <schema id="org.gnome.shell.extensions.quaverq-lyrics"
          path="/org/gnome/shell/extensions/quaverq-lyrics/">
    <key name="display-mode" type="s">
      <default>'both'</default>
    </key>
    <key name="osd-font-size" type="i">
      <default>22</default>
    </key>
    <key name="osd-bottom-margin" type="i">
      <default>80</default>
    </key>
    <key name="osd-opacity" type="d">
      <default>0.70</default>
    </key>
    <key name="show-translation" type="b">
      <default>true</default>
    </key>
    <key name="show-next-line" type="b">
      <default>true</default>
    </key>
    <key name="panel-max-width" type="i">
      <default>300</default>
    </key>
    <key name="panel-position" type="s">
      <default>'center'</default>
    </key>
  </schema>
</schemalist>
```

#### prefs.js (GNOME 50: async fillPreferencesWindow)

```javascript
import Gio from 'gi://Gio';
import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';
import {ExtensionPreferences, gettext as _}
    from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class QuaverQLyricsPreferences extends ExtensionPreferences {
    async fillPreferencesWindow(window) {
        const settings = this.getSettings();
        window._settings = settings;

        const page = new Adw.PreferencesPage({ title: _('General') });

        // 显示模式 ComboRow
        // OSD 设置: SpinRow(字号/边距), Scale(透明度), SwitchRow(翻译/下一行)
        // 顶栏设置: SpinRow(最大宽度), ComboRow(位置)

        window.add(page);
    }
}
```

#### extension.js settings 响应

```javascript
this._settings.connectObject(
    'changed::display-mode', () => this._rebuildDisplays(),
    'changed::osd-font-size', () => this._osd?.updateStyle(),
    'changed::osd-bottom-margin', () => this._osd?.reposition(),
    'changed::osd-opacity', () => this._osd?.updateStyle(),
    'changed::show-translation', () => this._osd?.updateVisibility(),
    'changed::show-next-line', () => this._osd?.updateVisibility(),
    'changed::panel-max-width', () => this._panel?.updateStyle(),
    'changed::panel-position', () => this._rebuildPanel(),
    this,
);
```

---

### Step 5: 安装脚本 + 文档

```bash
#!/bin/bash
set -e
SRCDIR="$(cd "$(dirname "$0")/quaverq-lyrics@quaverq" && pwd)"
EXTDIR="$HOME/.local/share/gnome-shell/extensions/quaverq-lyrics@quaverq"
glib-compile-schemas "$SRCDIR/schemas/"
[ -e "$EXTDIR" ] && rm -rf "$EXTDIR"
ln -s "$SRCDIR" "$EXTDIR"
echo "已安装。重新登录后执行: gnome-extensions enable quaverq-lyrics@quaverq"
```

Wayland 下需重新登录生效（GNOME 50 无 X11 热重载）。

## 设计决策

| 决策 | 理由 |
|------|------|
| OSD 用 `GetLyric()` 缓存全量 | `GetWindow()` 不含 words 数组，逐字高亮需要 |
| 顶栏只做行级更新 | 空间窄，逐字高亮噪音大 |
| 两种模式共享一个 `dbusClient` | 不重复 D-Bus 代理 |
| 动画用 `easeAsync()` | GNOME 50 原生支持，Promise 比 onComplete 清晰 |
| 日志用 `getLogger()` | GNOME 48+ 原生，自动带扩展名前缀 |
| `fillPreferencesWindow` 用 async | GNOME 50 原生支持 |
