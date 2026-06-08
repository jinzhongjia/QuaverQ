"""Windows SMTC (System Media Transport Controls) 集成.

为什么不用 winrt Python projection:
- ``winrt._winrt.SystemMediaTransportControls._from(ptr)`` 期望 winrt ``System.Object``,
  不接受裸 ``IUnknown*``. Win32 app 必须经
  ``ISystemMediaTransportControlsInterop::GetForWindow(hwnd, IID, **)`` 拿 SMTC, 返回
  的就是裸 COM 指针, winrt Python 没有公开 API 桥接到 Python 对象.
- 因此本模块**全程用 ctypes 直接调 COM vtable**, 不依赖 winrt Python 包.

设计:
- 进程级初始化 (``RoInitialize``) 幂等; 多次调用安全 (返 RPC_E_CHANGED_MODE 不抛).
- ``_SmtcHandle`` 持有 ``ISystemMediaTransportControls*`` (来自 GetForWindow); 析构时
  ``IUnknown::Release``. 调用方负责 add_ref / release 生命周期.
- 所有 ``put_*`` 属性走 vtable index 直调; 详细 index 见各方法文档.
- 按钮事件处理 (``ITypedEventHandler<...>``): 在 Python 端实现 COM 对象 + vtable
  (见本文件下面的 ``_ButtonHandler``), SMTC 回调时跨 ctypes thread → 用 Qt signal
  转主线程 (queued connection).
- 元数据 (DisplayUpdater) / 封面 (RandomAccessStreamReference) 同样 vtable 直调.

参考: ``Windows.Media.SystemMediaTransportControls`` IDL (Windows SDK).
"""

from __future__ import annotations

import asyncio
import ctypes
import inspect
import logging
import sys
from collections.abc import Callable
from ctypes import POINTER, byref, c_int32, c_uint32, c_void_p, wintypes
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal, Slot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- COM basics

if TYPE_CHECKING or sys.platform == "win32":
    _combase = ctypes.WinDLL("combase", use_last_error=True)
    _ole32 = ctypes.WinDLL("ole32", use_last_error=True)


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


# 错误码
_S_OK = 0
_RPC_E_CHANGED_MODE = 0x80010106  # RoInitialize 已用别的模式初始化, 视为 OK

