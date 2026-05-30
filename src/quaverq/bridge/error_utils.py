"""Shared bridge error handling helpers."""

from __future__ import annotations

import logging
import socket
from collections.abc import Iterator


_NETWORK_MODULE_PREFIXES = (
    "aiohttp",
    "httpx",
    "niquests",
    "requests",
    "urllib3",
)
_NETWORK_CLASS_TOKENS = (
    "Connection",
    "Connect",
    "NameResolution",
    "Network",
    "Protocol",
    "ReadTimeout",
    "Retry",
    "SSLError",
    "Timeout",
)
_DNS_TEXT_TOKENS = (
    "failed to resolve",
    "name or service not known",
    "temporary failure in name resolution",
)
_TIMEOUT_TEXT_TOKENS = (
    "connect timeout",
    "read timeout",
    "timed out",
    "timeout",
)
_AUTH_EXPIRED_TEXT_TOKENS = (
    "credential expired",
    "login expired",
    "登录已过期",
    "登录过期",
    "登录失效",
)


def user_error_message(exc: BaseException) -> str:
    """Return a user-facing message for common transient failures."""
    if is_auth_expired_error(exc):
        return "登录已过期，请重新扫码"
    if _has_text(exc, _DNS_TEXT_TOKENS) or _has_exception_name(exc, "NameResolution"):
        return "网络连接失败：无法解析 QQ 音乐服务域名，请检查 DNS 或网络连接"
    if _has_text(exc, _TIMEOUT_TEXT_TOKENS) or _has_exception_name(exc, "Timeout"):
        return "网络连接超时：请检查网络后重试"
    if is_network_error(exc):
        return "网络连接失败：请检查网络后重试"
    return str(exc) or exc.__class__.__name__


def log_bridge_error(
    logger: logging.Logger,
    operation: str,
    exc: BaseException,
) -> str:
    """Log expected network failures tersely, preserving traces for unknown bugs."""
    message = user_error_message(exc)
    if is_network_error(exc) or is_auth_expired_error(exc):
        logger.warning("%s: %s", operation, message)
    else:
        logger.exception(operation)
    return message


def is_auth_expired_error(exc: BaseException) -> bool:
    return _has_exception_name(exc, "CredentialExpiredError") or _has_text(
        exc,
        _AUTH_EXPIRED_TEXT_TOKENS,
    )


def is_network_error(exc: BaseException) -> bool:
    for item in _walk_exception_graph(exc):
        if isinstance(item, (ConnectionError, TimeoutError, socket.gaierror)):
            return True
        module = item.__class__.__module__
        name = item.__class__.__name__
        if module.startswith(_NETWORK_MODULE_PREFIXES) and any(
            token in name for token in _NETWORK_CLASS_TOKENS
        ):
            return True
    return _has_text(exc, _DNS_TEXT_TOKENS + _TIMEOUT_TEXT_TOKENS)


def _has_exception_name(exc: BaseException, token: str) -> bool:
    return any(token in item.__class__.__name__ for item in _walk_exception_graph(exc))


def _has_text(exc: BaseException, tokens: tuple[str, ...]) -> bool:
    text = " ".join(str(item) for item in _walk_exception_graph(exc)).lower()
    return any(token in text for token in tokens)


def _walk_exception_graph(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()

    def walk(item: BaseException) -> Iterator[BaseException]:
        if id(item) in seen:
            return
        seen.add(id(item))
        yield item
        for nested in (item.__cause__, item.__context__):
            if nested is not None:
                yield from walk(nested)
        for arg in item.args:
            if isinstance(arg, BaseException):
                yield from walk(arg)

    yield from walk(exc)
