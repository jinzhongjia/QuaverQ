# Issue #7：增加选择音频输出设备功能 — 调研与实施计划

> **状态（2026-06-12）**：Stage 1 / 2 / 3 已全部实施。实施中确定的细化：
> 「跟随系统默认」在 attach 后**完全不**显式 `setDevice`（出厂态即默认，保住后端自动跟随），
> 仅在「从具体设备切回默认 / 所选设备拔出」时 set null `QAudioDevice` 重置；
> attach 时偏好设备缺失同样不发物理调用（输出本就在默认）。
> 待真机验证项见下文 Stage 3 手动清单。

## 任务描述

GitHub issue #7（"Feature: 增加选择输出设备功能"，无正文）：允许用户在应用内选择音频输出设备
（扬声器 / 耳机 / HDMI / 蓝牙等），而不是只能跟随系统默认设备。

目标行为（对齐 QQ 音乐 PC 端「设置 → 播放」的输出设备下拉）：

- 设置页提供输出设备下拉框，首项为「跟随系统默认」，其余为当前可用设备。
- 选择持久化，重启后恢复。
- 设备热插拔事件驱动响应：所选设备被拔出时回退系统默认（不清除用户偏好），插回后自动恢复。
- 切换设备对正在播放的歌曲即时生效。

## 调研结果

### 现状：播放链路与音频出口

- 实际的 `MediaPlayer` / `AudioOutput` 在 **QML 侧**（`src/quaverq/qml/Main.qml:256-307`）；
  Python 的 `PlayerController` 只是状态 / 命令层，通过信号驱动 QML 播放器。
- `AudioOutput { id: audioOutput }` 目前只绑 `volume` / `muted`，**未管理 `device`** —— 永远使用
  系统默认输出设备（Qt ffmpeg 后端对未显式指定设备的输出会跟随系统默认切换）。
- 设置持久化在 `SettingsController`（QSettings backed，`src/quaverq/bridge/settings_controller.py`），
  既有固定模式：`_read_str` 白名单读取 + `@Property(notify=settingsChanged)` + `@Slot` setter。
- 设置页 `SettingsView.qml` 的「播放」分区已有 `ChoiceRow` inline 组件（通用 ComboBox 行：
  `model` / `values` / `currentValue` / `valueRequested(value)`，`SettingsView.qml:594`），
  可直接复用于设备下拉，无需新建 UI 组件。
- Controller 注入走 `__main__.py` `setContextProperty` + `Main.qml` 顶层 `readonly property var` alias
  （`Main.qml:42`），`SettingsView` 通过 `property var settingsController` 在 push 时接收（`Main.qml:840-842`）。

### Qt 6 QtMultimedia 设备 API（PySide6 已含，无新依赖）

- **`QMediaDevices`**（QObject，需实例化并持引用防 GC）：
  - `audioOutputs` → `list[QAudioDevice]`；
  - `audioOutputsChanged` 信号：设备插拔触发；系统默认切换也会触发（列表项的 `isDefault`
    标志属于列表数据，默认变化 = 列表内容变化）→ **纯事件驱动，符合「禁止轮询」规则**。
- **`QAudioDevice`**：`.id() -> QByteArray`（平台稳定标识：Linux 是 PulseAudio/PipeWire sink name，
  Windows 是 WASAPI endpoint GUID，重启不变，适合持久化）、`.description() -> str`（显示名）、
  `.isDefault()`、`.isNull()`。
- **`QAudioOutput.setDevice(QAudioDevice)`**：运行中可切换，ffmpeg 后端即时生效（切换瞬间可能有
  <100ms 中断，可接受）。设 null `QAudioDevice()` 重置回系统默认。
- QML 的 `AudioOutput` 类型背后就是 C++ `QAudioOutput`，可通过 `@Slot(QObject)` 传给 Python 后
  `isinstance(obj, QAudioOutput)` 直接持有并 `setDevice()`（项目已有 QML→Python 传 QObject 先例：
  `playFromModel(model, row)`）。

### 设备 id 持久化编码

`QAudioDevice.id()` 是任意字节的 `QByteArray`。统一用 **base64**（`base64.b64encode(bytes(id)).decode("ascii")`）
存入 `settings.ini`，空串表示「跟随系统默认」。base64 对任意字节安全、无跨平台编码歧义。

### 关键设计取舍

1. **逻辑放 Python 不放 QML**：QML 侧 `MediaDevices` 类型虽可用，但 `audioDevice.id` 在 JS 是
   `ArrayBuffer`，比较 / 持久化都很绕，且纯 QML 逻辑无法被 pytest 覆盖（违背项目 TDD 文化）。
   设备枚举、匹配、回退逻辑全部放 Python controller，QML 只做展示 + attach。
2. **新建 `AudioDeviceController` 而非塞进 `PlayerController`**：设备路由与播放队列状态是两个域；
   `PlayerController` 已 670 行。新 controller 是**全局单例**（同一时刻只有一个设置页生效，不入
   `contentStack` 栈），符合 CLAUDE.md「不可栈的单例 controller 走 setContextProperty 注入」豁免清单。
3. **持久化字段放 `SettingsController`**：与 `qualityPreference` / `themeMode` 同模式
   （`playback/audioOutputDeviceId`），`AudioDeviceController` 订阅 `settingsChanged` 拿最新值并
   apply（apply 幂等，杂烩信号多触发无害）。保持「所有用户偏好集中在 SettingsController」的现状。
4. **软回退策略**（与 QQ 音乐一致）：所选设备被拔出 → `setDevice(null)` 回退系统默认，**不改写**
   持久化偏好；`audioOutputsChanged` 再次触发（设备插回）时重新匹配 → 自动恢复用户选择。