# ISystemMediaTransportControlsInterop {DDB0472D-C911-4A1F-86D9-DC3D71A95F5A}
_IID_INTEROP = _make_iid("{DDB0472D-C911-4A1F-86D9-DC3D71A95F5A}")
# ISystemMediaTransportControls {99FA3FF4-1742-42A6-902E-087D41F965EC}
_IID_SMTC = _make_iid("{99FA3FF4-1742-42A6-902E-087D41F965EC}")
# ISystemMediaTransportControlsDisplayUpdater {8ABBC53E-FA55-4ECF-AD8E-C984E5DD1550}
_IID_DISPLAY_UPDATER = _make_iid("{8ABBC53E-FA55-4ECF-AD8E-C984E5DD1550}")
# IMusicDisplayProperties {6BBF0C59-D0A0-4286-9082-EB8F77D9CB1A}
_IID_MUSIC_PROPS = _make_iid("{6BBF0C59-D0A0-4286-9082-EB8F77D9CB1A}")
# IUnknown {00000000-0000-0000-C000-000000000046}
_IID_IUNKNOWN = _make_iid("{00000000-0000-0000-C000-000000000046}")
# IInspectable {AF86E2E0-B12D-4C6A-9C5A-D7AA65101E90}
_IID_IINSPECTABLE = _make_iid("{AF86E2E0-B12D-4C6A-9C5A-D7AA65101E90}")
# IAgileObject {94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}
_IID_IAGILEOBJECT = _make_iid("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
# ISystemMediaTransportControlsButtonPressedEventArgs {B7F47116-A56F-4DC8-9E11-92031F4A87C2}
_IID_BUTTON_ARGS = _make_iid("{B7F47116-A56F-4DC8-9E11-92031F4A87C2}")
# IUriRuntimeClassFactory {44A9796F-723E-4FDF-A218-033E75B0C084}
_IID_URI_FACTORY = _make_iid("{44A9796F-723E-4FDF-A218-033E75B0C084}")
# IRandomAccessStreamReferenceStatics {857309DC-3FBF-4E7D-986F-EF3B1A07A964}
# (实测 IID; 部分文档列的 {857DDDDB-...} 是错的)
_IID_RASR_STATICS = _make_iid("{857309DC-3FBF-4E7D-986F-EF3B1A07A964}")
# ITypedEventHandler<SystemMediaTransportControls, ButtonPressedEventArgs>
# (探测得到, 见 _qi_impl 日志)
_IID_BUTTON_HANDLER = _make_iid("{0557E996-7B23-5BAE-AA81-EA0D671143A4}")

# E_NOINTERFACE
_E_NOINTERFACE = 0x80004002


_HSTRING = c_void_p


def _setup_combase() -> None:
    """配置 combase 函数原型 (惰性, 仅 Windows 上调用)."""
    _combase.RoInitialize.argtypes = [c_int32]
    _combase.RoInitialize.restype = c_int32
    _combase.RoUninitialize.argtypes = []
    _combase.RoUninitialize.restype = None
    _combase.WindowsCreateString.argtypes = [wintypes.LPCWSTR, c_uint32, POINTER(_HSTRING)]
    _combase.WindowsCreateString.restype = c_int32
    _combase.WindowsDeleteString.argtypes = [_HSTRING]
    _combase.WindowsDeleteString.restype = c_int32
    _combase.RoGetActivationFactory.argtypes = [_HSTRING, POINTER(_IID), POINTER(c_void_p)]
    _combase.RoGetActivationFactory.restype = c_int32


_combase_inited = False


def _ensure_combase() -> None:
    global _combase_inited
    if _combase_inited:
        return
    _setup_combase()
    # RO_INIT_MULTITHREADED = 1; Qt main thread 一般已用 STA 初始化, COM 不允许混 ->
    # RoInitialize 返 RPC_E_CHANGED_MODE (0x80010106), 我们容忍 (用 Qt 已初的 STA).
    hr = _combase.RoInitialize(1) & 0xFFFFFFFF
    if hr not in (_S_OK, _RPC_E_CHANGED_MODE):
        raise OSError(f"RoInitialize failed: 0x{hr:08X}")
    _combase_inited = True


def _make_hstring(s: str) -> _HSTRING:
    h = _HSTRING()
    hr = _combase.WindowsCreateString(s, len(s), byref(h))
    if hr != _S_OK:
        raise OSError(f"WindowsCreateString failed: 0x{hr & 0xFFFFFFFF:08X}")
    return h


def _delete_hstring(h: _HSTRING) -> None:
    if h.value:
        _combase.WindowsDeleteString(h)


def _vtbl_ptr(com_ptr: c_void_p, index: int) -> int:
    """读 COM 对象 vtable 第 ``index`` 项 (函数指针)."""
    vtbl = ctypes.cast(com_ptr, POINTER(POINTER(c_void_p)))[0]
    return vtbl[index]


def _release(com_ptr: c_void_p) -> int:
    """IUnknown::Release (vtable[2]); 返回新 refcount."""
    if not com_ptr or not com_ptr.value:
        return 0
    Proto = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
    fn = Proto(_vtbl_ptr(com_ptr, 2))
    return fn(com_ptr)


# ---------------------------------------------------------------- 取 SMTC

# ISystemMediaTransportControlsInterop::GetForWindow vtable index = 6
# (3 IUnknown + 3 IInspectable)
_GetForWindowProto = ctypes.WINFUNCTYPE(
    c_int32,  # HRESULT
    c_void_p,  # this
    wintypes.HWND,  # hwnd
    POINTER(_IID),  # riid
    POINTER(c_void_p),  # **ppv
)


def _get_smtc_for_window(hwnd: int) -> c_void_p:
    """调 ISystemMediaTransportControlsInterop::GetForWindow.

    返回 ``ISystemMediaTransportControls*`` (调用方负责 Release).
    """
    _ensure_combase()
    name = _make_hstring("Windows.Media.SystemMediaTransportControls")
    try:
        interop = c_void_p()
        hr = _combase.RoGetActivationFactory(name, byref(_IID_INTEROP), byref(interop))
        if hr != _S_OK or not interop.value:
            raise OSError(f"RoGetActivationFactory failed: 0x{hr & 0xFFFFFFFF:08X}")
        try:
            get_for_window = _GetForWindowProto(_vtbl_ptr(interop, 6))
            smtc_ptr = c_void_p()
            hr = get_for_window(interop, hwnd, byref(_IID_SMTC), byref(smtc_ptr))
            if hr != _S_OK or not smtc_ptr.value:
                raise OSError(f"GetForWindow failed: 0x{hr & 0xFFFFFFFF:08X}")
            return smtc_ptr
        finally:
            _release(interop)
    finally:
        _delete_hstring(name)


# ---------------------------------------------------------------- ISMTC put_*

# vtable index (ISystemMediaTransportControls 在 IInspectable 6 个之后):
#   6  get_PlaybackStatus
#   7  put_PlaybackStatus
#   8  get_DisplayUpdater
#   9  get_SoundLevel
#  10  get_IsEnabled
#  11  put_IsEnabled
#  12  get_IsPlayEnabled
#  13  put_IsPlayEnabled
#  14  get_IsStopEnabled
#  15  put_IsStopEnabled
#  16  get_IsPauseEnabled
#  17  put_IsPauseEnabled
#  ...
#  24  get_IsPreviousEnabled
#  25  put_IsPreviousEnabled
#  26  get_IsNextEnabled
#  27  put_IsNextEnabled
#  ...
#  32  add_ButtonPressed
#  33  remove_ButtonPressed

# MediaPlaybackStatus enum: CLOSED=0, CHANGING=1, STOPPED=2, PLAYING=3, PAUSED=4
PLAYBACK_STATUS_CLOSED = 0
PLAYBACK_STATUS_CHANGING = 1
PLAYBACK_STATUS_STOPPED = 2
PLAYBACK_STATUS_PLAYING = 3
PLAYBACK_STATUS_PAUSED = 4

_PutBoolProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, ctypes.c_ubyte)
_PutInt32Proto = ctypes.WINFUNCTYPE(c_int32, c_void_p, c_int32)


