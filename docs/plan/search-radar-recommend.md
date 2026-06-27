# 雷达推荐功能 — 最小化集成设计方案

> 调研 + 计划任务。状态：方案设计完成，待用户确认后按分阶段实施。
> 所有 service / controller / QML 接入点均已对照真实代码逐项核实（行号截至本次调研）。

## 1. 任务描述

**做什么**：把 QQ 音乐的「雷达推荐」作为一个**独立功能**接入 QuaverQ —— 在侧栏 `Sidebar` 新增独立入口「雷达」，点击进入独立整页视图 `RadarView`，展示个性化推荐歌曲流，支持「播放全部 / 单曲点播 / 下拉自动加载下一页 / 队列耗尽自动续接」。

**为什么**：雷达推荐是 QQ 音乐核心的个性化发现入口，与现有「猜你喜欢 (daily)」是**不同接口**（`GetRadarSong` vs `get_radio_track`），返回字段与分页语义都不同（雷达带显式 `has_more` 分页流）。现有「猜你喜欢」嵌在首页卡片里、无独立页面、无分页流 UI，不能复用其展示层；但其 service / controller / 队列联动模式可以**整体照抄**。

**核心约束 (YAGNI)**：雷达流每次刷新内容都变 → **不做任何磁盘缓存**、**不进 SWR 首帧链路**、**不写 `home.json` 私有区块**。v1 只读 API 的 `songs` + `has_more` 两个字段，其余 (`recommend_song_ids` / `base_song_ids` / `toast` / `video_cards`) 一律不读。

---

## 2. API 调研结论

实测 `qqmusic_api/modules/recommend.py:107-128` 与 `models/recommend.py:75-94`：

```python
# qqmusic_api.modules.recommend.RecommendApi
def get_radar_recommend(self, page: int = 1):
    data = {"Page": page, "ReqType": 0, "FavSongs": [], "EntranceSongs": []}
    return self._build_request(
        "music.recommend.TrackRelationServer", "GetRadarSong", data,
        response_model=RadarRecommendResponse,
        pager_meta=PagerMeta(
            strategy=PageStrategy(page_key="Page", start_page=page),
            adapter=ResponseAdapter(has_more_flag="has_more"),
        ),
    )

class RadarRecommendResponse(Response):
    songs: list[Song] = Field(json_schema_extra={"jsonpath": "$.VecSongs[*].Track"})
    recommend_song_ids: list[int] = ...
    base_song_ids: list[int] = ...
    has_more: bool = Field(validation_alias="HasMore")
    toast: str = ""
    timestamp: int = ...
    video_cards: dict[str, Any] = ...
```

**已核实的关键事实**：

1. **入口存在**：`client.recommend` 在 `qqmusic_api/core/client.py:219` 暴露 `RecommendApi`，本项目 git pin (6504373) 已含。
2. **`get_radar_recommend(page)` 不接受 `credential=` 参数**（不同于 `get_guess_recommend(credential=...)`）。登录态走 client **全局凭据**：`service.py:398` 在设置凭据时 `self._client.credential = cred`，此后所有 client 调用自动携带。因此 service 层只写 `await self.client.recommend.get_radar_recommend(page=page)`，**不要**传 `credential=`，否则 `TypeError`。
3. **`resp.songs` 是 `list[Song]`**（jsonpath 已由库提取好），逐元素喂现有 `_to_song()`（`service.py:_to_song`，兼容 pydantic Song / dict / SimpleNamespace），**不新增转换函数**。
4. **`resp.has_more` 是真 `bool`**，直接作为「是否还有下一页」信号。
5. **需登录**：未登录时 client 携空凭据拿不到个性化结果，降级见 §3.3。

---

## 3. 架构决策

### 3.1 Controller：**单例 `RadarController`**（不走 Factory）

**结论：单例**，经 `engine.rootContext().setContextProperty("radarController", radar_controller)` 注入，`Main.qml` 顶层 `readonly property var radarController: RadarController` 收拢。

**理由**：CLAUDE.md「栈式视图必须自持状态」约束**只针对会被 `push` 多实例共存的 detail-like 视图**（`DetailController` 反例）。雷达是侧栏顶级路由，走 `resetContent(...)`（`Main.qml:152`，`StackView` clear+push，**同一时刻全局唯一一个实例**），与 `HomeController` / `LibraryController` / `DownloadController` 同类 —— 这些都是单例。雷达的可变 state（`page` / `songs model` / `loading` / `hasMore`）**不会**因 push/pop 多实例被覆写。

