# Lyrics D-Bus 接口 (`org.quaverq.Lyrics1`)

QuaverQ 在会话总线 (`DBUS_SESSION_BUS_ADDRESS`) 暴露一组**只读**接口，把当前歌词、播放进度、当前行/字索引推送给外部消费者。设计目标：让桌面歌词工具、状态栏小部件、用户脚本能拿到逐字 (karaoke / QRC) 级别的实时数据，**无需自己解析 LRC/QRC**。

与 MPRIS 并列，互不干扰；MPRIS 管控播放，本接口管输出歌词。

## 服务标识

| | 值 |
|---|---|
| Bus name | `org.quaverq.Lyrics1` |
| Object path | `/org/quaverq/Lyrics` |
| Interface | `org.quaverq.Lyrics1` |
| Bus type | Session |

`TrackId` 字段和 MPRIS 的 `mpris:trackid` 用同一套生成规则，方便客户端把两个接口的当前歌曲对齐。

## Properties (全部 readonly，emits-change)

| 名 | 签名 | 说明 |
|---|---|---|
| `Mid` | `s` | QQ Music 歌曲 mid；空串表示当前无歌曲 |
| `TrackId` | `o` | 对应 MPRIS trackid 路径 |
| `PositionMs` | `x` | 当前播放位置 (毫秒)；以 QMediaPlayer notify 节奏推送 (~50ms) |
| `ActiveLine` | `i` | 当前行索引；`-1` = 尚未进入第一行 |
| `ActiveWord` | `i` | 当前行内字索引；`-1` = 无逐字数据 / 在行首之前 |
| `HasWordTiming` | `b` | 是否提供逐字 (QRC) timing；`false` 时按整行高亮即可 |
| `HasTranslation` | `b` | 是否带翻译；`true` 时 `GetLyric()` lines 第三字段非空 |
| `LineCount` | `i` | 总行数 |

变更通过标准 `org.freedesktop.DBus.Properties.PropertiesChanged` 推送。

## Methods

### `GetLyric() → (s mid, b has_word_timing, a(xssa(xxs)) lines)`

取当前曲目全量歌词。**切歌时应当通过 `LyricChanged` 信号触发重新调用**，平时缓存到本地不用再要。

返回结构：
- `mid` — 歌曲 mid（与 `Mid` 属性一致）
- `has_word_timing` — 是否含逐字数据
- `lines` — 每行 `(timestamp_ms, text, translation, words)`：
  - `timestamp_ms` (x) — 行起始时间
  - `text` (s) — 整行歌词
  - `translation` (s) — 翻译（无则空串）
  - `words` (a(xxs)) — 每字 `(start_ms, duration_ms, text)`；普通 LRC 行为空数组

### `GetWindow(i before, i after) → (a(xss) window, i active_in_window)`

取当前行附近的窗口，给"瘦客户端"用（不想缓存全量歌词时）。

返回：
- `window` — `[(timestamp_ms, text, translation), ...]`，最多 `before + 1 + after` 行
- `active_in_window` — 当前行在 window 内的相对索引；`-1` = 还在首行之前

## Signals

| 名 | 签名 | 触发时机 |
|---|---|---|
| `LyricChanged` | `s mid` | 切歌、歌词加载完成、登出清空时；客户端收到应调 `GetLyric()` 重取 |
| `LineEntered` | `i line, x ts_ms` | 进入新行时触发一次（行内字切换不触发，看 `ActiveWord` 属性） |

## 逐字精度策略

**不发字级 signal**。`ActiveWord` 属性的 `PropertiesChanged` 在字边界跨越时推一次。如果客户端想要更细（比如帧级动画），自己拿 `PositionMs` + `words[i].start_ms` / `duration_ms` 插值。原因：D-Bus signal 不适合 ~16ms 频率，且消费者自己有 UI 刷新周期。

```python
# 客户端伪代码: 字内进度 (0.0 ~ 1.0)
ws, wd, _ = lines[active_line][3][active_word]
fraction = max(0.0, min(1.0, (position_ms - ws) / max(wd, 1)))
```

## 客户端样例

完整示例见 [`examples/lyrics_consumer.py`](../examples/lyrics_consumer.py)。

### 一行 shell：introspect

```bash
busctl --user introspect org.quaverq.Lyrics1 /org/quaverq/Lyrics
```

### 监听全部变化

```bash
gdbus monitor --session --dest org.quaverq.Lyrics1 --object-path /org/quaverq/Lyrics
```

### 一次性拉当前歌词

```bash
gdbus call --session --dest org.quaverq.Lyrics1 --object-path /org/quaverq/Lyrics \
  --method org.quaverq.Lyrics1.GetLyric
```

### Python 异步订阅 (dbus-next)

```python
from dbus_next.aio import MessageBus
from dbus_next import BusType

bus = await MessageBus(bus_type=BusType.SESSION).connect()
intr = await bus.introspect("org.quaverq.Lyrics1", "/org/quaverq/Lyrics")
proxy = bus.get_proxy_object("org.quaverq.Lyrics1", "/org/quaverq/Lyrics", intr)
lyrics = proxy.get_interface("org.quaverq.Lyrics1")
props = proxy.get_interface("org.freedesktop.DBus.Properties")

mid, has_word, lines = await lyrics.call_get_lyric()
props.on_properties_changed(lambda _i, changed, _inv: print(changed))
lyrics.on_lyric_changed(lambda mid: print("songchange:", mid))
```

## 边界与不保证

- **仅会话总线**：同用户内进程能连，跨用户/系统服务连不上（与 MPRIS 一致）
- **不保证持久**：QuaverQ 退出 / 崩溃即名字释放
- **不提供控制**：要播放控制走 MPRIS (`org.mpris.MediaPlayer2.quaverq`)
- **歌词内容受 QQ Music 服务端返回限制**：部分歌曲只有 LRC、无逐字 (`HasWordTiming=false`)；无歌词时 `LineCount=0`
- **`PositionMs` 不带 Seek 信号**：拖动进度条时连续 `PositionMs` 跳变，客户端别假设单调递增

## 版本

接口 `1` 即首发。后续不兼容变更会改 bus name (`org.quaverq.Lyrics2` …)，不会在 `Lyrics1` 上偷偷改语义。
