"""AudioDeviceController tests (fake 设备源 + fake QAudioOutput, 不触真实音频后端)."""

from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import QSettings

from quaverq.bridge.audio_device_controller import AudioDeviceController
from quaverq.bridge.settings_controller import SettingsController


def _settings_controller(path: Path) -> SettingsController:
    settings = QSettings(str(path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    return SettingsController(settings=settings)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


class _FakeSignal:
    def __init__(self) -> None:
        self._slots = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def emit(self) -> None:
        for slot in list(self._slots):
            slot()


class _FakeDevice:
    def __init__(self, raw_id: bytes, description: str, *, is_default: bool = False) -> None:
        self._id = raw_id
        self._description = description
        self._is_default = is_default

    def id(self) -> bytes:  # noqa: A003 - 模拟 QAudioDevice.id()
        return self._id

    def description(self) -> str:
        return self._description

    def isDefault(self) -> bool:
        return self._is_default


class _FakeMediaDevices:
    def __init__(self, devices: list[_FakeDevice]) -> None:
        self.devices = devices
        self.audioOutputsChanged = _FakeSignal()

    def audioOutputs(self) -> list[_FakeDevice]:
        return list(self.devices)


class _FakeAudioOutput:
    def __init__(self) -> None:
        self.calls = []

    def setDevice(self, device) -> None:
        self.calls.append(device)


SPEAKER = _FakeDevice(b"sink.speaker", "内置扬声器", is_default=True)
HEADSET = _FakeDevice(b"sink.usb-headset", "USB 耳机")


def _make(tmp_path, devices=None, *, settings_controller=None):
    sc = settings_controller or _settings_controller(tmp_path)
    media = _FakeMediaDevices(devices if devices is not None else [SPEAKER, HEADSET])
    controller = AudioDeviceController(sc, media_devices=media)
    return controller, sc, media


# ============================================================== 设备模型


def test_model_lists_follow_system_first_then_devices(tmp_path):
    controller, _sc, _media = _make(tmp_path)

    assert controller.deviceLabels == ["跟随系统默认", "内置扬声器", "USB 耳机"]
    assert controller.deviceValues == ["", _b64(b"sink.speaker"), _b64(b"sink.usb-headset")]


def test_model_appends_disconnected_entry_for_missing_persisted_device(tmp_path):
    sc = _settings_controller(tmp_path)
    sc.setAudioOutputDevice(_b64(b"sink.bt-buds"), "蓝牙耳机")

    controller, _sc, _media = _make(tmp_path, [SPEAKER], settings_controller=sc)

    assert controller.deviceLabels == ["跟随系统默认", "内置扬声器", "蓝牙耳机（已断开）"]
    assert controller.deviceValues == ["", _b64(b"sink.speaker"), _b64(b"sink.bt-buds")]


def test_model_rebuilds_on_hotplug_and_emits_devices_changed(tmp_path):
    controller, _sc, media = _make(tmp_path, [SPEAKER])
    seen = []
    controller.devicesChanged.connect(lambda: seen.append(1))

    media.devices = [SPEAKER, HEADSET]
    media.audioOutputsChanged.emit()

    assert controller.deviceLabels == ["跟随系统默认", "内置扬声器", "USB 耳机"]
    assert len(seen) == 1


def test_unchanged_hotplug_event_does_not_emit_devices_changed(tmp_path):
    controller, _sc, media = _make(tmp_path)
    seen = []
    controller.devicesChanged.connect(lambda: seen.append(1))

    media.audioOutputsChanged.emit()
    media.audioOutputsChanged.emit()

    assert seen == []


# ============================================================== 选择与应用


def test_select_device_persists_and_applies_to_attached_output(tmp_path):
    controller, sc, _media = _make(tmp_path)
    output = _FakeAudioOutput()
    controller.attachAudioOutput(output)
    output.calls.clear()  # attach 时跟随默认的那次 apply 不计

    controller.selectDevice(_b64(b"sink.usb-headset"))

    assert sc.audioOutputDeviceId == _b64(b"sink.usb-headset")
    assert sc.audioOutputDeviceLabel == "USB 耳机"
    assert output.calls == [HEADSET]


def test_select_follow_system_resets_to_null_device(tmp_path):
    sc = _settings_controller(tmp_path)
    sc.setAudioOutputDevice(_b64(b"sink.usb-headset"), "USB 耳机")
    controller, _sc, _media = _make(tmp_path, settings_controller=sc)
    output = _FakeAudioOutput()
    controller.attachAudioOutput(output)
    assert output.calls == [HEADSET]

    controller.selectDevice("")

    assert sc.audioOutputDeviceId == ""
    assert len(output.calls) == 2
    assert output.calls[-1].isNull()  # 真 QAudioDevice null = 重置回系统默认


def test_attach_applies_persisted_choice(tmp_path):
    sc = _settings_controller(tmp_path)
    sc.setAudioOutputDevice(_b64(b"sink.usb-headset"), "USB 耳机")
    controller, _sc, _media = _make(tmp_path, settings_controller=sc)
    output = _FakeAudioOutput()

    controller.attachAudioOutput(output)

    assert output.calls == [HEADSET]


def test_attach_with_follow_system_does_not_touch_device(tmp_path):
    # 跟随系统默认 = 不显式 setDevice, 保持 Qt 后端自动跟随系统默认切换的语义
    controller, _sc, _media = _make(tmp_path)
    output = _FakeAudioOutput()

    controller.attachAudioOutput(output)

    assert output.calls == []


def test_select_before_attach_then_attach_applies(tmp_path):
    controller, sc, _media = _make(tmp_path)

    controller.selectDevice(_b64(b"sink.usb-headset"))  # 未 attach, 不应崩
    assert sc.audioOutputDeviceId == _b64(b"sink.usb-headset")

    output = _FakeAudioOutput()
    controller.attachAudioOutput(output)
    assert output.calls == [HEADSET]


def test_attach_rejects_object_without_set_device(tmp_path):
    controller, _sc, _media = _make(tmp_path)

    controller.attachAudioOutput(object())  # 不崩, 仅 log warning

    controller.selectDevice(_b64(b"sink.usb-headset"))  # 后续选择也不崩


# ============================================================== 软回退与热插拔恢复


def test_missing_device_falls_back_to_default_but_keeps_preference(tmp_path):
    sc = _settings_controller(tmp_path)
    sc.setAudioOutputDevice(_b64(b"sink.bt-buds"), "蓝牙耳机")
    controller, _sc, _media = _make(tmp_path, [SPEAKER], settings_controller=sc)
    output = _FakeAudioOutput()

    controller.attachAudioOutput(output)

    assert output.calls == []  # 出厂即系统默认, 无须显式重置
    assert sc.audioOutputDeviceId == _b64(b"sink.bt-buds")  # 偏好保留


def test_device_unplugged_falls_back_then_replug_restores(tmp_path):
    sc = _settings_controller(tmp_path)
    sc.setAudioOutputDevice(_b64(b"sink.usb-headset"), "USB 耳机")
    controller, _sc, media = _make(tmp_path, settings_controller=sc)
    output = _FakeAudioOutput()
    controller.attachAudioOutput(output)
    assert output.calls == [HEADSET]

    media.devices = [SPEAKER]  # 拔出
    media.audioOutputsChanged.emit()
    assert len(output.calls) == 2
    assert output.calls[-1].isNull()
    assert controller.deviceLabels[-1] == "USB 耳机（已断开）"

    media.devices = [SPEAKER, HEADSET]  # 插回
    media.audioOutputsChanged.emit()
    assert output.calls[-1] is HEADSET  # 自动恢复用户选择
    assert "USB 耳机（已断开）" not in controller.deviceLabels


def test_reselect_disconnected_entry_keeps_persisted_label(tmp_path):
    sc = _settings_controller(tmp_path)
    sc.setAudioOutputDevice(_b64(b"sink.bt-buds"), "蓝牙耳机")
    controller, _sc, _media = _make(tmp_path, [SPEAKER], settings_controller=sc)

    controller.selectDevice(_b64(b"sink.bt-buds"))  # 重选断开占位项

    assert sc.audioOutputDeviceId == _b64(b"sink.bt-buds")
    assert sc.audioOutputDeviceLabel == "蓝牙耳机"


def test_apply_is_idempotent_across_repeated_events(tmp_path):
    sc = _settings_controller(tmp_path)
    sc.setAudioOutputDevice(_b64(b"sink.usb-headset"), "USB 耳机")
    controller, _sc, media = _make(tmp_path, settings_controller=sc)
    output = _FakeAudioOutput()
    controller.attachAudioOutput(output)

    media.audioOutputsChanged.emit()
    media.audioOutputsChanged.emit()
    sc.setThemeMode("dark")  # 无关设置变化触发 settingsChanged

    assert output.calls == [HEADSET]  # 仍只 set 过一次


def test_external_settings_change_triggers_apply(tmp_path):
    controller, sc, _media = _make(tmp_path)
    output = _FakeAudioOutput()
    controller.attachAudioOutput(output)

    sc.setAudioOutputDevice(_b64(b"sink.usb-headset"), "USB 耳机")  # 绕过 selectDevice

    assert output.calls == [HEADSET]


def test_select_updates_disconnected_entry_membership(tmp_path):
    sc = _settings_controller(tmp_path)
    sc.setAudioOutputDevice(_b64(b"sink.bt-buds"), "蓝牙耳机")
    controller, _sc, _media = _make(tmp_path, [SPEAKER], settings_controller=sc)
    assert controller.deviceLabels[-1] == "蓝牙耳机（已断开）"

    controller.selectDevice(_b64(b"sink.speaker"))  # 改选在线设备

    assert "蓝牙耳机（已断开）" not in controller.deviceLabels
