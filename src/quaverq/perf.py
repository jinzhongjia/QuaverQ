"""Lightweight performance logging helpers."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def log_elapsed(logger: logging.Logger, event: str, **fields: Any) -> Iterator[None]:
    """Log elapsed milliseconds for a scoped operation."""
    started_at = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        suffix = "".join(f" {key}={value}" for key, value in fields.items())
        logger.info("perf %s elapsed_ms=%.1f%s", event, elapsed_ms, suffix)
