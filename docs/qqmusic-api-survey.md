# qqmusic-api-python 接口集成调研

- 库版本: `qqmusic-api-python==0.6.1` (见 `pyproject.toml`)
- 调研日期: 2026-06-07
- 比对源: `src/quaverq/core/service.py` (项目当前对接面)
- 库源路径: `.venv/lib/python3.14/site-packages/qqmusic_api/`

目的: 枚举库内未被项目使用、但对桌面音乐播放器 (Linux, PySide6 + QML) 有集成价值的接口, 并按优先级分档.

---

## 当前已集成清单

来自 `client.<namespace>.<method>` 直调:

- `client.search.search_by_type` (SONG / SINGER / ALBUM / SONGLIST)
- `client.search.get_hotkey` / `client.search.complete`
- `client.album.get_detail` / `client.album.get_song`
- `client.songlist.get_detail` / `add_songs` / `del_songs`
- `client.singer.get_info` / `client.singer.get_tab_detail(TabType.SONG)`
- `client.user.get_fav_song` / `get_created_songlist` / `get_follow_singers`
- `client.login.get_qrcode` / `check_qrcode` / `check_expired`

通过 `_bypass_post(musicu.fcg)` 直拼实现 (绕开库默认 `ct=11` 风控):

- vkey 播放链 (`music.vkey.GetVkey / UrlGetVkey`)
- 歌词 QRC + LRC + 翻译 (`music.musichallSong.PlayLyricInfo`)
- 推荐歌单 (`music.playlist.PlaylistSquare / GetRecommendFeed`)
- 排行榜 (`music.musicToplist.Toplist / GetAll + GetDetail`)
- 新歌速递 (`newsong.NewSongServer / get_new_song_info`)
- 雷达推荐 (`music.recommend.TrackRelationServer / GetRadarSong`) + 私人 FM 回退 (`music.radioProxy.MbTrackRadioSvr / get_radio_track`)
- 收藏专辑 (`music.musicasset.AlbumFavRead / CgiGetAlbumFavInfo`, 因库版 `v_list` pydantic 解析 bug 走 bypass)

---

## 推荐集成接口

### 最高优先级 (低成本、用户可感)

| 接口 | 用途 | 接入位置建议 |
| --- | --- | --- |
| `client.login.refresh_credential` | 凭据过期前静默续命 | `service.probe_login_expired()` 流程 / 定时任务, 减少用户重新扫码 |
| `client.songlist.create` / `client.songlist.delete` | 自建歌单的创建 / 删除 | `LibraryController` + "我的歌单" tab 加 `+ 新建` 按钮; 配合既有 `add_songs` / `del_songs` 形成完整 CRUD |

### 高价值 (扩展"发现"链路)

| 接口 | 用途 |
| --- | --- |
| `client.song.get_similar_song(songid)` | 当前曲目"相似歌曲"卡片 |
| `client.song.get_related_songlist(songid)` | "包含此曲的相关歌单" |
| `client.singer.get_similar(mid)` | 歌手详情页底部"相似歌手"模块 |
| `client.user.get_music_gene(euin)` | "我的音乐画像"页面, 差异化卖点 |

### 中等价值 (浏览 / 库管理 完善)

| 接口 | 用途 / 备注 |
| --- | --- |
| `client.user.get_fav_songlist` | 收藏的歌单 (目前仅有收藏的专辑) |
| `client.user.get_fav_album` | ⚠ 项目当前用 `_bypass_post` 绕开 `v_list` pydantic 解析 bug, 0.6.1 若未修复保持现状 |
| `client.singer.get_singer_list_index` | 歌手按字母 / 地区分类浏览页 |
| `client.singer.get_album_list` / `get_songs_list` | 歌手详情页加 "全部专辑" / "全部歌曲" tab (当前只展示热门) |
| `client.song.get_detail` / `get_labels` / `get_producer` | 歌曲信息浮层: 语种 / 标签 / 制作人 / 作词作曲 |
| `client.user.get_vip_info` | 设置页显示 VIP 状态, 辅助解释音质 / 解锁限制 |

### 可选 (体验补完、面窄)

- `client.login.send_authcode` + `phone_authorize` — 手机号登录补一个登录方式选项 (现有 QR 已足够)
- `client.user.get_homepage(euin)` — "我的"页面顶部资料卡
- `client.comment.get_hot_comments` — 歌曲热评区块, 需新 UI

---

## 不建议集成

- **`modules/private_message.*`** — 私信系列, 与播放器主线无关
- **`modules/mv.*`** (`get_detail` / `get_mv_urls`) — 视频播放需 QtMultimedia video sink, 复杂度远高于音频; v1 Linux 优先目标下 ROI 低
- **`modules/recommend.*` / `modules/top.*` 库方法** — 项目已用 `_bypass_post` 拿到同源数据, 且 bypass 路径享有 `ct` 风控自由度, 切换到库方法是负优化

---

## 建议落地顺序

1. `login.refresh_credential` + `songlist.create` / `delete` — 工程量均在百行内, 有现成 controller 挂点
2. `song.get_similar_song` + `song.get_related_songlist` — 在歌曲详情 / 迷你播放器旁挂"相关"卡片
3. `singer.get_similar` — 歌手详情页底部模块
4. `user.get_music_gene` — 新增"音乐画像"页面 (独立 view, 工作量略大但卖点强)
5. 其余按 UI 设计节奏滚动接入
