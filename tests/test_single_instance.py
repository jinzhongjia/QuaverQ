"""SingleInstanceGuard 契约测试.

不连真 D-Bus, 用 SimpleNamespace + AsyncMock 替换 dbus_next; 验证:
- 占到 (PRIMARY_OWNER) -> acquire() 返回 True
- 被占 (EXISTS) -> acquire() 返回 False, 但 bus 仍在以便后续 notify
- notify_existing_raise() 发的是 MPRIS 接口的 Raise 调用
- release() 关 bus 连接
- D-Bus 连不上时 acquire() 容错返回 False
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from quaverq.core import single_instance


def _build_fake_dbus(monkeypatch, *, request_name_reply, raise_on_connect=False):
    name_flag = SimpleNamespace(NONE=0, DO_NOT_QUEUE=4)
    request_name_reply_enum = SimpleNamespace(
        PRIMARY_OWNER=SimpleNamespace(name="PRIMARY_OWNER"),
        IN_QUEUE=SimpleNamespace(name="IN_QUEUE"),
        EXISTS=SimpleNamespace(name="EXISTS"),
        ALREADY_OWNER=SimpleNamespace(name="ALREADY_OWNER"),
    )
    message_type = SimpleNamespace(METHOD_CALL="method_call")

    bus = SimpleNamespace()
    bus.request_name = AsyncMock(return_value=request_name_reply)
    bus.disconnect = MagicMock()
    bus.call = AsyncMock(return_value=None)

    if raise_on_connect:
        connect_mock = AsyncMock(side_effect=ConnectionError("no bus"))
    else:
        connect_mock = AsyncMock(return_value=bus)

    message_bus_instance = SimpleNamespace(connect=connect_mock)
    message_bus_factory = MagicMock(return_value=message_bus_instance)

    sent_messages: list[SimpleNamespace] = []

    def message_factory(**kwargs):
        msg = SimpleNamespace(**kwargs)
        sent_messages.append(msg)
        return msg

    fake = {
        "BusType": SimpleNamespace(SESSION="session"),
        "MessageBus": message_bus_factory,
        "Message": message_factory,
        "MessageType": message_type,
        "NameFlag": name_flag,
        "RequestNameReply": request_name_reply_enum,
        "_bus": bus,
        "_sent_messages": sent_messages,
    }
    monkeypatch.setattr(single_instance, "_import_dbus", lambda: fake)
    return fake


async def test_acquire_returns_true_when_primary_owner(monkeypatch):
    fake = _build_fake_dbus(
        monkeypatch,
        request_name_reply=SimpleNamespace(name="PRIMARY_OWNER"),
    )
    fake["RequestNameReply"].PRIMARY_OWNER = fake["_bus"].request_name.return_value

    guard = single_instance.SingleInstanceGuard()
    assert await guard.acquire() is True
    fake["_bus"].request_name.assert_awaited_once()
    args, _ = fake["_bus"].request_name.call_args
    assert args[0] == single_instance.LOCK_BUS_NAME


async def test_acquire_returns_false_when_name_already_taken(monkeypatch):
    exists_reply = SimpleNamespace(name="EXISTS")
    fake = _build_fake_dbus(monkeypatch, request_name_reply=exists_reply)
    fake["RequestNameReply"].PRIMARY_OWNER = SimpleNamespace(name="PRIMARY_OWNER")

    guard = single_instance.SingleInstanceGuard()
    assert await guard.acquire() is False
    # bus 仍开着, 以便 notify_existing_raise
    assert fake["_bus"].disconnect.call_count == 0


async def test_notify_existing_raise_sends_mpris_raise_method_call(monkeypatch):
    exists_reply = SimpleNamespace(name="EXISTS")
    fake = _build_fake_dbus(monkeypatch, request_name_reply=exists_reply)
    fake["RequestNameReply"].PRIMARY_OWNER = SimpleNamespace(name="PRIMARY_OWNER")

    guard = single_instance.SingleInstanceGuard()
    await guard.acquire()
    await guard.notify_existing_raise()

    assert fake["_bus"].call.await_count == 1
    sent = fake["_sent_messages"][-1]
    assert sent.destination == single_instance.MPRIS_BUS_NAME
    assert sent.path == single_instance.MPRIS_OBJECT_PATH
    assert sent.interface == "org.mpris.MediaPlayer2"
    assert sent.member == "Raise"


async def test_release_disconnects_bus(monkeypatch):
    primary_reply = SimpleNamespace(name="PRIMARY_OWNER")
    fake = _build_fake_dbus(monkeypatch, request_name_reply=primary_reply)
    fake["RequestNameReply"].PRIMARY_OWNER = primary_reply

    guard = single_instance.SingleInstanceGuard()
    await guard.acquire()
    guard.release()
    assert fake["_bus"].disconnect.call_count == 1


async def test_acquire_returns_false_when_dbus_unavailable(monkeypatch):
    fake = _build_fake_dbus(
        monkeypatch,
        request_name_reply=SimpleNamespace(name="PRIMARY_OWNER"),
        raise_on_connect=True,
    )
    fake["RequestNameReply"].PRIMARY_OWNER = SimpleNamespace(name="PRIMARY_OWNER")

    guard = single_instance.SingleInstanceGuard()
    # D-Bus 连不上时不应该崩, 而是返回 False (上层会按已存在实例处理)
    assert await guard.acquire() is False


async def test_notify_existing_raise_swallows_errors(monkeypatch):
    exists_reply = SimpleNamespace(name="EXISTS")
    fake = _build_fake_dbus(monkeypatch, request_name_reply=exists_reply)
    fake["RequestNameReply"].PRIMARY_OWNER = SimpleNamespace(name="PRIMARY_OWNER")
    fake["_bus"].call.side_effect = RuntimeError("no remote")

    guard = single_instance.SingleInstanceGuard()
    await guard.acquire()
    # 已存在实例没回应也不能崩 -- 静默退出即可
    await guard.notify_existing_raise()


async def test_release_is_idempotent(monkeypatch):
    primary_reply = SimpleNamespace(name="PRIMARY_OWNER")
    fake = _build_fake_dbus(monkeypatch, request_name_reply=primary_reply)
    fake["RequestNameReply"].PRIMARY_OWNER = primary_reply

    guard = single_instance.SingleInstanceGuard()
    await guard.acquire()
    guard.release()
    guard.release()  # 二次 release 不应抛
    assert fake["_bus"].disconnect.call_count == 1


@pytest.mark.parametrize("reply_name", ["IN_QUEUE", "EXISTS", "ALREADY_OWNER"])
async def test_acquire_returns_false_for_non_primary_owner_replies(monkeypatch, reply_name):
    reply = SimpleNamespace(name=reply_name)
    fake = _build_fake_dbus(monkeypatch, request_name_reply=reply)
    fake["RequestNameReply"].PRIMARY_OWNER = SimpleNamespace(name="PRIMARY_OWNER")

    guard = single_instance.SingleInstanceGuard()
    assert await guard.acquire() is False
