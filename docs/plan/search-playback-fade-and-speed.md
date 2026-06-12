# 规划：歌曲切换淡入淡出 + 切歌加载提速（issue #11）

> 2026-06-12 规划完成；**同日 Stage A1 / A2 / B / C1 / C2 全部实施完毕**（pytest 730 绿 + lint 过），待用户真机手测验收（清单见各 Stage）。对应 issue：[#11 Feature: 增加歌曲切换淡入淡出设置](https://github.com/jinzhongjia/QuaverQ/issues/11)。
>
> 实施期实测补记：① 批量 vkey 真机验证通过（高/均衡/标准三档单请求均可播，GET 206）；② 共享 `curl_cffi Session` 经代理拉流 + Range seek 真机验证通过；③ curl_cffi 0.15.0 `Session` 文档声明线程安全（默认 thread-local curl handle），直接共享单例，无需 thread-local 包装；④ 切歌淡出窗口内需冻结 `updatePosition` 回传（UI 已显示新歌，旧歌 position 会把进度条拽回去）——规划时未预见，实现为 `_suppress_position_updates` 标志。

## 任务描述

issue #11 实际包含两个诉求：

1. **淡入淡出设置**（标题）：切歌时音量渐弱→渐起，而不是硬切 + 静音空白；
2. **切歌加载速度**（正文「目前歌曲播放速度太慢了」）：缩短点歌 / 切歌到出声的延迟。

两者相关联：加载延迟是淡入淡出要"掩盖"的对象，淡入淡出是延迟无法归零部分的体验兜底。本规划把两件事一起做。

## 调研结果：切歌延迟的构成（现状链路）

切歌完整链路（`player_controller.py` `_load_current` → `service.py` `get_song_url` → QML `MediaPlayer`）：

| 步骤 | 代码位置 | 延迟构成 |
| --- | --- | --- |
| 1. 清空 `sourceUrl` 停掉当前播放 | `player_controller.py:530` | **静音空白从这里开始**，且是硬切（无淡出） |
| 2. 取 vkey URL：按音质档**串行降级**，每档一个 `musicu.fcg` POST | `service.py:801` `get_song_url` → `_try_bypass_url` | balanced 档最多 3 次串行往返（MP3_320 → OGG_192 → MP3_128）；每次 `creq.post` 都是一次性会话 = 完整 TCP + TLS 握手 + RTT，单档超时 4s |
| 3. 设 `sourceUrl` → FFmpeg 经 StreamProxy 拉流 | `stream_proxy.py:154` `_handle` | 每个代理请求 `creq.get` 新建会话 = 又一次到 CDN 的 TCP + TLS 握手；之后 FFmpeg 还要 probe 格式 + 填解码缓冲 |
| 4. 自然播完（EndOfMedia）切歌 | `Main.qml` `onMediaStatusChanged` → `handleEndOfMedia` | 走完整 2 + 3 全链路 → **歌间空白可达秒级** |

另有两个顺手可修的浪费：

- **REPEAT_ONE 单曲循环**：EOS 走 `on_song_end()` 返回当前曲后照样进 `_load_current` 重新取链，其实 `sourceUrl` 没变，seek(0) + play 即可。
- **下一首完全冷启动**：播放当前曲的整个时长里系统空闲，没有任何对下一首的预取。

### 关键约束：vkey 会话绑定（不能做的事）

项目已实锤（见单实例守卫的由来）：**同一 cookie 并发拉两路流会让前一份链路立即 401 失效**。这直接否决了"双 `MediaPlayer` A/B deck 真重叠 crossfade"方案——重叠期两路 CDN 流并发，必踩同款 401。QQ 官方 PC 端的"淡入淡出"听感上也是 fade-out → fade-in 衔接而非真重叠，单播放器方案对齐官方即可。

注意区分：**预取下一首的 URL**（一次 `musicu.fcg` POST，不开流）与"并发拉流"不是一回事，理论上安全，但列入实验验证项（见文末）。

## 方案

按性价比排序，P1–P3 解决"快"，P4 解决"淡入淡出"，P5 顺手修：

### P1 — vkey 批量取链：多档合一（串行降级 → 单请求）

`UrlGetVkey` 的 `filename` / `songmid` / `songtype` 参数本就是数组。把偏好档的全部 filename 一次性塞进**同一个**请求（`songmid` / `songtype` 重复对齐长度），响应 `midurlinfo` 按序对应，从中取第一个 `purl` 非空的档。

- 效果：最多 3 次串行往返 → 恒定 1 次往返。
- 改造点：`service.py` `_try_bypass_url` 泛化为 `_try_bypass_urls(mid, labels) -> dict[label, (url | None, result_code | None)]`；`get_song_url` 改成单次调用 + 本地按 `_QUALITY_PROFILES` 顺序挑选。命中 / 全档失败的日志语义保持不变。
- 前置实验：用调试脚本（`load_cached_credential_sync()` + 裸调）实测多 filename 响应结构。若服务端不支持，本项降级为"会话内记住上次命中档位，下次从该档开始试"。
- **✅ 实验结果（2026-06-12，`scripts/debug_vkey_batch.py` 真机实测）**：4 个 filename（FLAC/MP3_320/OGG_192/MP3_128）单请求返回 4 条 `midurlinfo`，**严格保序且逐条回显请求 `filename`**；不可播档形状与单请求一致（`purl` 空 + `result=104003`），可播档 `result=0` + `purl` 正常。实现时优先按回显 `filename` 对位（容乱序/缺条），缺回显时按下标兜底。

### P2 — 预取下一首 URL（prefetch）

当前曲成功起播后，后台预取"自然播完后的下一首"的 URL 缓存起来；切歌时命中缓存则**跳过整个 vkey 往返**。

- `PlayQueue` 新增 `peek_next() -> Song | None`（**非变异**）：
  - SEQUENCE：`index + 1`，末尾返 None；REPEAT_ALL：末尾绕回 `songs[0]`；
  - REPEAT_ONE：返回 current（配合 P5 短路，prefetch 检测到 mid 未变且 `sourceUrl` 有效则跳过）；
  - SHUFFLE：`_shuffle_remaining[0]`，空池返 None（**peek 不重洗**，重洗仍只发生在真正 advance 时）。
- `PlayerController`：
  - `_prefetched: tuple[mid, quality_pref, SongUrl] | None`，只存一条；
  - `_load_current` 成功设 `sourceUrl` 后 spawn 预取任务（先 `await asyncio.sleep(延迟)`，默认 ~5s，避免与当前曲起播缓冲争带宽；延迟做成实例属性供测试注入 0）；新一轮 `_load_current` 先 cancel 旧预取任务；
  - 消费：`_load_current` 取链前查缓存，**mid 与 quality_pref 都匹配**才用，**消费即清**（保证媒体错误重试路径 `handleMediaError` → `_load_current` 时已无缓存，自动走现签新链，与现有重试语义兼容）；不匹配（队列被改 / 切了音质）直接丢弃走正常链路。
- 失效兜底：vkey URL 有效期为小时级，提前几分钟预取安全；万一失效，现有 `_RETRYABLE_MEDIA_ERRORS` 重取链重试机制天然兜底，无需新代码。

### P3 — StreamProxy 连接复用

`stream_proxy.py` `_handle` 每请求 `creq.get(...)` 新建会话改为复用 `creq.Session`（keep-alive 到 CDN）：FFmpeg 的起播 / seek（Range）/ 重连请求省掉一次 TCP + TLS 握手。

- `ThreadingHTTPServer` 多线程并发调 handler，需确认 curl_cffi `Session` 的线程安全性；不安全则 `threading.local()` 按线程一个 Session。
- `stop()` 时关闭 Session。

### P4 — 淡入淡出（单播放器音量包络）

**架构**：QML 侧引入 `fadeFactor`（0↔1，`NumberAnimation` 驱动），`AudioOutput.volume` 改为乘性组合：

```
volume = (muteForPendingSeek ? 0 : playerController.volume) * fadeFactor
```

乘性组合下用户拖音量滑条、MPRIS 写 volume 都天然正确（`playerController.volume` 语义不变，fade 只是临时包络）。`muted` 与 fade 正交，不动。

**四个 fade 场景**：

1. **手动切歌**（next / prev / 点列表 / 点队列）：`_load_current` 在当前 `playbackState == "playing"` 时先 emit `fadeOutRequested(durMs)`，然后**与 fade 并行**取 URL；URL 取回后若 fade 还没播完则 `await asyncio.sleep(剩余)`，再设 `sourceUrl` 起播。**fade 时长正好掩盖取链延迟**——这是"淡入淡出"与"加载提速"在体验上的合流点。`asyncio.sleep` 后必须重查 generation guard（沿用现有模式）。
2. **自然播完尾部淡出**：QML `onPositionChanged` 中 `duration - position <= fadeMs` 且 playing → 启动 fadeOut；EndOfMedia 照旧走 `handleEndOfMedia`（此时 `playbackState` 已非 playing，Python 端条件自动跳过二次 fade）。配合 P2 预取命中，新歌即取即播 + fade-in，歌间听感连贯。
3. **起播淡入**：QML 在转入 PlayingState 且 `fadeFactor < 1` 时启动 fadeIn（fade 关闭时 `fadeFactor` 恒 1）。统一决策：fade 启用时冷起播也从 0 淡入（行为统一、听感一致）。
4. **暂停 / 恢复渐变**（低成本顺手做，对齐 QQ 官方）：`pauseRequested` 改为 fade 启用时先 fadeOut（固定 `min(fadeMs, 200)` ms，动画 `onStopped` 回调里真 `pause()`）；恢复时 play + fadeIn。快速连按 Space：fadeOut 动画进行中收到 play → stop 掉 fadeOut 动画直接转 fadeIn，QML 端动画互斥即可，Python 状态机不变。

**边界明确**：

- fade 关闭时：`fadeOutRequested` 不发、`fadeFactor` 恒 1、暂停立即生效——**与现状行为完全一致**（回归底线）。
- `reduceMotion` **不**联动 fade：它是视觉动效开关，音频淡入淡出有独立设置项（设计决策，写进代码注释）。
- 快速连点 next：generation guard 已覆盖；`fadeFactor` 已在 0 就不重复 fade。
- seek 不触发 fade。

**否决项（写明不做）**：

- ❌ 双 `MediaPlayer` 真重叠 crossfade：vkey 并发拉流 401 实锤风险 + pendingSeek / 重试 / 状态机全要双份，收益（重叠 vs 衔接）听感差距小。
- ❌ 歌曲完整文件磁盘缓存（彻底解决重复播放加载）：盘子大（容量管理 + 版权敏感性评估），本期不做；若未来落地，crossfade 双流可全走本地、401 约束解除，可届时重新评估。
- ❌ 三档 vkey 并行请求（3× 请求量有风控风险），被 P1 批量单请求替代。

### P5 — REPEAT_ONE 单曲循环 EOS 短路（顺手修）

`handleEndOfMedia` 中 `on_song_end()` 返回的歌 mid 与当前 `sourceUrl` 对应曲一致时（REPEAT_ONE 场景），不进 `_load_current`，直接 `seekRequested(0)` + `playRequested`。长时间循环后 URL 过期的极端情况由现有媒体错误重试兜底。

### 设置项设计

| 设置键 | 类型 / 范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `playback/fadeEnabled` | bool | `true` | 总开关，关闭后行为与现状一致 |
| `playback/fadeDurationMs` | int，钳位 200–2000，步进 100 | `500` | 切歌淡出 / 淡入时长；暂停渐变取 `min(该值, 200)` |

- `SettingsController`：`fadeEnabled` / `fadeDurationMs` Property + `setFadeEnabled` / `setFadeDurationMs`，复用 `_read_bool` / `_read_int_clamped`，照 `qualityPreference` 模式（同值早退 + `settings.sync()` + `settingsChanged`）。
- `PlayerController` 经已持有的 `_settings_controller` 引用读取（照 `_quality_preference()` 的 getattr 容错模式）。
- `SettingsView.qml`「播放」区（`qualityPreference` 的 ChoiceRow 下方）加：开关行（淡入淡出）+ 时长滑条行（仅开关开启时启用），复用设置页现有行组件风格。
- 预取 / 批量取链 / 连接复用**不设开关**——纯优化，无用户可感知的权衡。

## 实施步骤（每步 ≤300 行，TDD，完成后附手动验证清单等用户"过了"再推进）

### Stage A1 — vkey 批量取链（P1）

1. 前置实验：调试脚本实测多 filename 单请求的 `midurlinfo` 响应结构（顺序对应性、混合可播/不可播档的形状），结果回填本文档。
2. 测试先行 `tests/test_service.py`（或现有 service 测试文件）：mock `_bypass_post` 返回多条 `midurlinfo`，断言按偏好顺序选第一个非空 `purl`、空 `purl` 跳过、全空时透传 result 码、`filename`/`songmid`/`songtype` 数组长度对齐。
3. 实现 `_try_bypass_urls` + 改 `get_song_url`；删旧串行循环。
4. 验证清单：`uv run pytest`；真机播放（VIP 命中首档 / 非 VIP 降级 / 灰色歌曲自动跳过日志码 104003 不回归）；日志确认每次切歌只有一条 vkey 请求。

### Stage A2 — 预取 + REPEAT_ONE 短路（P2 + P5）

1. 测试：`test_queue.py` 补 `peek_next` 四模式契约（含 SHUFFLE 空池不重洗、SEQUENCE 末尾 None）；`test_bridge_player_controller.py` 补：起播后预取被调（delay 注 0）、next 命中缓存不再调 `get_song_url`、队列变更后 mid 失配走正常链路、消费即清、REPEAT_ONE EOS 不重新取链。
2. 实现 `PlayQueue.peek_next` + `PlayerController` 预取任务管理 + 消费 + EOS 短路。
3. 验证清单：pytest 全绿；真机顺播一张歌单，观察自然切歌歌间空白显著缩短、日志中下一首 vkey 在上一首播放期间已取；**全程观察无 401**（预取与在播流共存的实验验证）；单曲循环模式 EOS 无新 vkey 请求。

### Stage B — StreamProxy 连接复用（P3）

1. 确认 curl_cffi Session 线程安全性（文档 / 小实验），决定全局 Session 或 thread-local。
2. 测试：现有 stream_proxy 测试基础上补"多请求复用会话"的可测断言（如注入 fake session 工厂计数）。
3. 实现 + 验证清单：pytest；真机播放 + 频繁 seek，听感起播 / seek 更跟手，日志无新告警。

### Stage C1 — 淡入淡出设置项（P4 设置面）

1. 测试：`test_bridge_settings_controller.py` 补两字段的默认值 / 钳位 / 持久化 / 同值早退契约。
2. 实现 `SettingsController` 字段 + `SettingsView.qml` UI。
3. 验证清单：pytest + `scripts/lint.py`（含 qmllint）；设置页可见可调、重启后保留。

### Stage C2 — 淡入淡出播放面（P4 主体）

1. 测试：`test_bridge_player_controller.py` 补：playing 态切歌发 `fadeOutRequested(durMs)`、stopped 态切歌不发、fade 关闭不发、`asyncio.sleep` 等待后 generation 失效不设 `sourceUrl`（fake clock / 短时长注入）。
2. 实现：`PlayerController._load_current` fade 协调（信号 + 并行取链 + 剩余等待）；`Main.qml` `fadeFactor` + 两个 NumberAnimation + `AudioOutput.volume` 乘性改造 + EOS 尾部淡出 + 暂停/恢复渐变 + 起播淡入。
3. 验证清单（手测为主，QML 动画无法单测）：
   - 开关开：手动切歌听到渐弱→渐起，无硬切爆音；自然播完尾部渐弱、下一首渐起；暂停/恢复渐变；快速连点 next / 连按 Space 无卡死、无音量卡在中间值；fade 中拖音量滑条行为正确；静音态切歌无异常。
   - 开关关：行为与改造前完全一致（硬切、暂停立即）。
   - `reduceMotion` 开启不影响音频 fade。
   - pytest + lint 全绿；`src/quaverq/bridge/README.md`、`src/quaverq/core/README.md` 同步（peek_next / 预取 / fade 信号）。

## 预期结果

- **手动切歌**：感知从「硬切 + 1–3s 静音空白」变为「~0.5s 渐弱渐起」，取链延迟（P1 单往返 + P2 缓存命中时趋零）被 fade 完全掩盖。
- **自然切歌**：预取命中时歌间间隙只剩 FFmpeg 起播缓冲（数百 ms），配合尾部淡出听感连贯。
- **单曲循环**：EOS 零网络往返即时重播。
- 设置页新增「淡入淡出」开关 + 时长，持久化；关闭后所有行为与现状一致。

## 风险与实验验证项

| # | 验证项 | 时机 | 失败时降级 |
| --- | --- | --- | --- |
| 1 | `UrlGetVkey` 多 filename 单请求的响应结构 | Stage A1 前置 | P1 降级为"记住上次命中档位优先试" |
| 2 | 预取 URL（仅 POST 不开流）不影响在播流（无 401 互踢） | Stage A2 真机验证 | 预取延迟推迟到「剩余 ≤20s」时再取，进一步缩短共存窗口；仍不行则砍 P2 |
| 3 | curl_cffi `Session` 多线程安全性 | Stage B 前置 | thread-local Session |
| 4 | fade 期间 `asyncio.sleep` 与 qasync 事件循环的时序（连点场景） | Stage C2 测试覆盖 | generation guard 已有先例，预期无问题 |
