# src/quaverq/core

**业务核心层**。纯 Python + asyncio，不依赖 Qt / GUI，可以在 headless 环境下被 pytest 完整覆盖。[`bridge/`](../bridge/README.md) 的控制器持有这层的对象并把状态翻译给 QML，本目录从不反向感知 QML。

## 数据与序列化

| 文件 | 作用 |
| --- | --- |
| `models.py` | 所有领域 dataclass：`Singer` / `Song` / `Album` / `Playlist` / `Singer` / `ArtistDetail` / `TopList` / `Lyric` / `LyricLine` / `LyricWord`。轻量、可序列化、`bridge` 适配器和 `serde` 共用。 |
| `serde.py` | `Song <-> dict` / `Lyric <-> dict` / `UserProfile <-> dict` 序列化。`state.json`（会话快照）、`home.json`（首屏 SWR 缓存）和 `lyrics/`（歌词缓存）共用这一套，避免随 dataclass 字段演进而漂移（尤其 `file_qualities` 是 `set`，对 JSON 不友好）。 |

## 业务逻辑

| 文件 | 作用 |
| --- | --- |
| `service.py` | **QQ 音乐服务层**（基于 `qqmusic-api-python` 0.6.1）。封装搜索、详情、首页、推荐、歌词、链接获取。`get_song_url` 走 bypass 路径自拼 `musicu.fcg`，避开默认 `ct=11` 触发的版本风控；`ct` 在启动时从白名单 `random.choice`，实例生命周期固定；偏好内全部降级档批量塞进单个 `UrlGetVkey` 请求（`_try_bypass_urls`，1 次往返取代旧按档串行最多 3 次，issue #11），本地按偏好顺序挑第一个 `purl` 非空档，对位优先用响应回显 `filename`（实测保序，见 `scripts/debug_vkey_batch.py`），缺回显按下标兜底。歌词 `get_lyric()` 优先 QRC 逐字，失败回退 LRC；同一运行期内确认某 mid 无可用 QRC 后写入 10 分钟 memo，下次直接 LRC，减少无逐字歌曲的两跳串行等待。识别凭据过期 (`CredentialExpiredError`)。`probe_login_expired` 在检测到过期时会先尝试 `login.refresh_credential` 静默续命；成功则同步新凭据到内存 + 落盘 `credential.json`，失败再走旧 expired 流程。`get_fav_songlist` 走库方法分页 (单页 cap=50)，pydantic 校验挂时回退 bypass。`get_album_detail` / `get_artist_detail` 把基础信息与歌曲列表独立请求包成本地 coroutine 后并发拉取，兼容 qqmusic-api 返回的 awaitable 但 unhashable 的 Request 对象。`get_song_related(songid)` 并发拉 `get_similar_songs` + `get_related_songlists`，公开接口，凭据过期类异常仍透传给 controller。`get_similar_singers / get_singer_songs / get_singer_albums` 为歌手详情页 tab 拉数据，AlbumBrief 字段使用 `time_public / total_num / singer_name`（不是 `publish_date / songnum / singer_list`），无封面字段时用 `_cover_url(mid, 300)` 自拼。`get_song_info(song_mid, song_id)` 并发拉 `song.get_detail / get_labels / get_producer` 合并成 `SongInfo`（语种/流派/公司/发行日期/简介/标签/制作人）；labels 接口含统计营销噪声，按 tag_type/species 黑名单过滤；任一接口失败降级为空字段。`get_user_profile()` 并发拉 `user.get_homepage`（昵称/头像）+ `user.get_vip_info`（VIP 身份块，上游 #258 起类型化建模，依赖临时 git pin）合成 `UserProfile`；徽章优先级 SVIP > 豪华绿钻 > 绿钻 > 无，非会员抑制服务端等级 icon；任一失败不挡另一半，双失败返 None，凭据过期抛 `CredentialExpiredError`。 |
| `queue.py` | **播放队列 + 4 种播放模式**（`SEQUENCE` / `REPEAT_ALL` / `REPEAT_ONE` / `SHUFFLE`）。区分 `on_song_end()`（EOS 回调，遵守模式）和 `next()` / `prev()`（用户主动）；`peek_next()` 非变异地看"自然播完后将播哪首"（SHUFFLE 空池不重洗返 None），供预取下一首链接用；SHUFFLE 维护独立的索引置换列表。`push(..., source="daily")` 给队列打来源标签，`append(songs)` 按 mid 去重追加更多歌——配合 `PlayerController.queueExhausted` 信号实现猜你喜欢播完自动续接下一批。 |
| `lyric.py` | **LRC / QRC 解析 + 序列化 + 同步定位**。LRC 行级、QRC 逐字（`[起始ms,时长ms](文字起始,时长)...`）。给定播放进度返回当前行 + 字内进度，驱动 karaoke 高亮；无逐字数据时回退逐行。`to_lrc(lyric, title= , artist= , album= , with_translation= )` 把解析后的 `Lyric` 序列化回标准 LRC 文本（下载落盘用；QRC 行只取行级时间戳，翻译按 QQ 双行风格同时间戳紧随原文行）。 |
| `downloader.py` | **音乐下载核心**。`sanitize_filename(name)` 把歌名/歌手清洗为跨平台安全的文件名主干（Windows 非法字符 + 控制字符替 `_`、尾点/空格去除、UTF-8 字节截断不切多字节字符、Windows 保留设备名加 `_` 前缀、全空回退 `untitled`）。`Downloader.download_file(url, dest, progress_cb=, cancel=)` 同步流式下载（调用方放 `to_thread`）：与 StreamProxy 同路用 curl_cffi 官方浏览器 TLS 指纹过 QQ CDN 的 JA3 风控；经 `.part` 临时文件写入、完成后原子改名；**断点续传**——已有非空 `.part` 时带 `Range` 请求（206 追加续传 / 200 重头写 / 416 丢弃旧 `.part` 重下），取消与失败**保留** `.part` 供下次续传；`progress_cb(received, total)`（total=0 表示长度未知，续传时 received 从断点起算）；`cancel`（`threading.Event`）chunk 间检查抛 `DownloadCanceled`；HTTP 非 2xx 抛 `DownloadError`；float timeout 在 stream 模式是连接超时 + 低速断开（非总超时），大文件慢网安全。`quality_extension(label)` 标签→扩展名（含 MASTER/ATMOS_2 → flac）。`embed_tags(path, title=, artists=, album=, cover_path=)` 用 mutagen 按扩展名写标签：mp3 走 ID3v2（TIT2/TPE1/TALB + APIC 内嵌封面）、flac 写 Vorbis comment + Picture、ogg 仅文字 tag；坏容器抛错由调用方按非致命吞。 |
| `mpris.py` | **MPRIS2 D-Bus 集成**（`org.mpris.MediaPlayer2.quaverq`）。dbus-next pure-python async，挂在 qasync / Qt 主事件循环。方法调用回调由 `bridge.MprisController` 注入，状态/元数据变化由 controller 主动推。 |
| `lyric_dbus.py` | **Lyrics D-Bus 服务**（`org.quaverq.Lyrics1` @ `/org/quaverq/Lyrics`）。把当前歌词 + 实时位置 + 当前行/字索引暴露给桌面歌词工具（osdlyrics / waybar 自写模块 / 用户脚本）。Properties: `Mid` `TrackId` `PositionMs` `ActiveLine` `ActiveWord` `HasWordTiming` `HasTranslation` `LineCount`，标准 PropertiesChanged 推送。Methods: `GetLyric() → (s, b, a(xssa(xxs)))` 全量歌词 + 逐字 timing；`GetWindow(i, i) → (a(xss), i)` 当前行附近窗口。Signals: `LyricChanged(s mid)` `LineEntered(i, x)`。逐字精度（~16ms）不走 signal，客户端拿 `PositionMs` + 全行 word timing 自己插值。状态由 `bridge.LyricsDBusController` 推。 |
| `single_instance.py` | **单实例守卫**。启动时占 well-known name `org.quaverq.SingleInstance`（`RequestName + DO_NOT_QUEUE`），占到即第一实例；占不到则给 `org.mpris.MediaPlayer2.quaverq` 发 `Raise` 通知已有实例前置窗口，调用方退出。bus 连接由 `SingleInstanceGuard` 自持到 `release()`，断连即释放名字。 |

