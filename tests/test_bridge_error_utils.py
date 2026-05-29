"""Bridge error handling helper tests."""

from __future__ import annotations

import logging

from quaverq.bridge.error_utils import log_bridge_error


def test_log_bridge_error_squashes_dns_traceback(caplog):
    logger = logging.getLogger("tests.bridge_error_utils")
    exc = ConnectionError(
        "Failed to resolve 'u.y.qq.com' (Name or service not known)"
    )

    with caplog.at_level(logging.WARNING, logger=logger.name):
        message = log_bridge_error(logger, "refresh liked songs failed", exc)

    assert message == "网络连接失败：无法解析 QQ 音乐服务域名，请检查 DNS 或网络连接"
    assert "refresh liked songs failed" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_log_bridge_error_keeps_unknown_traceback(caplog):
    logger = logging.getLogger("tests.bridge_error_utils")
    exc = ValueError("bad payload")

    with caplog.at_level(logging.ERROR, logger=logger.name):
        message = log_bridge_error(logger, "parse failed", exc)

    assert message == "bad payload"
    assert any(record.exc_info is not None for record in caplog.records)
