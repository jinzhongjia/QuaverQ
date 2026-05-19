"""Player 单元测试.

GStreamer pipeline 本身是 IO + 系统级, 无法在纯单元层完整 mock,
所以这里专门测 bus message → callback 的纯函数路径.
"""

from __future__ import annotations

from types import SimpleNamespace

from quaverq.core.player import GStreamerBackend, _StubBackend


# ============================================================== callbacks 存在

def test_gstreamer_backend_has_on_error_slot():
    p = GStreamerBackend()
    # 默认 None, 可赋值
    assert p.on_error is None
    p.on_error = lambda msg: None
    assert callable(p.on_error)


def test_gstreamer_backend_has_on_eos_slot():
    p = GStreamerBackend()
    assert p.on_eos is None
    p.on_eos = lambda: None
    assert callable(p.on_eos)


def test_stub_backend_has_same_callback_slots():
    """Stub 必须接口对齐, 否则 UI 后端切换会爆."""
    p = _StubBackend()
    assert hasattr(p, "on_error")
    assert hasattr(p, "on_eos")
    assert p.on_error is None
    assert p.on_eos is None


# ============================================================== bus error 转发

def test_bus_error_invokes_callback_with_message_text():
    """GStreamer 在 bus 上抛 error 时, on_error 回调收到错误描述."""
    p = GStreamerBackend()
    received: list[str] = []
    p.on_error = received.append

    fake_message = SimpleNamespace(
        parse_error=lambda: (RuntimeError("HTTP 403"), "debug: cdn rejected")
    )
    p._on_bus_error(None, fake_message)

    assert len(received) == 1
    assert "HTTP 403" in received[0]


def test_bus_error_without_callback_does_not_raise():
    p = GStreamerBackend()
    fake_message = SimpleNamespace(
        parse_error=lambda: (RuntimeError("boom"), "")
    )
    # 不应抛
    p._on_bus_error(None, fake_message)


# ============================================================== bus EOS 转发

def test_bus_eos_invokes_callback():
    p = GStreamerBackend()
    fired = []
    p.on_eos = lambda: fired.append(True)

    p._on_bus_eos(None, SimpleNamespace())

    assert fired == [True]


def test_bus_eos_without_callback_does_not_raise():
    p = GStreamerBackend()
    p._on_bus_eos(None, SimpleNamespace())