> 自检：①是否 `contentStack.push` 多实例进栈？→ 否，是 `resetContent` 顶级路由。②controller 有可变 state？→ 是。**①为否即不需 Factory**（与 `HomeController` 持有 daily 分页 state 同理）。

### 3.2 缓存：**完全不缓存**

**结论：不做磁盘缓存、不做内存 memo、不进 SWR 首帧链路。**

**理由**：雷达是快速变化的个性化推荐流，缓存会让用户看到过期推荐。daily 的 6h TTL（`home_controller.py:52`）/ `_memo` 都**不照抄** —— daily 取头部相对稳定，雷达「每次刷新都要新内容」。**禁止**：① 把 radar 加入 `home_cache._PRIVATE_SECTIONS`；② 把任何 `prime_radar_*` 加入 `__main__.py` 的 prime 链路（破坏首帧契约）；③ service 层加 `_memo_put`。每次进页面 / 刷新都实时拉。

### 3.3 未登录降级

**结论：照抄 daily 的登录门槛**（`home_controller.py:241-247` 的 `_set_daily_requires_login`）。`RadarController` 暴露 `radarRequiresLogin: bool`；未登录时 `requiresLogin=true` + 清空 model + 不发请求；`RadarView` 渲染空态，按钮文案「登录」点击触发 `loginRequested()`。登录态变化经 `serviceController.authStateChanged` 信号驱动自动刷新（照抄 `home_controller._handle_auth_state_changed` `service.py`/`home_controller.py:78,359`，**事件驱动不轮询**）。

### 3.4 雷达流接队列（照抄 daily 的三条路径）

> ⚠️ 修正：**播放全部与单曲点播都必须走 `playSourceFromModel(model, row, "radar")`**（`player_controller.py:223`），**不能**用 `playFromModel`（`:219`，不带 source）。只有带上 `source="radar"`，队列耗尽时 `queueExhausted("radar")`（`:432`，`Signal(str)`）才会触发自动续接。

| 交互 | 实现 | 照抄范例 |
|---|---|---|
| **播放全部** | `playerController.playSourceFromModel(radarModel, 0, "radar")` | `HomeView` daily「播放全部」`playSourceFromModel(model, 0, "daily")` |
| **单曲点播** | `SongRow.onActivated → playerController.playSourceFromModel(radarModel, row, "radar")` | `SongRow.qml` `activated(song, row)` 信号 |
| **下拉加载下一页** | `ListView.onAtYEndChanged: if (atYEnd && radarController.hasMore && !radarController.loading) radarController.loadNextPage()` | 事件驱动，非轮询 |
| **队列耗尽自动续接** | `RadarController` 连 `playerController.queueExhausted`，`if source == RADAR_SOURCE` → 拉下一页 → `append_to_queue` → `radarModel.append_songs(added)` | `home_controller._handle_queue_exhausted` (`:83` connect) + `extend_daily` 整段照抄 |

**雷达 source 标识**：`RadarController.RADAR_SOURCE = "radar"`（与 `home_controller.DAILY_SOURCE = "daily"` `:51` 并列）。

**分页内聚到 controller**：service 层只返回单页 `(songs, has_more)`；`page` 游标、跨页去重（`seen mids`）、`hasMore` 状态全在 `RadarController`。`append_to_queue`（`player_controller.py:288`）返回去重后**实际加入**的歌曲，UI model 用返回值更新，不要用请求的全量。

---

## 4. 改动清单（具体到能照着写）

### 新建文件

| 文件 | 内容 | 照抄范例 |
|---|---|---|
| `src/quaverq/bridge/radar_controller.py` | `RadarController(QObject)` 单例，见 §5 | `bridge/home_controller.py`（daily 部分：登录门槛 / 续接 / auth 信号） |
| `src/quaverq/qml/views/RadarView.qml` | 整页 UI，**详见 §4.1**。沿用 DownloadsView 骨架，delegate 直接复用 `SongRow` | `qml/views/DownloadsView.qml`（header+ListView+empty 布局）；SongRow / 播放全部 / requiresLogin 见 `HomeView` |
| `src/quaverq/qml/icons/radar.svg` | 雷达图标（同心圆 + 扫描线，`source` 上色随 `iconColor`） | 照 `qml/icons/home.svg` 的 viewBox / 尺寸规格 |
| `src/quaverq/qml/icons/refresh.svg`（可选） | 「换一批」按钮图标；若砍掉换一批则不需要 | 照 `qml/icons/*.svg` 规格 |
| `tests/test_service_radar.py` | service `get_radar_recommend` 契约测试 | `tests/test_service_user_profile.py`（`_RequestLike` mock 模式） |
| `tests/test_radar_controller.py` | controller 登录门槛 / 分页 / 去重 / 续接测试 | 现有 controller 测试 + `tests/conftest.py` fixture |

