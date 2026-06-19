"""Lightweight performance logging helpers."""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


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
