"""GUI 线程假死 (deadlock / hang) 诊断 —— 看门狗检测 GUI 线程长时间无心跳时,
用 ``faulthandler`` 把**所有线程**的 Python 栈 dump 到 ``CACHE_DIR/hang.log``.

为什么需要 (``diagnostics_crash`` 补不上的洞):

- 死锁**不抛异常**, ``sys.excepthook`` / ``threading.excepthook`` 永不触发,
  ``crash.log`` 一片空白, 用户只看到"卡死"却拿不到现场。
- 典型卡死: GUI 线程被原生调用 join 住 —— ``QMediaPlayer`` (FFmpeg 后端)
  ``setSource`` / ``stop`` 等待 demuxer 工作线程、ctypes COM (SMTC) 同步调用、
  curl_cffi 读阻塞等。一旦 GUI 线程卡住, 整个 qasync 事件循环停摆。
- Nuitka 打包后无 console, ``py-spy`` 也未必在手, 必须程序自带抓栈能力。

为什么用看门狗 (项目通常 [禁止轮询](CLAUDE.md)):

进程**自身** GUI 线程是否假死, 没有任何 OS 级事件 / 信号可订阅 —— Windows 无
``SIGUSR1`` 之类的用户信号; 而且线程自己都卡住了, 也 emit 不出 signal。这正是
"禁止轮询"规则里写明的**唯一合法例外**: 被监听方无 OS 级通知, 经文档取舍后采用
独立看门狗线程。看门狗是 C 级 ``Event.wait`` 阻塞的 daemon 线程, 不占 GUI 线程,
静止期几乎零开销。

机制:

- GUI 线程上一个 ``QTimer`` 周期性 ``heartbeat()`` (单调 +1, 极廉价)。
- 独立 daemon 看门狗线程每 ``check_interval_s`` 秒 ``poll()`` 一次心跳是否前进;
  连续停顿超过 ``hang_threshold_s`` 秒 -> dump 全线程栈, 并 **解除武装** 避免同一次
  假死反复刷 (心跳恢复后自动重新武装, 下次再卡再 dump)。
- 关键: GUI 线程卡在原生调用里时已**释放 GIL**, 看门狗线程能拿到 GIL 跑
  ``faulthandler.dump_traceback(all_threads=True)``, 抓到 GUI 线程最后停在的 Python 帧
  (即真正的卡死点)。
"""

from __future__ import annotations

import faulthandler
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CACHE_DIR

logger = logging.getLogger(__name__)

_LOG_NAME = "hang.log"


class HangWatchdog:
    """心跳停顿检测 + faulthandler 全线程栈 dump。

    ``clock`` / ``dump_fn`` 可注入便于测试 (默认 ``time.monotonic`` + faulthandler 落盘)。
    """

    def __init__(
        self,
        *,
        hang_threshold_s: float = 6.0,
        check_interval_s: float = 1.0,
        log_path: Any = None,
        clock: Callable[[], float] = time.monotonic,
        dump_fn: Callable[[Any], None] | None = None,
    ) -> None:
        self._hang_threshold_s = float(hang_threshold_s)
        self._check_interval_s = float(check_interval_s)
        self._log_path = log_path
        self._clock = clock
        self._dump_fn = dump_fn or self._dump_all_threads
        # 心跳: GUI 线程 +1; 看门狗线程只读 (CPython int 读写受 GIL 保护, 无需锁)
        self._beat = 0
        self._last_beat_value = 0
        self._last_progress_time = clock()
        self._armed = True
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._timer: Any = None  # QTimer 引用, 防 GC (由 install 持有)

    # ---- GUI 线程侧 ----

    def heartbeat(self) -> None:
        """GUI 线程心跳 (QTimer 调)。GUI 卡住时此计数停止前进 -> 被看门狗发现。"""
        self._beat += 1

    # ---- 看门狗线程侧 ----

    def poll(self, now: float | None = None) -> bool:
        """检查一次心跳; 判定假死则 dump 并返回 True (本次假死只 dump 一次)。"""
        if now is None:
            now = self._clock()
        current = self._beat
        if current != self._last_beat_value:
            # 心跳前进 = GUI 仍活: 记录进展时刻, 重新武装
            self._last_beat_value = current
            self._last_progress_time = now
            self._armed = True
            return False
        if self._armed and (now - self._last_progress_time) >= self._hang_threshold_s:
            self._armed = False
            try:
                self._dump_fn(self._log_path)
            except Exception:
                logger.exception("hang dump 失败")
            return True
        return False

    def _run(self) -> None:
        # Event.wait 返回 True=被 stop() 唤醒 (退出); False=超时 (继续巡检). 非忙等。
        while not self._stop.wait(self._check_interval_s):
            self.poll()

    def start_thread(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="HangWatchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ---- 默认 dump 实现 ----

    def _dump_all_threads(self, log_path: Any) -> None:
        """把全线程 Python 栈追加写到 ``log_path`` (含时间戳分隔头)。"""
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write(
                f"[{datetime.now(timezone.utc).isoformat()}] GUI 线程疑似假死 "
                f"(连续 {self._hang_threshold_s:.0f}s 无心跳), 全线程栈:\n"
            )
            f.flush()
            # faulthandler 直接写 fd (C 层), 故先 flush 上面的文本再交给它
            faulthandler.dump_traceback(file=f, all_threads=True)
            f.write("\n")
        logger.error("检测到 GUI 假死, 已 dump 线程栈到 %s", path)


_watchdog: HangWatchdog | None = None


def install_hang_watchdog(
    app: Any,
    *,
    hang_threshold_s: float = 6.0,
    heartbeat_interval_ms: int = 1000,
    check_interval_s: float = 1.0,
    log_path: Any = None,
) -> HangWatchdog:
    """在 ``app`` 上挂 GUI 心跳 QTimer + 启动看门狗线程。幂等 (重复调返回同一实例)。

    必须保留返回值引用 (模块级单例已持有), 否则 QTimer / 线程随 GC 失效。
    """
    global _watchdog
    if _watchdog is not None:
        return _watchdog
    from PySide6.QtCore import QTimer

    if log_path is None:
        log_path = CACHE_DIR / _LOG_NAME
    wd = HangWatchdog(
        hang_threshold_s=hang_threshold_s,
        check_interval_s=check_interval_s,
        log_path=log_path,
    )
    timer = QTimer(app)  # parent=app -> 生命周期随 app, 防 GC
    timer.setInterval(int(heartbeat_interval_ms))
    timer.timeout.connect(wd.heartbeat)
    timer.start()
    wd._timer = timer  # noqa: SLF001 - 显式持有 QTimer 引用防 GC
    wd.start_thread()
    _watchdog = wd
    logger.info(
        "GUI 假死看门狗已启动 (阈值 %.0fs, 心跳 %dms), dump -> %s",
        hang_threshold_s,
        heartbeat_interval_ms,
        log_path,
    )
    return wd