def _put_bool(com_ptr: c_void_p, vtbl_index: int, value: bool, *, label: str) -> None:
    fn = _PutBoolProto(_vtbl_ptr(com_ptr, vtbl_index))
    hr = fn(com_ptr, 1 if value else 0)
    if hr != _S_OK:
        raise OSError(f"{label} failed: 0x{hr & 0xFFFFFFFF:08X}")


def _put_int(com_ptr: c_void_p, vtbl_index: int, value: int, *, label: str) -> None:
    fn = _PutInt32Proto(_vtbl_ptr(com_ptr, vtbl_index))
    hr = fn(com_ptr, value)
    if hr != _S_OK:
        raise OSError(f"{label} failed: 0x{hr & 0xFFFFFFFF:08X}")


# ---------------------------------------------------------------- 按钮事件 handler (Python 端 COM 对象)

# SystemMediaTransportControlsButton enum
BUTTON_PLAY = 0
BUTTON_PAUSE = 1
BUTTON_STOP = 2
BUTTON_NEXT = 6
BUTTON_PREVIOUS = 7

# IUnknown vtable function prototypes
_QueryInterfaceProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, POINTER(_IID), POINTER(c_void_p))
_AddRefRelease = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
# ITypedEventHandler<T,U>::Invoke(this, IInspectable* sender, IInspectable* args)
_InvokeProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, c_void_p, c_void_p)

# IButtonArgs::get_Button(this, MediaButton* out): vtable index 6 (IInspectable 6 + 0)
_GetButtonProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, POINTER(c_int32))


class _ButtonHandlerVTable(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", c_void_p),
        ("AddRef", c_void_p),
        ("Release", c_void_p),
        ("Invoke", c_void_p),
    ]


class _ButtonHandlerStruct(ctypes.Structure):
    """COM 对象布局: 第一个字段必须是 vtable 指针, 之后是私有数据."""

    _fields_ = [
        ("vtable", POINTER(_ButtonHandlerVTable)),
        # refcount: 用 c_long, AddRef/Release 用 Interlocked* 但单 Python 进程内 vtable 调用
        # 都在 SMTC 内部线程串行, 无并发, 用普通 +/- 也 OK.
        ("refcount", c_int32),
    ]


# 全局表: handler 指针 -> Python 回调函数. 防 GC, 同时让 vtable C 回调能找回 Python 对象.
_handler_callbacks: dict[int, _PyButtonHandler] = {}


def _iid_eq(a: _IID, b: _IID) -> bool:
    if a.Data1 != b.Data1 or a.Data2 != b.Data2 or a.Data3 != b.Data3:
        return False
    return bytes(a.Data4) == bytes(b.Data4)


# SMTC handler 允许的 IID 集合: 严格列表, 其他全 E_NOINTERFACE.
# 关键: INoMarshal 必须返 E_NOINTERFACE -- 否则 SMTC 认为我们"无法跨线程 marshal",
# 拒绝注册 (它需要 agile handler 从系统线程派发按钮事件).
_ACCEPTED_IIDS = (_IID_IUNKNOWN, _IID_IINSPECTABLE, _IID_IAGILEOBJECT, _IID_BUTTON_HANDLER)


