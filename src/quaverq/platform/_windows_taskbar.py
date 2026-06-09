"""Windows 任务栏深度集成 -- ``ITaskbarList3`` 进度条 + 缩略图按钮.

通过 ctypes 直接调 ``ITaskbarList3`` COM 接口 (classic COM, 非 WinRT):

- ``SetProgressValue`` / ``SetProgressState``: 把播放进度画到任务栏图标上
  (类似 IE / Edge 下载进度条).
- ``ThumbBarAddButtons`` / ``ThumbBarUpdateButtons``: 鼠标悬停任务栏图标弹出
  缩略图时显示 ⏮ ⏯ ⏭ 三个按钮.

按钮点击通过 ``SetWindowSubclass`` 安装自定义 WndProc 截 ``WM_COMMAND``
(``HIWORD=0``, ``LOWORD=button id``). 不能用 ``QAbstractNativeEventFilter`` —
PySide6 + frameless QML 窗口下不可靠 (见 AGENTS.md 已踩过的雷).

延迟初始化: ``QTimer.singleShot(500ms)`` 等主窗口 HWND 就绪后再 ``CoCreateInstance``;
后续按 ``player_controller`` 信号增量更新.

只在 Windows 实例化; Linux / macOS PAL 返 None.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable
from ctypes import POINTER, byref, c_int32, c_uint64, c_void_p, wintypes
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QFont, QImage, QPainter

if TYPE_CHECKING or sys.platform == "win32":
    _ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    _comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- 类型别名


_LRESULT = ctypes.c_ssize_t  # LONG_PTR (signed pointer-sized)
_UINT_PTR = ctypes.c_size_t
_DWORD_PTR = ctypes.c_size_t


# ---------------------------------------------------------------- IID / CLSID


class _IID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _make_iid(s: str) -> _IID:
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


_CLSID_TASKBARLIST = _make_iid("{56FDF344-FD6D-11D0-958A-006097C9A090}")
_IID_ITASKBARLIST3 = _make_iid("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")

_CLSCTX_INPROC_SERVER = 0x1
_S_OK = 0
_WM_COMMAND = 0x0111

# TBPFLAG (SetProgressState)
_TBPF_NOPROGRESS = 0
_TBPF_NORMAL = 0x2
_TBPF_PAUSED = 0x8

# THBMASK (THUMBBUTTON.dwMask)
_THB_ICON = 0x2
_THB_TOOLTIP = 0x4
_THB_FLAGS = 0x8

# THBFLAGS (THUMBBUTTON.dwFlags)
_THBF_ENABLED = 0

# ITaskbarList3 vtable indices (3 IUnknown + ITaskbarList[3..7] + ITaskbarList2[8] + ITaskbarList3[9+])
_VT_HRINIT = 3
_VT_SETPROGRESSVALUE = 9
_VT_SETPROGRESSSTATE = 10
_VT_THUMBBARADDBUTTONS = 15
_VT_THUMBBARUPDATEBUTTONS = 16

# Button IDs (任意 16-bit; subclass WndProc 用这些 ID 区分点击源)
_BTN_PREV = 1001
_BTN_PLAY_PAUSE = 1002
_BTN_NEXT = 1003

# DWM iconic representation (Windows 7+, 让任务栏悬停缩略图显示自定义图而不是窗口缩影).
_DWMWA_FORCE_ICONIC_REPRESENTATION = 7
_DWMWA_HAS_ICONIC_BITMAP = 10
_WM_DWMSENDICONICTHUMBNAIL = 0x0323
_WM_DWMSENDICONICLIVEPREVIEWBITMAP = 0x0326
# DIB 格式常量
_BI_RGB = 0
_DIB_RGB_COLORS = 0
# 预渲染封面分辨率 (Windows 任务栏缩略图通常 ≤ 280x180; 200 足够清晰且高度可适应正方形封面)
_COVER_BITMAP_SIZE = 200


# ---------------------------------------------------------------- C 结构体


class _THUMBBUTTON(ctypes.Structure):
    _fields_ = [
        ("dwMask", wintypes.DWORD),
        ("iId", wintypes.UINT),
        ("iBitmap", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 260),
        ("dwFlags", wintypes.DWORD),
    ]


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        # bmiColors 仅 BI_BITFIELDS / 索引模式用; BI_RGB 32bpp 不需要, 保留 3 项占位.
        ("bmiColors", wintypes.DWORD * 3),
    ]


# ---------------------------------------------------------------- COM helpers


def _vtbl_ptr(com_ptr: c_void_p, index: int) -> int:
    """读 COM 对象 vtable 第 ``index`` 项 (函数指针)."""
    vtbl = ctypes.cast(com_ptr, POINTER(POINTER(c_void_p)))[0]
    return vtbl[index]


def _release_com(com_ptr: c_void_p) -> None:
    if not com_ptr or not com_ptr.value:
        return
    proto = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
    fn = proto(_vtbl_ptr(com_ptr, 2))
    fn(com_ptr)


def _co_create_taskbar_list() -> c_void_p:
    """``CoCreateInstance`` 拿 ``ITaskbarList3`` + ``HrInit``. 失败返空指针."""
    _ole32.CoCreateInstance.argtypes = [
        POINTER(_IID),
        c_void_p,
        wintypes.DWORD,
        POINTER(_IID),
        POINTER(c_void_p),
    ]
    _ole32.CoCreateInstance.restype = c_int32

    ptr = c_void_p()
    hr = _ole32.CoCreateInstance(
        byref(_CLSID_TASKBARLIST),
        None,
        _CLSCTX_INPROC_SERVER,
        byref(_IID_ITASKBARLIST3),
        byref(ptr),
    )
    if hr != _S_OK or not ptr.value:
        logger.warning("CoCreateInstance ITaskbarList3 失败: HRESULT=0x%08X", hr & 0xFFFFFFFF)
        return c_void_p()

    init_proto = ctypes.WINFUNCTYPE(c_int32, c_void_p)
    init_fn = init_proto(_vtbl_ptr(ptr, _VT_HRINIT))
    hr = init_fn(ptr)
    if hr != _S_OK:
        logger.warning("ITaskbarList3::HrInit 失败: HRESULT=0x%08X", hr & 0xFFFFFFFF)
        _release_com(ptr)
        return c_void_p()
    return ptr


# ---------------------------------------------------------------- HICON 工具


def _qimage_to_hicon(image: QImage) -> int:
    """``QImage`` -> ``HICON``. 返 0 表示失败. 调用方负责后续 ``DestroyIcon``."""
    img = image.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    raw = bytes(img.constBits()[: img.bytesPerLine() * h])

    _gdi32.CreateBitmap.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
    ]
    _gdi32.CreateBitmap.restype = wintypes.HBITMAP
    # 必须显式声明: 64-bit 上 HANDLE 值是 8 字节, 不声明 ctypes 默认按 c_int 转 ->
    # OverflowError "int too long to convert". HGDIOBJ 是 c_void_p 别名.
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _gdi32.DeleteObject.restype = wintypes.BOOL

    hb_color = _gdi32.CreateBitmap(w, h, 1, 32, raw)
    if not hb_color:
        return 0
    # 1bpp mask 全 0 = 全部不透明; 透明信息走 32bpp ARGB 的 alpha 通道.
    mask_stride = ((w + 31) // 32) * 4
    hb_mask = _gdi32.CreateBitmap(w, h, 1, 1, bytes(mask_stride * h))
    if not hb_mask:
        _gdi32.DeleteObject(hb_color)
        return 0

    info = _ICONINFO(True, 0, 0, hb_mask, hb_color)
    _user32.CreateIconIndirect.argtypes = [POINTER(_ICONINFO)]
    _user32.CreateIconIndirect.restype = wintypes.HICON
    hicon = _user32.CreateIconIndirect(byref(info))

    _gdi32.DeleteObject(hb_color)
    _gdi32.DeleteObject(hb_mask)
    return int(hicon) if hicon else 0


def _qimage_to_dib(image: QImage) -> int:
    """``QImage`` -> ``HBITMAP`` (DIB section, 32bpp BGRA top-down).

    DWM 的 ``DwmSetIconicThumbnail`` / ``DwmSetIconicLivePreviewBitmap`` 必须收 DIB
    (CreateDIBSection 产物), 不接受 CreateBitmap 产的 DDB. 这里专门做 DIB 路径,
    跟图标的 ``_qimage_to_hicon`` 区分.
    返 0 表示失败.
    """
    img = image.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return 0

    bi = _BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h  # 负数 = top-down, 与 QImage 行顺序一致, 不用翻转
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = _BI_RGB
    bi.bmiHeader.biSizeImage = w * h * 4

    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.ReleaseDC.restype = ctypes.c_int
    _gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        POINTER(_BITMAPINFO),
        wintypes.UINT,
        POINTER(c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    _gdi32.CreateDIBSection.restype = wintypes.HBITMAP

    hdc = _user32.GetDC(None)
    bits_ptr = c_void_p()
    hbm = _gdi32.CreateDIBSection(hdc, byref(bi), _DIB_RGB_COLORS, byref(bits_ptr), None, 0)
    _user32.ReleaseDC(None, hdc)
    if not hbm or not bits_ptr.value:
        return 0

    # 拷贝 QImage 像素到 DIB. QImage::Format_ARGB32 = BGRA in 内存 (与 Windows DIB 一致).
    src = bytes(img.constBits()[: img.bytesPerLine() * h])
    ctypes.memmove(bits_ptr, src, len(src))
    return int(hbm)


def _render_glyph_icon(glyph: str, size: int = 20) -> int:
    """渲染 Unicode 符号为 ``HICON`` (透明背景 + 白色字形, 任务栏缩略图下都看得清)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont("Segoe UI Symbol", size - 6, QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255))
    p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    return _qimage_to_hicon(img)