### 改动文件

| 文件:位置 | 改动 | 范例 |
|---|---|---|
| `src/quaverq/core/service.py`（`get_daily_recommend_songs` 下方） | 新增 `async def get_radar_recommend(self, *, page=1) -> tuple[list[Song], bool]`，见 §5。**不传 `credential=`、不加 memo** | 转换照用 `_to_song` |
| `src/quaverq/core/README.md` | service 接口表补一行 radar | 现有表 |
| `src/quaverq/bridge/__init__.py` `__all__` | 导出 `RadarController` | 现有 `HomeController` 导出行 |
| `src/quaverq/bridge/README.md` | 补 RadarController 段 | 现有 |
| `src/quaverq/__main__.py`（实例化区，与 `home_controller =` 同段） | `radar_controller = RadarController(service_controller, player_controller)` + `rootContext().setContextProperty("radarController", radar_controller)`；**赋给 `_radar_controller` 或加入持有列表防 GC** | `home_controller` 实例化 + 注入 + 持有 |
| `src/quaverq/qml/Main.qml`（controller 别名区，`:43` 同级） | `readonly property var radarController: RadarController`（`// qmllint disable unqualified`） | `:43 readonly property var downloadController` |
| `Main.qml` `routeTitle()`（`:135`） | `case "radar": return qsTr("雷达")` | 现有 case |
| `Main.qml` `navigate()`（`:162-177`） | `else if (route === "radar") root.resetContent(radarPageComponent, "radar")` | `:175` downloads 分支 |
| `Main.qml` 末尾 Component 区（`:1003` 附近） | `Component { id: radarPageComponent; Views.RadarView { radarController: root.radarController; coverController: ...; playerController: ...; songDetailController: ...; downloadController: ...; onSearchRequested: ...; onDetailRequested: ... } }` | `downloadsPageComponent` |
| `src/quaverq/qml/components/Sidebar.qml`（`:71-75` model 数组） | 追加 `{ route: "radar", label: qsTr("雷达"), icon: "../icons/radar.svg" }`（放 library 与 downloads 之间或之后） | 现有 4 个路由项（inline JS array + SVG icon） |

**注意**：`__main__.py` 改动**不得**碰 prime 链路，radar 不预载。

### 4.1 RadarView UI 设计

**不做** QQ 音乐式渐变 hero 大图 —— 项目所有整页（下载 / 资料库）都是「简洁 header + 列表」，加 hero 需带渐变资产 + 封面合成，与全局不一致且费工。保持一致：沿用 `DownloadsView` 的 `ColumnLayout`（margins `s6` / spacing `s5`）骨架，delegate **直接复用 `SongRow`**（`SongListModel` 的 role：`song`/`name`/`singers`/`albumName`/`durationText`/`coverUrl` 正好命中 SongRow 的 `required property`，自动绑定，免费白嫖菜单 / 收藏 / 详情 / 播放）。**0 个新组件**。

**线框**：

```
┌──────────────────────────────────────────────────────────┐
│  雷达                                      [换一批]  ( ▶ ) │  ← header
│  根据你的口味实时推荐 · 共 32 首                            │
├──────────────────────────────────────────────────────────┤
│  1  ♪ 封面  歌名                    ♥   03:21   ⋯          │  ← SongRow (复用)
│  2  ▶ 封面  歌名                    ♥   04:05   ⋯          │
│  …                                                         │
│              加载更多…   /   没有更多推荐了                │  ← ListView.footer
└──────────────────────────────────────────────────────────┘
```

**四态**（`visible` 互斥切换，同 DownloadsView）：

