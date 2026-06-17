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
| 3 | Windows ctypes 去重（`_make_iid`/`_IID`/`_vtbl_ptr`/`_release` 在 `_windows_media_session` + `_windows_taskbar` 各一份 → 抽 `platform/_windows_com.py`） | ⏸ **推迟** | （~-32） | 见下 |

### 为什么推迟 Phase 3

那两个文件 `import ctypes.wintypes`，**在 Linux 上根本 import 不了**，无单元测试、无法运行验证。
盲改底层 COM 代码（vtable 偏移、IID）省 32 行还多加一个文件，一旦抄错运行期才在 Windows 上崩，
违反项目"每改动留可跑验证"。**需在 Windows 上验证才做**——届时确认 4 个 helper 字节级一致 + 全调用点
更新 + `python -m quaverq.packaging --smoke` 通过。

### 同样未做（低收益 / 高风险，留作记录）

- focus-ring / Badge 共享组件：浅重复 + 跨目录耦合，见上「否掉」。
- `scripts/debug_*.py` 8 个一次性脚本 ~280 行重复：**别给一次性脚本造 `_debug_lib.py` 框架**
  （过度工程换地方）；该删的删，但哪些已用完需作者点名，未动。

## 预期结果 / 实测

- 现役代码净 **-150 行**（119 增 / 269 删，7 文件）。
- `uv run pytest` → **988 passed, 21 skipped**（skip 均 Windows-only）。
- `uv run python scripts/lint.py` → ruff + ruff format + pyside6-qmllint 全绿。
- 无公共接口变化，无 README 需同步（被删符号未在任何 README 出现）。
