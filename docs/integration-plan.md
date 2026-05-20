# QuaverQ 完整集成方案 — QQ 音乐 × Spotify 体验

> 把 QuaverQ 从「搜索 + 单曲试听」原型升级为接近 Spotify 桌面客户端的完整播放器。
> 范围：QQ 音乐 API 全量集成 + 本地库 + 桌面媒体集成。

---

## 0. 协作方式

**TDD 驱动 + 分阶段实现 + 逐步人工验证**。不一次性铺开。每一步先写测试 → 写实现 → 用户跑一遍 → 反馈 → 继续。

### 0.1 TDD 工作流

每个步骤的标准节奏：

1. **写测试** (`tests/test_*.py`)：覆盖该步骤的核心契约 (输入 → 输出、状态机、边界、回归)
2. **跑测试** → 应该红（新功能没实现 / 老 bug 未修）
3. **写实现** (`src/quaverq/...`)
4. **跑测试** → 绿
5. **手动验证清单** → 用户跑 `uv run quaverq` 实测，覆盖测试覆不到的（UI 表现、跨进程行为、依赖外部服务的端到端流）

测试框架：`pytest` + `pytest-asyncio` (async-mode=auto)。
分类：
- `tests/test_<module>.py` — 单元测试，QQ API 走 SimpleNamespace mock
- `tests/integration/` (P1+) — 真实 API 集成测试，需登录态，默认 `@pytest.mark.integration` skip

每次步骤完成时 Claude 提交的内容必须包含：
- 新增/修改的 `tests/*.py`（**必备**）
- 实现代码
- 一份「如何手动验证」清单（覆盖测试不到的部分）

### 0.2 节奏

- 每个分期 (P0/P1/P2/P3) 拆为若干"步骤" (见 §14)
- 一次只动一个步骤的代码 ≤ ~300 行变更（不含测试），方便人工审阅与回归
- Claude 在每步完成后给出：
  1. 新增/修改的测试 + 它们覆盖了什么
  2. 修改了哪些实现文件 + 关键设计点
  3. **如何手动验证**（测试覆不到的，具体跑什么命令、点哪个按钮、看哪个日志/UI 表现）
  4. 已知盲点（哪些情况没覆盖，需要人工探一下）

### 0.3 用户验证流程

- 用户拉新代码 → `uv run --group dev pytest` (必绿) → `uv run quaverq` 按手动清单过一遍
- 通过 → 回复"过了" / "下一步" → 进入下一步
- 失败 → 贴错误日志 / 截图 → Claude 先复现到测试里再修
- 调整方向 → 用户在"步骤"之间插入新需求 → Claude 更新本文档的进度块

### 0.4 进度跟踪

每个步骤前的 checkbox 反映当前状态：

- `[ ]` 未开始
- `[~]` 进行中 (Claude 已动手, 等用户验证)
- `[x]` 已验收

进度仅在本文档第 14 节维护；不另开 issue/PR 列表。

---

## 1. 目标与边界

### 1.1 In-Scope (P0 → P2)

| 能力 | 描述 |
|---|---|
| 首页发现 | 个性推荐 / 雷达 / 新歌速递 / 热门歌单 / 排行榜入口 |
| 完整搜索 | 综合 + 按类型 (歌曲/歌手/专辑/歌单/MV/歌词命中)，含建议词与热搜 |
| 个人库 | 我喜欢 / 我创建/收藏的歌单 / 收藏的专辑 / 关注的歌手 |
| 详情页 | 专辑 / 歌手 / 歌单 / 歌曲 (相似歌曲、制作人、相关歌单) |
| 现在播放 | 大封面 / 同步歌词 / 队列侧栏 |
| 播放策略 | 顺序 / 单曲 / 列表循环 / 随机 / 跨曲队列 |
| 音质 | MP3_128 ↔ MP3_320 ↔ FLAC ↔ Master (按 VIP 与 cookie 自动降级) |
| 桌面集成 | MPRIS2 (媒体键 / GNOME 通知 / KDE 媒体控件) |
| 会话恢复 | 启动恢复上次队列、当前曲、播放位置、音量、循环模式 |
| 离线缓存 | 已听过的歌可本地复用 (LRU + 配额) |

### 1.2 Out-of-Scope

- 上传 / 个人音乐云盘 / 听歌识曲
- 付费 / VIP 续费流程
- 社交动态 / 好友圈 / 分享卡片
- DRM 受限内容 (Atmos / DTS_X — API 返回，但服务端常拒绝非客户端来源)
- 评论流互动 (只读展示可放 P3)

