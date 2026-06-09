"""Windows 系统主题跟随测试 (注册表 AppsUseLightTheme).

策略: monkeypatch ``winreg`` 让 ``QueryValueEx`` 返回 0 / 1, 不真碰系统注册表.
轮询逻辑用 QTimer; 测试通过手动调内部 ``_poll_once()`` 触发, 不等真定时.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


# ============================================================== 注册表读


def test_dark_returns_true_when_apps_use_light_theme_is_zero(qapp, monkeypatch):
    """注册表 AppsUseLightTheme=0 -> 系统当前深色, dark=True."""
    import winreg

    from quaverq.platform._windows_system_theme import WindowsSystemThemeWatcher

    monkeypatch.setattr(
        winreg,
        "QueryValueEx",
        lambda _key, _name: (0, winreg.REG_DWORD),
    )

    w = WindowsSystemThemeWatcher()
    w._poll_once()
    assert w.dark is True


def test_dark_returns_false_when_apps_use_light_theme_is_one(qapp, monkeypatch):
    """注册表 AppsUseLightTheme=1 -> 系统当前浅色, dark=False."""
    import winreg

    from quaverq.platform._windows_system_theme import WindowsSystemThemeWatcher

    monkeypatch.setattr(
        winreg,
        "QueryValueEx",
        lambda _key, _name: (1, winreg.REG_DWORD),
    )

    w = WindowsSystemThemeWatcher()
    w._poll_once()
    assert w.dark is False


def test_dark_defaults_to_false_when_registry_key_missing(qapp, monkeypatch):
    """注册表 key 不存在 (老 Windows / 用户没设过) -> 安全降级到 dark=False, 不 raise."""
    import winreg

    from quaverq.platform._windows_system_theme import WindowsSystemThemeWatcher

    def _raise_file_not_found(*_args, **_kwargs):
        raise FileNotFoundError("simulated missing registry key")

    monkeypatch.setattr(winreg, "OpenKey", _raise_file_not_found)

    w = WindowsSystemThemeWatcher()
    w._poll_once()
    assert w.dark is False


# ============================================================== Signal


def test_dark_changed_signal_emits_when_value_flips(qapp, monkeypatch):
    """darkChanged 在值变化时触发, 不变化时不重复发 (回避无效 UI 刷新)."""
    import winreg

    from quaverq.platform._windows_system_theme import WindowsSystemThemeWatcher

    state = {"value": 1}  # 初始浅色

    def _fake_query(_key, _name):
        return (state["value"], winreg.REG_DWORD)

    monkeypatch.setattr(winreg, "QueryValueEx", _fake_query)

    w = WindowsSystemThemeWatcher()
    emissions = []
    w.darkChanged.connect(lambda: emissions.append(w.dark))

    w._poll_once()  # 第一次, dark False (浅色), 不变化 -> 不 emit
    assert emissions == []

    state["value"] = 0  # 切深色
    w._poll_once()
    assert emissions == [True]

    state["value"] = 1  # 切回浅色
    w._poll_once()
    assert emissions == [True, False]

    w._poll_once()  # 再来一次浅色, 值未变 -> 不 emit
    assert emissions == [True, False]


# ============================================================== 启停


async def test_start_initial_read_and_stop_clean(qapp, monkeypatch):
    """start() 应当先做一次初始读 (而不是等第一个 tick); stop() 干净停止."""
    import winreg

    from quaverq.platform._windows_system_theme import WindowsSystemThemeWatcher

    monkeypatch.setattr(
        winreg,
        "QueryValueEx",
        lambda _key, _name: (0, winreg.REG_DWORD),
    )

    w = WindowsSystemThemeWatcher()
    assert w.dark is False  # 初值
    await w.start()
    assert w.dark is True  # start() 触发一次同步读, 不用等 2s tick
    await w.stop()


async def test_start_connects_color_scheme_signal(qapp, monkeypatch):
    """start() 应当接 QStyleHints.colorSchemeChanged 信号; stop() 摘掉.
    PySide6 6.x 的 installNativeEventFilter 在 frameless QML 窗口下不可靠,
    改走 Qt 高层信号 (内部已钩 WM_SETTINGCHANGE), 我们当 trigger 用."""
    import winreg

    from quaverq.platform._windows_system_theme import WindowsSystemThemeWatcher

    monkeypatch.setattr(winreg, "QueryValueEx", lambda _key, _name: (1, winreg.REG_DWORD))
    w = WindowsSystemThemeWatcher()
    assert w._connected is False
    await w.start()
    assert w._connected is True
    await w.stop()
    assert w._connected is False


async def test_color_scheme_signal_triggers_reread(qapp, monkeypatch):
    """模拟系统主题切换: 注册表先返浅色, 触发信号后改返深色, dark 应同步翻转."""
    import winreg

    from PySide6.QtGui import QGuiApplication

    from quaverq.platform._windows_system_theme import WindowsSystemThemeWatcher

    state = {"value": 1}  # 初始浅色
    monkeypatch.setattr(winreg, "QueryValueEx", lambda _k, _n: (state["value"], winreg.REG_DWORD))

    w = WindowsSystemThemeWatcher()
    await w.start()
    assert w.dark is False

    # 模拟 OS 改主题: 改注册表值 + emit Qt 信号
    state["value"] = 0  # 切深色
    QGuiApplication.instance().styleHints().colorSchemeChanged.emit(
        QGuiApplication.instance().styleHints().colorScheme()
    )
    qapp.processEvents()
    assert w.dark is True

    await w.stop()


# ============================================================== Protocol / Platform 接入


def test_windows_platform_returns_real_system_theme(qapp):
    """WindowsPlatform.system_theme() 不再返 None, 应是 WindowsSystemThemeWatcher 实例."""
    from PySide6.QtCore import QObject

    from quaverq.platform import get_platform
    from quaverq.platform._windows_system_theme import WindowsSystemThemeWatcher

    pal = get_platform()
    w = pal.system_theme()
    assert isinstance(w, WindowsSystemThemeWatcher)
    assert isinstance(w, QObject)  # 必须是 QObject, QML 才能绑 Property
