# 调查文档：QQ 音乐"收藏 / 取消收藏歌单"接口

> 状态：✅ 已实测验证（2026-06-27）。可直接据此落地。

## 1. 背景与任务

项目用的 `qqmusic-api-python`（L-1124 fork，git pin）**只暴露了读收藏歌单**
（`user.get_fav_songlist` → `music.musicasset.PlaylistFavRead` / `CgiGetPlaylistFavInfo`），
**没有收藏 / 取消收藏歌单的写接口**。`songlist` 模块的 `create/delete` 是管理自建歌单、
`add_songs/del_songs` 是歌单内增删歌曲，都不是"收藏别人的歌单"。

任务：调研出"收藏 / 取消收藏歌单"的真实 `musicu.fcg` 接口（module / method / param），
并**真机验证**，为后续接入 `service` + UI 做准备。

## 2. 调研方法

两段式：

1. **多源逆向调研**（4 路并行）锁定候选接口名与参数：
   - jsososo/QQMusicApi（最流行的 Node 逆向项目）
   - QQ 音乐 web/客户端 `musicu.fcg` 协议（开源逆向库的真实请求代码）
   - Python 版 QQMusicApi 各 fork 的 issues/PR/源码
   - 本地已装库 + 本仓 `service.py` 的请求约定（确定探针走哪条通道）
2. **真机探针验证**：走 `_bypass_post` 实打 `https://u.y.qq.com/cgi-bin/musicu.fcg`，
   用一个**公开、未收藏、非自建**的歌单做闭环——
   收藏 → 回读收藏列表确认出现 → 取消 → 回读确认消失，**测完恢复原状**。

## 3. 候选汇总（调研阶段）

各来源对 module 高度一致（`music.musicasset.PlaylistFavWrite`，与读接口 `PlaylistFavRead` 同
namespace），分歧在 method 命名与 param 字段：

| # | method | param | 区分收藏/取消 | 来源 | 把握度 |
|---|--------|-------|--------------|------|--------|
| A | `FavPlaylist` | `{uin, v_tid:[int], opertype}` | `opertype` 1=收藏 / 2=取消 | power721/Harmony（Python 客户端 + 单测） | high |
| B | `FavPlaylist` / `CancelFavPlaylist` | `{uin, v_playlistId:[int]}` | 不同 method 名 | tlyanyu/multiPlatformMusicApi（JS）+ hongyun-robot/qqmusic（文档） | high |
| C | `CgiAddPlaylistFav` / `CgiDelPlaylistFav` | `{optype, dissid, uin}` | 方法名 + optype | 本地库命名对称推断 | low |
| — | 旧 CGI `fcg_qm_order_diss.fcg` | `{dissid, optype, g_tk...}` | optype 1/2 | jsososo（旧 fcgi-bin 端点，硬编码 g_tk） | 历史，不用 |

旁证：同 namespace 的专辑收藏是 `music.musicasset.AlbumFavWrite` + `FavAlbum`/`CancelFavAlbum`
+ `v_albumMid`，与候选 B 同构。

## 4. 实测验证

探针走本仓 `_bypass_post`（与已确认可用的 `_fetch_fav_songlist_via_bypass` 同通道，
用 `self._ct_value` 跳过库默认 `ct=11` 的降级响应；登录态由 comm 的 `qq/authst` 自动注入）。
逐个候选打，以**回读收藏列表**为唯一判据。

实测结果：

```
收藏 FavPlaylist  {uin: owCF7KcPoioq7c**, v_playlistId: [9578424174]}
  -> {'reason': '', 'result': 0, 'v_failedPlaylistId': []}        回读: 出现 ✅
取消 CancelFavPlaylist {uin: owCF7KcPoioq7c**, v_playlistId: [9578424174]}
  -> {'reason': '', 'result': 0, 'v_failedPlaylistId': []}        回读: 消失 ✅（恢复原状）
```

