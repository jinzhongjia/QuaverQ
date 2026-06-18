# 代码优化（去臃肿 / 全仓审计）

## 任务描述

全仓审计，目标只锁定**过度工程 / 臃肿 / 可读性**（不查正确性 bug、不查安全、不查性能 ——
那些走单独 review）。找出可删、可用 stdlib 替代、单实现假抽象、纯转发 wrapper、死代码，
按"砍得最多"排序后分阶段实施。

## 审计结果（6 个并行 agent 扫全树，已人工复核）

被复核**否掉**的注水项（agent 报了但不成立）：

- `asyncSlot/_async 包装对 ~350 行`：**假的**。`*_async` 版本被内部 `asyncio.gather` 复用
  （`home_controller.refresh_home_async` gather 了一串 `refresh_*_async`），不是纯转发，
  塌掉会破坏并发组合 + 改 qasync 异常语义。
- `cover_url_for`：被 `download_controller` 真调用，是合法公共 API。
- `_get_cached_credential`：`service_controller` 经 `getattr` 调它 + 测试 mock，async 面向外部。
- focus-ring 共享组件：**浅重复**——恒定的只有 3 行（color/border.color/border.width），
  `visible`（每处绑不同 id）/`radius`/`z`/`anchors.margins` 全因地而异；消费者跨
  `components`/`views`/`dialogs` 三目录（后两者当前未 import components）。抽组件每处仍得
  自填 visible+radius，只省 3 行却换来跨目录耦合，**负收益，不做**。

## 分阶段实施 + 结果

| 阶段 | 内容 | 状态 | 净行数 | 验证 |
|------|------|------|--------|------|
| 1 | `settings_controller` 26 个同构 setter → 抽 `_apply(attr, key, value)` 收口（`value is None`=归一化拒绝） | ✅ 完成 | ~-90 | 58 setter 测试全绿 |
| 2a | `config.load()` 去掉 `_deep_merge(DEFAULTS.copy(), {})` no-op → `DEFAULTS.copy()`（`_deep_merge` 从不原地改 base，等价）；`_deep_merge` 本身保留（136 行合并用户 TOML 真用，嵌套 dict 不能用 `dict.update`） | ✅ 完成 | ~0（去费解点） | 现有测试绿 |
| 2b | 删死函数 `packaging.linux_package_layout()`（全仓零引用，逻辑已内联进 `prepare_linux_package_root`） | ✅ 完成 | -15 | ruff 绿 |
| 2c | 删死方法 `service.to_song_simple()`（纯转发 `_to_song`，零调用方） | ✅ 完成 | -4 | service 测试绿 |
| 2d | 删死方法 `desktop_lyrics._fill_brush`（仅测试引用，生产走 `_ensure_brush_cache`+直接读缓存）+ `_draw_outline`（零引用）；测试 `test_fill_brush_for_gradient` 改指向 `_ensure_brush_cache`+`_cached_brush_highlight` 保住渐变覆盖 | ✅ 完成 | -14 | desktop_lyrics 测试绿 |
| 4 | `PlayerBar` 两个 Slider（仅 `Layout.preferredHeight` 18/24 不同）→ 同文件 `component VolumeSlider`（仿现成 `OverflowRow` 自包含写法，暴露 `muted` 属性，`value`/`onMoved` 使用处绑） | ✅ 完成 | ~-31 | qmllint --max-warnings=0 绿 |
| 3 | Windows ctypes 去重（`_make_iid`/`_IID`/`_vtbl_ptr`/`_release` 在 `_windows_media_session` + `_windows_taskbar` 各抄一份 → 抽 `platform/_windows_com.py`；`_release_com`→`_release` 统一，返回值本就全忽略） | ✅ 完成 | ~-30 | 见下 |

### Phase 3 验证说明（Linux 上能验 / 不能验）

逐字比对确认 4 个 helper 两边等价后才抽。关键设计：共享模块只用跨平台 ctypes 原语
（`WINFUNCTYPE` 取不到回退 `CFUNCTYPE`），**不 import `wintypes`**，所以 `_windows_com.py`
自身在 Linux 也能 import / 单测。

- ✅ **能验**：新增 `tests/test_platform_windows_com.py`（Linux 直接跑，3 测试覆盖唯一有解析逻辑的
  `_make_iid` + 结构 16 字节）；`ruff check` 静态确认两消费文件无 F821 未定义名 / 无 F401 孤儿 import
  （= import 接对了、`c_uint32` 仍被 `WindowsCreateString` 用着没误删）。
- ⚠️ **不能验（需 Windows）**：media_session / taskbar 因各自 `wintypes` 依赖在 Linux import 不了，
  COM vtable 运行期调用无法在此跑。但这些路径**字节未改**——只搬了 helper 定义 + 统一了 `_release`
  名称，行为按构造保持不变。上 Windows 后跑 `python -m quaverq.packaging --smoke` + 实测任务栏/SMTC 即可。

### 同样未做（低收益 / 高风险，留作记录）

- focus-ring / Badge 共享组件：浅重复 + 跨目录耦合，见上「否掉」。
- `scripts/debug_*.py` 8 个一次性脚本 ~280 行重复：**别给一次性脚本造 `_debug_lib.py` 框架**
  （过度工程换地方）；该删的删，但哪些已用完需作者点名，未动。

## 预期结果 / 实测

- **Phase 1/2/4**（已提交 `bf97b4a`）：现役代码净 **-150 行**（119 增 / 269 删，7 文件）。
- **Phase 3**（未提交）：两个 Windows 文件去重 **-82 行**，抽出 56 行 `_windows_com.py` + 32 行测试
  → 净源码 **-26 行**，COM helper 单一来源。
- 累计源码净 **约 -176 行**（+ 新增 32 行 Windows COM 测试）。
- `uv run pytest` → **991 passed, 21 skipped**（skip 均 Windows-only；+3 为新增 `_windows_com` 测试）。
- `uv run python scripts/lint.py` → ruff + ruff format + pyside6-qmllint 全绿。
- 无公共接口变化；README 文件表只列 adapter 入口（`__init__`/`base`/`linux`/`windows`），不列
  `_windows_*` 实现文件，故新增 `_windows_com.py` 按既有约定不入表，无 README 需同步。