def _qi_impl(this: int, riid_ptr: int, ppv_ptr: int) -> int:
    """QueryInterface: 只对允许列表里的 IID 返 this + AddRef; 其余 E_NOINTERFACE.

    必须对 ``INoMarshal`` 返 E_NOINTERFACE (而非 S_OK), 否则 SMTC 视我们为不可跨线程
    marshal 的对象, 拒绝注册 (它需要 agile handler 从系统线程派发按钮事件).
    """
    iid = ctypes.cast(riid_ptr, POINTER(_IID))[0]
    if any(_iid_eq(iid, ok) for ok in _ACCEPTED_IIDS):
        ctypes.cast(ppv_ptr, POINTER(c_void_p))[0] = this
        _addref_impl(this)
        return _S_OK
    ctypes.cast(ppv_ptr, POINTER(c_void_p))[0] = 0
    return _E_NOINTERFACE


def _addref_impl(this: int) -> int:
    handler = _handler_callbacks.get(this)
    if handler is None:
        return 1
    handler._struct.refcount += 1
    return handler._struct.refcount


def _release_impl(this: int) -> int:
    handler = _handler_callbacks.get(this)
    if handler is None:
        return 0
    handler._struct.refcount -= 1
    refs = handler._struct.refcount
    if refs <= 0:
        # SMTC 已不再持有 -> 解除全局引用, Python 端可 GC
        _handler_callbacks.pop(this, None)
    return refs


def _invoke_impl(this: int, _sender: int, args_ptr: int) -> int:
    """ITypedEventHandler::Invoke. args 是 ButtonPressedEventArgs*. 读 button 调 Python 回调."""
    handler = _handler_callbacks.get(this)
    if handler is None:
        return _S_OK
    try:
        # 从 args 读 button via get_Button (vtable index 6)
        args_void = c_void_p(args_ptr)
        get_button = _GetButtonProto(_vtbl_ptr(args_void, 6))
        out = c_int32()
        get_button(args_void, byref(out))
        handler._on_button(out.value)
    except Exception:
        logger.exception("SMTC 按钮回调出错")
    return _S_OK


# 全局保活: WINFUNCTYPE 回调一旦被 GC vtable 就成野指针
_QI_C = _QueryInterfaceProto(_qi_impl)
_ADDREF_C = _AddRefRelease(_addref_impl)
_RELEASE_C = _AddRefRelease(_release_impl)
_INVOKE_C = _InvokeProto(_invoke_impl)

# 单一全局 vtable, 所有 handler 共用 (vtable 指向函数, 不指向实例数据)
_GLOBAL_BUTTON_VTABLE = _ButtonHandlerVTable(
    QueryInterface=ctypes.cast(_QI_C, c_void_p).value,
    AddRef=ctypes.cast(_ADDREF_C, c_void_p).value,
    Release=ctypes.cast(_RELEASE_C, c_void_p).value,
    Invoke=ctypes.cast(_INVOKE_C, c_void_p).value,
)


class _PyButtonHandler:
    """Python 端实现的 ``ITypedEventHandler<SMTC, ButtonArgs>`` COM 对象."""

    def __init__(self, callback) -> None:
        self._callback = callback
        self._struct = _ButtonHandlerStruct()
        self._struct.vtable = ctypes.pointer(_GLOBAL_BUTTON_VTABLE)
        self._struct.refcount = 1  # SMTC add_ButtonPressed 内部还会 AddRef 一次
        self._ptr = ctypes.addressof(self._struct)
        _handler_callbacks[self._ptr] = self

    @property
    def ptr(self) -> int:
        return self._ptr

    def _on_button(self, button_id: int) -> None:
        try:
            self._callback(button_id)
        except Exception:
            logger.exception("button callback raised")


# add_ButtonPressed: vtable index 32; signature (this, handler*, token*)
_EventRegistrationToken = ctypes.c_int64  # 64-bit
_AddButtonProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, c_void_p, POINTER(_EventRegistrationToken))
_RemoveButtonProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, _EventRegistrationToken)


# ---------------------------------------------------------------- DisplayUpdater (元数据)

