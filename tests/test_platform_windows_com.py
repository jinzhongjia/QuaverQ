"""``_windows_com`` 共享 COM 助手测试.

纯 ctypes struct 构造, 不碰任何 Win32 API, 故跨平台可跑 (非 Windows 也执行, 不 skip).
覆盖唯一有解析逻辑的 ``_make_iid`` —— vtable/Release 是平凡 wrapper, 真行为需 Windows COM
指针, 不在此单测.
"""

from __future__ import annotations

import ctypes

from quaverq.platform._windows_com import _IID, _make_iid


def test_make_iid_parses_guid_string():
    # IID_IRandomAccessStreamReferenceStatics (见 CLAUDE.md 实测 IID).
    iid = _make_iid("{857309DC-3FBF-4E7D-986F-EF3B1A07A964}")
    assert iid.Data1 == 0x857309DC
    assert iid.Data2 == 0x3FBF
    assert iid.Data3 == 0x4E7D
    assert list(iid.Data4) == [0x98, 0x6F, 0xEF, 0x3B, 0x1A, 0x07, 0xA9, 0x64]


def test_make_iid_tolerates_missing_braces():
    bare = _make_iid("44A9796F-723E-4FDF-A218-033E75B0C084")
    braced = _make_iid("{44A9796F-723E-4FDF-A218-033E75B0C084}")
    assert bare.Data1 == braced.Data1 == 0x44A9796F
    assert list(bare.Data4) == list(braced.Data4)


def test_iid_struct_is_16_bytes():
    assert ctypes.sizeof(_IID) == 16
