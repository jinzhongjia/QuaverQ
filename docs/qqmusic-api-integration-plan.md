# qqmusic-api 集成落地计划

- 调研依据: [qqmusic-api-survey.md](qqmusic-api-survey.md)
- 制定日期: 2026-06-07
- 适用版本: `qqmusic-api-python==0.6.1`

按 **"零 UI 改动 → 既有 UI 加挂点 → 新页面"** 三档分批接入. 前两档全部塞进现有 controller, 不动 QML 顶层结构, 测试夹具复用现成的 `types.SimpleNamespace` mock; 第三档才需要新 view + 新 controller, 工作量阶跃式上升.

---

## 第一档 (零 UI 改动)

目标: 用户无感知, 体验默默变好. 单个 PR 可落.

### 1.1 `login.refresh_credential` — 凭据静默续命

- **接入点**: `core/service.py:356 probe_login_expired()`. `check_expired() == True` 时, 先 `await self._client.login.refresh_credential()`, 成功 → `_assign_credential(new)` + 返回 `False`; 失败 (`CredentialRefreshError`) → 返回 `True` 走旧 expired 流程.
- **落盘**: 新 credential 通过 `ServiceController` 同步回现有 credential store (复用 prime 路径用的同一个 key), 下次启动不会回到旧 cred.
- **启动期不变**: `prime_credential_sync()` 是同步路径, 不塞异步刷新; 只在 `ServiceController.start()` 之后挂一个 (可选) 定时刷新, 默认随每次 `probe_login_expired` 触发即可.
- **测试**: `tests/test_service_refresh_credential.py`, mock `client.login.check_expired` / `refresh_credential` 为 `SimpleNamespace`, 覆盖 3 个契约: (a) 快过期 → 刷新成功 → 不抛错 + 新 cred 写入; (b) 刷新失败 → 走旧 expired; (c) `check_expired` 本身就报登录过期错时也走刷新尝试.

### 1.2 `user.get_fav_songlist` — 补"我收藏的歌单"

- **接入点**: `LibraryController` 加 `favSonglists` model. QML 里"我的"tab 已经有 grid 容器, 复用 `_to_playlist_brief`.
- **库 vs bypass**: 先试 0.6.1 库方法; 若返回 pydantic 解析炸 (类似 `get_fav_album` 的 v_list bug) 再退 bypass.
- **测试**: 契约测试同 `get_fav_albums`, mock `client.user.get_fav_songlist`.

---

## 第二档 (既有页面挂卡片)

目标: "发现"链路扩展, 用户感知明显. 每条独立 PR, 互不阻塞.

### 2.1 `song.get_similar_song` + `song.get_related_songlist`

- **接入点**: 新增 `service.get_song_related(song_mid) -> SongRelated` (`asyncio.gather` 并发两个调用); `DetailController` 的歌曲详情面板底部加两个 horizontal list.
- **触发**: 详情页打开懒加载. **不进 SWR 首帧链路**.

### 2.2 `singer.get_similar` + `singer.get_album_list` / `get_songs_list`

- **接入点**: 歌手页 `detail_controller.py` 已有 `singerTab`, 加"全部专辑" / "全部歌曲" / "相似歌手"三个子 tab. 分页参数透传, 不一次拉全部.

### 2.3 `songlist.create` / `songlist.delete` — 闭合 CRUD

- **接入点**: `LibraryController` + "我的歌单"加 `+ 新建` / 右键 `删除`. 已经有 `add_songs` / `del_songs`, 这两个补完后是真正可写库.
- **UX**: 删除二次确认 dialog, 不能误触.

### 2.4 `song.get_detail` / `get_labels` / `get_producer` — 歌曲信息浮层

- **接入点**: 播放栏 / 列表项右键"歌曲信息"打开 popup. 不进主路径, 不影响首帧.

---

## 第三档 (新页面)

排到 v1 GA 之后或单独 milestone.

### 3.1 `user.get_music_gene` — 音乐画像页

- 新 view + 新 controller, 数据契约要单独设计. 先写探针脚本看一遍 gene 接口返回结构再设计.
- 这是差异化卖点, 但 ROI 不如前两档稳, 不挤 v1 GA.

---

## 跨档执行约定

1. **TDD 硬约束**: 每接一个 API 都先写 `tests/test_service_<feature>.py`, mock `_client.<ns>.<method>` 为 `types.SimpleNamespace`, 红 → 实现 → 绿. (CLAUDE.md "开发必须做的事".)
2. **bypass vs 库方法**: 调研已说"项目用 bypass 拿首页/排行/雷达是为 `ct` 风控自由度, 不要回退到库方法". 新接口默认先用库方法, 只有库方法挂 (pydantic 解析炸 / 风控拒) 才退 bypass, 注释里写明原因 + 0.6.1 版本号.
3. **不动 SWR 首帧契约**: 新接口一律懒加载, 不塞进 `prime_*_from_cache`. (CLAUDE.md "禁止破坏 SWR 首帧契约".)
4. **README 同步**: 每接一档同步 `src/quaverq/core/README.md` 和 `bridge/<dir>/README.md`, 加新方法说明. (CLAUDE.md "Readme 维护".)
5. **commit 风格**: 中文 Conventional `feat(qq)`/`feat(library)`/`feat(detail)`, 不带任何 LLM Co-Authored-By.
6. **不重复 `start()`**: 走 `call_service()` / `_ensure_started()` 统一入口, 不要绕开 `_start_lock`. (CLAUDE.md "禁止重复 start()".)

---

## 当前进度

- [ ] 1.1 `login.refresh_credential` — **进行中**
- [ ] 1.2 `user.get_fav_songlist`
- [ ] 2.1 `song.get_similar_song` + `get_related_songlist`
- [ ] 2.2 `singer.get_similar` + 列表
- [ ] 2.3 `songlist.create` / `delete`
- [ ] 2.4 `song.get_detail` / `get_labels` / `get_producer`
- [ ] 3.1 `user.get_music_gene`