---

## 2. 现状 vs 缺口

### 2.1 已实现

- `qqmusic_api.Client` 连接 / 凭据持久化 (`~/.config/quaverq/credential.json`)
- 二维码登录 + 过期检查
- 综合搜索 (只用了歌曲分支)
- 歌曲 URL 获取 (硬编码 `MP3_128`)
- GStreamer playbin (play/pause/resume/stop/seek)
- Qt + GTK 4/Libadwaita 双前端，异步运行时与主线程派发
- 欢迎页 / 扫码登录 / 搜索结果 / 底部播放栏

### 2.2 缺口（按重要性）

1. 队列：没有"下一首"概念，单曲播完即止
2. 详情页：点开专辑/歌手/歌单 → 没有视图
3. 个人库：登录后看不到 fav_song / created_songlist
4. 歌词：API 已能取，UI 没渲染
5. 首页发现：完全空白
6. MPRIS：媒体键失效、桌面无 Now Playing
7. 音质：固定 128k
8. 缓存：每次重启全冷启动
9. 会话恢复：关掉就丢

---

## 3. API 能力对照 — QQ × Spotify × QuaverQ

| QQ API (qqmusic-api-python)          | Spotify 概念              | QuaverQ 视图          |
| ------------------------------------ | ------------------------- | --------------------- |
| `recommend.get_home_feed`            | Home                      | `HomeView`            |
| `recommend.get_guess_recommend`      | Daily Mix                 | `HomeView`            |
| `recommend.get_radar_recommend`      | Release Radar             | `HomeView`            |
| `recommend.get_recommend_newsong`    | New Releases              | `HomeView`            |
| `recommend.get_recommend_songlist`   | Featured Playlists        | `HomeView`            |
| `top.get_category` / `get_detail`    | Charts                    | `TopChartsView`       |
| `search.get_hotkey` / `complete`     | Search Suggestions        | `SearchView (intro)`  |
| `search.general_search`              | Global Search             | `SearchView`          |
| `search.search_by_type`              | Search filters (tabs)     | `SearchView`          |
| `album.get_detail` + `get_song`      | Album page                | `AlbumView`           |
| `singer.get_info` + `get_*`          | Artist page               | `ArtistView`          |
| `songlist.get_detail`                | Playlist (read)           | `PlaylistView`        |
| `songlist.create/add/del/delete`    | Playlist (edit)           | `PlaylistView (edit)` |
| `song.get_detail` + `get_lyric`      | Track Details             | `NowPlayingView`      |
| `song.get_song_urls`                 | Audio resolver            | `Player`              |
| `song.get_similar_song`              | Song Radio                | `NowPlayingView`      |
| `lyric.get_lyric`                    | Synced Lyrics             | `LyricView`           |
| `user.get_fav_song`                  | Liked Songs               | `LibraryView`         |
| `user.get_created_songlist`          | Your Playlists            | `LibraryView`         |
| `user.get_fav_album/songlist`        | Saved Albums/Playlists    | `LibraryView`         |
| `user.get_follow_singers`            | Followed Artists          | `LibraryView`         |
| `user.get_vip_info`                  | VIP 状态                  | `SettingsView`        |
| `mv.*`                               | Music Videos              | (P3)                  |
| `comment.*`                          | Track Comments            | (P3)                  |

`SearchType` 全表：`SONG=0, SINGER=1, ALBUM=2, SONGLIST=3, MV=4, LYRIC=7, USER=8, AUDIO_ALBUM=15, AUDIO=18`。
`SongFileType` 主流：`MP3_128, MP3_320, OGG_192, OGG_320, OGG_640, FLAC, NAC, MASTER, ATMOS_2/51/71` — 高码率绝大多数要 VIP，集成时按 cookie 能力做降级。

---

## 4. 架构

