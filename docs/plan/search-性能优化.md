# 性能优化调研

## 任务描述

梳理当前 QuaverQ 中值得优先关注的性能优化点，覆盖启动链路、服务请求、缓存读写、QML 渲染与封面图片加载，并给出后续可按 TDD 落地的实施顺序。

GitHub issue：[#22 Feature: 性能优化](https://github.com/jinzhongjia/QuaverQ/issues/22)，创建于 2026-06-13，要求：
- 良好的跨平台性
- 禁止使用轮询
- 尽量低的 CPU 占用
- 尽量低的内存占用
- 充分利用不同平台本地特性

## 2026-06-14 实施记录：StreamProxy 懒启动

### 决策

- 不再在 `src/quaverq/__main__.py` 启动阶段同步调用 `stream_proxy.start()`。
- `StreamProxy` 仍在入口处构造并注入给播放器和 Windows SMTC，保证对象生命周期由主程序持有，退出时继续由 `stream_proxy.stop()` 幂等清理。
- 在线播放真正需要把 QQ CDN URL 包成回环 URL 时，由 `PlayerController._load_current()` 先按需 `start()`，再调用 `local_url()`。
- 本地优先播放命中已下载文件时不启动 `StreamProxy`，离线播放不额外占用 server 线程。
- Windows SMTC 只有在缓存封面已经存在或后台拉到封面、且需要把本地文件转为 `http://127.0.0.1` URI 时，才按需启动 `StreamProxy`。
- 懒启动失败不阻断主功能：播放器保留 `local_url()` 未运行时的直连降级语义；SMTC 只跳过封面 thumbnail，标题/歌手元数据仍推送。
- 不引入任何轮询；触发点全部来自用户播放动作或 SMTC 元数据更新信号链路。

### 修改内容

- `src/quaverq/__main__.py`：移除启动期 `stream_proxy.start()`，保留构造、注入与退出清理。
- `src/quaverq/bridge/player_controller.py`：新增 `_start_stream_proxy_if_available()`，在线挂源前懒启动代理。
- `src/quaverq/platform/_windows_media_session.py`：新增 `_local_file_url()`，SMTC 本地封面 URI 生成前懒启动代理。
- `tests/test_bridge_player_controller.py`：新增在线首次挂源前启动代理的回归测试。
- `tests/test_platform_windows_media_session.py`：新增 SMTC 封面 URI 懒启动代理的纯逻辑测试。
- `src/quaverq/README.md` / `src/quaverq/bridge/README.md` / `src/quaverq/platform/README.md`：同步启动流程、播放器、代理与 Windows SMTC 的新生命周期说明。
- `src/quaverq/platform/windows.py`：校正 Windows PAL 顶部说明，移除历史 mutex / 轮询描述。

### 预期收益

- 未播放、只浏览首页/搜索/设置的用户启动后不会创建 `ThreadingHTTPServer` 服务线程，也不会提前创建 `curl_cffi.Session`。
- 启动链路少一个本地 socket bind 与线程启动点，启动期 CPU/内存峰值更低。
- 在线首播仍保持 QQ CDN 经 curl_cffi 官方 JA3 指纹代理的行为；本地下载优先播放不受影响。
- Windows Now Playing/SMTC 封面仍可在需要时通过本机回环 HTTP 暴露，不牺牲平台原生体验。

### 自动化验证

- 新增红绿测试：
  - `uv run pytest tests/test_bridge_player_controller.py::test_remote_play_starts_stream_proxy_lazily_before_routing tests/test_platform_windows_media_session.py::test_resolve_thumbnail_uri_starts_stream_proxy_lazily`
- Review follow-up：测试替身 `_LazyProxy` 补齐真实 `StreamProxy.running` 接口，生产代码直接调用 `running/start()/local_file_url()`，不再用防御性 `getattr` 掩盖不完整 mock。
- 需要回归：
  - `uv run pytest`
  - `uv run python scripts/lint.py`

### 人工验证清单

- 启动应用但不播放音乐：日志不应出现 `StreamProxy 启动于 127.0.0.1:<port>`；任务线程数不应出现名为 `StreamProxy` 的线程。
- 首次在线播放任意歌曲：播放能正常起声，日志应在首次在线挂源附近出现一次 `StreamProxy 启动于 ...`。
- 播放已下载歌曲：应直接使用 `file://` 本地路径，不应因为本地播放启动 StreamProxy。
- Windows 10+：播放有缓存封面的歌曲时，系统 SMTC / Now Playing 卡片仍应显示标题、歌手和封面；首次需要封面时允许出现一次 `StreamProxy 启动于 ...`。
- 退出应用：无论代理是否启动过，退出都应正常，不应因 `stream_proxy.stop()` 幂等清理报错。

## 调研结果

### P1：封面加载热路径可以加内存缓存

相关位置：
- `src/quaverq/qml/components/AlbumArt.qml`
- `src/quaverq/bridge/cover_provider.py`
- `src/quaverq/core/cover_cache.py`

现状：
- `AlbumArt.coverCached` 会同步调用 `CoverController.isCached()`，随后 `requestCover()` 又会调用 `fetchCover()`；两边都会落到 `CoverCache.get_path()`，即至少一次 `path.exists()`，命中时还可能节流更新 mtime。
- `CoverImageProvider.requestImage()` 每次都从磁盘读图、按目标尺寸裁剪，再用 `QPainter` 烘焙圆角。
- QML 两个 `Image` 都设置了 `cache: false`，滚动回到同一封面时更容易重复触发 provider 读图/裁剪/圆角处理。

优化方案：
- 给 `CoverImageProvider` 加一个小型有界内存 LRU，key 使用 `(path, mtime_ns, target_size, radius)`，value 存处理后的 `QImage`。
- 给 `CoverCache` 或 `CoverController` 加运行期命中索引，下载完成、清理缓存、LRU 淘汰时同步更新，减少 QML 热路径里的重复 `stat/exists`。
- 评估将列表场景的 `Image.cache` 改为可配置属性，默认仍保守，或直接依赖 provider 侧 LRU 控制内存上限。

预期结果：
- 列表滚动、切回页面、打开队列面板时减少磁盘读和 CPU 图像处理。
- 封面多处复用时减少重复解码，同一 URL 的小图/中图命中率更高。

测试与验收：
- 新增 `tests/test_bridge_cover_provider.py` 覆盖重复 `requestImage()` 命中内存缓存、文件 mtime 变化后失效、缓存上限淘汰。
- 新增/扩展 `tests/test_qml_album_art.py`，验证 `coverReady` 后 revision 仍能刷新图片，不出现旧图粘连。
- 手动验证：启动应用，进入搜索/资料库长列表，快速上下滚动，观察封面加载是否更稳、CPU 峰值是否下降。

### P1：资料库刷新需要去重，避免重复打接口

相关位置：
- `src/quaverq/bridge/library_controller.py`
- `src/quaverq/qml/views/LibraryView.qml`

现状：
- `LibraryController._handle_auth_state_changed()` 在登录态变为 true 时会 `create_task(self.refresh_liked_async())`。
- `LibraryView` 同时在 `onAuthStateChanged` 调 `refreshCurrentTab()`；默认 tab 是“我喜欢”时也会调用 `refreshLiked()`。
- `refresh_liked_async()` 目前没有“同一 section 已在刷新则复用/跳过”的任务守卫，可能并发重复请求。

优化方案：
- 为资料库每个 section 增加独立任务守卫或 `_loading_sections`，同一 section 在途时直接 await 旧任务或 no-op。
- QML 侧保留“切 tab 刷新”的行为，但 controller 层保证幂等，避免界面状态与网络请求耦合。

预期结果：
- 登录、切入资料库、账号恢复时减少重复网络请求。
- 避免慢请求后返回覆盖快请求结果的竞态。

测试与验收：
- 在 `tests/test_bridge_library_controller.py` 增加“authStateChanged + refreshLiked 并发只调用一次 service”的测试。
- 增加不同 tab 刷新互不阻塞或行为符合预期的测试。

### P1：详情页独立接口可以并发

相关位置：
- `src/quaverq/core/service.py`

现状：
- `get_album_detail()` 顺序等待 `client.album.get_detail()` 和 `client.album.get_song()`。
- `get_artist_detail()` 顺序等待 `client.singer.get_info()` 和 `client.singer.get_tab_detail()`。
- 代码注释提到上游 `Request` 对象不能直接塞进 `asyncio.gather`，但项目里 `get_user_profile()` 已有成熟做法：用本地 coroutine 包一层再 gather。

优化方案：
- 对 album/artist 两处独立请求套本地 coroutine 后 `asyncio.gather()`。
- 保留凭据过期异常透传逻辑，避免并发后错误语义变化。

预期结果：
- 专辑详情、歌手详情打开耗时从“两次接口串行 RTT”降到“较慢一次 RTT”。

测试与验收：
- 在 `tests/test_service.py` 用 `_RequestLike` 或带延迟 mock 覆盖 Request-like awaitable 并发兼容。
- 验证 album/artist 原有字段解析测试继续通过。

### P2：首页缓存写入可以合并

相关位置：
- `src/quaverq/bridge/home_controller.py`
- `src/quaverq/core/home_cache.py`
- `src/quaverq/bridge/app_controller.py`
- `src/quaverq/bridge/library_controller.py`

现状：
- `HomeController.refresh_home_async()` 并发刷新 daily/playlists/newSongs/tops。
- 每个 section 成功后都会 `_persist()`，`HomeCache.update()` 会同步读整个 `home.json`、改一个 section、再同步写回。
- 首屏 revalidate 时可能短时间内产生多次主线程 JSON I/O。文件目前不大，但 daily/playlist/profile/my_playlists 都进入同一个文件，后续变大后容易变成可感知小卡顿。

优化方案：
- 给 `HomeCache` 增加批量更新入口，`refresh_home_async()` 聚合成功结果后一次写入。
- 或在 controller 层做短延迟 coalescing：多个 section 的写入合并到同一轮事件循环尾部执行。
- 如果保持同步 API，首帧 prime 继续同步读；后台刷新写入可移到 `asyncio.to_thread`，并加锁保证不互相覆盖。

预期结果：
- 启动后台刷新期间减少磁盘 I/O 次数。
- 降低 HomeCache 多 section 并发写时的互相覆盖风险。

测试与验收：
- 增加 spy HomeCache，验证一次 `refresh_home_async()` 不再写 3-4 次。
- 增加并发 section 更新不丢字段测试。

### P2：搜索请求需要 generation/cancel 保护

相关位置：
- `src/quaverq/bridge/service_controller.py`
- `src/quaverq/qml/views/SearchView.qml`
- `src/quaverq/qml/components/SearchField.qml`

现状：
- 搜索目前主要由 Enter/按钮触发，不是每个字符都请求，基础风险不高。
- 但 `search_async()`、`set_search_type_async()`、翻页请求没有统一 generation；慢的旧请求可能晚于新请求返回并覆盖模型。
- 同一个关键词、类型、页码短时间重复搜索没有复用。

优化方案：
- 在 `ServiceController` 增加 `_search_generation`，每次新关键词/类型/页码递增；请求返回时只采纳当前 generation。
- 可选：取消上一条在途 search task，或增加短 TTL 内存缓存 `(type, keyword, page)`。

预期结果：
- 快速切换搜索类型、重复点击搜索时减少废请求和 UI 闪动。
- 避免旧结果覆盖新结果。

测试与验收：
- 在 `tests/test_bridge_service_controller.py` 增加“慢旧请求不覆盖快新请求”的异步测试。
- 增加同参重复搜索命中缓存或不重复调用 service 的测试。

### P2：启动链路可加耗时打点，再决定是否懒启动 StreamProxy

相关位置：
- `src/quaverq/__main__.py`
- `src/quaverq/bridge/stream_proxy.py`
- `src/quaverq/diagnostics.py`

现状：
- 启动时在 `engine.load()` 前后做了较多初始化：diagnostics、系统主题 watcher、HomeCache prime、SessionState restore、StreamProxy start。
- `StreamProxy` 当前无论是否播放都会启动一个本机 HTTP server 和后台线程。
- 系统主题 watcher 为了避免首帧白闪，会在 `engine.load()` 前同步等待，Linux portal 路径已有 timeout 兜底。

优化方案：
- 先加启动阶段耗时日志，例如 config/diagnostics/platform/theme/cache-prime/engine-load/tray/proxy 各阶段。
- 如果打点确认 `StreamProxy.start()` 可见，可改为首播前懒启动；Windows SMTC 需要封面 HTTP URL 时也由调用方确保启动。
- 系统主题不建议盲目后移；若要优化，优先考虑缓存上次系统主题作为首帧值，再异步校验 portal。

预期结果：
- 有数据后再动启动顺序，避免破坏 SWR 首帧契约。
- 未播放用户的启动成本更低。

测试与验收：
- 增加启动阶段打点函数的纯函数/日志测试。
- 若懒启动 StreamProxy，补 `tests/test_bridge_player_controller.py` 或 `tests/test_stream_proxy.py` 覆盖首播前启动、退出幂等停止。

### P3：首页布局未来数据变多时应虚拟化

相关位置：
- `src/quaverq/qml/views/HomeView.qml`

现状：
- 首页是 `ScrollView + ColumnLayout`，每个 section 内用 `Repeater + GridLayout/ColumnLayout` 一次性创建 delegate。
- 当前推荐歌单 8、新歌 12、排行榜 9，规模较小，问题不急。
- 如果后续把每日推荐列表、更多推荐、无限滚动加到首页，这种结构会一次性创建大量 `SongRow/Card/AlbumArt`。

优化方案：
- 保持首页小规模精选时不用动。
- 一旦 section 数据超过约 30-50 项，把对应 section 改为固定高度 `ListView/GridView`，或拆到“查看更多”详情页，首页只保留首屏精选。

预期结果：
- 避免首页扩容后首帧 delegate 暴涨。
- 保持启动和切回首页稳定。

### P3：下载后处理可以并行一部分

相关位置：
- `src/quaverq/bridge/download_controller.py`

现状：
- 音频下载完成后依次执行 `_save_lyric()`、`_save_cover()`、`_embed_tags()`。
- `embed_tags()` 依赖封面文件，但歌词保存与封面下载互不依赖。

优化方案：
- 下载完成后先并发执行歌词保存与封面下载，封面完成后再嵌入标签。
- 保持所有附加产物失败“不影响音频本体”的语义。

预期结果：
- 单曲下载完成后的尾部等待更短，批量下载总耗时略降。

## 建议落地顺序

1. 先做资料库刷新去重：范围小、可测试、减少真实网络浪费。
2. 做详情页接口并发：不改 UI，收益直接，已有 `RequestLike` 测试经验可复用。
3. 做封面 provider 内存 LRU：对滚动体验最有感，但需要更细的图片失效测试。
4. 做 HomeCache 写入合并：需要谨慎保持账号私有区块归属语义。
5. 加启动耗时打点，再决定 StreamProxy 是否懒启动。

## 预期目标

- 首屏和切页不因后台缓存写入产生可感知卡顿。
- 搜索、详情、资料库在快速操作时不重复请求、不被旧请求覆盖。
- 列表滚动时封面解码与圆角处理成本下降。
- 后续每个优化都能通过 pytest 回归测试守住契约，再跑 `uv run pytest` 与 `uv run python scripts/lint.py` 验收。