# ---------------------------------------------------------------- SUBCLASSPROC


_SUBCLASSPROC = ctypes.WINFUNCTYPE(
    _LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    _UINT_PTR,
    _DWORD_PTR,
)


# ---------------------------------------------------------------- 主类


class WindowsTaskbar(QObject):
    """Windows 任务栏 controller. 进度条 + ⏮ ⏯ ⏭ 缩略图按钮."""

    def __init__(
        self,
        player_controller: Any,
        hwnd_provider: Callable[[], int],
        cover_cache: Any = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player_controller
        self._hwnd_provider = hwnd_provider
        self._cover_cache = cover_cache  # 用于把当前歌封面拿来当任务栏缩略图
        self._hwnd: int = 0
        self._taskbar = c_void_p()
        self._initialized = False
        self._is_playing = False
        self._subclass_proc: Any = None  # 必须持有引用防 GC, 否则 SUBCLASSPROC 变野指针
        self._thumbnail_hbm: int = 0  # 当前歌封面的 DIB HBITMAP, 切歌时替换 + DeleteObject

        # 预渲染 4 个 HICON (无需 HWND, 可以提前做)
        self._icon_prev = _render_glyph_icon("⏮")
        self._icon_play = _render_glyph_icon("⏵")
        self._icon_pause = _render_glyph_icon("⏸")
        self._icon_next = _render_glyph_icon("⏭")

        for sig_name, slot in (
            ("playbackStateChanged", self._on_state_changed),
            ("positionMsChanged", self._on_position_changed),
            ("durationMsChanged", self._on_position_changed),
            ("currentSongChanged", self._on_song_changed),
        ):
            sig = getattr(self._player, sig_name, None)
            if sig is not None:
                sig.connect(slot)

        # 延迟初始化: engine.load 返回时 HWND 可能还没分配 / taskbar 还没识别本窗口.
        # 500ms 是经验值 — taskbar 注册流程通常 ms 级, 给一点 buffer.
        QTimer.singleShot(500, self._try_init)

    # ------------------------------------------------------------------ 初始化
    def _try_init(self) -> bool:
        if self._initialized:
            return True
        hwnd = self._hwnd_provider()
        if not hwnd:
            # HWND 还没好, 下一次 signal 来时再尝试.
            return False
        self._hwnd = hwnd
        self._taskbar = _co_create_taskbar_list()
        if not self._taskbar.value:
            return False
        if not self._add_thumb_buttons():
            return False
        self._install_subclass()
        self._enable_iconic_thumbnail()
        self._initialized = True
        logger.info(
            "Windows 任务栏: ITaskbarList3 + 缩略图按钮 + DWM 封面预览已就绪 (hwnd=0x%X)", hwnd
        )
        # 启动时同步一次
        self._sync_progress()
        self._sync_button_icons(force=True)
        self._refresh_cover_thumbnail()
        return True

    def _enable_iconic_thumbnail(self) -> None:
        """开启 DWM 自定义缩略图: 任务栏悬停不再显示窗口快照, 改请求我们提供 bitmap.

        ``DWMWA_FORCE_ICONIC_REPRESENTATION`` 让 DWM 用 iconic 表示 (要么图标要么我们给的 bitmap),
        ``DWMWA_HAS_ICONIC_BITMAP`` 告 DWM 我们会通过 ``WM_DWMSENDICONICTHUMBNAIL`` 回应实际 bitmap.
        """
        _dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            c_void_p,
            wintypes.DWORD,
        ]
        _dwmapi.DwmSetWindowAttribute.restype = c_int32
        flag = ctypes.c_int32(1)  # TRUE
        for attr in (_DWMWA_FORCE_ICONIC_REPRESENTATION, _DWMWA_HAS_ICONIC_BITMAP):
            hr = _dwmapi.DwmSetWindowAttribute(self._hwnd, attr, byref(flag), 4)
            if hr != _S_OK:
                logger.warning(
                    "DwmSetWindowAttribute(%d) 失败: HRESULT=0x%08X", attr, hr & 0xFFFFFFFF
                )

    def _add_thumb_buttons(self) -> bool:
        """``ThumbBarAddButtons`` 每个窗口只允许调一次, 后续走 ``ThumbBarUpdateButtons``."""
        buttons = self._build_buttons(playing=False)
        proto = ctypes.WINFUNCTYPE(
            c_int32, c_void_p, wintypes.HWND, wintypes.UINT, POINTER(_THUMBBUTTON)
        )
        fn = proto(_vtbl_ptr(self._taskbar, _VT_THUMBBARADDBUTTONS))
        hr = fn(self._taskbar, self._hwnd, 3, buttons)
        if hr != _S_OK:
            logger.warning("ThumbBarAddButtons 失败: HRESULT=0x%08X", hr & 0xFFFFFFFF)
            return False
        return True

    def _build_buttons(self, *, playing: bool):
        """构造 ``THUMBBUTTON[3]``: 上一首 / 播放或暂停 / 下一首."""
        buttons = (_THUMBBUTTON * 3)()
        mask = _THB_ICON | _THB_TOOLTIP | _THB_FLAGS

        buttons[0].dwMask = mask
        buttons[0].iId = _BTN_PREV
        buttons[0].hIcon = self._icon_prev
        buttons[0].szTip = "上一首"
        buttons[0].dwFlags = _THBF_ENABLED

        buttons[1].dwMask = mask
        buttons[1].iId = _BTN_PLAY_PAUSE
        buttons[1].hIcon = self._icon_pause if playing else self._icon_play
        buttons[1].szTip = "暂停" if playing else "播放"
        buttons[1].dwFlags = _THBF_ENABLED

        buttons[2].dwMask = mask
        buttons[2].iId = _BTN_NEXT
        buttons[2].hIcon = self._icon_next
        buttons[2].szTip = "下一首"
        buttons[2].dwFlags = _THBF_ENABLED
        return buttons

    def _install_subclass(self) -> None:
        """``SetWindowSubclass`` 截 ``WM_COMMAND`` 收按钮点击."""
        proc = _SUBCLASSPROC(self._subclass_wndproc)
        self._subclass_proc = proc  # 持有引用; SUBCLASSPROC 被 GC 会变野指针 -> 崩
        _comctl32.SetWindowSubclass.argtypes = [
            wintypes.HWND,
            _SUBCLASSPROC,
            _UINT_PTR,
            _DWORD_PTR,
        ]
        _comctl32.SetWindowSubclass.restype = wintypes.BOOL
        _comctl32.DefSubclassProc.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        _comctl32.DefSubclassProc.restype = _LRESULT
        ok = _comctl32.SetWindowSubclass(self._hwnd, proc, 1, 0)
        if not ok:
            logger.warning("SetWindowSubclass 失败 (任务栏按钮点击会丢)")

    def _subclass_wndproc(self, hwnd, msg, wparam, lparam, _id_subclass, _ref_data):
        if msg == _WM_COMMAND:
            high = (wparam >> 16) & 0xFFFF
            low = wparam & 0xFFFF
            if high == 0:
                handler = {
                    _BTN_PREV: self._on_prev_clicked,
                    _BTN_PLAY_PAUSE: self._on_play_pause_clicked,
                    _BTN_NEXT: self._on_next_clicked,
                }.get(low)
                if handler is not None:
                    try:
                        handler()
                    except Exception:  # 不允许回调异常吃掉, 但也不能崩窗口
                        logger.exception("任务栏缩略图按钮点击回调失败 (id=%d)", low)
                    return 0
        elif msg == _WM_DWMSENDICONICTHUMBNAIL:
            # DWM 来要任务栏悬停缩略图. lParam HIWORD=最大宽, LOWORD=最大高,
            # 我们预渲染的封面 200x200 一般都 <= 限制, 直接送过去就行 (DWM 会按需缩放).
            if self._thumbnail_hbm:
                try:
                    _dwmapi.DwmSetIconicThumbnail.argtypes = [
                        wintypes.HWND,
                        wintypes.HBITMAP,
                        wintypes.DWORD,
                    ]
                    _dwmapi.DwmSetIconicThumbnail.restype = c_int32
                    _dwmapi.DwmSetIconicThumbnail(hwnd, self._thumbnail_hbm, 0)
                except Exception:
                    logger.exception("DwmSetIconicThumbnail 失败")
            return 0
        elif msg == _WM_DWMSENDICONICLIVEPREVIEWBITMAP:
            # Aero Peek 把任务栏缩略图放大成全屏预览; 同一张封面塞过去就行.
            if self._thumbnail_hbm:
                try:
                    _dwmapi.DwmSetIconicLivePreviewBitmap.argtypes = [
                        wintypes.HWND,
                        wintypes.HBITMAP,
                        c_void_p,  # POINT* (传 NULL 让 DWM 居中)
                        wintypes.DWORD,
                    ]
                    _dwmapi.DwmSetIconicLivePreviewBitmap.restype = c_int32
                    _dwmapi.DwmSetIconicLivePreviewBitmap(hwnd, self._thumbnail_hbm, None, 0)
                except Exception:
                    logger.exception("DwmSetIconicLivePreviewBitmap 失败")
            return 0
        return _comctl32.DefSubclassProc(hwnd, msg, wparam, lparam)

    # ------------------------------------------------------------------ 按钮回调
    def _on_prev_clicked(self) -> None:
        fn = getattr(self._player, "prev", None)
        if callable(fn):
            fn()

    def _on_play_pause_clicked(self) -> None:
        fn = getattr(self._player, "togglePlayPause", None)
        if callable(fn):
            fn()

    def _on_next_clicked(self) -> None:
        fn = getattr(self._player, "next", None)
        if callable(fn):
            fn()

    # ------------------------------------------------------------------ 信号同步
    @Slot()
    def _on_state_changed(self) -> None:
        if not self._try_init():
            return
        self._sync_progress()
        self._sync_button_icons()

    @Slot()
    def _on_position_changed(self) -> None:
        if not self._try_init():
            return
        self._sync_progress()

    @Slot()
    def _on_song_changed(self) -> None:
        if not self._try_init():
            return
        self._refresh_cover_thumbnail()

    def _refresh_cover_thumbnail(self) -> None:
        """从当前歌封面生成新 DIB HBITMAP, 通知 DWM 重取缩略图.

        - 没接 ``cover_cache`` / 当前歌无 coverUrl / 缓存未命中 -> 不动 (保留旧封面 or 默认窗口缩影)
        - 命中 -> 生成 200x200 DIB, 替换旧 HBITMAP (DeleteObject 老的), 调
          ``DwmInvalidateIconicBitmaps`` 强制 DWM 下一次悬停时重新询问.
        """
        if not self._initialized or self._cover_cache is None:
            return
        song = getattr(self._player, "currentSong", None) or {}
        cover_url = str(song.get("coverUrl", "") or "") if isinstance(song, dict) else ""
        if not cover_url:
            return
        try:
            path = self._cover_cache.get_path(cover_url)
        except Exception:
            logger.exception("cover_cache.get_path 失败: url=%s", cover_url)
            return
        if path is None or not path.exists():
            return  # 缓存未命中, 等下次切歌再来
        img = QImage(str(path))
        if img.isNull():
            logger.debug("封面 QImage 加载失败: %s", path)
            return
        # 缩到目标尺寸 (任务栏缩略图最大 ~280x180, 200 留余量)
        scaled = img.scaled(
            _COVER_BITMAP_SIZE,
            _COVER_BITMAP_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        new_hbm = _qimage_to_dib(scaled)
        if not new_hbm:
            return
        # 替换旧 HBITMAP, 释放老的
        if self._thumbnail_hbm:
            _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
            _gdi32.DeleteObject.restype = wintypes.BOOL
            _gdi32.DeleteObject(self._thumbnail_hbm)
        self._thumbnail_hbm = new_hbm
        # 让 DWM 下次询问时拿新封面
        try:
            _dwmapi.DwmInvalidateIconicBitmaps.argtypes = [wintypes.HWND]
            _dwmapi.DwmInvalidateIconicBitmaps.restype = c_int32
            _dwmapi.DwmInvalidateIconicBitmaps(self._hwnd)
        except Exception:
            logger.exception("DwmInvalidateIconicBitmaps 失败")

    def _sync_progress(self) -> None:
        state = str(getattr(self._player, "playbackState", "") or "")
        position = int(getattr(self._player, "positionMs", 0) or 0)
        duration = int(getattr(self._player, "durationMs", 0) or 0)

        if state == "playing":
            tbpf = _TBPF_NORMAL
        elif state == "paused":
            tbpf = _TBPF_PAUSED
        else:
            tbpf = _TBPF_NOPROGRESS

        state_proto = ctypes.WINFUNCTYPE(c_int32, c_void_p, wintypes.HWND, c_int32)
        state_fn = state_proto(_vtbl_ptr(self._taskbar, _VT_SETPROGRESSSTATE))
        state_fn(self._taskbar, self._hwnd, tbpf)

        if duration > 0 and tbpf != _TBPF_NOPROGRESS:
            value_proto = ctypes.WINFUNCTYPE(c_int32, c_void_p, wintypes.HWND, c_uint64, c_uint64)
            value_fn = value_proto(_vtbl_ptr(self._taskbar, _VT_SETPROGRESSVALUE))
            value_fn(self._taskbar, self._hwnd, min(position, duration), duration)

    def _sync_button_icons(self, *, force: bool = False) -> None:
        state = str(getattr(self._player, "playbackState", "") or "")
        is_playing = state == "playing"
        if not force and is_playing == self._is_playing:
            return
        self._is_playing = is_playing
        buttons = self._build_buttons(playing=is_playing)
        update_proto = ctypes.WINFUNCTYPE(
            c_int32, c_void_p, wintypes.HWND, wintypes.UINT, POINTER(_THUMBBUTTON)
        )
        fn = update_proto(_vtbl_ptr(self._taskbar, _VT_THUMBBARUPDATEBUTTONS))
        fn(self._taskbar, self._hwnd, 3, buttons)

    # ------------------------------------------------------------------ 清理
    def release(self) -> None:
        """退出前显式撤销 subclass + 释放 COM + 销毁 HICON. 重复调用幂等."""
        if self._subclass_proc is not None and self._hwnd:
            _comctl32.RemoveWindowSubclass.argtypes = [
                wintypes.HWND,
                _SUBCLASSPROC,
                _UINT_PTR,
            ]
            _comctl32.RemoveWindowSubclass.restype = wintypes.BOOL
            _comctl32.RemoveWindowSubclass(self._hwnd, self._subclass_proc, 1)
            self._subclass_proc = None

        if self._taskbar.value:
            # 撤回任务栏图标进度条 (否则程序退出图标可能还残留进度颜色)
            try:
                state_proto = ctypes.WINFUNCTYPE(c_int32, c_void_p, wintypes.HWND, c_int32)
                state_fn = state_proto(_vtbl_ptr(self._taskbar, _VT_SETPROGRESSSTATE))
                state_fn(self._taskbar, self._hwnd, _TBPF_NOPROGRESS)
            except (OSError, ValueError):
                pass
            _release_com(self._taskbar)
            self._taskbar = c_void_p()

        _user32.DestroyIcon.argtypes = [wintypes.HICON]
        _user32.DestroyIcon.restype = wintypes.BOOL
        for hicon in (
            self._icon_prev,
            self._icon_play,
            self._icon_pause,
            self._icon_next,
        ):
            if hicon:
                _user32.DestroyIcon(hicon)
        self._icon_prev = self._icon_play = self._icon_pause = self._icon_next = 0

        if self._thumbnail_hbm:
            _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
            _gdi32.DeleteObject.restype = wintypes.BOOL
            _gdi32.DeleteObject(self._thumbnail_hbm)
            self._thumbnail_hbm = 0
        self._initialized = False