```
┌──────────────────────────────────────────────────────────────────┐
│ UI                                                                │
│  Qt (PySide6) | GTK 4 + Libadwaita                                │
│  HomeView · SearchView · LibraryView · AlbumView · ArtistView     │
│  PlaylistView · NowPlayingView · QueueView · LyricView · Settings │
└────────────────────┬─────────────────────────────────────────────┘
                     │ 事件 (ui.on / ui.show_*)
┌────────────────────▼─────────────────────────────────────────────┐
│ Controller (__main__.py)                                           │
│  - asyncio runner (后台事件循环)                                    │
│  - 事件→协程: search/play/like/queue/seek/...                       │
└──┬──────────────┬─────────────┬───────────┬────────────┬─────────┘
   │              │             │           │            │
┌──▼───────────┐ ┌▼──────────┐ ┌▼────────┐ ┌▼─────────┐ ┌▼────────┐
│ Service      │ │ Player    │ │ Queue   │ │ Library  │ │ MPRIS   │
│ core/service │ │ +GStreamer│ │ + Mode  │ │ +Cache   │ │ D-Bus   │
│ (API 门面)    │ │  + Gapless│ │  +History│ │ (SQLite)│ │         │
└──┬───────────┘ └───────────┘ └─────────┘ └──────────┘ └─────────┘
   │
┌──▼────────────────────┐
│ qqmusic_api.Client    │
└───────────────────────┘
```

### 4.1 关键原则

- **服务层薄而无状态**：`core/service.py` 只把 QQ API 包成 dataclass，不缓存
- **缓存独立**：`core/cache.py` 持有 SQLite，是服务的可选写穿包装 (TTL + LRU)
- **Player 与 Queue 解耦**：Player 只管单曲；Queue 监听 EOS 信号驱动 next
- **UI 与 Controller 通过事件解耦**：UI 不直接调 API/Player；全部 `_emit(event)` → Controller → `runner.submit(coro)`
- **MPRIS 单向写入 + 命令回流**：Player/Queue 状态变更推到 MPRIS；MPRIS 收外部命令调 Controller 暴露的 API

---

## 5. 数据模型 (`core/models.py`)

```python
@dataclass
class Singer:
    mid: str
    name: str
    avatar_url: str = ""

@dataclass
class Song:
    mid: str
    name: str
    singers: list[Singer]
    album_mid: str = ""
    album_name: str = ""
    cover_url: str = ""           # 三种规格 90/300/500 由 service 拼接
    duration: int = 0             # 秒
    pay_play: int = 0             # 0 免费 / 1 VIP / 2 单独购买
    file_qualities: set[str] = field(default_factory=set)  # {"MP3_128","FLAC",...}
    media_mid: str = ""           # 用于 get_song_urls

@dataclass
class SongUrl:
    mid: str
    url: str
    quality: str                  # "MP3_128" / "FLAC" / ...
    expires_at: int               # unix ts, 用于失效重取

@dataclass
class Album:
    mid: str
    name: str
    cover_url: str
    singers: list[Singer]
    publish_date: str = ""
    description: str = ""
    song_count: int = 0
    songs: list[Song] = field(default_factory=list)  # lazy 填充

@dataclass
class Playlist:
    pid: str                      # songlist dirid / id
    name: str
    cover_url: str
    description: str = ""
    creator: str = ""
    song_count: int = 0
    play_count: int = 0
    songs: list[Song] = field(default_factory=list)
    is_mine: bool = False         # 我创建的 / 收藏的

@dataclass
class LyricLine:
    timestamp_ms: int
    text: str
    translation: str = ""

@dataclass
class Lyric:
    mid: str
    lines: list[LyricLine] = field(default_factory=list)
    has_translation: bool = False
    has_romanji: bool = False     # 罗马音 (日韩歌)
```

旧 `Song.singer_names: list[str]` 会被 `singers: list[Singer]` 取代；现有调用站点（GTK/Qt list rendering、controller）需要同步改为 `" / ".join(s.name for s in song.singers)`。

---

## 6. 服务层 (`core/service.py`，从现 `core/api.py` 升级而来)

按 QQ API 分组，每个方法返回 dataclass：

