"""性能打点工具测试。"""

from __future__ import annotations

import logging

from quaverq.perf import log_elapsed


def test_log_elapsed_records_duration_and_fields(caplog, monkeypatch):
    ticks = iter([10.0, 10.125])
    monkeypatch.setattr("quaverq.perf.time.perf_counter", lambda: next(ticks))
    logger = logging.getLogger("tests.perf")

    with caplog.at_level(logging.INFO, logger=logger.name):
        with log_elapsed(logger, "startup.prime_cache", phase="prime", sections=4):
            pass

    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == (
        "perf startup.prime_cache elapsed_ms=125.0 phase=prime sections=4"
    )
