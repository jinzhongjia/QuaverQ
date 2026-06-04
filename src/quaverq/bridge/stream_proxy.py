"""本机回环流代理（反风控 U2）。

数据流::

    MediaPlayer(FFmpeg) --http--> 127.0.0.1 本代理 --https(curl_cffi 官方JA3)--> QQ CDN

- 回环跳走明文 http：``127.0.0.1`` 流量不出网卡，无窃听面，且免去 FFmpeg 信任自签证书。
- 出网跳走 curl_cffi impersonate 的官方浏览器 TLS 指纹 https，既加密又过 CDN 的 JA3 风控。
- token + host 白名单：防本机其他进程把它当开放代理乱用（SSRF）。

未启动时 :meth:`local_url` 降级为 http 直连（FFmpeg 直连 http 同样能过 CDN），保证可用性。
"""

from __future__ import annotations

import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit

from curl_cffi import requests as creq

logger = logging.getLogger(__name__)

# 只允许代理到 QQ 音乐 CDN，避免变成开放代理
_ALLOWED_HOST_SUFFIXES = (".qqmusic.qq.com",)
_STREAM_CHUNK = 65536


class StreamProxy:
    """把 QQ CDN 的 https 拉流包装成本机回环 http 端点。"""

    def __init__(
        self,
        *,
        impersonate: str = "chrome",
        allowed_suffixes: tuple[str, ...] = _ALLOWED_HOST_SUFFIXES,
        timeout: float = 20.0,
    ) -> None:
        self._impersonate = impersonate
        self._allowed = allowed_suffixes
        self._timeout = timeout
        self._token = secrets.token_urlsafe(16)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server is not None else 0

    def start(self) -> None:
        if self._server is not None:
            return
        proxy = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                proxy._handle(self, head=False)

            def do_HEAD(self) -> None:  # noqa: N802
                proxy._handle(self, head=True)

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="StreamProxy", daemon=True
        )
        self._thread.start()
        logger.info("StreamProxy 启动于 127.0.0.1:%d", self.port)

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None

    def local_url(self, real_url: str) -> str:
        """把真实 CDN url 映射为本机回环 url；未运行时降级 http 直连。"""
        if not self.running:
            if real_url.startswith("https://"):
                return "http://" + real_url[len("https://") :]
            return real_url
        return f"http://127.0.0.1:{self.port}/{self._token}?u={quote(real_url, safe='')}"

    def _host_allowed(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return any(host.endswith(suffix) for suffix in self._allowed)

    def _handle(self, handler: BaseHTTPRequestHandler, *, head: bool) -> None:
        parts = urlsplit(handler.path)
        if parts.path.strip("/") != self._token:
            handler.send_response(403)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        target = unquote((parse_qs(parts.query).get("u") or [""])[0])
        if not target or not self._host_allowed(target):
            handler.send_response(403)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return

        fwd: dict[str, str] = {}
        if "Range" in handler.headers:
            fwd["Range"] = handler.headers["Range"]

        try:
            resp = creq.get(
                target,
                headers=fwd,
                impersonate=self._impersonate,
                stream=True,
                timeout=self._timeout,
            )
        except Exception as exc:  # 上游不可达
            logger.warning("StreamProxy 上游请求失败: %s", exc)
            handler.send_response(502)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return

        try:
            handler.send_response(resp.status_code)
            for key in ("Content-Length", "Content-Range", "Content-Type", "Accept-Ranges"):
                value = resp.headers.get(key)
                if value:
                    handler.send_header(key, value)
            handler.end_headers()
            if head:
                return
            for chunk in resp.iter_content(_STREAM_CHUNK):
                if not chunk:
                    continue
                handler.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端(FFmpeg) seek/停止时正常断开
        except Exception as exc:
            logger.warning("StreamProxy 转发中断: %s", exc)
        finally:
            resp.close()
