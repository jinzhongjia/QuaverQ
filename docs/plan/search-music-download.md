# 音乐下载功能方案（issue #6）

## 任务描述

[Issue #6](https://github.com/jinzhongjia/quaverq/issues/6)：**增加音乐下载功能，支持下载音乐的不同音质 + 封面 + 歌词**。Issue 正文为空，需求即标题；本文档给出调研结论与分阶段实施计划。

## 一、现状调研结论

### 1.1 音频 URL 获取（可直接复用）

- `QuaverService.get_song_url(song, quality_preference)`（`core/service.py:801`）走 vkey bypass 路径，按 `_QUALITY_PROFILES` 降级取明文 URL，返回 `SongUrl(mid, url, quality)`。**需要登录**（`require_login=True`）。
- 现支持 4 档（`_QUALITY_FILE`，`core/service.py:269`）：

  | 档位 | filename 前缀 | 扩展名 |
  |------|--------------|--------|
  | FLAC | F000 | .flac |
  | MP3_320 | M800 | .mp3 |
  | OGG_192 | O600 | .ogg |
  | MP3_128 | M500 | .mp3 |

- 三档偏好降级链（`_QUALITY_PROFILES`）：`high` → FLAC→MP3_320→OGG_192→MP3_128；`balanced` → MP3_320 起；`standard` → MP3_128 起。**下载音质选项直接复用这三档 profile**，与播放语义一致、零 service 改动，完成后用 `SongUrl.quality` 报告实际命中档位。
- `docs/findings.md` 验证过 MASTER（AI00 母带）/ ATMOS_2（Q000）接口可拿明文 URL，但未实装进 `_QUALITY_FILE`，且 findings 第九节提示高档位接口有被收紧风险 → **列为可选扩展，默认不做**。

### 1.2 CDN 下载方式（必须 curl_cffi）

- QQ CDN 有 JA3 指纹风控，`StreamProxy`（`bridge/stream_proxy.py`）即用 `curl_cffi` `impersonate="chrome"` + `stream=True` + `iter_content` 拉流。**下载器必须走同样方式**，不能用 niquests/QNetworkAccessManager 直连。
- `CoverCache._download_sync`（`core/cover_cache.py`）提供了"流式下载 + `_closing` 中断 + 写盘"的现成模式，但它整体缓冲且无进度回调；音频大文件（FLAC 可达 ~50MB）需要**边收边写 .part 临时文件 + 进度回调 + 原子 rename**，需新写。

### 1.3 歌词（需新增 LRC 序列化器）

- `QuaverService.get_lyric(mid, with_translation=True)`（`core/service.py:682`）返回解析后的 `Lyric`（`core/models.py:73`：`lines: list[LyricLine]`，行含 `timestamp_ms / text / translation / words`），**不保留原始文本**。
- 下载 `.lrc` 走 **`Lyric` → LRC 文本序列化**（新增纯函数 `to_lrc()`，放 `core/lyric.py`）：QRC 逐字行用行级 `timestamp_ms` 输出标准 `[mm:ss.xx]`；翻译行以同时间戳第二行输出（QQ 双行风格）。比再加一个"取原始 LRC"的网络方法更稳，且纯函数完美 TDD。

### 1.4 封面

- 封面 URL 模板：`_cover_url(album_mid, size)`（`core/service.py:122`）→ `https://y.qq.com/music/photo_new/T002R{size}x{size}M000{mid}.jpg`，项目已验证 300/500 两档，**下载用 500**。
- `Song.cover_url` / `song_to_map()["albumMid"]`（`bridge/models.py`）已带所需字段。`_cover_url` 是模块级私有函数，实施时在 `core/service.py` 导出公开别名（如 `cover_url_for(album_mid, size)`）供 downloader 使用。
- 封面是普通 CDN（无 JA3 风控），但统一走下载器的 curl_cffi 路径即可，不必两套客户端。

### 1.5 设置 / 控制器 / UI 模式（均有现成模板）

- 设置：`SettingsController` 的 `_read_str` + `@Property(notify=settingsChanged)` + `@Slot` setter + `_settings.setValue` 三段式（参照 `playback/qualityPreference`，`bridge/settings_controller.py`）。
- 控制器：构造注入 `ServiceController`，API 调用统一 `await self._service_controller.call_service(lambda svc: ...)`；错误经 `error_utils.log_bridge_error` → `errorRaised(str)` 信号 → Main.qml 根级 `Connections` → `globalSnackbar.show(msg, kind)`。
- 列表模型：`QAbstractListModel` + `roleNames()`（参照 `bridge/models.py` 的 `SongListModel`）。
- 注入：`__main__.py` 在 service/settings 创建之后实例化、`setContextProperty("DownloadController", ...)`，并在 `Main.qml` 顶部按约定声明 `readonly property var downloadController: DownloadController` 别名。
- QML 入口现成挂点：
  - `SongRow.qml` 的 contextMenu（行 125-227，已有播放/收藏/查看歌手等项）→ 加"下载"项；
  - `PlayerBar.qml` / `NowPlayingView.qml` 操作按钮区 → 加下载 IconButton（需新增 `icons/download.svg`，遵循 `icons/README.md` 风格）;
  - `DetailView.qml` 头部"播放全部"旁 → "下载全部"；
  - `SettingsView.qml` 的 `SettingsSection` / `ChoiceRow` / `SwitchRow` / `SettingsRow` 组件 → 新增"下载"分组；
  - 抽屉浮层参照 `QueuePanel`（Loader + `everOpened` 闩锁 + Translate 滑入，Main.qml:903 区域）。

### 1.6 其他约束

- 默认下载目录用 Qt 的 `QStandardPaths.writableLocation(MusicLocation)` + `/QuaverQ`（Linux `~/Music/QuaverQ`，Windows `C:\Users\<u>\Music\QuaverQ`）——platformdirs 没有"音乐目录"概念，且这是**用户文档型产物**，不能放 `CACHE_DIR`（会被 LRU 清理）。
- 所有文本 IO 显式 `encoding="utf-8"`（Windows GBK 雷区，写 .lrc 必须带）。
- License：项目 GPL-3.0-or-later，未来若做标签嵌入可引入 mutagen（GPL-2.0+，兼容，纯 Python 打包友好）。
- 风控：项目 memory 记录过多客户端并发拉流会让 vkey 互相失效（401）。下载与播放并发属同实例不同 URL，理论无碍，但保守起见**下载 worker 串行（并发 1）**，vkey 获取也随队列串行。

## 二、设计决策

### 2.1 产物布局（旁路文件，v1 不嵌标签）

```
<下载目录>/
  周杰伦 - 晴天.flac      ← 音频（扩展名随实际命中档位）
  周杰伦 - 晴天.lrc       ← 歌词（UTF-8，含翻译双行）
  周杰伦 - 晴天.jpg       ← 封面（500x500）
```

- 命名 `<歌手1、歌手2> - <歌名>.<ext>`，`sanitize_filename()` 清洗 Windows 非法字符 `\/:*?"<>|`、控制字符、尾部空格/点，并按字节长度截断。
- 同名音频已存在 → 任务直接标记"已存在"跳过（不覆盖、不弹错）。
- 下载到 `<名字>.<ext>.part`，完成后原子 `rename`；中断/失败删除 .part。
- 歌词/封面单项失败**不致命**：音频成功即任务成功，缺项记进任务备注。

### 2.2 音质粒度

- 设置页"默认下载音质"三档：`standard`（流畅 MP3 128k）/ `balanced`（高品质 MP3 320k）/ `high`（无损 FLAC 优先），直接传给 `get_song_url(quality_preference=...)` 复用降级链。
- SongRow 的"下载"做成**二级子菜单**（仿 QQ 音乐桌面端）：三档任选 + 首项"下载（默认音质）"；PlayerBar / NowPlayingView / 下载全部一律用默认音质。

### 2.3 新增模块

```
src/quaverq/core/downloader.py        ← 核心下载逻辑（可独立测试）
src/quaverq/bridge/download_controller.py
src/quaverq/qml/panels/DownloadsPanel.qml   （阶段 5）
src/quaverq/qml/icons/download.svg
tests/test_downloader.py
tests/test_download_controller.py
```

**core/downloader.py**：

```python
def sanitize_filename(name: str) -> str: ...            # 纯函数
@dataclass
class DownloadTask:
    song: Song
    quality_preference: str
    status: str          # pending/running/done/exists/failed/canceled
    received: int = 0
    total: int = 0
    quality_label: str = ""   # 实际命中档位
    dest_path: Path | None = None
    error: str = ""

class Downloader:
    def download_file(self, url, dest, *, progress_cb=None, cancel=None) -> None:
        # curl_cffi impersonate="chrome" stream=True → .part → 原子 rename
        # 同步函数，调用方用 asyncio.to_thread 包
```

**core/lyric.py** 追加：

```python
def to_lrc(lyric: Lyric, *, with_translation: bool = True) -> str: ...
```

**bridge/download_controller.py**：

```python
class DownloadListModel(QAbstractListModel): ...   # roles: title/singers/status/progress/qualityText/errorText

class DownloadController(QObject):
    downloadFinished = Signal(str, str)   # name, quality_label
    errorRaised = Signal(str)
    activeCountChanged = Signal()

    @Property(QObject, constant=True)  downloadModel
    @Property(int, notify=activeCountChanged)  activeCount
    @asyncSlot("QVariant")        downloadSong(song_map)               # 默认音质
    @asyncSlot("QVariant", str)   downloadSongWithQuality(song_map, q) # 指定三档之一
    @Slot(int)                    cancelTask(row)
    @Slot()                       openDownloadDir()                    # QDesktopServices.openUrl
```

- 内部 `asyncio.Queue` + 惰性单 worker task（并发 1）；每首流程：`call_service(get_song_url)` → `to_thread(download_file)`（进度经 `loop.call_soon_threadsafe` 回灌 model，节流 ~100ms）→ `call_service(get_lyric)` + `to_lrc` 写盘 → 封面 `download_file` → done。
- 退出：`_closing` 标志中断 chunk 循环（同 CoverCache 模式），不挂 `aboutToQuit`（qasync 雷区）。

### 2.4 设置项（QSettings 键）

| key | 类型 | 默认 |
|-----|------|------|
| `download/directory` | str | `QStandardPaths(MusicLocation)/QuaverQ` |
| `download/quality` | str ∈ {standard, balanced, high} | `balanced` |
| `download/withLyric` | bool | true |
| `download/withCover` | bool | true |

## 三、分阶段实施计划（每步 ≤300 行，TDD，等用户验证再推进）

### 阶段 1：core 纯函数 + 设置项（~250 行）

1. 先写 `tests/test_downloader.py::test_sanitize_filename_*`（非法字符/控制符/尾点空格/长度截断/全非法回退）与 `tests/test_lyric.py::test_to_lrc_*`（时间戳格式 `[mm:ss.xx]`、翻译双行、空 Lyric、>60min）→ 跑红。
2. 实现 `sanitize_filename`（core/downloader.py 起骨架）+ `to_lrc`（core/lyric.py）→ 跑绿。
3. `SettingsController` 加 4 个键（仿 qualityPreference 三段式）+ `tests/test_settings_controller.py` 补默认值/越界回退用例。
4. 更新 `core/README.md`、`bridge/README.md`。

**手动验证**：`uv run pytest` 全绿；`uv run python scripts/lint.py` 绿。（无 UI 变化）

### 阶段 2：core Downloader（~250 行）

1. 测试先行：pytest 起本地 `ThreadingHTTPServer` 夹具，覆盖——正常下载（内容一致 + .part 不残留）、Content-Length 进度回调序列、404 抛错、cancel 事件中断后无 .part、目标已存在跳过。
2. 实现 `Downloader.download_file` + `DownloadTask`。curl_cffi 对 127.0.0.1 测试服务器照常工作（impersonate 只影响 TLS，本地 http 不受影响）。

**手动验证**：`uv run pytest tests/test_downloader.py -v` 全绿。

### 阶段 3：DownloadController 最小可用 + SongRow 入口（~300 行）

1. 测试：fake `ServiceController`（SimpleNamespace 返回构造的 `SongUrl` / `Lyric`）+ `tmp_path` 下载目录——单曲入队→状态流转 pending→running→done；音频 404 → failed + errorRaised；同名已存在 → exists；歌词失败不影响音频成功。
2. 实现 `DownloadListModel` + `DownloadController.downloadSong`（默认音质，含歌词 + 封面旁置）。
3. `__main__.py` 注入（service/settings 之后实例化 + setContextProperty）；`Main.qml` 加别名 + 根级 `Connections`（downloadFinished → Snackbar success；errorRaised → error）。
4. `SongRow.qml` contextMenu 加单项"下载"（默认音质），透传 `downloadController` property（沿现有 controller 透传链）。

**手动验证**：`uv run quaverq` → 登录 → 搜索任一歌曲 → 行"更多"菜单点"下载" → Snackbar 提示完成 → `~/Music/QuaverQ/` 出现 `.mp3/.flac` + `.lrc`（UTF-8 可读）+ `.jpg`；重复点同曲 → 提示已存在；断网点下载 → 错误 Snackbar。

### 阶段 4：设置分组 + 音质子菜单 + 播放器入口（~300 行）

1. `SettingsView.qml` 新增"下载"`SettingsSection`：`ChoiceRow` 默认下载音质 / `SettingsRow` 下载目录（actionText"更改"弹 `FolderDialog`，旁加"打开"用 `Qt.openUrlExternally`）/ `SwitchRow` ×2 歌词、封面开关。
2. `SongRow` "下载"改为子菜单（默认音质 + 三档显式选择，调 `downloadSongWithQuality`）。
3. 新增 `icons/download.svg`；`PlayerBar` 队列按钮旁 + `NowPlayingView` 顶行喜欢按钮旁加下载按钮（当前歌曲、默认音质，无歌曲时 disabled）。

**手动验证**：设置页切音质/目录后下载落到新目录新档位；关闭歌词开关后不再产出 .lrc；PlayerBar 播放中点下载按钮成功；改目录到只读路径 → 错误提示不崩。

### 阶段 5（可选）：下载管理抽屉 + 批量下载（~300 行）

1. `panels/DownloadsPanel.qml` 仿 QueuePanel 抽屉：任务列表（标题/歌手/进度条/状态/失败重试/取消）、底部"打开下载目录"；入口：PlayerBar 下载按钮长按或 activeCount 角标点击。
2. `DetailView` 头部"下载全部"（遍历 songModel 入队，复用队列串行）；`cancelTask` / 重试接通。

**手动验证**：歌单页点"下载全部" → 抽屉里看到任务依次推进；中途取消一首 → 状态变已取消且无 .part 残留。

### 阶段 6（可选，默认不做）

- MASTER/ATMOS_2 档位（往 `_QUALITY_FILE` 加 AI00/Q000，注意 findings 第九节风控风险）；
- mutagen 标签嵌入（ID3v2 / FLAC tags + 内嵌封面，license 兼容已确认，需验证 Nuitka 打包）；
- 断点续传（CDN 支持 Range，当前 .part 重下已够用）。

## 四、风险与边界

| 风险 | 应对 |
|------|------|
| 下载与播放并发触发 vkey/CDN 风控 | worker 并发 1、vkey 串行获取；出现 401/403 记任务失败可重试，不自动重试轰炸 |
| FLAC 大文件占内存 | 流式 64KB chunk 边收边写 .part，不整体缓冲 |
| Windows 文件名/编码 | `sanitize_filename` 全覆盖测试；.lrc 显式 UTF-8 |
| 退出时下载中 | `_closing` 中断 + 删 .part；不挂 aboutToQuit |
| 未登录点下载 | `call_service` 抛错 → errorRaised → Snackbar"请先登录"（与播放一致） |
| 灰色无版权曲 | `get_song_url` 返 None → 任务 failed +"无版权或不可下载" |

## 五、预期结果

- 任意歌曲列表（搜索/歌单/专辑/资料库）行菜单、播放栏、正在播放页均可发起下载；可选三档音质（流畅/高品质/无损，自动降级并如实报告命中档位）。
- 产物为 `音频 + .lrc 歌词 + .jpg 封面` 三件套，落在用户可配置的音乐目录，文件名跨平台安全。
- 下载行为有队列、进度、完成/失败提示；设置页可配置默认音质、目录、歌词/封面开关。
- 全程 TDD：core 纯函数与下载器、controller 状态机均有 pytest 覆盖；`scripts/lint.py` 与 `pytest` 全绿后才进入下一阶段。

---

# 六、PR #16 UI 反馈后的重构（路线2：本地播放 + 持久化 + 整页）

阶段 1–6 完成并开 PR #16 后，真机使用暴露 4 个 UI/UX 问题，与用户讨论后定稿如下方案。

## 6.1 反馈与决策

| 反馈 | 根因 | 决策 |
|------|------|------|
| 下载抽屉与背景混色看不清 | 浅色下 `surfaceElevated == background == #ffffff`，边框 `outlineMuted #f0f0f0` 极淡，所有右侧抽屉通病 | **改整页后浮层消失，问题自然解决**（不单独改配色） |
| 播放栏下载按钮呼出抽屉、不该 | 阶段 4→5 设计反复 | 改回**直接下载当前歌曲**（默认音质，设置里配） |
| 缺独立下载页入口 | 只有播放栏抽屉入口 | **侧边栏加「下载」导航项 → 整页 `DownloadsView`**，废弃抽屉 |
| 下载页信息不全、item 不可点 | 模型无封面、delegate 无点击 | 加封面；**点击 = 在 QuaverQ 内播放下载的本地文件（路线2）** |

补充决策:**下载记录持久化**（重启后下载页保留历史，且本地播放要靠它定位文件）。

## 6.2 架构设计

### 下载记录持久化（新子系统）

- **`core/download_store.py`**:`DownloadRecord` dataclass + `DownloadStore`，存 `CONFIG_DIR/downloads.json`（配置型数据，**不放 CACHE_DIR**——会被 LRU 清）。路径由 controller 注入（遵 core 约定）。
- `DownloadRecord` 字段:`mid / name / singers / album_mid / album_name / cover_url / quality_label / path / size / downloaded_at`——够还原列表显示、找到文件、重建 `Song` 用于播放/详情。
- `DownloadStore` 接口:`load() -> list[DownloadRecord]`（坏文件返空不抛，遵 core 容错）/ `add(record)` / `remove(mid)` / `find(mid) -> record|None` / `all()`；原子写（tmp + `os.replace`）、显式 `encoding="utf-8"`（Windows GBK 雷）。

### 播放核心本地优先（路线2）

- `PlayerController` 注入一个**本地解析器** `local_resolver(mid) -> path|None`（由 `DownloadController`/`DownloadStore` 提供）。
- `_load_current` 开头查本地:命中且文件存在 → `QUrl.fromLocalFile(path)` 直接 setSource，**跳过 `get_song_url` + stream_proxy**（本地播放不需登录/不需 vkey/不走代理，离线可听）。
- **失效回退**:记录有但文件已删/移动 → 删 store 记录 + 回退在线流程（绝不因本地缺失而播放失败）。

### DownloadController 改造

- 注入 `DownloadStore`:任务 `done` 时 `store.add(record)`；启动时 `store.load()` 填充 `DownloadListModel`（重启后显示历史，文件失效的标 invalid）。
- `DownloadListModel` 加 `coverUrl` + `song`（完整 dict）两个 role:封面显示、点击播放/详情传参。
- 暴露 `local_path_for(mid) -> str` 给 PlayerController 当解析器。
- 加「移除记录」（可选连带删文件）能力。

### 整页 DownloadsView（替代抽屉）

- 新建 `views/DownloadsView.qml`:行 = 封面（`image://covers`）+ 歌名 + 歌手 + 状态/音质/进度 + 失效标记 + 行尾操作。
- **整行点击 → `playerController.playSongs([song])`**（播放核心自动命中本地文件）。
- 行尾操作:完成 → 打开所在文件夹 / 移除；进行中 → 取消；失败/失效 → 重试/重新下载。
- 顶部:统计 + 打开下载目录 + 清空已完成（可选）；空态引导。
- 侧边栏（`Sidebar.qml`）加 `{route:"downloads", icon:"download.svg"}`；`Main.qml` 路由三处；**删除** `DownloadsPanel.qml` + 抽屉全套接线（`downloadsPanelOpen`/Loader/Esc 互斥）。
- `PlayerBar` 下载按钮改回"下载当前歌曲"（去角标，进度去下载页看）。

## 6.3 分阶段（接续阶段编号，每步 ≤300 行，TDD）

- **阶段 7**:`core/download_store.py`（DownloadRecord + DownloadStore，原子写/容错/失效检测）+ `test_download_store.py`。纯 core，验证 pytest。
- **阶段 8**:DownloadController 接 store（done 写入、启动加载历史、`local_path_for`）+ 模型加 coverUrl/song role + `__main__` 注入。验证 pytest（持久化文件模拟重启）。
- **阶段 9**:PlayerController 本地优先 + 失效回退。验证 pytest + 手动（下一首→下载页点它→断网仍能播）。
- **阶段 10**:整页 `DownloadsView` + 侧边栏入口 + 删抽屉 + 播放栏按钮改回。验证 lint + 手动点 UI。
- **阶段 11**:README/plan/CLAUDE.md 同步 + 全量回归。

## 6.4 风险与边界（增量）

| 风险 | 应对 |
|------|------|
| 本地文件被用户在外部删除/移动 | 播放与列表展示都做失效检测，删记录回退在线，不崩 |
| downloads.json 损坏 | `load()` 返空快照（遵 core 容错），不阻塞启动 |
| 本地文件进播放队列后被 `state.json` 持久化、重启文件已失效 | 恢复后 `_load_current` 走失效回退，自动转在线 |
| 同一首歌多次下载（不同音质）覆盖记录 | `store` 按 mid 唯一，后下载的覆盖前者（path 也覆盖，旧文件留盘不动） |
| 本地播放 vs 在线播放的音质标识 | 列表展示 record 里存的 quality_label；播放本地时不重新协商音质 |