## 缓存与持久化

| 文件 | 作用 |
| --- | --- |
| `cover_cache.py` | **封面磁盘缓存**（`~/.cache/quaverq/covers/`）。文件名 `sha1(url) + 扩展名`；`get_path` 同步秒级查询给 UI 渲染前用，命中时按节流刷新 mtime 充当 LRU 访问时间；`fetch` 异步用 `niquests` 同步下载放进 `to_thread`，新下载后触发上限淘汰。`max_bytes <= 0` = 不限。 |
| `home_cache.py` | **首屏发现页快照**（`~/.cache/quaverq/home.json`）。SWR：先显示上次缓存，再后台刷新。公共区块无条件恢复（今日推荐 / 新歌 / 排行榜），私有区块（猜你喜欢 / 我的歌单 / 身份画像 `profile`）按 `account_key`（`hash(musicid)`）逐块匹配才恢复，登出 `clear_private()` 全部抹掉。`update(**sections)`：`None` 表示该区块本次不更新（保留旧值），`[]` 表示明确清空（`profile` 是单对象无清空形参，登出走 `clear_private`）。在运行中的 asyncio/qasync 事件循环里，连续 `update()` 会在短窗口内合并成一次磁盘写；`load()` 优先读 pending raw，保证刷新后立即可见，`flush()` 可在收尾时强制落盘。`daily` 区块写入时附 `updated_at` 时间戳，`HomeSnapshot.daily_updated_at` 给上层判 TTL 用（启动 6h 内复用缓存，不主动重拉猜你喜欢）。 |
| `lyric_cache.py` | **歌词磁盘缓存**（`~/.cache/quaverq/lyrics/`）。按 `mid + with_translation` 生成 sha1 文件名，保存解析后的 `Lyric`（含逐字 `words` 和翻译），启动 / 切歌时可同步 prime 当前歌词首帧；网络刷新成功后覆盖，缺失 / 损坏 / schema 版本不符返回 `None` 不抛。 |
| `state.py` | **会话快照**（`~/.config/quaverq/state.json`）。退出存 / 启动恢复 `queue + current_index + position + mode`。`play_mode` 用 `enum.name` 持久化，未知值回退 `SEQUENCE`。不自动恢复播放——UI 显示历史 queue 但停在 paused 状态。 |
| `download_store.py` | **下载记录持久化**（`~/.config/quaverq/downloads.json`，配置型数据**不放 CACHE_DIR**）。`DownloadRecord`（song + path + quality_label + size + downloaded_at，`file_exists()` 查本地文件是否还在）；`DownloadStore` 内存镜像 + 持久化，`load()`（不存在/损坏返 `[]` 不抛）/ `add`（按 mid 去重，原位替换或追加）/ `remove` / `find(mid)` / `all()`，`add`/`remove` 立即原子落盘（tmp + `os.replace`）、显式 UTF-8。供下载页重启恢复历史 + 播放核心按 mid 定位本地文件（本地优先播放）。Song↔dict 复用 `serde`。 |

## 模块边界

- **无 Qt 引入**：`from PySide6 ...` 在本目录禁止；要 GUI 状态请去 `bridge/`。
- **路径由 controller 注入**：`CoverCache(path)` / `HomeCache(path)` / `LyricCache(path)` / `SessionState(path)`，本目录不写 `~/.cache/...` 这种隐式常量，方便测试覆盖。
- **错误容忍**：缓存类的 `load()` 一律对损坏/缺失返回空快照，绝不抛；服务层把网络异常显式分类（`CredentialExpiredError` / `is_credential_expired_error`）。
- **异步**：服务层、MPRIS、封面下载都是 `async`，由上层 `qasync` 事件循环驱动；纯计算（`lyric`, `queue`, `serde`）保持同步。
