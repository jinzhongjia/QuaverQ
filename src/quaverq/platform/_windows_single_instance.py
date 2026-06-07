"""Windows 单实例守卫 —— 命名 Mutex 占位.

类比 Linux 的 D-Bus well-known name (``SingleInstanceGuard``):
- 第一实例: CreateMutexW 拿到一个新 mutex (``GetLastError() != ERROR_ALREADY_EXISTS``), 持有 handle 直到 release()
- 第二实例: CreateMutexW 返回已有 mutex (``GetLastError() == ERROR_ALREADY_EXISTS``), close handle 后返 False;
  调 notify_existing_raise() 通过 ``EnumWindows`` 找第一实例主窗 + ``SetForegroundWindow`` 前置, 然后本进程退出.

设计要点:
- **ctypes 而非 pywin32**: pywin32 ~50MB 太重, 且 Nuitka 打包要额外处理. ctypes 是标准库, Win32 API 直调.
- **mutex 名带版本后缀**: ``QuaverQ-SingleInstance-v1``; 未来锁语义变更时换 v2, 避免老锁干扰新版本.
- **不用 ``Global\\`` 前缀**: 默认 per-session per-user, 不同用户登录同机器各跑各的, 不互锁.
- **SetForegroundWindow 在 Win10+ 可能被拒**: 默认前台锁机制不允许任意进程抢前台.
  退而求其次 ``ShowWindow(SW_RESTORE)`` + ``FlashWindow`` 让任务栏图标闪烁提醒用户 (足够 UX).
- **acquire / notify_existing_raise 用 ``asyncio.to_thread``**: Win32 调用是同步的, 但走 thread 避免
  阻塞 qasync event loop (即使是几毫秒).
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import sys
from ctypes import wintypes
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING or sys.platform == "win32":
    # 只在 Windows 上加载 Win32 API; 其他平台 import 本模块时不连 DLL.
    _ERROR_ALREADY_EXISTS = 183
    _SW_RESTORE = 9
    _FLASHW_TRAY = 0x00000002
    _FLASHW_TIMERNOFG = 0x0000000C

    DEFAULT_MUTEX_NAME = "QuaverQ-SingleInstance-v1"
    DEFAULT_WINDOW_TITLE = "QuaverQ"


def _kernel32() -> ctypes.WinDLL:
    """惰性加载 kernel32; 不在 module 顶部 import, 让本文件在 Linux 上也能被 mypy/grep 等读到."""
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    dll.CreateMutexW.restype = wintypes.HANDLE
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    return dll


def _user32() -> ctypes.WinDLL:
    dll = ctypes.WinDLL("user32", use_last_error=True)
    dll.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    dll.EnumWindows.restype = wintypes.BOOL
    dll.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    dll.GetWindowTextLengthW.restype = ctypes.c_int
    dll.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    dll.GetWindowTextW.restype = ctypes.c_int
    dll.IsWindowVisible.argtypes = [wintypes.HWND]
    dll.IsWindowVisible.restype = wintypes.BOOL
    dll.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    dll.ShowWindow.restype = wintypes.BOOL
    dll.SetForegroundWindow.argtypes = [wintypes.HWND]
    dll.SetForegroundWindow.restype = wintypes.BOOL
    return dll


class WindowsSingleInstance:
    """命名 Mutex 实现的单实例守卫.

    满足 ``quaverq.platform.base.SingleInstance`` Protocol (acquire / notify_existing_raise / release).
    """

    def __init__(
        self,
        mutex_name: str = "QuaverQ-SingleInstance-v1",
        window_title: str = "QuaverQ",
    ) -> None:
        self._mutex_name = mutex_name
        self._window_title = window_title
        self._handle: int | None = None

    async def acquire(self) -> bool:
        """走 thread, 调 ``CreateMutexW``.

        - 返回 True: 占到 mutex (本进程为首实例); handle 持有直到 release()
        - 返回 False: 已被占 (有别的进程持着同名 mutex) / CreateMutex 失败
        """
        return await asyncio.to_thread(self._try_create_mutex)

    def _try_create_mutex(self) -> bool:
        kernel32 = _kernel32()
        handle = kernel32.CreateMutexW(None, True, self._mutex_name)
        last_err = ctypes.get_last_error()
        if not handle:
            logger.warning("Windows 单实例: CreateMutexW 失败, GetLastError=%s", last_err)
            return False
        if last_err == _ERROR_ALREADY_EXISTS:
            # 已经有别的进程占住了, 我们这个 handle 是"已有 mutex"的另一个引用, 释放掉
            kernel32.CloseHandle(handle)
            logger.info("Windows 单实例: %s 已被占用, 视为已存在实例", self._mutex_name)
            return False
        self._handle = handle
        logger.info("Windows 单实例: 占用 %s 成功", self._mutex_name)
        return True

    async def notify_existing_raise(self) -> None:
        """通知已有实例把主窗口前置.

        Windows 没有 MPRIS Raise 那种统一接口; 用 ``EnumWindows`` 暴力找符合标题的顶层窗口,
        然后 ``ShowWindow(SW_RESTORE)`` + ``SetForegroundWindow``. 后者在 Win10+ 可能被拒,
        但任务栏图标会闪烁 (默认行为), 用户能注意到.
        """
        await asyncio.to_thread(self._find_and_raise)

    def _find_and_raise(self) -> None:
        user32 = _user32()
        EnumWindowsProc = ctypes.WINFUNCTYPE(  # noqa: N806
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        target: list[int] = []

        def cb(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value == self._window_title:
                target.append(hwnd)
                return False  # 找到一个就停
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if not target:
            logger.info("Windows 单实例: 未找到主窗口 (title=%s), 跳过 raise", self._window_title)
            return

        hwnd = target[0]
        user32.ShowWindow(hwnd, _SW_RESTORE)
        ok = user32.SetForegroundWindow(hwnd)
        if not ok:
            # Win10+ 前台锁机制拒绝时, 任务栏图标会自动闪烁 (这是系统提示用户"有进程想抢前台").
            # 实际 UX 上够用, 不再绕开 (绕开方法是 AttachThreadInput, 风险高且不一定可靠).
            logger.info(
                "Windows 单实例: SetForegroundWindow 被前台锁拒绝, 任务栏将闪烁提醒用户切到 QuaverQ"
            )

    def release(self) -> None:
        """关闭 mutex handle; 二次调用幂等."""
        if self._handle is None:
            return
        try:
            _kernel32().CloseHandle(self._handle)
        except OSError:
            logger.exception("Windows 单实例: 关闭 mutex handle 异常")
        self._handle = None