5. **断开设备的 UI 呈现**：持久化 id 不在当前设备列表时，`devicesModel` 末尾附加一项
   「\<上次描述\>（已断开）」占位（label 持久化一份 `playback/audioOutputDeviceLabel` 供拼接），
   避免下拉显示「跟随系统默认」与实际偏好不一致的误导。
6. **「跟随系统默认」语义** = 不显式指定设备（`setDevice(QAudioDevice())`），由 Qt 后端跟随系统
   默认切换；**不**显式 set `defaultAudioOutput()`（那会把输出钉死在"此刻的默认"上）。
   ⚠️ 实施 Stage 2 时需真机验证 null device 重置行为；若后端不接受 null，保底方案：
   set `defaultAudioOutput()` + 在 `audioOutputsChanged` 回调里重新 apply 以跟随默认变化。

### 不受影响的部分

- MPRIS / SMTC / 桌面歌词不感知音频路由，零改动。
- 打包：`--include-qt-plugins=multimedia` 已带 QtMultimedia 后端，无新增依赖。

## 实施步骤（3 个阶段，每步 ≤300 行，过一步验证一步）

### Stage 1：SettingsController 持久化字段（~80 行）

1. 测试先行（`tests/test_bridge_settings_controller.py` 增补）：
   - `audioOutputDeviceId` 默认空串；
   - `setAudioOutputDeviceId(id, label)` round-trip（含 `audioOutputDeviceLabel`）；
   - 同值早退不发 `settingsChanged`；非 str 输入归一化。
2. 实现：`_audio_output_device_id` / `_audio_output_device_label` 字段 + Property + Slot，
   key `playback/audioOutputDeviceId` / `playback/audioOutputDeviceLabel`，照抄既有 setter 模式。

**验证**：`uv run pytest tests/test_bridge_settings_controller.py` 全绿。

### Stage 2：AudioDeviceController（~250 行 + 测试）

1. 测试先行（新建 `tests/test_bridge_audio_device_controller.py`，fake 设备源 +
   `types.SimpleNamespace` fake `QAudioOutput`，不触真实音频后端）：
   - 枚举映射：`deviceLabels` / `deviceValues` 首项「跟随系统默认」/`""`；
   - `selectDevice(b64)` → settings 持久化 + fake output 收到匹配 `setDevice`；
   - 空选择 → `setDevice(null)`；
   - 持久化 id 对应设备不存在 → 回退 null + 偏好保留 + model 末尾出现「（已断开）」项；
   - 设备源发 `audioOutputsChanged`（设备回归）→ 自动重新 `setDevice` 恢复；
   - `attachAudioOutput` 之前调用 `selectDevice` 不崩，attach 后补 apply；
   - apply 幂等（同设备不重复 set）。
2. 实现 `src/quaverq/bridge/audio_device_controller.py`：
   - 构造注入 `settings_controller` + 可选 `media_devices`（默认 `QMediaDevices(self)`，**持引用**）；
   - Property：`deviceLabels` / `deviceValues`（`QStringList`，配 `ChoiceRow`）+ `devicesChanged` 信号；
   - Slot：`attachAudioOutput(QObject)`、`selectDevice(str)`；
   - 订阅 `audioOutputsChanged` → 重建 model + 幂等 re-apply。

**验证**：`uv run pytest` 全绿；`uv run python scripts/lint.py --py` 绿。

### Stage 3：QML 接线 + 文档（~100 行）

1. `__main__.py`：构造 `AudioDeviceController`（在 `settings_controller` 之后）+
   `setContextProperty("AudioDeviceController", ...)`，Python 端持引用。
2. `Main.qml`：顶层 alias `readonly property var audioDeviceController: AudioDeviceController`
   （`// qmllint disable unqualified`）；`audioOutput` 上
   `Component.onCompleted: root.audioDeviceController.attachAudioOutput(audioOutput)`。
3. `SettingsView.qml`：增 `property var audioDeviceController`（Main.qml push 处传入）；
   「播放」分区音质偏好下加 `ChoiceRow`「输出设备」：
   `model: deviceLabels` / `values: deviceValues` / `currentValue: settingsController.audioOutputDeviceId`
   / `onValueRequested: audioDeviceController.selectDevice(value)`；`showSeparator: false`
   从音质行挪到新行（新行成为分区末行）。
4. 更新 `src/quaverq/bridge/README.md`（新 controller 条目）；检查 `src/quaverq/qml/` README 是否需同步。

**验证**：
- `uv run pytest` + `uv run python scripts/lint.py` 全绿；
- `uv run quaverq` 手动清单：
  1. 设置 → 播放 → 「输出设备」下拉列出本机全部输出设备 + 首项「跟随系统默认」；
  2. 播放中切换设备，声音即时从新设备出（中断 <1s）；
  3. 选定非默认设备后重启应用，下拉恢复选择且声音走该设备；
  4. （有蓝牙耳机时）播放中断开所选耳机 → 声音回退默认设备、下拉出现「（已断开）」项；
     重连后自动切回耳机；
  5. 「跟随系统默认」下用系统设置切默认设备，声音跟随。

## 预期结果

- 设置页「播放」分区新增「输出设备」下拉，选择即时生效并持久化（`settings.ini`
  `playback/audioOutputDeviceId`，base64 编码设备 id，空 = 跟随系统默认）。
- 设备热插拔全程事件驱动（`QMediaDevices.audioOutputsChanged`），零轮询；拔出软回退、
  插回自动恢复。
- 跨平台（Linux freedesktop / Windows）行为一致；无新增运行时依赖，打包配置零改动。
- 新增 `AudioDeviceController` 单元测试 + `SettingsController` 增量测试全绿，逻辑层 100% 可测
  （QML 层仅声明式绑定）。
