"""Audio output device selection bridge (issue #7)."""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtMultimedia import QAudioDevice, QMediaDevices

if TYPE_CHECKING:
    from .settings_controller import SettingsController

logger = logging.getLogger(__name__)

_FOLLOW_SYSTEM_LABEL = "跟随系统默认"
_DISCONNECTED_SUFFIX = "（已断开）"
_FALLBACK_DISCONNECTED_LABEL = "上次使用的设备"


def _encode_device_id(device: Any) -> str:
    """QAudioDevice.id() 是任意字节的 QByteArray, base64 后才能进 settings.ini / QML."""
    return base64.b64encode(bytes(device.id())).decode("ascii")


class AudioDeviceController(QObject):
    """枚举音频输出设备并把用户选择应用到 QML 侧 AudioOutput.

    设计 (docs/plan/search-audio-output-device.md):

    - 枚举 / 匹配 / 回退逻辑全在 Python (可测); QML 只 attach 实例 + ChoiceRow 展示.
    - "跟随系统默认" = 不显式 setDevice —— QAudioOutput 出厂即默认设备且后端会跟随
      系统默认切换; 仅在"从具体设备切回默认 / 所选设备拔出"时 set null QAudioDevice 重置.
    - 软回退: 所选设备消失 → 回退系统默认但**不清**持久化偏好, 设备插回经
      audioOutputsChanged 自动恢复; 断开期间设置页模型末尾附 "<名字>（已断开）" 占位.
    - 纯事件驱动 (QMediaDevices.audioOutputsChanged + SettingsController.settingsChanged),
      不轮询.
    """

    devicesChanged = Signal()

    def __init__(
        self,
        settings_controller: SettingsController,
        *,
        media_devices: Any = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_controller = settings_controller
        # 必须持引用: QMediaDevices 被 GC 后 audioOutputsChanged 不再触发 (项目铁律)
        self._media_devices = media_devices if media_devices is not None else QMediaDevices(self)
        self._audio_output: Any = None
        # 幂等 key: None = attach 后从未显式 setDevice (出厂默认态);
        # "" = 已显式重置回系统默认; "<b64>" = 已应用该具体设备
        self._applied_key: str | None = None
        self._device_labels: list[str] = []
        self._device_values: list[str] = []
        self._media_devices.audioOutputsChanged.connect(self._on_outputs_changed)
        self._settings_controller.settingsChanged.connect(self._on_settings_changed)
        self._rebuild_model()

    @Property("QStringList", notify=devicesChanged)
    def deviceLabels(self) -> list[str]:
        """ChoiceRow.model: 首项「跟随系统默认」, 之后为设备显示名 (+ 可能的断开占位项)."""
        return list(self._device_labels)

    @Property("QStringList", notify=devicesChanged)
    def deviceValues(self) -> list[str]:
        """ChoiceRow.values: 与 deviceLabels 一一对应的 base64 设备 id, 首项空串."""
        return list(self._device_values)

    @Slot(QObject)
    def attachAudioOutput(self, output: Any) -> None:
        """QML 把 AudioOutput (QAudioOutput) 实例交给 Python 托管设备路由."""
        if not hasattr(output, "setDevice"):
            logger.warning("attachAudioOutput: 对象缺少 setDevice, 忽略: %r", output)
            return
        self._audio_output = output
        self._applied_key = None  # 新 output 出厂即跟随系统默认
        self._apply()

    @Slot(str)
    def selectDevice(self, value: str) -> None:
        """设置页选择设备; value 为 deviceValues 中的 base64 id, 空串 = 跟随系统默认.

        只写偏好, 实际应用经 settingsChanged 信号驱动 (同值时信号不发, 本就无须动作).
        """
        value = str(value or "")
        self._settings_controller.setAudioOutputDevice(value, self._label_for_value(value))

    # ------------------------------------------------------------------ internal

    def _on_outputs_changed(self) -> None:
        self._rebuild_model()
        self._apply()

    def _on_settings_changed(self) -> None:
        self._apply()
        self._rebuild_model()  # 断开占位项的出现 / 消失跟随偏好变化

    def _list_devices(self) -> list[Any]:
        try:
            return list(self._media_devices.audioOutputs())
        except Exception:
            logger.exception("枚举音频输出设备失败")
            return []

    def _label_for_value(self, value: str) -> str:
        if not value:
            return ""
        for device in self._list_devices():
            if _encode_device_id(device) == value:
                return str(device.description())
        if value == self._settings_controller.audioOutputDeviceId:
            # 重选断开占位项: 设备不在线, 沿用持久化的显示名快照
            return self._settings_controller.audioOutputDeviceLabel
        return ""

    def _rebuild_model(self) -> None:
        labels = [_FOLLOW_SYSTEM_LABEL]
        values = [""]
        for device in self._list_devices():
            labels.append(str(device.description()))
            values.append(_encode_device_id(device))
        persisted = self._settings_controller.audioOutputDeviceId
        if persisted and persisted not in values:
            base = self._settings_controller.audioOutputDeviceLabel or _FALLBACK_DISCONNECTED_LABEL
            labels.append(base + _DISCONNECTED_SUFFIX)
            values.append(persisted)
        if labels == self._device_labels and values == self._device_values:
            return
        self._device_labels = labels
        self._device_values = values
        self.devicesChanged.emit()

    def _apply(self) -> None:
        if self._audio_output is None:
            return
        target = self._settings_controller.audioOutputDeviceId
        chosen: Any = None
        if target:
            chosen = next(
                (d for d in self._list_devices() if _encode_device_id(d) == target),
                None,
            )
        key = _encode_device_id(chosen) if chosen is not None else ""
        if key == self._applied_key:
            return
        previous = self._applied_key
        self._applied_key = key
        try:
            if chosen is not None:
                self._audio_output.setDevice(chosen)
            elif previous is not None:
                # 曾显式选过设备 → set null 重置回系统默认;
                # 从未选过 (previous None) 则不碰, 保持后端对系统默认的自动跟随
                self._audio_output.setDevice(QAudioDevice())
        except Exception:
            self._applied_key = previous  # 失败回滚, 下次事件重试
            logger.exception("应用音频输出设备失败")
