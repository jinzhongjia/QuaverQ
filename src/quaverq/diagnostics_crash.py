"""崩溃日志落盘 -- ``sys.excepthook`` 把 unhandled exception traceback 写到
``CACHE_DIR/crash.log``.

为什么需要: 启动期 / 后台线程的 unhandled exception 一闪而过到 stderr 就丢了
(尤其是 Nuitka 打包后无 console 子系统的可执行文件). 用户报 bug 时拿不到回溯,
研发只能远程猜. 落盘后用户能用 ``%LOCALAPPDATA%\\quaverq\\crash.log`` 直接附上.

实现:
- 安装新的 ``sys.excepthook`` / ``threading.excepthook`` 先写文件再**链给原 hook**
  (默认输出到 stderr) —— 控制台调试体验不变.
- 追加模式 (``"a"``), 不覆盖历史; 每条记录用分隔线 + 时间戳便于回看.
- 写入前做简单轮转, 避免 ``crash.log`` 无限增长.
- 写文件本身的异常吞掉, 避免崩溃日志写失败导致二次崩溃.

注意: asyncio task 异常走 ``loop.set_exception_handler``, QObject signal/slot 异常走 Qt 的
``qInstallMessageHandler`` (我们已经装了 ``_qt_message_handler``); crash.log 主要拦住
``main()`` 同步路径 + Python 线程未处理异常.
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from contextlib import suppress
from datetime import datetime, timezone
from types import TracebackType

from .config import CACHE_DIR

logger = logging.getLogger(__name__)

_LOG_NAME = "crash.log"
_ROTATED_LOG_NAME = "crash.log.1"
_MAX_LOG_BYTES = 1024 * 1024
_installed = False


def _rotate_if_needed(log_path) -> None:
    if not log_path.exists() or log_path.stat().st_size < _MAX_LOG_BYTES:
        return
    rotated = log_path.with_name(_ROTATED_LOG_NAME)
    if rotated.exists():
        rotated.unlink()
    log_path.replace(rotated)


def _write_crash_log(
    log_path,
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed(log_path)
    with log_path.open("a", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {exc_type.__name__}: {exc_value}\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        f.write("\n")


def install_crash_logger() -> None:
    """安装 ``sys.excepthook`` 把 unhandled exception 写到 ``CACHE_DIR/crash.log``.

    幂等: 重复调用替换为新 hook, 但保留链回原 hook 的能力 (用闭包捕获当时的 ``sys.excepthook``).
    """
    global _installed
    if _installed:
        return

    log_path = CACHE_DIR / _LOG_NAME
    previous_hook = sys.excepthook
    previous_thread_hook = threading.excepthook

    def _crash_hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        # 崩溃日志写失败 (磁盘满 / 权限 / 文件被锁) 也别再崩, 静默吞掉.
        with suppress(Exception):
            _write_crash_log(log_path, exc_type, exc_value, exc_tb)
        # 链回上一个 hook: 默认 hook 把 traceback 写 stderr, 控制台调试体验不变.
        try:
            previous_hook(exc_type, exc_value, exc_tb)
        except Exception:
            sys.__excepthook__(exc_type, exc_value, exc_tb)

    def _thread_crash_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is not None and args.exc_value is not None:
            with suppress(Exception):
                _write_crash_log(log_path, args.exc_type, args.exc_value, args.exc_traceback)
        try:
            previous_thread_hook(args)
        except Exception:
            threading.__excepthook__(args)

    sys.excepthook = _crash_hook
    threading.excepthook = _thread_crash_hook
    _installed = True
    logger.debug("崩溃日志已就位: %s", log_path)