```python
class QuaverService:
    # 生命周期
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...

    # 登录
    async def login_by_qrcode(self) -> bool: ...
    async def check_login_expired(self) -> bool: ...
    async def refresh_credential(self) -> bool: ...
    async def get_vip_info(self) -> VipInfo: ...

    # 首页发现 (并发 fan-out)
    async def get_home_feed(self) -> HomeFeed: ...
    async def get_daily_recommend(self) -> list[Song]: ...
    async def get_radar(self) -> list[Song]: ...
    async def get_new_songs(self) -> list[Song]: ...
    async def get_featured_playlists(self) -> list[Playlist]: ...

    # 排行榜
    async def get_top_categories(self) -> list[TopCategory]: ...
    async def get_top_detail(self, top_id: int) -> Playlist: ...

    # 搜索
    async def get_hotkey(self) -> list[str]: ...
    async def search_suggest(self, kw: str) -> list[str]: ...
    async def search(self, kw: str, kind: SearchKind, page=1, limit=30) -> SearchResult: ...

    # 详情
    async def get_album(self, album_mid: str) -> Album: ...           # detail + songs
    async def get_artist(self, singer_mid: str) -> Artist: ...        # info + top songs + albums
    async def get_playlist(self, pid: str) -> Playlist: ...           # 含全部歌曲
    async def get_song_detail(self, mid: str) -> SongDetail: ...
    async def get_similar_songs(self, mid: str) -> list[Song]: ...

    # 播放
    async def get_song_urls(self, songs: list[Song], quality: str) -> list[SongUrl]: ...
    async def get_lyric(self, mid: str, *, translation=True) -> Lyric: ...

    # 个人库
    async def get_liked_songs(self) -> list[Song]: ...
    async def get_my_playlists(self) -> list[Playlist]: ...
    async def get_saved_albums(self) -> list[Album]: ...
    async def get_saved_playlists(self) -> list[Playlist]: ...
    async def get_followed_singers(self) -> list[Singer]: ...

    # 歌单编辑
    async def create_playlist(self, name: str) -> Playlist: ...
    async def delete_playlist(self, pid: str) -> None: ...
    async def add_to_playlist(self, pid: str, mids: list[str]) -> None: ...
    async def remove_from_playlist(self, pid: str, mids: list[str]) -> None: ...
```

实现要点：
- 每个方法把 QQ pydantic 响应 → QuaverQ dataclass，封面 URL 在这里拼好 (`cover_url(300)`)
- 错误统一：QQ 返回 `result != 0` → 抛 `ServiceError(code, msg)`
- 并发：`get_home_feed` 用 `asyncio.gather` 并发请求 5 个子推荐 + 排行榜入口
- 限频：使用 `qqmusic_api.Client(rate=...)` 全局节流，避免被风控

---

## 7. 本地持久化

### 7.1 文件布局

```
~/.config/quaverq/
├── config.toml              # 用户偏好
├── credential.json          # 登录凭据 (already)
├── state.json               # 会话快照 (queue + position)
└── library.db               # SQLite

~/.cache/quaverq/
├── covers/                  # 封面图缓存 (sha1 → jpg)
├── audio/                   # 离线音频缓存 (LRU)
└── lyrics/                  # 歌词 JSON 缓存
```

### 7.2 SQLite schema (`core/cache.py`)

```sql
-- 歌曲元数据缓存 (TTL 7d)
CREATE TABLE song_meta (
  mid TEXT PRIMARY KEY,
  name TEXT, singer_json TEXT,
  album_mid TEXT, album_name TEXT,
  cover_url TEXT, duration INTEGER,
  pay_play INTEGER, qualities TEXT,
  media_mid TEXT,
  fetched_at INTEGER
);

CREATE TABLE album_meta (
  mid TEXT PRIMARY KEY,
  name TEXT, singer_json TEXT,
  cover_url TEXT, publish_date TEXT,
  description TEXT, song_count INTEGER,
  fetched_at INTEGER
);

CREATE TABLE playlist_meta (
  pid TEXT PRIMARY KEY,
  name TEXT, cover_url TEXT,
  description TEXT, creator TEXT,
  song_count INTEGER, play_count INTEGER,
  is_mine INTEGER,
  fetched_at INTEGER
);

CREATE TABLE playlist_track (
  pid TEXT, mid TEXT, position INTEGER,
  PRIMARY KEY (pid, mid)
);

-- 我喜欢 (QQ 端镜像 + 离线可见)
CREATE TABLE liked_song (
  mid TEXT PRIMARY KEY,
  added_at INTEGER
);

-- 播放历史
CREATE TABLE play_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mid TEXT, played_at INTEGER,
  played_ms INTEGER, completed INTEGER
);

CREATE INDEX idx_history_time ON play_history(played_at DESC);

-- 音频文件缓存索引
CREATE TABLE audio_cache (
  mid TEXT, quality TEXT,
  file_path TEXT, size INTEGER,
  added_at INTEGER, last_used_at INTEGER,
  PRIMARY KEY (mid, quality)
);

CREATE INDEX idx_audio_lru ON audio_cache(last_used_at);

-- 设置 (覆盖 config.toml 之外的运行时偏好)
CREATE TABLE setting (
  key TEXT PRIMARY KEY,
  value TEXT
);
```

