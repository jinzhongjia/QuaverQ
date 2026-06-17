"""共享 Win32 COM ctypes 助手 (IID / vtable / Release).

被 ``_windows_media_session`` 与 ``_windows_taskbar`` 复用 —— 之前两边各抄一份完全相同的
``_IID`` / ``_make_iid`` / ``_vtbl_ptr`` / ``Release`` helper. 本模块只用 ctypes 跨平台原语
(``WINFUNCTYPE`` 取不到时回退 ``CFUNCTYPE``), 故自身在非 Windows 上也能 import / 单测; 但
消费方 (media_session / taskbar) 仍因各自的 ``wintypes`` 依赖只在 Windows 加载.
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, c_uint32, c_void_p

_WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)


class _IID(ctypes.Structure):
    """COM IID / GUID (16 bytes)."""

    _fields_ = [
        ("Data1", c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _make_iid(s: str) -> _IID:
    """从 ``{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`` 字符串构造 IID."""
    s = s.strip("{}")
    parts = s.split("-")
    return _IID(
        int(parts[0], 16),
        int(parts[1], 16),
        int(parts[2], 16),
        (ctypes.c_ubyte * 8)(
            int(parts[3][0:2], 16),
            int(parts[3][2:4], 16),
            *(int(parts[4][i : i + 2], 16) for i in (0, 2, 4, 6, 8, 10)),
        ),
    )


def _vtbl_ptr(com_ptr: c_void_p, index: int) -> int:
    """读 COM 对象 vtable 第 ``index`` 项 (函数指针)."""
    vtbl = ctypes.cast(com_ptr, POINTER(POINTER(c_void_p)))[0]
    return vtbl[index]


def _release(com_ptr: c_void_p) -> int:
    """IUnknown::Release (vtable[2]); 返回新 refcount (调用方通常忽略)."""
    if not com_ptr or not com_ptr.value:
        return 0
    Proto = _WINFUNCTYPE(ctypes.c_ulong, c_void_p)
    fn = Proto(_vtbl_ptr(com_ptr, 2))
    return fn(com_ptr)
