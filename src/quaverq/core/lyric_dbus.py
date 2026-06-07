"""Lyrics D-Bus 接口 (org.quaverq.Lyrics1).

把当前歌词 + 实时位置暴露给桌面歌词工具 (osdlyrics、waybar 自写模块、用户脚本).
和 MPRIS 并列, 不冲突.

设计要点 (参考 core/mpris.py 的同款套路):
- 纯函数 helpers (lyric_to_payload / compute_active_word / window_to_payload) 可单测
- ServiceInterface 装饰器签名是 dbus-next __annotations__ 读的 D-Bus 签名字符串,
  不是 Python 类型注解, 不要"修正"成 bool/str/list
- 一次性把全行 word timing 推给客户端, 客户端拿 PositionMs 自己插值定位当前字 ——
  逐字精度需要 ~16ms, D-Bus signal 不适合这个频率
- 设计接口契约: PropertiesChanged 推 PositionMs / ActiveLine / ActiveWord;
  LyricChanged signal 在切歌时触发, 客户端收到后调 GetLyric() 拿全量

接口规范 (BUS_NAME=org.quaverq.Lyrics1, OBJECT_PATH=/org/quaverq/Lyrics):

    interface org.quaverq.Lyrics1 {
        // properties
        readonly s   Mid;            // QQ Music mid; "" 表示无歌曲
        readonly o   TrackId;        // 对应 MPRIS trackid
        readonly x   PositionMs;
        readonly i   ActiveLine;     // -1 = 尚未开始
        readonly i   ActiveWord;     // -1 = 无逐字 / 行间隙
        readonly b   HasWordTiming;
        readonly b   HasTranslation;
        readonly i   LineCount;

        // methods
        GetLyric() → (s mid, b has_word_timing,
                      a(xssa(xxs)) lines);  // [(ts, text, translation, words)]
                                            // words: [(start_ms, duration_ms, text)]
        GetWindow(i before, i after) → (a(xss) window, i active_in_window);

        // signals
        LyricChanged(s mid);                // 切歌
        LineEntered(i line, x ts_ms);       // 行边界进入
    }
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import Lyric, LyricLine

logger = logging.getLogger(__name__)

_TRACKID_SANITIZE = re.compile(r"[^A-Za-z0-9_]")


# ---------------------------------------------------------------- 纯函数 helpers


def _sanitize_trackid_segment(mid: str) -> str:
    return _TRACKID_SANITIZE.sub("_", mid or "unknown")


def build_trackid(mid: str) -> str:
    """与 MPRIS song_to_metadata 中的 trackid 保持一致, 方便客户端关联两个接口."""
    return f"/org/mpris/MediaPlayer2/quaverq/track/{_sanitize_trackid_segment(mid)}"


def lyric_to_payload(
    lyric: Lyric | None,
) -> tuple[str, bool, list[tuple[int, str, str, list[tuple[int, int, str]]]]]:
    """Lyric → GetLyric() 返回值: (mid, has_word_timing, lines).

    lines: 每行 (timestamp_ms, text, translation, words);
    words: 每字 (start_ms, duration_ms, text); 普通 LRC 行 words=[].
    """
    if lyric is None or not lyric.lines:
        return "", False, []

    has_word_timing = any(line.words for line in lyric.lines)
    lines: list[tuple[int, str, str, list[tuple[int, int, str]]]] = []
    for line in lyric.lines:
        words = [(w.start_ms, w.duration_ms, w.text) for w in line.words]
        lines.append((line.timestamp_ms, line.text, line.translation, words))
    return lyric.mid, has_word_timing, lines


def compute_active_word(line: LyricLine, position_ms: int) -> int:
    """在 line.words 中定位 position_ms 所在的字索引.

    返回 -1: 无 words / position 早于第一字 start_ms;
    在末字结束时间之后: 仍返回最后一字索引 (展示语义: 整行已唱完最后一字保持高亮).
    字之间无 gap 的真实场景下, position 落在 (words[i].start_ms, words[i+1].start_ms)
    区间内一律算 i.
    """
    words = line.words
    if not words:
        return -1
    if position_ms < words[0].start_ms:
        return -1
    for i in range(len(words) - 1):
        if position_ms < words[i + 1].start_ms:
            return i
    return len(words) - 1


def window_to_payload(lines: list[LyricLine]) -> list[tuple[int, str, str]]:
    """LyricSync.window() 的行列表 → GetWindow() 返回的 (ts, text, translation) 元组."""
    return [(ln.timestamp_ms, ln.text, ln.translation) for ln in lines]


# ---------------------------------------------------------------- D-Bus 接口


def _import_dbus():
    from dbus_next import BusType, PropertyAccess, Variant  # noqa: F401
    from dbus_next.aio import MessageBus  # noqa: F401
    from dbus_next.service import (  # noqa: F401
        ServiceInterface,
        dbus_property,
        method,
        signal,
    )

    return {
        "BusType": BusType,
        "PropertyAccess": PropertyAccess,
        "Variant": Variant,
        "MessageBus": MessageBus,
        "ServiceInterface": ServiceInterface,
        "dbus_property": dbus_property,
        "method": method,
        "signal": signal,
    }


def _build_interface():
    """工厂: 构造 LyricsInterface 类 (放函数里同 mpris.py, 装饰器依赖 dbus-next)."""
    d = _import_dbus()
    ServiceInterface = d["ServiceInterface"]
    PropertyAccess = d["PropertyAccess"]
    method = d["method"]
    dbus_property = d["dbus_property"]
    signal = d["signal"]

    class _LyricsInterface(ServiceInterface):
        def __init__(self):
            super().__init__("org.quaverq.Lyrics1")
            self._mid: str = ""
            self._trackid: str = build_trackid("")
            self._position_ms: int = 0
            self._active_line: int = -1
            self._active_word: int = -1
            self._has_word_timing: bool = False
            self._has_translation: bool = False
            self._payload: list[tuple[int, str, str, list[tuple[int, int, str]]]] = []

        # 方法
        @method()
        def GetLyric(  # noqa: N802
            self,
        ) -> sba(xssa(xxs)):
            return [self._mid, self._has_word_timing, self._payload]

        @method()
        def GetWindow(self, before: i, after: i) -> "(a(xss)i)":  # noqa: N802
            n = len(self._payload)
            if n == 0:
                return [[], -1]
            active = max(self._active_line, 0)
            start = max(0, active - max(0, int(before)))
            end = min(n, active + max(0, int(after)) + 1)
            # STRUCT 用 list, 同 update_lyric 的边界规则
            window = [
                [ts, text, translation] for (ts, text, translation, _) in self._payload[start:end]
            ]
            rel = self._active_line - start if self._active_line >= 0 else -1
            return [window, rel]

        # 属性
        @dbus_property(access=PropertyAccess.READ)
        def Mid(self) -> s:  # noqa: N802
            return self._mid

        @dbus_property(access=PropertyAccess.READ)
        def TrackId(self) -> o:  # noqa: N802
            return self._trackid

        @dbus_property(access=PropertyAccess.READ)
        def PositionMs(self) -> x:  # noqa: N802
            return self._position_ms

        @dbus_property(access=PropertyAccess.READ)
        def ActiveLine(self) -> i:  # noqa: N802
            return self._active_line

        @dbus_property(access=PropertyAccess.READ)
        def ActiveWord(self) -> i:  # noqa: N802
            return self._active_word

        @dbus_property(access=PropertyAccess.READ)
        def HasWordTiming(self) -> b:  # noqa: N802
            return self._has_word_timing

        @dbus_property(access=PropertyAccess.READ)
        def HasTranslation(self) -> b:  # noqa: N802
            return self._has_translation

        @dbus_property(access=PropertyAccess.READ)
        def LineCount(self) -> i:  # noqa: N802
            return len(self._payload)

        # 信号: dbus-next 把签名放在 return 注解上 (不是 args), 方法必须 return 值
        @signal()
        def LyricChanged(self, mid) -> s:  # noqa: N802
            return mid

        @signal()
        def LineEntered(self, line, ts_ms) -> "ix":  # noqa: N802
            return [line, ts_ms]

        # 外部 push (controller / service 调)
        def update_lyric(self, lyric: Lyric | None) -> None:
            mid, has_word, payload = lyric_to_payload(lyric)
            self._mid = mid
            self._trackid = build_trackid(mid)
            # dbus-next 要 STRUCT 是 list 而不是 tuple, 在 D-Bus 边界统一转一次
            self._payload = [
                [ts, text, translation, [list(w) for w in words]]
                for (ts, text, translation, words) in payload
            ]
            self._has_word_timing = has_word
            self._has_translation = bool(lyric and lyric.has_translation)
            self._active_line = -1
            self._active_word = -1
            self.emit_properties_changed(
                {
                    "Mid": self._mid,
                    "TrackId": self._trackid,
                    "HasWordTiming": self._has_word_timing,
                    "HasTranslation": self._has_translation,
                    "LineCount": len(self._payload),
                    "ActiveLine": -1,
                    "ActiveWord": -1,
                }
            )
            self.LyricChanged(self._mid)

        def update_position(self, position_ms: int) -> None:
            new_pos = max(0, int(position_ms))
            if new_pos == self._position_ms:
                return
            self._position_ms = new_pos
            self.emit_properties_changed({"PositionMs": new_pos})

        def update_active(self, line_index: int, word_index: int) -> None:
            changed: dict[str, Any] = {}
            line_entered = False
            if line_index != self._active_line:
                self._active_line = line_index
                changed["ActiveLine"] = line_index
                line_entered = line_index >= 0
            if word_index != self._active_word:
                self._active_word = word_index
                changed["ActiveWord"] = word_index
            if changed:
                self.emit_properties_changed(changed)
            if line_entered and 0 <= line_index < len(self._payload):
                ts = self._payload[line_index][0]
                self.LineEntered(line_index, ts)

    return _LyricsInterface


# ---------------------------------------------------------------- 高层 service


class LyricsService:
    """启动 / 维持 D-Bus 服务对象; 由 service 层主动 push 状态."""

    BUS_NAME = "org.quaverq.Lyrics1"
    OBJECT_PATH = "/org/quaverq/Lyrics"

    def __init__(self) -> None:
        self._bus = None
        self._iface = None

    async def start(self) -> bool:
        """连接 session bus + 注册 org.quaverq.Lyrics1.

        返回 False 表示 D-Bus 不可用 (无 session bus / 名字被占), 上层应当容忍.
        """
        try:
            d = _import_dbus()
            self._bus = await d["MessageBus"](bus_type=d["BusType"].SESSION).connect()
            Iface = _build_interface()
            self._iface = Iface()
            self._bus.export(self.OBJECT_PATH, self._iface)
            await self._bus.request_name(self.BUS_NAME)
            logger.info("Lyrics D-Bus 已注册: %s", self.BUS_NAME)
            return True
        except Exception as exc:
            logger.warning("Lyrics D-Bus 启动失败 (%s), 外部歌词消费不可用", exc)
            self._bus = None
            self._iface = None
            return False

    def push_lyric(self, lyric: Lyric | None) -> None:
        if self._iface is not None:
            try:
                self._iface.update_lyric(lyric)
            except Exception:
                logger.exception("Lyrics 推 lyric 异常")

    def push_position(self, position_ms: int) -> None:
        if self._iface is not None:
            try:
                self._iface.update_position(position_ms)
            except Exception:
                logger.exception("Lyrics 推 position 异常")

    def push_active(self, line_index: int, word_index: int) -> None:
        if self._iface is not None:
            try:
                self._iface.update_active(line_index, word_index)
            except Exception:
                logger.exception("Lyrics 推 active 异常")

    async def stop(self) -> None:
        if self._bus is not None:
            try:
                self._bus.disconnect()
            except Exception:
                logger.exception("Lyrics D-Bus 关闭异常")
            self._bus = None
            self._iface = None