**被真机证伪的候选**（重要，避免照抄）：

- ❌ 候选 A（`v_tid` + `opertype`）：返 `{'reason':'no valid playlist in req','result':1}`。
  虽有 Python + 单测佐证，但本账号/端点不吃。
- ❌ `uin` 用 `str(musicid)`：同样 `no valid playlist`。**必须用 `encrypt_uin`**（与读接口一致）。
- ⚠️ 成功字段是 **`result`**（=0 成功），**不是** `retCode`（库里其它写接口看 `retCode`，此接口不同）。

## 5. 最终确认的接口规格 ✅

| 项 | 值 |
|----|----|
| module | `music.musicasset.PlaylistFavWrite` |
| 收藏 method | `FavPlaylist` |
| 取消 method | `CancelFavPlaylist` |
| param | `{"uin": <cred.encrypt_uin>, "v_playlistId": [<歌单 pid/dissid, int>]}` |
| 成功判定 | 返回 dict 的 **`result == 0`** |
| 返回形状 | `{"result": 0, "reason": "", "v_failedPlaylistId": [...]}` |
| sign | 不需要 |
| 通道 | `_bypass_post(module, method, param, require_login=True)` |

## 6. 已知坑

- **id 用歌单 `pid/dissid`（别人的公开歌单），不是 `dirid`**（dirid 是自建歌单本地目录，
  201 = "我喜欢"）；混淆是最常见失败原因。
- **`uin` = `cred.encrypt_uin`**（形如 `owCF...**`），不是 `musicid`。
- 成功看 **`result`** 字段；`v_failedPlaylistId` 非空 = 部分失败。
- `_fetch_fav_songlist_via_bypass` 单页 cap=50，回读判定靠"新收藏置顶出现"，不靠总数变化。
- 必须登录（`require_login=True`）；无 `musickey` 直接返 None。

## 7. 与现有代码的衔接

- 读接口锚点：`service.py` 的 `get_fav_songlist` / `_fetch_fav_songlist_via_bypass`
  （`music.musicasset.PlaylistFavRead` / `CgiGetPlaylistFavInfo`，param `{uin: encrypt_uin, offset, size}`）。
- 请求通道：`service.py:_bypass_post`（`u.y.qq.com/cgi-bin/musicu.fcg`，curl_cffi 官方 TLS 指纹）。
- 命名对照：`music.musicasset.PlaylistBaseWrite`（AddPlaylist/DelPlaylist，自建歌单）、
  `PlaylistDetailWrite`（AddSonglist/DelSonglist，歌单内歌曲）。

## 8. 落地建议（下一步，待批）

1. **service**：加 `fav_playlist(pid)` / `unfav_playlist(pid)` —— 走 `_bypass_post` +
   `PlaylistFavWrite` / `FavPlaylist`·`CancelFavPlaylist`，判 `result == 0` 返 bool；
   凭据过期类异常透传。配 `tests/test_*.py` mock `_bypass_post` 覆盖 result=0/1 + 字段断言。
2. **controller + QML**：歌单详情页加"收藏 / 已收藏"切换按钮（参照 `LikeButton`）；
   写成功后刷新 `get_fav_songlist`（库侧 SWR），并据此初始化按钮态。
3. 更新 `src/quaverq/core/README.md` 的 `service.py` 行。

## 9. 参考来源

- power721/Harmony — `plugins/builtin/qqmusic/lib/qqmusic_client.py`（候选 A，被证伪）
- tlyanyu/multiPlatformMusicApi — `platforms/qqmusic/module/playlist_subscribe.js`（候选 B，命中）
- hongyun-robot/qqmusic — README（候选 B 旁证）
- luren-dc/QQMusicApi、L-1124/QQMusicApi — 只读 `PlaylistFavRead`（namespace 锚点）
- jsososo/QQMusicApi — `routes/songlist.js`（旧 CGI `fcg_qm_order_diss.fcg`，历史参考）
