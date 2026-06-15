# 调研：播放链接偶发 401 与 ct 风控

## 任务描述

排查「拉取歌曲播放链接 / 播放 CDN 链接时有时 401、有时正常」的原因，重点确认 `ct` 字段在 `music.vkey.GetVkey.UrlGetVkey` 中的作用，并修正旧文档里“不传 `ct`”的过期结论。目标是让播放、预取、下载在遇到被拉黑的 `ct` 或 CDN 401 / 403 时能自动换 `ct` 重签，尽量不把失败暴露给用户。

## 调研结果

### 已确认事实

1. 当前项目没有走 `qqmusic-api-python` 的 `client.song.get_song_urls()`，而是在 `src/quaverq/core/service.py` 自拼 `musicu.fcg`。
2. 本地依赖为 `qqmusic_api 0.6.6`。上游默认版本策略仍是 Android `ct=11`、Desktop `ct=19`、Web `ct=24`；`request_api()` 默认会先构建平台 `comm`，调用方不使用 `override_comm=True` 时无法得到真正的“无 ct”。
3. 上游 `get_song_urls()` 使用 `music.vkey.GetVkey / UrlGetVkey`，参数包含 `uin`、`filename`、`guid`、`songmid`、`songtype`、`ctx=0`。项目的 bypass 路径目前只发 `filename`、持久 `guid`、`songmid`、`songtype`，并在 `comm` 中显式放 `ct/cv/qq/authst`。
4. 旧文档 `docs/findings.md` 中“不传 `ct` 最稳”的判断已经过期。当前约束应改为：**必须传 `ct`，但某些 `ct` 会被拉黑，需要候选池和动态剔除**。
5. 项目现在启动时从 `_SAFE_CT_VALUES` 随机选择一个 `ct`，实例生命周期内固定。这个设计会把远端风控变化放大成“偶发”：选中仍可用的 `ct` 就正常，选中被新拉黑的 `ct` 就整次会话持续失败。
6. 当前代码只处理 vkey 层的 `purl` 为空；如果服务端返回了 `purl`，但 CDN 对该链接返回 401 / 403，`QuaverService` 不知道这个 `ct` 已经不可用。播放层会重取链一次，但因为 `ct` 固定，重签仍然可能拿到同类坏链。
7. 旧规划 `search-playback-fade-and-speed.md` 记录过一个独立风险：同一账号同时拉两路 CDN 流可能让其中一路 401。预取 vkey 本身通常不拉 CDN 流，但下载、播放、seek、调试探针、未来的“URL 预验证”都可能制造并发拉流。

### 2026-06-16 当前 CT 扫描

测试环境：本机缓存登录态、持久 `device_id`、队列歌曲《重生之我是非酋》（`mid=000x41If2GZ8KR`），扫描 `ct=0..100`。每个 `ct` 只请求 `MP3_128`，签出 `purl` 后用 `curl_cffi` + `Range: bytes=0-0` 做最小 CDN GET 验证。

全量结果：

| 状态 | ct 值 | 说明 |
| --- | --- | --- |
| `VKEY_EMPTY` | `1, 11, 19, 27` | vkey 阶段拿不到可用 `purl`；`1/11` 返回 `result=101404`，`19` 的 result 为空，`27` 返回 `result=0` 但 `purl` 为空 |
| `CDN_403` | `18` | vkey 能签出 `purl`，但 CDN `Range GET` 返回 403 |
| `OK` | `0, 2..17(除 11), 20..26, 28..100` | vkey + CDN 最小 GET 均可用 |

交叉复核：用队列前 5 首歌对 `1, 11, 18, 19, 27` 和对照值 `2, 3, 23, 46` 复测。

| ct | 5 首歌结果 | 结论 |
| --- | --- | --- |
| `1` | 5/5 `VKEY_EMPTY` | 当前坏值 |
| `11` | 5/5 `VKEY_EMPTY` | 当前坏值 |
| `18` | 5/5 `CDN_403` | 当前坏值 |
| `19` | 5/5 `VKEY_EMPTY` | 当前坏值 |
| `27` | 5/5 `VKEY_EMPTY` | 当前坏值 |
| `2` | 5/5 `OK` | 当前可用 |
| `3` | 5/5 `OK` | 当前可用，旧黑名单已不适用 |
| `23` | 5/5 `OK` | 当前可用，旧黑名单已不适用 |
| `46` | 5/5 `OK` | 当前可用，旧黑名单已不适用 |

当前结论：`ct=1, 11, 18, 19, 27` 应列为硬 blocklist；现有 `_SAFE_CT_VALUES` 中没有命中这 5 个坏值，因此当前候选池本身是健康的。不过 `18` 证明“vkey 成功不等于 CDN 可播”，仍需要 CDN 401 / 403 上报后换 `ct` 重签。

### 初步根因模型

401 不是单一原因，而是至少三类问题叠加：

| 类别 | 触发方式 | 现状表现 | 处理方向 |
| --- | --- | --- | --- |
| 坏 `ct` | 会话随机选中被远端拉黑的 `ct` | vkey 可能拒发，或返回 `purl` 但 CDN 401 / 403 | 运行期剔除当前 `ct`，换值重签 |
| CDN 链接失效 / 被替换 | 预取链接过久、媒体错误后复用旧缓存、CDN 边缘节点策略变化 | 播放中断或起播失败 | 媒体错误后清预取，强制现签 |
| 同账号并发拉流 | 播放与下载并发、调试 HEAD/Range 探测与播放并发、双播放器交叉淡入淡出 | 其中一路 401，且“有时发生” | 保持单播放流；下载串行；不要在播放时做 CDN 预验证 |