# DisplayUpdater vtable index (在 IInspectable 6 个之后):
#   6  get_Type
#   7  put_Type (MediaPlaybackType: NONE=0, MUSIC=1, VIDEO=2, IMAGE=3)
#   8  get_AppMediaId
#   9  put_AppMediaId
#  10  get_Thumbnail
#  11  put_Thumbnail
#  12  get_MusicProperties
#  13  get_VideoProperties
#  14  get_ImageProperties
#  15  CopyFromFileAsync
#  16  ClearAll
#  17  Update

MEDIA_PLAYBACK_TYPE_MUSIC = 1

_GetIfaceProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, POINTER(c_void_p))
_PutHStringProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, _HSTRING)
_VoidProto = ctypes.WINFUNCTYPE(c_int32, c_void_p)


def _get_iface(com_ptr: c_void_p, vtbl_index: int, label: str) -> c_void_p:
    fn = _GetIfaceProto(_vtbl_ptr(com_ptr, vtbl_index))
    out = c_void_p()
    hr = fn(com_ptr, byref(out)) & 0xFFFFFFFF
    if hr != _S_OK or not out.value:
        raise OSError(f"{label} failed: 0x{hr:08X}")
    return out


def _put_hstring(com_ptr: c_void_p, vtbl_index: int, value: str, *, label: str) -> None:
    h = _make_hstring(value)
    try:
        fn = _PutHStringProto(_vtbl_ptr(com_ptr, vtbl_index))
        hr = fn(com_ptr, h) & 0xFFFFFFFF
        if hr != _S_OK:
            raise OSError(f"{label} failed: 0x{hr:08X}")
    finally:
        _delete_hstring(h)


def _call_void(com_ptr: c_void_p, vtbl_index: int, *, label: str) -> None:
    fn = _VoidProto(_vtbl_ptr(com_ptr, vtbl_index))
    hr = fn(com_ptr) & 0xFFFFFFFF
    if hr != _S_OK:
        raise OSError(f"{label} failed: 0x{hr:08X}")


# ---------------------------------------------------------------- Thumbnail (URI -> RandomAccessStreamReference)

# IUriRuntimeClassFactory::CreateUri(HSTRING, IUriRuntimeClass**)
# vtable[6] (after 3 IUnknown + 3 IInspectable)
_CreateUriProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, _HSTRING, POINTER(c_void_p))
# IRandomAccessStreamReferenceStatics::CreateFromUri(IUriRuntimeClass*, IRandomAccessStreamReference**)
_CreateFromUriProto = ctypes.WINFUNCTYPE(c_int32, c_void_p, c_void_p, POINTER(c_void_p))


def _make_stream_reference_from_uri(uri: str) -> c_void_p:
    """``RandomAccessStreamReference.CreateFromUri(Uri.from_string(uri))``.

    返回 IRandomAccessStreamReference* (调用方 Release).
    """
    _ensure_combase()
    # 1. Uri factory + 创建 Uri
    uri_factory_name = _make_hstring("Windows.Foundation.Uri")
    try:
        uri_factory = c_void_p()
        hr = (
            _combase.RoGetActivationFactory(
                uri_factory_name, byref(_IID_URI_FACTORY), byref(uri_factory)
            )
            & 0xFFFFFFFF
        )
        if hr != _S_OK or not uri_factory.value:
            raise OSError(f"Uri factory failed: 0x{hr:08X}")
    finally:
        _delete_hstring(uri_factory_name)

    try:
        uri_hstr = _make_hstring(uri)
        try:
            uri_obj = c_void_p()
            create_uri = _CreateUriProto(_vtbl_ptr(uri_factory, 6))
            hr = create_uri(uri_factory, uri_hstr, byref(uri_obj)) & 0xFFFFFFFF
            if hr != _S_OK or not uri_obj.value:
                raise OSError(f"CreateUri failed: 0x{hr:08X}")
        finally:
            _delete_hstring(uri_hstr)
    finally:
        _release(uri_factory)

    try:
        # 2. RASR statics + CreateFromUri
        rasr_name = _make_hstring("Windows.Storage.Streams.RandomAccessStreamReference")
        try:
            rasr_factory = c_void_p()
            hr = (
                _combase.RoGetActivationFactory(
                    rasr_name, byref(_IID_RASR_STATICS), byref(rasr_factory)
                )
                & 0xFFFFFFFF
            )
            if hr != _S_OK or not rasr_factory.value:
                raise OSError(f"RASR statics failed: 0x{hr:08X}")
        finally:
            _delete_hstring(rasr_name)
        try:
            stream_ref = c_void_p()
            # vtable[6] = CreateFromFile, [7] = CreateFromUri, [8] = CreateFromStream
            create_from_uri = _CreateFromUriProto(_vtbl_ptr(rasr_factory, 7))
            hr = create_from_uri(rasr_factory, uri_obj, byref(stream_ref)) & 0xFFFFFFFF
            if hr != _S_OK or not stream_ref.value:
                raise OSError(f"CreateFromUri failed: 0x{hr:08X}")
            return stream_ref
        finally:
            _release(rasr_factory)
    finally:
        _release(uri_obj)


