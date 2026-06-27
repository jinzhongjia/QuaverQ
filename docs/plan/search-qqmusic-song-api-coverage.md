# 调研：qqmusic-api 歌曲接口覆盖情况

## 任务描述

排查 `qqmusic-api-python`（git pin `0ef9645`）的 `SongApi`（`client.song.*`）暴露的歌曲接口，
对照本项目 `src/quaverq/core/service.py` 的实际使用，找出**还没支持的歌曲接口**。

## 调研结果

库 `modules/song.py` 的 `SongApi` 共 **13 个公开接口**。逐一对照：

| # | 库接口 | 作用 | 项目状态 | 入口 |
|---|--------|------|----------|------|
| 1 | `get_detail(value)` | 歌曲详情 | ✅ | `service.get_song_info` |
| 2 | `get_labels(songid)` | 歌曲标签 | ✅ | `service.get_song_info` |
| 3 | `get_producer(value)` | 制作人 | ✅ | `service.get_song_info` |
| 4 | `get_similar_song(songid)` | 相似歌曲 | ✅ | `service.get_similar_songs` |
| 5 | `get_related_songlist(songid)` | 相关歌单 | ✅ | `service.get_related_songlists` |
| 6 | `get_song_urls(...)` | 播放/下载链接 | ⚠️ 绕过 | `service.get_song_url`（自拼 vkey，故意不走库方法，见 service.py 文件头注释）|
| 7 | `query_song(value)` | 按 id/mid 批量取歌曲信息 | ❌ 未支持 | — |
| 8 | `get_related_mv(songid, last_mvid)` | 歌曲相关 MV（分页）| ❌ 未支持 | — |
| 9 | `get_other_version(value)` | 其他版本（现场/翻唱/remix）| ❌ 未支持 | — |
| 10 | `get_fav_num(song_ids)` | 歌曲收藏数 | ❌ 未支持 | — |
| 11 | `get_sheet(mid, ttype)` | 相关曲谱（用户/AI/虫虫钢琴）| ❌ 未支持 | — |
| 12 | `has_sheet(mid)` | 是否有曲谱 | ❌ 未支持 | — |
| 13 | `get_cdn_dispatch()` | 音频 CDN 调度信息 | ✅ 已接 | `service._get_cdn_prefix`（2026-06-27 补，替代硬编码兜底域名）|

**未支持歌曲接口共 6 个**：第 7–12 行（`get_song_urls` 已用自拼 vkey 覆盖；`get_cdn_dispatch`
已于 2026-06-27 接入，详见下方"已落地"）。

### 已落地：get_cdn_dispatch 动态 CDN 调度（2026-06-27）

裸路径 `purl` 原先硬编码拼 `https://isure.stream.qqmusic.qq.com/`，改走 `get_cdn_dispatch`
拿服务端按当前网络调度的节点：`service._get_cdn_prefix`（`_cdn_lock` 双检并发只发一次、按服务端
`cache_time/expiration` 做 TTL 缓存；失败/无兼容 host/未连接回落原兜底域名），`_try_bypass_urls`
仅在出现裸路径时按需取一次。

**关键坑（实测修正）**：`sip[0]` 真机返 `aqqmusic.tc.qq.com`，它不在 `StreamProxy` 的 SSRF
白名单 `.qqmusic.qq.com`（`bridge/stream_proxy.py`）内，FFmpeg 经回环代理时被代理自己拒成
**403**。修正：`_pick_stream_host` 只挑 `.qqmusic.qq.com` 族 host（`sjy6/ws6/ws.stream.qqmusic.qq.com`，
vkey purl 在它们上实测全 206）。诊断脚本 `scripts/debug_cdn_dispatch.py`，测试
`tests/test_service_cdn_dispatch.py`。

## 结论与建议

按对桌面播放器的价值，值得接的只有 2 个：

- **`get_related_mv`** — 相关 MV。现有歌曲详情页已有"相似歌曲 + 相关歌单"
  （`song_detail_controller` + `get_song_related`），MV 是同款自然扩展。
- **`get_other_version`** — 其他版本，详情页"换个版本听"。

暂不建议接的 5 个（边角/底层，YAGNI）：

- `get_sheet` / `has_sheet` — 曲谱（钢琴/吉他谱），播放器用不到。
- `get_fav_num` — 收藏数，纯 UI 装饰。
- `query_song` — 队列/歌单里已携带完整 `Song` 对象，无"只有 mid 待回填"场景。

## 预期目标

如需补齐，优先 `get_related_mv` + `get_other_version`：在 `service.py` 各加一个
`async` 包装方法（参考既有 `get_similar_songs` / `get_related_songlists` 的写法 +
回归测试），并接到歌曲详情页。其余 5 个保持不接。