| 状态 | 条件 | 渲染 |
|---|---|---|
| **未登录** | `requiresLogin` | 居中：「登录后开启雷达推荐」+ 副文案 + 「登录」按钮 → `loginRequested()` |
| **首屏加载** | `loading && !hasRows` | `SongRowSkeleton` ×6（复用 HomeView 骨架） |
| **已登录空** | `!loading && !hasRows` | 居中：「暂无推荐 / 多听多收藏，雷达会更懂你」 |
| **列表** | `hasRows` | `ListView`（`reuseItems`）+ `SongRow` delegate + 底部 footer |

**关键交互（全部事件驱动，0 轮询）**：

- **播放全部 / 单曲点播**：都走 `playSourceFromModel(radarModel, row, "radar")`（带 source 才能触发队列耗尽自动续接，见 §3.4）。
- **下拉加载**：`ListView.onAtYEndChanged → loadNextPage()`（`atYEnd && hasMore && !loading`）。
- **footer**：`loading` 显「加载更多…」，`!hasMore` 显「没有更多推荐了」。
- **首次进入**：`Component.onCompleted` 仅在 model 空时 `refresh()`（单例 controller 持有 model，切回不重置流）。
- **换一批**（可选，需 `refresh.svg`）：`refresh()` 重 roll page=1。想再省可砍，靠下拉无限取新歌。
- **播放全部按钮的 play/暂停 toggle**（QQ 音乐有）：v1 不做（需新增「当前 source 是否 radar 且在播」属性），始终从首曲起播；列为可选增强。

RadarView.qml 完整骨架见配套实现（Step 3），结构 = header(`RowLayout`) + `ListView`(SongRow delegate + footer) + 3 个 `visible` 切换的状态 `Item`。

---

## 5. Controller 接口设计 + service 签名

### service 层

```python
async def get_radar_recommend(self, *, page: int = 1) -> tuple[list[Song], bool]:
    """雷达推荐 (个性化分页流). 返回 (本页歌曲, 是否还有下一页).

    需登录态 (client 全局凭据自动携带, 不传 credential=).
    不缓存: 推荐流每次刷新都变, 不走 memo / 磁盘.
    """
    try:
        resp = await self.client.recommend.get_radar_recommend(page=page)
    except Exception as exc:
        logger.warning("get_radar_recommend 失败: %s", exc)
        return [], False
    songs = [s for raw in (resp.songs or []) if (s := self._to_song(raw)).mid]
    return songs, bool(getattr(resp, "has_more", False))
```

> v1 串行单页拉取，无 unhashable Request 问题。若未来并发预取多页，**必须**先把 `client.recommend.get_radar_recommend(...)` 包成本地 coroutine 再 `asyncio.gather`（CLAUDE.md unhashable Request 坑）。

### RadarController（单例）

```python
class RadarController(QObject):
    RADAR_SOURCE = "radar"

    # signals
    radarModelChanged = Signal()
    loadingChanged = Signal()
    hasMoreChanged = Signal()
    requiresLoginChanged = Signal()
    errorRaised = Signal(str)

    def __init__(self, service_controller, player_controller, parent=None):
        ...
        # 持有 SongListModel(self)
        # player_controller.queueExhausted.connect(self._handle_queue_exhausted)
        # service_controller.authStateChanged.connect(self._handle_auth_state_changed)

    # Q_PROPERTY
    @Property(QObject, notify=radarModelChanged)      def radarModel(self) -> SongListModel
    @Property(bool,    notify=loadingChanged)         def loading(self) -> bool
    @Property(bool,    notify=hasMoreChanged)         def hasMore(self) -> bool
    @Property(bool,    notify=requiresLoginChanged)   def radarRequiresLogin(self) -> bool

    # @asyncSlot
    @asyncSlot() async def refresh(self)       # page=1, 清 model+seen, 拉首页; 未登录→门槛
    @asyncSlot() async def loadNextPage(self)  # page+=1 拉下页, 去重 append_songs; loading/!hasMore→no-op

    # 内部
    def _handle_auth_state_changed(self)       # 照抄 home_controller:359
    def _handle_queue_exhausted(self, source)  # if source == RADAR_SOURCE: create_task(_extend)
    async def _extend(self)                    # 拉下页 → player.append_to_queue → radarModel.append_songs
```

**state**：`_page:int`、`_has_more:bool`、`_seen:set[str]`（跨页 mid 去重）、`_loading:bool`、`_requires_login:bool`、`_refresh_task` / `_extend_task`（防重入，照抄 daily 的 task 守门）。