读写策略：
- 写穿：`get_song_detail` 命中数据 → 同步入 `song_meta`
- 读优先缓存 + TTL：`fetched_at + ttl > now` 直接返回
- 失效：手动 `invalidate(mid)` 或 24h 后台清扫
- 离线音频：`audio_cache` LRU 上限可配 (默认 2 GB)

### 7.3 会话快照 `state.json`

```json
{
  "queue": ["mid1", "mid2", "..."],
  "current_index": 3,
  "position_ms": 84500,
  "play_mode": "shuffle",          // sequence | repeat_one | repeat_all | shuffle
  "volume": 0.7,
  "quality": "MP3_320"
}
```

启动时：读 `state.json` → 用 `cache.song_meta` 还原 Song 对象 → 放进 Queue → 不自动开播，停在暂停态。

---

## 8. 队列 (`core/queue.py`)

```python
class PlayMode(Enum):
    SEQUENCE = auto()       # 顺序播完即停
    REPEAT_ALL = auto()     # 列表循环
    REPEAT_ONE = auto()     # 单曲循环
    SHUFFLE = auto()        # 随机 (维护独立 shuffle order)

class PlayQueue:
    songs: list[Song]
    current_index: int
    mode: PlayMode
    _shuffle_order: list[int]   # 随机模式下的索引置换

    def push(self, songs: list[Song], play_now: bool = False) -> None: ...
    def insert_next(self, song: Song) -> None: ...    # "下一首播放"
    def clear(self) -> None: ...
    def next(self) -> Song | None: ...                # 根据 mode 决定下一首
    def prev(self) -> Song | None: ...
    def jump_to(self, index: int) -> Song: ...

    def on_song_end(self, completed: bool) -> Song | None:
        """Player 收到 GStreamer EOS 时调用; 返回下一首或 None."""
```

Queue 是无锁的，所有调用都在 asyncio 线程；UI 通过事件 `queue_changed` / `current_changed` 订阅。

---

## 9. 歌词 (`core/lyric.py`)

```python
def parse_lrc(raw: str) -> list[LyricLine]:
    """解析 [mm:ss.xx]text 格式; 多时间戳行展开."""

class LyricSync:
    """根据播放位置定位当前行 + 提供 ±N 行窗口."""
    def set_lyric(self, lyric: Lyric) -> None: ...
    def line_at(self, position_ms: int) -> int: ...
    def window(self, position_ms: int, before=2, after=4) -> list[LyricLine]: ...
```

UI 滚动：UI 用 200ms 定时器查 `position_ms`，调用 `LyricSync.line_at` 得到当前行索引，按索引滚动 `LyricView` 列表（GTK 用 `Gtk.ListView` + `scroll_to`，Qt 用 `QListWidget.scrollToItem`）。当前行用 `accent` / `bold`，前后行 `dim-label`。

---

## 10. MPRIS2 (`core/mpris.py`)

依赖：`dbus-next` (纯异步 D-Bus，pure-python，不需要 GLib)。

实现两个标准接口：
- `org.mpris.MediaPlayer2` — 应用元信息 + Raise/Quit
- `org.mpris.MediaPlayer2.Player` — 播放控制 + 元数据

```python
class MprisService:
    def __init__(self, controller: ControllerAPI): ...

    # 收命令 (来自媒体键 / GNOME 控件)
    async def Play(self) -> None: ...
    async def Pause(self) -> None: ...
    async def PlayPause(self) -> None: ...
    async def Next(self) -> None: ...
    async def Previous(self) -> None: ...

    # 状态变更 → 推 PropertiesChanged 信号
    def push_metadata(self, song: Song, cover_path: str) -> None: ...
    def push_playback_status(self, state: str) -> None: ...
    def push_position(self, position_us: int) -> None: ...
```

Bus name：`org.mpris.MediaPlayer2.quaverq`。
封面通过 `mpris:artUrl = file:///~/.cache/quaverq/covers/<sha>.jpg`，所以下载封面要落地磁盘。

---

## 11. 会话恢复 (`core/state.py`)

```python
class SessionState:
    def save(self, queue: PlayQueue, player: PlayerBackend) -> None:
        """退出钩子调用; 写 state.json."""

    def restore(self, queue: PlayQueue, player: PlayerBackend, cache: Cache) -> None:
        """启动时调用; 还原但不自动开播."""
```

退出顺序：UI quit → controller `_cleanup` → `session.save(...)` → `player.stop()` → `service.disconnect()` → `runner.shutdown()`。

---

## 12. UI 视图

