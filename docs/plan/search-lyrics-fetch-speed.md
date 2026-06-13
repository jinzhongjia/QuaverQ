# 歌词拉取速度优化调研

## 任务描述

评估当前歌曲歌词拉取链路是否还能更快，并给出可落地的优化顺序。重点关注主窗口歌词与桌面悬浮歌词首次显示、切歌后显示、以及无逐字歌词时的回退耗时。

## 当前链路

- 启动阶段 `src/quaverq/__main__.py` 的 `_load_initial_state()` 会先 `await service_controller.start()`，然后并发刷新首页和当前歌词。
- `LyricController.refresh_current_lyric_async()` 从 `PlayerController.currentSong` 取当前歌曲，清空旧歌词后调用 `_load_lyric(mid, generation)`。
- `LyricController._load_lyric()` 通过 `ServiceController.get_lyric(mid, with_translation=True)` 进入服务层。
- `ServiceController.get_lyric()` 会先 `_ensure_started()`，因此服务尚未完成启动、凭据读取、账号有效性校验时，歌词请求需要等待。
- `QuaverService.get_lyric()` 当前策略是先请求逐字 QRC；如果 QRC 失败、无逐字、解密失败或解析不到行，再串行回退请求逐行 LRC。

## 调研结果

### 主要瓶颈

1. **首次显示依赖网络**
   - 当前没有歌词磁盘缓存。每次启动后当前歌曲的歌词内容都需要等 `GetPlayLyricInfo` 网络请求返回。
   - 之前已修复“启动恢复当前 mid / position”的问题，但内容本身仍没有同步缓存可用，所以首屏歌词仍会晚于窗口。

2. **服务启动会阻塞歌词请求**
   - `ServiceController.get_lyric()` 前置 `_ensure_started()`。
   - 冷启动时如果 `service_controller.start()` 还在做真实连接或登录态校验，歌词请求会排队等待。

3. **无 QRC 时存在串行两跳**
   - `QuaverService.get_lyric()` 先请求 `crypt=1, qrc=1` 的 QRC。
   - 如果没有可用逐字歌词，再请求 `crypt=0, qrc=0` 的 LRC。
   - 对纯音乐、版权信息、无逐字歌词或 QRC 异常歌曲，最坏路径是两次串行网络请求。

4. **解析不是优先瓶颈**
   - QRC/LRC 解析是本地字符串解析，通常远小于网络 RTT 和服务启动耗时。
   - 优化解析器收益有限，不建议作为第一阶段目标。

## 可选方案

### 方案 A：歌词磁盘缓存 + 启动同步 prime

新增 `LyricCache`，保存成功拉取并解析后的歌词结果：

- 路径建议：`CACHE_DIR / "lyrics"`。
- key 建议：`mid + with_translation`，文件内带 schema version，方便以后兼容字段变化。
- 内容建议：序列化 `Lyric`，包含 `mid`、`has_translation`、`lines`、`words`、`timestamp_ms`、`translation`。
- 控制器启动时，如果当前 `mid` 有缓存，先同步填充歌词模型；后台网络刷新成功后覆盖缓存。

收益：

- 启动恢复当前歌曲时，歌词可以近乎瞬时显示。
- 切回最近听过的歌不必等待网络。
- 对桌面悬浮歌词尤其明显，因为它可以跟随已恢复的进度直接显示正确行。

风险与注意：

- 歌词可能被服务端更新，需要后台 revalidate 覆盖旧缓存。
- 翻译是否随账号/区域变化不确定。保守做法是缓存公开内容，同时网络刷新总是可覆盖。
- 需要给缓存失败、JSON 解析失败、schema 过期做静默降级。

### 方案 B：同会话内内存缓存和 in-flight 去重

在 `ServiceController` 或 `LyricController` 层维护：

- 短期内存缓存：同一个 `mid + with_translation` 切回时直接复用。
- in-flight 请求去重：多个入口同时请求同一首歌歌词时，只保留一个实际网络请求，其他调用 await 同一个 task。

收益：

- 避免主歌词、悬浮歌词、下载、DBus 等入口重复打同一条网络请求。
- 对快速切歌又切回、重复刷新很有效。

风险与注意：

- generation 校验仍应留在 `LyricController`，防止旧请求覆盖新歌。
- in-flight task 失败后要及时移除，避免缓存一个失败状态。

### 方案 C：优化 QRC / LRC 回退策略

当前 QRC 失败后才请求 LRC。可以考虑两种优化：

- 对已知无 QRC 的 `mid` 做短期失败记忆，下次直接走 LRC。
- 谨慎地并发请求 QRC 和 LRC，优先用 QRC；QRC 不可用时无需再等第二次 RTT。

收益：

- 对无逐字歌词的歌曲，明显减少等待。

风险与注意：

- 默认并发会让大多数有 QRC 的歌曲多打一条 LRC 请求，增加请求量和风控压力，不建议第一阶段默认开启。
- 失败记忆需要 TTL，避免服务端后来补上 QRC 后长期拿不到逐字歌词。

### 方案 D：服务启动前移或更细粒度解耦

继续保留 SWR 首帧契约的前提下，让 `ServiceController.start()` 更早进入后台任务，减少用户切到歌词时才等待启动的概率。

收益：

- 冷启动网络较慢时能少等一点。

风险与注意：

- 不能破坏当前启动期同步预载凭据、公共区缓存和私有区缓存的首帧契约。
- 需要确认不会重复 `start()` 或泄漏 curl-cffi 客户端线程。

## 推荐实施顺序

1. **先做方案 A：歌词磁盘缓存 + 当前歌曲启动 prime。**
   - 收益最大，能直接改善启动后歌词晚显示的问题。
   - 即使网络慢，也能先显示上次成功拉取的歌词。

2. **再做方案 B：内存缓存 + in-flight 去重。**
   - 代码范围较小，能减少重复请求。
   - 与磁盘缓存互补：内存解决本次运行，磁盘解决跨启动。

3. **最后评估方案 C：无 QRC 的短期失败记忆。**
   - 优先做失败记忆，不默认并发 QRC/LRC。
   - 如果实测无 QRC 歌曲仍慢，再考虑受控开关或更精细策略。

## 预期结果

- 冷启动恢复同一首歌时，缓存命中情况下歌词可在主窗口和悬浮歌词创建后立即显示。
- 切回最近播放过的歌曲时，不再重复等待网络。
- 同一首歌多入口请求只产生一次实际网络调用。
- 对无逐字歌词歌曲，后续重复播放可以绕开已知慢路径。
