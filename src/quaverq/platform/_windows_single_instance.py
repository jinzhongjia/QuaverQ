"""Windows 单实例守卫 —— 用 ``LockFileEx`` 真正跨进程独占锁.

为什么 (尝试过又放弃的方案):
- **命名 mutex (``CreateMutexW``)**: 现代 Windows / Python 3.14 上, 不同 python.exe
  进程的 named kernel object 走 isolated namespace, ``ERROR_ALREADY_EXISTS`` 不触发,
  互斥失效.
- **``msvcrt.locking``**: 它基于 CRT 的 ``_locking()``, 实测两个独立进程都能 "拿到锁"
  (CRT 抽象层不真正调用 OS-level byte-range lock 或调用方式有问题).
- **``LockFileEx`` (本实现)**: 直接走 Win32 API, 真正的 OS-level byte-range lock,
  跨进程一致互斥. 进程退出时 OS 自动释放 (handle close 时自动 unlock).

实现:
- ``CONFIG_DIR / .app.lock`` 用 ``CreateFileW`` 打开 (FILE_SHARE_READ|WRITE)
- ``LockFileEx(hFile, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &OVERLAPPED)``
  抢字节 0 的独占锁; 失败 GetLastError = ERROR_LOCK_VIOLATION (33)
- 进程退出 OS 自动释放; ``release()`` 显式 ``UnlockFileEx`` + ``CloseHandle``
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING or sys.platform == "win32":
    _SW_RESTORE = 9
    # CreateFileW flags
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _OPEN_ALWAYS = 4
    _FILE_ATTRIBUTE_NORMAL = 0x80
    _INVALID_HANDLE_VALUE = -1
    # LockFileEx flags
    _LOCKFILE_EXCLUSIVE_LOCK = 0x00000002
    _LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
    _ERROR_LOCK_VIOLATION = 33


class _OVERLAPPED(ctypes.Structure):
    """Win32 OVERLAPPED struct (LockFileEx 必填, 但 byte range 锁可以全 0)."""

    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


def _kernel32() -> ctypes.WinDLL:
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    dll.CreateFileW.restype = wintypes.HANDLE
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    dll.LockFileEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_OVERLAPPED),
    ]
    dll.LockFileEx.restype = wintypes.BOOL
    dll.UnlockFileEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_OVERLAPPED),
    ]
    dll.UnlockFileEx.restype = wintypes.BOOL
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


def _default_lock_path() -> str:
    from ..config import CONFIG_DIR

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return str(CONFIG_DIR / ".app.lock")


class WindowsSingleInstance:
    """``LockFileEx`` 实现的单实例守卫 (满足 ``platform.base.SingleInstance`` Protocol)."""

    def __init__(
        self,
        lock_path: str | None = None,
        window_title: str = "QuaverQ",
    ) -> None:
        self._lock_path = lock_path
        self._window_title = window_title
        self._handle: int | None = None

    def _resolve_lock_path(self) -> str:
        return self._lock_path if self._lock_path is not None else _default_lock_path()

    async def acquire(self) -> bool:
        path = self._resolve_lock_path()
        kernel32 = _kernel32()
        # 打开文件: 跟其他读者 / 写者共享 (FILE_SHARE_*), 但锁字节 0 独占
        handle = kernel32.CreateFileW(
            path,
            _GENERIC_READ | _GENERIC_WRITE,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_ALWAYS,
            _FILE_ATTRIBUTE_NORMAL,
            None,
        )
        # CreateFileW 失败时返回 INVALID_HANDLE_VALUE (-1 as signed; 0xFFFFFFFFFFFFFFFF as unsigned)
        if handle == 0 or handle == 0xFFFFFFFFFFFFFFFF or handle == _INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            logger.warning("Windows 单实例: CreateFileW(%s) 失败, err=%d", path, err)
            return False
        overlapped = _OVERLAPPED()
        ok = kernel32.LockFileEx(
            handle,
            _LOCKFILE_EXCLUSIVE_LOCK | _LOCKFILE_FAIL_IMMEDIATELY,
            0,
            1,
            0,
            ctypes.byref(overlapped),
        )
        if not ok:
            last_err = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            if last_err == _ERROR_LOCK_VIOLATION:
                logger.info("Windows 单实例: 锁文件 %s 已被占用, 视为已存在实例", path)
            else:
                logger.warning("Windows 单实例: LockFileEx 失败, err=%d", last_err)
            return False
        self._handle = handle
        logger.info("Windows 单实例: 占用锁 %s 成功", path)
        return True

    async def notify_existing_raise(self) -> None:
        user32 = _user32()
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
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
                return False
            return True

        user32.EnumWindows(proc(cb), 0)
        if not target:
            logger.info("Windows 单实例: 未找到主窗口 (title=%s), 跳过 raise", self._window_title)
            return
        hwnd = target[0]
        user32.ShowWindow(hwnd, _SW_RESTORE)
        ok = user32.SetForegroundWindow(hwnd)
        if not ok:
            logger.info("Windows 单实例: SetForegroundWindow 被前台锁拒绝, 任务栏将闪烁提醒")

    def release(self) -> None:
        """释放锁; 幂等. 不删锁文件 —— OS close handle 时自动 unlock, 文件留着即可
        (1 byte 文件, 删了反而会触发 ``CreateFileW(OPEN_ALWAYS)`` 重建新 inode,
        让后续进程锁到不同的文件, 互斥失效).
        """
        if self._handle is None:
            return
        kernel32 = _kernel32()
        try:
            overlapped = _OVERLAPPED()
            kernel32.UnlockFileEx(self._handle, 0, 1, 0, ctypes.byref(overlapped))
        except OSError:
            pass
        try:
            kernel32.CloseHandle(self._handle)
        except OSError:
            logger.exception("Windows 单实例: 关闭锁 handle 异常")
        self._handle = None
