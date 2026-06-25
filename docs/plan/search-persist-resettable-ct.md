# 持久化 + 可重置 ct 风控指纹

## 任务描述

播放偶发 401 的根因：`ct` 值每次启动 `random.choice` 重抽（`service.py:318`），会话内固定且无失败重试。
候选池 `_SAFE_CT_VALUES` 是静态猜测、会随时间变馊（如 `ct=19` 已于 2026-06-07 被加黑）。
抽到已被风控的 ct → vkey 拒发 → CDN 返 401 → **整个会话所有歌都播不了**，重启换个 ct 才好。

真实设备不会每次启动换客户端类型。改为：

1. **持久化 ct**：首次生成后落盘 `~/.config/quaverq/risk_ct`，之后永久复用（与 `device_guid` 同构）。消灭"启动抽签命中坏 ct"。
2. **设置页"重置风控指纹"按钮**：UI 文案"重置风控指纹"，实际重抽一个 ct 写回，**立即生效**（更新内存 `_ct_value`，下一首取流即用新值，无需重启）。
3. **读时校验**：落盘的 ct 若已不在当前候选池（池子缩小后），自动重抽——避免把用户钉死在一个后来被加黑的 ct 上。

## ct 现状（调查结论）

- `_ct_value` **仅用于 vkey 取流接口** `music.vkey.GetVkey`（`_bypass_post`）。其它接口走库默认 `ct=11`，不受影响。
- 候选池（22 个）：`2,5,6,7,8,9,10,12,13,14,15,16,17,20,21,22,24,25,26,28,29,30`
- 被风控/排除：`1,3,4,11,18,19,23,27,46`（`ct=11` 安卓默认命中 104003；`ct=19` 2026-06-07 起 CDN 403）
- findings.md 第 64 行另记"不传 ct 最稳"——与本需求正交，暂不改路线。

## 实测数据（2026-06-25，`scripts/probe_ct.py`，凭据有效时，样本"晴天" MP3_320）

- ✅ 可播 ct：除下列外全部；**`_SAFE_CT_VALUES` 22 个值本次全部可播**。
- ❌ 不可播 ct：`{0, 1, 3, 4, 11, 18, 23, 27, 46}`（均已在黑名单；`ct=0` 是"传值 0"≠"不传 ct"）。
- **`ct=19` 已被 QQ 解封**（findings.md 记的 2026-06-07 封禁失效），代码仍保守排除，无需动。
- **结论：ct 抽签当前不是播放失败主因，ct 池健康。**

## ⚠️ 真正根因：musickey 过期未被识别 + 续期只跑一次

调查"为何每次启动可能播不了"时实测发现（见 memory `project-musickey-expiry-104003`）：

- musickey 寿命仅 **3 天**（`key_expires_in=259200`）。过期返 **`104003`**，但 `_CREDENTIAL_EXPIRED_CODES=(1000,104400,104401)` **不含 104003** → `get_song_url` 当成"灰色歌曲"不续期。
- 续期链（`refresh_credential`）本身好用，但**只在 `ServiceController.start()` 启动时跑一次**；会话跨过 3 天 / 启动续期失败时无补救。
- `get_song_url` 取流前从不调 `credential.is_expired()`（本地时间判定、零网络）。

→ 这才是"大多数能播、个别整段播不了"的根因。401 是 CDN 拉流层另一问题（见 `project-stream-401-multi-instance`）。

## 实施步骤（TDD，每步附手动验证）

### Step A（最高优先）— 取流前过期守卫
- `get_song_url` 进入时：`if cred and cred.is_expired(): await self._try_refresh_credential()` 再取流。
- 事件驱动（由播放动作触发，非轮询），`is_expired()` 零网络。
- **不要**改成"104003 就续期重试"——灰色歌曲合法返 104003，会给每首灰歌加无谓往返。
- 测试：`tests/test_service_*.py` —— mock 过期凭据 + mock refresh，断言取流前调用了续期一次；未过期时不调。

## 实施步骤（TDD，每步附手动验证）

### Step 1 — config.py 落盘读写 + 测试
- `risk_ct(allowed: Sequence[int], path=None) -> int`：文件存在且值 ∈ allowed 则读，否则 `random.choice(allowed)` 落盘。
- `reset_risk_ct(allowed, path=None) -> int`：强制重抽并落盘。
- `_risk_ct_file()`: `_config_dir() / "risk_ct"`。
- `tests/test_config.py`：首次生成落盘 ∈ 池、二次读同值、reset 换值、落盘值不在池时重抽。

### Step B1 — config.py 落盘读写 + 测试（接上方 Step 1）
（即上方"Step 1"，与 ct 持久化属同组）

### Step B2 — service.py 接线
- `connect()`：`self._ct_value = risk_ct(self._SAFE_CT_VALUES)` 替换 `random.choice`。
- 新增 `reset_risk_fingerprint() -> int`：`reset_risk_ct(...)` → 更新 `self._ct_value` → 返回新值（立即生效）。
- 测试覆盖：connect 后 ct 持久；reset 后内存值变化。

### Step 3 — service_controller.py 暴露 QML 入口
- `Slot`/`@asyncSlot` `resetRiskFingerprint()` → 走 service。

### Step 4 — SettingsController + SettingsView.qml
- 设置页加"重置风控指纹"按钮 + Snackbar 提示"已重置风控指纹"。

## 预期结果

- 正常启动不再每次换 ct → 偶发 401 消失（除多实例并发场景，另见 project-stream-401-multi-instance）。
- 用户遇到某 ct 被风控时，设置页一键重置即可换池中另一个，立即生效。
