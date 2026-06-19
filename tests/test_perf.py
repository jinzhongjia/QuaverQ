"""性能打点工具测试。"""

from __future__ import annotations

import logging

import pytest

from quaverq import perf
from quaverq.perf import log_elapsed


def test_log_elapsed_records_duration_and_fields(caplog, monkeypatch):
    monkeypatch.delenv("QUAVERQ_PERF_LOG", raising=False)
    monkeypatch.setattr(perf, "is_packaged", lambda: False)
    ticks = iter([10.0, 10.125])
    monkeypatch.setattr("quaverq.perf.time.perf_counter", lambda: next(ticks))
    logger = logging.getLogger("tests.perf")

    with caplog.at_level(logging.INFO, logger=logger.name):
        with log_elapsed(logger, "startup.prime_cache", phase="prime", sections=4):
            pass

    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == (
        "perf event=startup.prime_cache status=ok elapsed_ms=125.0 phase=prime sections=4"
    )


def test_log_elapsed_records_error_status(caplog, monkeypatch):
    monkeypatch.delenv("QUAVERQ_PERF_LOG", raising=False)
    monkeypatch.setattr(perf, "is_packaged", lambda: False)
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr("quaverq.perf.time.perf_counter", lambda: next(ticks))
    logger = logging.getLogger("tests.perf")

    with caplog.at_level(logging.INFO, logger=logger.name):
        with pytest.raises(ValueError, match="boom"):
            with log_elapsed(logger, "startup.qml_load", path="Main QML"):
                raise ValueError("boom")

    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == (
        "perf event=startup.qml_load status=error elapsed_ms=250.0 path='Main QML' error=ValueError"
    )


def test_log_elapsed_is_disabled_by_default_in_packaged_build(caplog, monkeypatch):
    monkeypatch.delenv("QUAVERQ_PERF_LOG", raising=False)
    monkeypatch.setattr(perf, "is_packaged", lambda: True)
    monkeypatch.setattr(
        "quaverq.perf.time.perf_counter",
        lambda: pytest.fail("disabled perf logging should not read the clock"),
    )
    logger = logging.getLogger("tests.perf")

    with caplog.at_level(logging.INFO, logger=logger.name):
        with log_elapsed(logger, "startup.qml_load"):
            pass

    assert caplog.records == []


def test_log_elapsed_can_be_enabled_by_env_in_packaged_build(caplog, monkeypatch):
    monkeypatch.setenv("QUAVERQ_PERF_LOG", "1")
    monkeypatch.setattr(perf, "is_packaged", lambda: True)
    ticks = iter([10.0, 10.01])
    monkeypatch.setattr("quaverq.perf.time.perf_counter", lambda: next(ticks))
    logger = logging.getLogger("tests.perf")

    with caplog.at_level(logging.INFO, logger=logger.name):
        with log_elapsed(logger, "startup.qml_load"):
            pass

    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == (
        "perf event=startup.qml_load status=ok elapsed_ms=10.0"
    )