### 12.1 导航 (`Adw.NavigationSplitView` / Qt 自实现 sidebar)

```
┌───────────┬──────────────────────────────────┐
│ QuaverQ   │ [view-specific header]           │
├───────────┼──────────────────────────────────┤
│ 🏠 首页    │                                  │
│ 🔍 搜索    │                                  │
│ 📚 资料库  │           主内容区               │
│ 🏆 排行榜  │                                  │
│ ──────    │                                  │
│ ❤️ 我喜欢  │                                  │
│ + 新建歌单│                                  │
│ • 歌单 A   │                                  │
│ • 歌单 B   │                                  │
├───────────┴──────────────────────────────────┤
│ [cover] Title—Artist  [▶] [─●────] 1:23/3:45 │
└──────────────────────────────────────────────┘
```

### 12.2 视图清单

| 视图 | 关键内容 |
|---|---|
| `HomeView` | 日推 Hero 卡 + 新歌轮播 + 推荐歌单网格 + 排行榜入口 |
| `SearchView` | 搜索框 + Tabs(全部/歌曲/歌手/专辑/歌单/MV) + 热搜（空态） |
| `LibraryView` | 4 Tabs: 喜欢的音乐 / 我的歌单 / 收藏的专辑 / 关注的歌手 |
| `TopChartsView` | 排行榜分类网格 → 进入 PlaylistView |
| `AlbumView` | 大封面 + 歌手/年份 + Tracklist + 操作栏 (播放/收藏/+到歌单) |
| `ArtistView` | 头图 + 简介 + 热门歌曲 + 专辑网格 + 相似歌手 |
| `PlaylistView` | 大封面 + 创建者 + Tracklist + 操作栏 |
| `NowPlayingView` | 全屏大封面 + 歌曲信息 + 同步歌词 + 控件 |
| `QueueView` | 侧栏抽屉，列出当前队列，可拖拽/删除 |
| `LyricView` | 单独抽屉/全屏歌词模式 |
| `SettingsView` | 音质偏好 / 缓存大小 / 主题 / VIP 状态 |

### 12.3 现有视图改造

- 把目前 `_MainWindow` 的 `_stack` 拆为：sidebar 导航 + 主区 ViewStack (GTK 用 `Adw.ViewStack` + `Adw.ViewSwitcher`)。
- 顶部搜索保留，但只在 `SearchView` 激活；其他视图各自的 header 由 `Adw.ToolbarView` 嵌入。

---

## 13. 关键流程

### 13.1 启动

```
main()
 ├─ AsyncRunner spin up
 ├─ Service.connect()
 ├─ load credential.json → service.set_credential() → check_login_expired()
 │   ├─ valid    → ui.set_authenticated(True), 异步预热 home feed
 │   └─ expired  → 清凭据，停留欢迎页
 ├─ Cache.open(library.db)
 ├─ SessionState.restore() → 恢复 queue + position (暂停态)
 ├─ Mpris.register()
 ├─ register UI callbacks
 └─ ui.run()        # 阻塞
```

### 13.2 点歌播放

```
UI: list_view.activate(idx)
 → emit("play_song", song)
   → controller submits coro:
       queue.push([song], play_now=True)
       url = service.get_song_urls([song], quality_pref)[0]
       lyric = service.get_lyric(song.mid)         # 并发
       cover = cache.fetch_cover(song.cover_url)   # 并发
       player.play(url)
       ui.set_now_playing(song)
       ui.set_lyric(lyric)
       mpris.push_metadata(song, cover_path)
       cache.record_play_start(song.mid)
```

### 13.3 自动下一首

```
GStreamer EOS bus message
 → player._on_eos() (主线程 GLib idle 派发)
 → controller submits coro:
     completed = (position_at_eos > 0.9 * duration)
     cache.record_play_end(mid, completed)
     next_song = queue.on_song_end(completed)
     if next_song: play(next_song)
     else: ui.set_play_state(False); mpris.push_status("Stopped")
```

### 13.4 喜欢/取消喜欢

```
UI heart-button toggle
 → emit("toggle_like", song)
   → controller submits:
       liked = library.is_liked(song.mid)
       if liked:
           library.unlike(song.mid)         # 本地立刻改
           service.unlike_song(song.mid)    # 调 QQ API
       else:
           library.like(song.mid)
           service.like_song(song.mid)
       ui.set_liked_state(song.mid, not liked)
```