---

## 6. 分阶段实施计划（TDD，≤300 行/步）

### Step 1 — service 层 `get_radar_recommend`

- **范围**：`service.py` 新增方法 + `core/README.md`。
- **测试（先写跑红）**：`tests/test_service_radar.py` —— mock `client.recommend.get_radar_recommend` 返回带 `songs` / `has_more` 的 `SimpleNamespace`（含一个 `_RequestLike` 用例验证可 await）；断言 ① 返回 `(list[Song], bool)`；② 空 mid 被过滤；③ 异常返 `([], False)`；④ **调用 kwargs 不含 `credential`**（`MagicMock` 断言）。
- **手动验证**：`uv run pytest tests/test_service_radar.py` 全绿；（可选）登录态下临时脚本打印首页歌曲数 + has_more。

### Step 2 — `RadarController`（无 UI）

- **范围**：`radar_controller.py` + `bridge/__init__.py` 导出 + `bridge/README.md`。
- **测试（先写跑红）**：`tests/test_radar_controller.py` —— ① 未登录 `refresh()` → `radarRequiresLogin==True`、model 空、不调 service；② 登录 `refresh()` → model 填充、`hasMore` 跟随、`page==1`；③ `loadNextPage()` → page 递增、跨页 mid 去重、`!hasMore` 时 no-op；④ `queueExhausted("radar")` 触发 `_extend` 续接并 `append_to_queue`，`queueExhausted("daily")` 不触发；⑤ service 抛错 → `errorRaised`。用 fake service_controller / player_controller（mock `call_service` / `append_to_queue` / `queueExhausted` 信号）。
- **手动验证**：`uv run pytest tests/test_radar_controller.py` 全绿；`uv run python scripts/lint.py --py` 绿。

### Step 3 — QML 接入（路由 + 侧栏 + 视图）

- **范围**：`__main__.py` 实例化 + 注入（不碰 prime）、`Main.qml`（别名 / routeTitle / navigate / Component）、`Sidebar.qml`（model）、`RadarView.qml`、`icons/radar.svg`、`qml/views/README.md`。
- **测试**：QML 无单测，靠 `pyside6-qmllint --max-warnings=0`；ContextProperty 经 root 别名 qualified 访问。
- **手动验证清单**：
  1. `uv run python scripts/lint.py` 全绿（ruff + qmllint）。
  2. `uv run quaverq` 启动，侧栏出现「雷达」图标项，文案随展开 / 紧凑显隐。
  3. **未登录**：点「雷达」→ 空态 + 「登录」按钮 → 点按钮弹二维码登录。
  4. **登录后**：自动加载首屏歌曲；点「播放全部」从第 1 首起播，PlayerBar 出曲。
  5. 单击某行 → 从该行起播。
  6. 列表滚到底 → 自动追加下一页（loading 指示出现→消失，无重复曲）。
  7. 队列自然播到最后一首结束 → 自动续接下一页继续播（控制台无 `unhashable` 报错）。
  8. 切到别的页面再返回「雷达」→ 状态正常（单例无 push/pop 覆写问题）。
  9. **重启 app**：雷达页不预载、首帧无残留旧数据（确认未进 SWR 链路）。

---

## 7. 预期结果 / 验收标准

- **功能**：侧栏独立「雷达」入口 → 独立 `RadarView` → 登录后展示个性化推荐流，支持播放全部 / 单曲点播 / 下拉加载下一页 / 队列耗尽自动续接；未登录显示登录引导。
- **契约合规**：① 单例 controller 经 root 别名收拢；② `__main__.py` 持有 controller 引用防 GC；③ **未**进 prime 链路、**未**写 `home.json`、**未**加 memo / 磁盘缓存；④ 登录态 / 队列耗尽均事件驱动，**无轮询**；⑤ client 调用不传 `credential=`，串行单页拉取无 unhashable Request 风险；⑥ 播放统一走 `playSourceFromModel(..., "radar")`，保证队列携带 source。
- **质量门**：`uv run pytest` 全绿（新增 2 个测试文件先红后绿）；`uv run python scripts/lint.py` 全绿（ruff + qmllint `--max-warnings=0`）。
- **零回退**：现有「猜你喜欢 (daily)」首页卡片行为不变（雷达是独立路径，不复用 daily 的展示层与缓存）。
