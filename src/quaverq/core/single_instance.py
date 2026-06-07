"""单实例守卫.

用 D-Bus 专用 well-known name 占位, 同一 session 下 QuaverQ 只允许跑一份:
- 第一实例: RequestName(DO_NOT_QUEUE) 拿到 PRIMARY_OWNER, 名字常驻直到 release()
- 第二实例: RequestName 失败 -> 调 ``org.mpris.MediaPlayer2.quaverq`` 的 ``Raise``
  让已有窗口前置, 然后本进程退出

设计要点:
- 用独立的 lock name ``org.quaverq.SingleInstance`` 而非 MPRIS name; 避免和 MPRIS
  注册同一个 bus 名字相互打架 (两条不同的 connection 占同一 name 必然冲突)
- bus 连接保留在 self._bus 直到 release(), 否则 dbus_next 断连即释放名字, 守卫失效
- 任意 D-Bus 异常都视为 "无法占住" 并返回 False; 调用方再决定怎么处理. v1 仅 Linux,
  正常桌面环境 session bus 必存在, 失败属异常路径走告警即可
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

LOCK_BUS_NAME = "org.quaverq.SingleInstance"
MPRIS_BUS_NAME = "org.mpris.MediaPlayer2.quaverq"
MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
MPRIS_ROOT_INTERFACE = "org.mpris.MediaPlayer2"


def _import_dbus() -> dict[str, Any]:
    """惰性 import dbus_next; 单元测试通过 monkeypatch 整体替换以避免真连 bus."""
    from dbus_next import BusType, Message, MessageType
    from dbus_next.aio import MessageBus
    from dbus_next.constants import NameFlag, RequestNameReply

    return {
        "BusType": BusType,
        "Message": Message,
        "MessageType": MessageType,
        "MessageBus": MessageBus,
        "NameFlag": NameFlag,
        "RequestNameReply": RequestNameReply,
    }


class SingleInstanceGuard:
    """守卫一个 well-known D-Bus name; bus 连接随实例生命周期."""

    def __init__(
        self,
        lock_name: str = LOCK_BUS_NAME,
        mpris_name: str = MPRIS_BUS_NAME,
    ) -> None:
        self._lock_name = lock_name
        self._mpris_name = mpris_name
        self._bus: Any = None

    async def acquire(self) -> bool:
        """连 session bus 并 RequestName(DO_NOT_QUEUE).

        - 返回 True: 占到; self._bus 持有连接, 直到 release() 才释放名字
        - 返回 False: 已被占 / D-Bus 不可用; bus (若已连上) 仍开着, 以便接着 notify
        """
        d = _import_dbus()
        try:
            self._bus = await d["MessageBus"](bus_type=d["BusType"].SESSION).connect()
        except Exception:
            logger.exception("单实例守卫: D-Bus 连接失败")
            self._bus = None
            return False

        try:
            reply = await self._bus.request_name(
                self._lock_name,
                d["NameFlag"].DO_NOT_QUEUE,
            )
        except Exception:
            logger.exception("单实例守卫: RequestName 失败")
            return False

        if reply == d["RequestNameReply"].PRIMARY_OWNER:
            logger.info("单实例守卫: 占用 %s 成功", self._lock_name)
            return True
        logger.info(
            "单实例守卫: %s 已被占用 (reply=%s), 视为已存在实例",
            self._lock_name,
            getattr(reply, "name", reply),
        )
        return False

    async def notify_existing_raise(self) -> None:
        """让已有实例把主窗口前置: 给 MPRIS 根接口发 Raise 调用."""
        if self._bus is None:
            return
        d = _import_dbus()
        msg = d["Message"](
            destination=self._mpris_name,
            path=MPRIS_OBJECT_PATH,
            interface=MPRIS_ROOT_INTERFACE,
            member="Raise",
            message_type=d["MessageType"].METHOD_CALL,
        )
        try:
            await self._bus.call(msg)
        except Exception:
            logger.exception("单实例守卫: 通知已有实例 Raise 失败")

    def release(self) -> None:
        """断开 bus 连接释放名字; 二次调用幂等.

        ``MessageBus.disconnect()`` 是同步关 socket, 没有 await 点; 故 release 本身
        声明为普通函数, 以便在 ``aboutToQuit`` 这种 loop 已经停转的时机直接调用 ——
        若声明为 async, 用 ``loop.create_task`` 调度出去的 coroutine 永远不会被 driven.
        """
        if self._bus is None:
            return
        try:
            self._bus.disconnect()
        except Exception:
            logger.exception("单实例守卫: 关闭 D-Bus 异常")
        self._bus = None