QQ API 没有直接的 like/unlike 单曲方法，需要通过 `add_to_playlist(my_fav_pid, mid)` 与 `remove_from_playlist`。`my_fav_pid` 在登录时从 `user.get_created_songlist()` 取（第一个就是"我喜欢"）。

### 13.5 搜索建议 (debounced)

```
SearchEntry "changed" signal
 → 取消上一次 timer → 启动 250ms timer
 → fire timer:
   → submit: keywords = service.search_suggest(text)
   → ui.show_search_completions(keywords)
```

---

## 14. 分期实施 (进度跟踪)

> 状态符号：`[ ]` 未开始 / `[~]` 进行中等验证 / `[x]` 已验收
>
> 每个步骤由 Claude 一次提交，附"如何验证"清单。用户跑完回复"过了"才推进。

### P0 — 让现有客户端「能用」

| # | 状态 | 步骤 | 主要文件 | 验证要点 |
|---|---|---|---|---|
| P0.1 | `[x]` | service 重构 + 模型扩展 (Song.singers, Album, Playlist, Singer) + qqmusic-api 降到 0.4.1 (v0.5/0.6 服务端拒下发 VIP 完整版) + 38 单元测试 | `core/service.py`, `core/models.py`, `pyproject.toml`, `tests/` | ✅ 启动 / 搜索 / 凭据流转 / 真实 cookie 拿到 FLAC 完整 URL |
| P0.2 | `[x]` | 搜索按类型 (歌曲/歌手/专辑/歌单 4 Tabs) + Adw.ViewStack/ViewSwitcher + service.search_{songs,singers,albums,playlists} + highlight=False 清 HTML | `core/service.py`, `ui/{qt,gtk}/app.py` | ✅ 4 Tab 都能拿到对应类型数据, 真接 QQ API 验证 |
| P0.2.5 | `[x]` | GTK UI 现代化: HeaderBar 改 WindowTitle + 搜索框独立 top_bar + Tab 加 symbolic icon + Gtk.ListView→Gtk.ListBox+Adw.ActionRow+boxed-list | `ui/gtk/app.py` | ✅ Libadwaita 风格, 列表 title+subtitle+suffix 标准 |
| P0.3 | `[x]` | AlbumView / ArtistView / PlaylistView 三个详情页 (Adw.NavigationView push/pop) + 详情 API (album.get_detail/get_song, singer.get_info+get_tab_detail, songlist.get_detail) + HeaderBar 自定义返回按钮 + 修复 ResponseCodeError 2001 (search_by_type 显式带 credential) | `core/service.py`, `core/models.py`, `ui/gtk/app.py`, `__main__.py` | ✅ 从搜索点歌手/专辑/歌单能进详情, 点歌能播 |
| P0.4 | `[x]` | PlayQueue + 4 种 PlayMode + GStreamer EOS 自动 next + 4 按钮 transport (prev/play/next/mode) + 失败自动跳过 + 20 单元测试 | `core/queue.py`, `__main__.py`, `ui/gtk/app.py` | ✅ 多首连播验证; 模式 cycle 按钮在; 跨页面 (tab/详情) 入队 |
| P0.5 | `[x]` | 歌词同步滚动 (LRC 解析 + LyricSync + LyricView 点击 push + 行高亮 + 自动滚动) + 19 单元测试 | `core/lyric.py`, `core/service.py`, `ui/gtk/app.py`, `__main__.py` | ✅ 点歌曲信息进歌词页, 实时跟随高亮 |
| P0.6 | `[x]` | 音质偏好 3 档 (high/balanced/standard) + Settings PreferencesPage + 退出登录 + config.toml 持久化 (tomli-w) + show_welcome/show_qrcode/show_search_results 自动 pop_to_tag("home") + 网络超时友好 toast + GLibUnix.signal_add_full 替代 deprecated API | `core/service.py`, `config.py`, `ui/gtk/app.py`, `__main__.py`, `pyproject.toml` | ✅ 音质切换生效, 持久化, settings 页能登/退 |
| P0.7 | `[x]` | MPRIS2 D-Bus 集成 (Root+Player 接口, song_to_metadata, dbus-next 在 asyncio loop, gdbus 实测注册成功) | `core/mpris.py`, `__main__.py`, `pyproject.toml` | ✅ playerctl/gdbus 能查到 + 媒体键能控 |

### P1 — 个人库 + 持久化