### 已实施：播放与下载 CDN 并发避让

2026-06-16 已先修生产里最容易触发的并发拉流路径：

1. `PlayerController` 新增 `onlineStreamActive` / `onlineStreamActiveChanged`，在线取链/挂源/恢复播放置 true，本地播放、暂停、停止置 false。
2. `DownloadController` 构造时接收 `player_controller`，监听 `onlineStreamActiveChanged`。
3. 下载 worker 在签下载 URL 前和真正拉音频前都等待在线播放空闲；如果音频下载已经开始而用户发起在线播放，则置位当前下载 cancel event，保留 `.part`，把任务重新排回 `pending`，等播放空闲后续传。
4. 覆盖测试：
   - `test_download_waits_until_online_playback_idle`
   - `test_online_playback_preempts_active_download_and_requeues`
   - `test_online_stream_active_clears_on_stop`
   - `test_local_playback_does_not_mark_online_stream_active`

## 处理计划

### Stage 0：观测与复现

1. 给 vkey 请求加结构化 debug 日志：`ct`、`mid`、`media_mid`、请求音质列表、每档 `result`、是否返回 `purl`。不要打印完整 URL 或 `authst`。
2. 给 `StreamProxy` / 下载器补充 401 / 403 可观测性：记录状态码、目标 host、当前曲 `mid`、当前 URL 使用的 `ct`。
3. 扩展 `scripts/debug_song_url.py`：保留强制 `QQ_DEBUG_CT=<值>` 和扫描池能力，但把结论输出区分为 vkey 拒发、CDN 401、CDN 403、可播。

### Stage 1：ct 管理器

1. 引入运行期 `ct` 状态：候选池、临时 blocklist、失败原因、过期时间。
2. `_bypass_post()` 不再直接读取一个全局固定 `_ct_value`，而是接收本次请求确定的 `ct`，保证并发请求不会因为全局值切换而日志错位。
3. `get_song_url()` 在全档失败、vkey 空响应、或外部报告 CDN 401 / 403 后，最多换 2-3 个 `ct` 重签，再判定歌曲不可播。
4. 避免把真实无版权歌曲误判为坏 `ct`：只有“同一 `ct` 下多首 / 多次 CDN 401/403”或“换 `ct` 后同一首立即成功”才提升为临时 block。

### Stage 2：播放层 401 自愈

1. `SongUrl` 或等价内部结构记录签发时使用的 `ct`。
2. `PlayerController` 保存当前挂源的 `ct`；媒体错误字符串或 `StreamProxy` 回调显示 401 / 403 时，调用 `ServiceController.mark_song_url_ct_failed(ct, status)`。
3. 401 / 403 重试时清空对应预取缓存，强制重新取链；重试次数按“换过几个 `ct`”计数，而不是重复用同一 `ct`。
4. `StreamProxy` 如果能看到上游状态码，应通过线程安全回调上报，避免完全依赖 QML/FFmpeg 的 error string。

### Stage 3：下载层 401 自愈

1. `DownloadError` 增加 `status_code` 字段，下载器遇到 401 / 403 时保留 `.part`，由上层决定是否重签。
2. `DownloadController._process()` 下载音频遇到 401 / 403 时：标记当前 `ct` 失败 → 重新 `get_song_url()` → 再下载一次。仍失败才把任务置为 failed。
3. 保持下载 worker 并发 1；播放与下载是否允许同时拉流需要再实测。如果仍互踢，下载应在播放态提示排队或限速到用户可控。

### Stage 4：文档与测试

1. 测试先行：
   - `_bypass_post` 必须带 `ct`；
   - connect 选值不在静态 blocklist；
   - vkey 空响应 / 全档空时会尝试备用 `ct`；
   - CDN 401 / 403 上报后当前 `ct` 被临时剔除；
   - 播放媒体错误触发换 `ct` 重签；
   - 下载 401 / 403 触发一次重签重试。
2. 更新 `docs/findings.md`、`src/quaverq/core/README.md`、`src/quaverq/bridge/README.md`，明确“必须传 `ct` + 动态避开坏值”，删除或标记所有“不传 `ct`”的生产建议。
3. 手动验证：
   - `QQ_DEBUG_CT=19 uv run python scripts/debug_song_url.py` 应能稳定复现坏值路径；
   - `QQ_DEBUG_CT=-1 uv run python scripts/debug_song_url.py` 输出当前候选池健康度；
   - 真机播放一张歌单 20 首，观察无连续 401；
   - 播放中启动单首下载，确认是否出现互踢，记录是否需要下载与播放互斥策略。

## 预期结果

1. 启动随机选到坏 `ct` 不再导致整次会话不可播；最多经历一次短暂重签。
2. vkey 成功但 CDN 401 / 403 时，应用能识别为签链策略问题，而不是只做同 `ct` 重试。
3. 旧文档不再指导“不传 `ct`”；所有后续实现都以“显式 `ct` + 动态坏值剔除”为准。
4. 播放和下载路径都具备同一套 401 自愈能力，减少用户看到“播放失败 / 下载失败”的概率。

## 参考

- 本地代码：`src/quaverq/core/service.py`、`src/quaverq/bridge/player_controller.py`、`src/quaverq/bridge/stream_proxy.py`、`src/quaverq/bridge/download_controller.py`
- 本地依赖源码：`.venv/Lib/site-packages/qqmusic_api/core/versioning.py`、`.venv/Lib/site-packages/qqmusic_api/modules/song.py`
- 上游仓库：<https://github.com/L-1124/QQMusicApi>