# ---------------------------------------------------------------- WindowsMediaSession


class _SmtcSession:
    """SMTC COM 包装层 (vtable 直调, 不与 Qt 耦合); 由 WindowsMediaSession 持有."""

    def __init__(self) -> None:
        self._smtc: c_void_p | None = None
        self._display: c_void_p | None = None
        self._music: c_void_p | None = None
        self._handler: _PyButtonHandler | None = None
        self._button_token: int = 0

    def attach(self, hwnd: int, *, on_button) -> None:
        """绑到指定窗口的 SMTC, 注册按钮事件回调 (button_id: int)."""
        self._smtc = _get_smtc_for_window(hwnd)
        # 启用 + 4 个按钮
        _put_bool(self._smtc, 11, True, label="put_IsEnabled")
        _put_bool(self._smtc, 13, True, label="put_IsPlayEnabled")
        _put_bool(self._smtc, 17, True, label="put_IsPauseEnabled")
        _put_bool(self._smtc, 25, True, label="put_IsPreviousEnabled")
        _put_bool(self._smtc, 27, True, label="put_IsNextEnabled")
        _put_int(self._smtc, 7, PLAYBACK_STATUS_STOPPED, label="put_PlaybackStatus")

        # 拿 DisplayUpdater (vtbl 8) + 设 Type = MUSIC + 拿 MusicProperties
        self._display = _get_iface(self._smtc, 8, "get_DisplayUpdater")
        _put_int(self._display, 7, MEDIA_PLAYBACK_TYPE_MUSIC, label="put_Type=Music")
        self._music = _get_iface(self._display, 12, "get_MusicProperties")

        # 注册按钮事件
        self._handler = _PyButtonHandler(on_button)
        add_button = _AddButtonProto(_vtbl_ptr(self._smtc, 32))
        token = _EventRegistrationToken()
        hr = add_button(self._smtc, c_void_p(self._handler.ptr), byref(token)) & 0xFFFFFFFF
        if hr != _S_OK:
            raise OSError(f"add_ButtonPressed failed: 0x{hr:08X}")
        self._button_token = token.value

        logger.info("Windows SMTC: 已绑定到 hwnd=0x%X (含按钮事件)", hwnd)

    def set_playback_status(self, status: int) -> None:
        """status ∈ {PLAYBACK_STATUS_*}."""
        if self._smtc is None:
            return
        _put_int(self._smtc, 7, status, label="put_PlaybackStatus")

    def push_metadata(self, *, title: str = "", artist: str = "") -> None:
        """更新音乐元数据 (Title / Artist), 调 Update() 提交.

        Album 名字属于 ``IMusicDisplayProperties2.put_AlbumTitle``, 暂不接 (要走 QI 拿
        v2 接口, 多 50 行 ctypes; 第一版优先 Title + Artist 即可).
        """
        if self._music is None or self._display is None:
            return
        # IMusicDisplayProperties vtable: 7 put_Title, 11 put_Artist
        _put_hstring(self._music, 7, title, label="put_Title")
        _put_hstring(self._music, 11, artist, label="put_Artist")
        # 提交到 SMTC
        _call_void(self._display, 17, label="DisplayUpdater.Update")

    def push_thumbnail_from_uri(self, uri: str | None) -> None:
        """把 HTTP(S) URI 设为 SMTC 卡片封面.

        ``uri = None`` 或空时清空封面 (put_Thumbnail(NULL)).

        关键约束: ``RandomAccessStreamReference.CreateFromUri`` 只支持
        ``ms-appx://`` / ``ms-appdata://`` / ``http(s)://`` URI, **不支持
        ``file://``**. 调用方需要先把本地文件经由本机 http 服 (见 ``StreamProxy``)
        包成 ``http://127.0.0.1:port/...`` URI.
        """
        if self._display is None:
            return
        # vtable: put_Thumbnail 在 DisplayUpdater[11]
        put_thumb = ctypes.WINFUNCTYPE(c_int32, c_void_p, c_void_p)(_vtbl_ptr(self._display, 11))

        if not uri:
            hr = put_thumb(self._display, c_void_p(0)) & 0xFFFFFFFF
            if hr == _S_OK:
                try:
                    _call_void(self._display, 17, label="DisplayUpdater.Update")
                except OSError:
                    logger.debug("SMTC clear thumbnail Update 失败 (忽略)")
            return

        try:
            stream_ref = _make_stream_reference_from_uri(uri)
        except OSError:
            logger.exception("SMTC: 构造 thumbnail StreamReference 失败 (uri=%s)", uri)
            return
        try:
            hr = put_thumb(self._display, stream_ref) & 0xFFFFFFFF
            if hr != _S_OK:
                logger.warning("SMTC: put_Thumbnail 失败 hr=0x%08X", hr)
                return
            _call_void(self._display, 17, label="DisplayUpdater.Update")
        finally:
            _release(stream_ref)

    def detach(self) -> None:
        if self._smtc is not None:
            if self._handler is not None and self._button_token:
                try:
                    remove_button = _RemoveButtonProto(_vtbl_ptr(self._smtc, 33))
                    remove_button(self._smtc, _EventRegistrationToken(self._button_token))
                except OSError:
                    logger.exception("SMTC: 移除按钮回调失败")
                self._button_token = 0
            try:
                _put_bool(self._smtc, 11, False, label="put_IsEnabled (detach)")
            except OSError:
                logger.exception("Windows SMTC: 关闭 IsEnabled 失败")
        if self._music is not None:
            _release(self._music)
            self._music = None
        if self._display is not None:
            _release(self._display)
            self._display = None
        if self._smtc is not None:
            _release(self._smtc)
            self._smtc = None
        self._handler = None
        logger.info("Windows SMTC: 已解绑")