| # | 状态 | 步骤 | 主要文件 | 验证要点 |
|---|---|---|---|---|
| P1.1 | `[~]` | SQLite cache 层 (song/album/playlist/artist meta + TTL) | `core/cache.py`, `core/service.py`, `__main__.py` | 第二次访问详情页明显更快；DB 文件存在且 schema 正确 |
| P1.2 | `[ ]` | 喜欢/取消喜欢 (本地 + QQ fav 歌单镜像) | `core/library.py`, controller, UI heart 按钮 | 喜欢操作即时反映 UI；重启后状态保留；QQ 端 fav 歌单同步 |
| P1.3 | `[ ]` | LibraryView 4 Tabs (我喜欢/我的歌单/收藏的专辑/关注的歌手) | `ui/*/views/library.py` | 4 Tab 都能拉到对应数据；点击可进入详情 |
| P1.4 | `[ ]` | 会话恢复 (state.json: queue + position + mode) | `core/state.py`, controller | 退出再启动队列、当前曲、暂停态、音量都恢复 |
| P1.5 | `[ ]` | 封面磁盘缓存 (`~/.cache/quaverq/covers/`) | `core/cache.py` 扩展 | 第二次显示同一封面不走网络；MPRIS 拿到本地 file:// URL |

### P2 — 发现 + 打磨

| # | 状态 | 步骤 | 主要文件 | 验证要点 |
|---|---|---|---|---|
| P2.1 | `[ ]` | HomeView (5 个推荐 + 排行榜入口) | `ui/*/views/home.py`, `core/service.py` | 启动后首页有内容；点卡片能跳详情 |
| P2.2 | `[ ]` | TopChartsView (排行榜分类网格) | `ui/*/views/charts.py` | 分类列出 → 进具体榜 → Tracklist 能播 |
| P2.3 | `[ ]` | 搜索建议词 / 热搜 (空态 + 输入补全) | `core/service.py`, `ui/*/views/search.py` | 搜索框空态显示热搜；输入时 250ms debounce 拉补全 |
| P2.4 | `[ ]` | 离线音频 LRU 缓存 | `core/cache.py` 扩展 | 已听过的歌断网仍能播；超过配额自动淘汰旧文件 |
| P2.5 | `[ ]` | SettingsView 完整 (音质/缓存/清理/主题/VIP 状态) | `ui/*/views/settings.py` | 各项实际生效且持久化 |

### P3 — 可选

| # | 状态 | 步骤 |
|---|---|---|
| P3.1 | `[ ]` | MV 播放 (GStreamer + UI 视频面板) |
| P3.2 | `[ ]` | 评论流只读展示 |
| P3.3 | `[ ]` | 歌手相似推荐入口 |
| P3.4 | `[ ]` | 桌面歌词浮窗 (X11 + Wayland 各自实现) |
| P3.5 | `[ ]` | 全局快捷键 (DE 级注册) |

---

## 15. 风险与限制

| 风险 | 应对 |
|---|---|
| **VIP 内容**：高音质 / 部分新歌返回 URL 但播放被拒 | service 收到 `result != 0` → UI 提示 "需 VIP" 并自动尝试降一档音质 |
| **API 限频**：风控可能返回 403 | `Client(rate=4.0, capacity=10)` 全局限流；失败指数退避 |
| **凭据过期**：长期不用导致 cookie 失效 | 启动 `check_expired`；调用 `refresh_credential` 兜底；最后失败再回登录 |
| **DRM/Master 拒下发**：Atmos/DTS 受限 | 仅在 cookie 显示有此权限时显示选项；否则隐藏 |
| **GStreamer 编解码缺失**：FLAC/OGG 需对应插件 | `Gst.ElementFactory.find("flacdec")` 探测，缺则降级到 MP3_320 |
| **API 版本漂移**：qqmusic-api 升级断 API | service 层做适配；`pyproject.toml` 锁次版本 `>=0.6,<0.7` |
| **跨桌面图标主题**：symbolic 图标在非 GNOME 主题下可能缺失 | 提供 fallback `.svg` 资源，路径加 `Gtk.IconTheme.add_search_path` |
| **MPRIS 与外部播放器冲突**：用户系统已有 Spotify 等占 D-Bus name | 我们用 `org.mpris.MediaPlayer2.quaverq` 独立 bus name，不互斥 |

---

## 16. 下一步

从 **P0.1 (service 重构 + 模型扩展)** 开始。等用户说"开始 P0.1"再动手；每完成一个步骤等"过了"再推进下一个。

---

*文档维护：进度变化时只更新第 14 节的状态格；现状描述仅在需要时调整第 2 节。*
