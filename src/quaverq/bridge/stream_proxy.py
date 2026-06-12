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
import mimetypes
import secrets
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
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
        local_dir: Path | None = None,
        upstream_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._impersonate = impersonate
        self._allowed = allowed_suffixes
        self._timeout = timeout
        # 上游会话整个代理生命周期只建一次 (issue #11 Stage B): curl_cffi Session
        # 线程安全 (默认 thread-local curl handle), 同一服务线程内的连续请求
        # (FFmpeg keep-alive 的 Range/seek) 复用到 CDN 的 TLS 连接, 免去旧实现
        # 每请求新建会话的完整 TCP+TLS 握手. upstream_factory 供测试注入 fake.
        self._upstream_factory = upstream_factory or self._default_upstream
        self._upstream: Any = None
        self._token = secrets.token_urlsafe(16)
        # 本地静态文件目录 (供 Windows SMTC 把封面通过 http:// 暴露出去, 因 SMTC
        # 的 RandomAccessStreamReference.CreateFromUri 不支持 file:// URI).
        # 仅 127.0.0.1 监听; 用 token 做额外鉴权防止本机其他进程瞎读.
        self._local_dir = Path(local_dir).resolve() if local_dir is not None else None
        self._local_token = secrets.token_urlsafe(16)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server is not None else 0

    def _default_upstream(self) -> Any:
        return creq.Session(impersonate=self._impersonate, timeout=self._timeout)

    def start(self) -> None:
        if self._server is not None:
            return
        self._upstream = self._upstream_factory()
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
        # 退出要快: 请求线程 daemon 化且关闭时不 join 在途请求 (随进程退出);
        # serve_forever 用小 poll 间隔, 让 stop() 的 shutdown() 几乎立即返回
        # (默认 0.5s 会让退出明显钝一下).
        self._server.daemon_threads = True
        self._server.block_on_close = False
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.05),
            name="StreamProxy",
            daemon=True,
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
        # 服务停掉后再关上游会话; 在途 daemon 请求线程随后用到失效 handle 时
        # 由 _handle 的 except 兜住 (行为同旧实现的连接中断)
        if self._upstream is not None:
            try:
                self._upstream.close()
            except Exception as exc:
                logger.debug("StreamProxy 上游会话关闭异常 (忽略): %s", exc)
            self._upstream = None

    def local_url(self, real_url: str) -> str:
        """把真实 CDN url 映射为本机回环 url；未运行时降级 http 直连。"""
        if not self.running:
            if real_url.startswith("https://"):
                return "http://" + real_url[len("https://") :]
            return real_url
        return f"http://127.0.0.1:{self.port}/{self._token}?u={quote(real_url, safe='')}"

    def local_file_url(self, filename: str) -> str | None:
        """给本机静态文件 (在 ``local_dir`` 下) 生成回环 http url.

        典型用途: Windows SMTC 用 ``RandomAccessStreamReference.CreateFromUri(http://)``
        加载本地封面 —— 它不支持 ``file://`` URI.

        返回 None 表示: 未启动 / 没配置 local_dir / 文件名含路径分隔符.
        """
        if not self.running or self._local_dir is None:
            return None
        # 防 path traversal: 只允许干净文件名
        if "/" in filename or "\\" in filename or filename in ("", ".", ".."):
            return None
        return f"http://127.0.0.1:{self.port}/_local/{self._local_token}/{quote(filename, safe='')}"

    def _host_allowed(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return any(host.endswith(suffix) for suffix in self._allowed)

    def _handle(self, handler: BaseHTTPRequestHandler, *, head: bool) -> None:
        parts = urlsplit(handler.path)
        path = parts.path
        # 本地静态文件路径: /_local/<token>/<filename>
        if path.startswith("/_local/"):
            self._handle_local(handler, path, head=head)
            return
        if path.strip("/") != self._token:
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

        session = self._upstream
        if session is None:  # stop() 竞态: 服务线程残留请求
            handler.send_response(502)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        try:
            resp = session.get(target, headers=fwd, stream=True)
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

    def _handle_local(self, handler: BaseHTTPRequestHandler, path: str, *, head: bool) -> None:
        """``/_local/<token>/<filename>`` -> 从 ``local_dir`` 读文件."""
        if self._local_dir is None:
            handler.send_response(403)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        # path: /_local/<token>/<filename>
        parts = path[len("/_local/") :].split("/", 1)
        if len(parts) != 2 or parts[0] != self._local_token:
            handler.send_response(403)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        filename = unquote(parts[1])
        # 二次防 traversal: resolve 后必须仍在 local_dir 下
        try:
            target = (self._local_dir / filename).resolve()
            target.relative_to(self._local_dir)
        except (OSError, ValueError):
            handler.send_response(403)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        if not target.is_file():
            handler.send_response(404)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        try:
            size = target.stat().st_size
            content_type, _ = mimetypes.guess_type(str(target))
            handler.send_response(200)
            handler.send_header("Content-Length", str(size))
            handler.send_header("Content-Type", content_type or "application/octet-stream")
            handler.send_header("Cache-Control", "public, max-age=3600")
            handler.end_headers()
            if head:
                return
            with open(target, "rb") as f:
                while True:
                    chunk = f.read(_STREAM_CHUNK)
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            logger.warning("StreamProxy 本地文件读取失败: %s", exc)