# ---------------------------------------------------------------- Qt 侧 controller


# Qt PlaybackState → SMTC PlaybackStatus 映射 (Qt 端是字符串, 见 PlayerController.playbackState)
_PLAYBACK_STATE_MAP = {
    "playing": PLAYBACK_STATUS_PLAYING,
    "paused": PLAYBACK_STATUS_PAUSED,
    "stopped": PLAYBACK_STATUS_STOPPED,
}


class WindowsMediaSession(QObject):
    """Windows 端媒体会话 controller, 类比 Linux ``MprisController``.

    生命周期:
    - ``__init__(player_controller, *, raise_window, quit_app)``: 不连 SMTC, 只挂 signal.
    - ``async start_async()``: 找主窗口 HWND -> 绑 SMTC -> sync 一次状态; 返 True/False.
    - ``async stop_async()``: 解绑 SMTC; 但 Python signal 仍挂着 (用于 controller 被复用场景).

    线程模型:
    - SMTC 按钮事件回调来自 system thread; ctypes 调用 ``_emit_button(button_id)`` 后,
      通过 Qt signal (auto/queued) 把控制流转回 main thread 处理 player_controller 调用.
    """

    _buttonPressed = Signal(int)  # button_id

    def __init__(
        self,
        player_controller,
        *,
        raise_window: Callable[[], None] | None = None,
        quit_app: Callable[[], None] | None = None,
        cover_cache=None,
        stream_proxy=None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player_controller
        self._raise_window = raise_window or (lambda: None)
        self._quit_app = quit_app or (lambda: None)
        self._cover_cache = cover_cache
        self._stream_proxy = stream_proxy
        self._session: _SmtcSession | None = None
        self._started = False
        # 跨线程: SMTC 系统线程 emit -> Qt 队列到 main thread 调 _on_button_main
        self._buttonPressed.connect(self._on_button_main, Qt.ConnectionType.QueuedConnection)
        # 接 PlayerController 信号 (run on main thread, 直接 push 到 SMTC)
        self._player.currentSongChanged.connect(self._push_metadata)
        self._player.playbackStateChanged.connect(self._push_playback_status)

    async def start_async(self) -> bool:
        from PySide6.QtGui import QGuiApplication

        hwnd = 0
        for w in QGuiApplication.topLevelWindows():
            wid = int(w.winId())
            if wid:
                hwnd = wid
                break
        if not hwnd:
            logger.warning("Windows SMTC: 未找到主窗口, 跳过")
            return False
        try:
            session = _SmtcSession()
            session.attach(hwnd, on_button=self._emit_button)
            self._session = session
            self._started = True
            self._sync_all()
            return True
        except OSError:
            logger.exception("Windows SMTC 启动失败")
            return False

    async def stop_async(self) -> None:
        if self._session is not None:
            try:
                self._session.detach()
            except Exception:
                logger.exception("Windows SMTC 解绑失败")
            self._session = None
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    # ---- SMTC -> Python (called from SMTC system thread!) ----

    def _emit_button(self, button_id: int) -> None:
        """ctypes callback (SMTC thread); 经 Qt signal 队列到 main thread."""
        self._buttonPressed.emit(button_id)

    @Slot(int)
    def _on_button_main(self, button_id: int) -> None:
        """Main thread slot: button_id -> PlayerController 动作."""
        try:
            if button_id == BUTTON_PLAY:
                self._invoke(self._player.play)
            elif button_id == BUTTON_PAUSE:
                self._invoke(self._player.pause)
            elif button_id == BUTTON_STOP:
                self._invoke(self._player.stop)
            elif button_id == BUTTON_NEXT:
                self._invoke(self._player.next)
            elif button_id == BUTTON_PREVIOUS:
                self._invoke(self._player.prev)
        except Exception:
            logger.exception("SMTC 按钮派发失败")

    @staticmethod
    def _invoke(command: Callable[[], object]) -> None:
        """模仿 MprisController._invoke_player_command: 接 async 命令也能跑."""
        try:
            result = command()
        except RuntimeError as exc:
            logger.warning("SMTC command ignored: %s", exc)
            return
        if asyncio.isfuture(result):
            return
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("SMTC command ignored: no running event loop")
                return
            loop.create_task(result)

    # ---- Player signals -> SMTC ----

    def _sync_all(self) -> None:
        self._push_metadata()
        self._push_playback_status()

    def _push_metadata(self) -> None:
        if not self._started or self._session is None:
            return
        song = self._player.currentSong  # dict 形态, 见 PlayerController
        if not isinstance(song, dict):
            return
        title = str(song.get("name", "") or "")
        # singers 字段: list of {"name": ...}
        artists = []
        for s in song.get("singers", []) or []:
            if isinstance(s, dict):
                n = s.get("name")
                if n:
                    artists.append(str(n))
        artist = " / ".join(artists)
        try:
            self._session.push_metadata(title=title, artist=artist)
        except OSError:
            logger.exception("SMTC push_metadata 失败")

        # 封面: 用 stream_proxy 把本地缓存文件包成 http URI (SMTC.CreateFromUri 不收 file://).
        cover_url = str(song.get("coverUrl") or "") if isinstance(song, dict) else ""
        thumb_uri = self._resolve_thumbnail_uri(cover_url)
        try:
            self._session.push_thumbnail_from_uri(thumb_uri)
        except Exception:
            logger.exception("SMTC push_thumbnail 失败")
        # 本地还没下: 后台拉, 拉完再推
        if thumb_uri is None and self._cover_cache is not None and cover_url:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(self._fetch_and_push_thumbnail(cover_url))

    def _resolve_thumbnail_uri(self, cover_url: str) -> str | None:
        """把歌曲 coverUrl (远端 CDN) 转成本机 http url (经 StreamProxy)."""
        if not cover_url or self._cover_cache is None or self._stream_proxy is None:
            return None
        local = self._cover_cache.get_path(cover_url)
        if local is None:
            return None
        return self._stream_proxy.local_file_url(local.name)

    async def _fetch_and_push_thumbnail(self, url: str) -> None:
        try:
            local = await self._cover_cache.fetch(url)
        except Exception:
            logger.exception("SMTC: 后台拉封面失败")
            return
        if local is None or not self._started or self._session is None:
            return
        # 拉到时可能用户已经切歌了; 再核对一次当前歌曲的封面 URL
        song = self._player.currentSong
        if not isinstance(song, dict) or str(song.get("coverUrl") or "") != url:
            return
        uri = self._stream_proxy.local_file_url(local.name) if self._stream_proxy else None
        if uri is None:
            return
        try:
            self._session.push_thumbnail_from_uri(uri)
        except Exception:
            logger.exception("SMTC: 后台拉到封面后推送失败")

    def _push_playback_status(self) -> None:
        if not self._started or self._session is None:
            return
        state_raw = self._player.playbackState
        status = _PLAYBACK_STATE_MAP.get(str(state_raw or "").lower(), PLAYBACK_STATUS_STOPPED)
        try:
            self._session.set_playback_status(status)
        except OSError:
            logger.exception("SMTC set_playback_status 失败")
