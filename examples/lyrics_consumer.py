"""QuaverQ Lyrics D-Bus 消费者示例.

订阅 org.quaverq.Lyrics1, 在终端实时打印当前行 + 高亮当前字 (karaoke 风格).

运行 (确保 QuaverQ 已经启动并正在播放):
    uv run python examples/lyrics_consumer.py

行为:
- 切歌时调 GetLyric() 取全量逐字 timing 缓存到本地
- 订阅 PropertiesChanged 跟踪 PositionMs / ActiveLine / ActiveWord
- 在终端单行原地刷新, 已唱过的字用粗体 + 反色显示

依赖: dbus-next (项目已声明). 退出: Ctrl-C.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from dbus_next import BusType
from dbus_next.aio import MessageBus

logger = logging.getLogger("lyrics_consumer")

BUS_NAME = "org.quaverq.Lyrics1"
OBJECT_PATH = "/org/quaverq/Lyrics"
IFACE = "org.quaverq.Lyrics1"

# ANSI: 已唱过 + 当前字 / 未唱字
SUNG = "\033[1;7m"   # 粗体 + 反色
PLAIN = "\033[0;90m"  # 暗灰
RESET = "\033[0m"


class LyricsConsumer:
    def __init__(self) -> None:
        self._mid: str = ""
        self._has_word_timing: bool = False
        # 每行: (ts_ms, text, translation, words=[(start_ms, dur_ms, text), ...])
        self._lines: list[tuple[int, str, str, list[tuple[int, int, str]]]] = []
        self._active_line: int = -1
        self._active_word: int = -1
        self._iface = None  # 填进去后用于 GetLyric

    async def run(self) -> None:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        introspection = await bus.introspect(BUS_NAME, OBJECT_PATH)
        proxy = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
        self._iface = proxy.get_interface(IFACE)
        props = proxy.get_interface("org.freedesktop.DBus.Properties")

        # 启动: 拉一次全量 + 当前状态
        await self._reload()
        self._active_line = await self._iface.get_active_line()
        self._active_word = await self._iface.get_active_word()
        self._render()

        # 订阅 PropertiesChanged 跟踪 active 行/字
        props.on_properties_changed(self._on_properties_changed)
        # 订阅 LyricChanged 切歌时重新拉
        self._iface.on_lyric_changed(self._on_lyric_changed)

        # 让 dbus-next 事件循环跑下去
        await asyncio.Event().wait()

    async def _reload(self) -> None:
        mid, has_word, lines = await self._iface.call_get_lyric()
        self._mid = mid
        self._has_word_timing = has_word
        self._lines = lines

    def _on_lyric_changed(self, mid: str) -> None:
        # 异步 reload (signal handler 不能直接 await)
        asyncio.create_task(self._reload_and_render(mid))

    async def _reload_and_render(self, mid: str) -> None:
        await self._reload()
        print(f"\n♪ {mid}", flush=True)
        self._render()

    def _on_properties_changed(self, _iface: str, changed: dict, _invalid) -> None:
        if "ActiveLine" in changed:
            self._active_line = changed["ActiveLine"].value
        if "ActiveWord" in changed:
            self._active_word = changed["ActiveWord"].value
        if "ActiveLine" in changed or "ActiveWord" in changed:
            self._render()

    def _render(self) -> None:
        if not self._lines or self._active_line < 0:
            sys.stdout.write("\r\033[K(等待歌词...)")
            sys.stdout.flush()
            return
        if self._active_line >= len(self._lines):
            return
        _, text, translation, words = self._lines[self._active_line]
        if not words or not self._has_word_timing:
            line = f"{SUNG}{text}{RESET}"
        else:
            parts = []
            for idx, (_, _, w_text) in enumerate(words):
                if idx <= self._active_word:
                    parts.append(f"{SUNG}{w_text}{RESET}")
                else:
                    parts.append(f"{PLAIN}{w_text}{RESET}")
            line = "".join(parts)
        suffix = f"  {PLAIN}/ {translation}{RESET}" if translation else ""
        # \r + \033[K = 回到行首并清行尾, 实现原地刷新
        sys.stdout.write(f"\r\033[K{line}{suffix}")
        sys.stdout.flush()


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    consumer = LyricsConsumer()
    try:
        await consumer.run()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    asyncio.run(main())
