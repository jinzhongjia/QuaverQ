"""Lightweight performance logging helpers."""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

_PERF_LOG_ENV = "QUAVERQ_PERF_LOG"
_TRUTHY = {"1", "true", "yes", "on"}


def _is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False) or globals().get("__compiled__") is not None)


def perf_logging_enabled() -> bool:
    """源码运行默认开启 perf 日志; Nuitka 打包产物默认关闭, 可用环境变量覆盖."""
    override = os.getenv(_PERF_LOG_ENV)
    if override is not None:
        return override.strip().lower() in _TRUTHY
    return not _is_packaged()


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    text = str(value)
    if not text or any(ch.isspace() for ch in text):
        return repr(text)
    return text


@contextmanager
def log_elapsed(logger: logging.Logger, event: str, **fields: Any) -> Generator[None]:
    """Log elapsed milliseconds for a scoped operation."""
    if not perf_logging_enabled():
        yield
        return

    started_at = time.perf_counter()
    status = "ok"
    error: BaseException | None = None
    try:
        yield
    except BaseException as exc:
        status = "error"
        error = exc
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        log_fields: dict[str, Any] = {
            "event": event,
            "status": status,
            "elapsed_ms": f"{elapsed_ms:.1f}",
            **fields,
        }
        if error is not None:
            log_fields["error"] = type(error).__name__
        payload = " ".join(f"{key}={_format_value(value)}" for key, value in log_fields.items())
        logger.info("perf %s", payload)
