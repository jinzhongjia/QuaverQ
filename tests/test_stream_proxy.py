"""Step B 本地回环代理测试（反风控 U2）。

代理：FFmpeg 连 127.0.0.1(http)，代理用 curl_cffi 官方指纹 https 拉 CDN。
明文只在回环；token + host 白名单防本机其他进程乱连 / SSRF。
"""

from __future__ import annotations

import http.client
import urllib.parse

from quaverq.bridge.stream_proxy import StreamProxy


def _get(local_url: str, headers: dict | None = None):
    u = urllib.parse.urlsplit(local_url)
    conn = http.client.HTTPConnection(u.netloc, timeout=5)
    conn.request("GET", u.path + ("?" + u.query if u.query else ""), headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body


def test_local_url_degrades_to_http_when_not_running():
    proxy = StreamProxy()
    # 未启动时降级为 http 直连（FFmpeg 直连 http 也能过 CDN）
    out = proxy.local_url("https://isure.stream.qqmusic.qq.com/M800.mp3?vkey=k")
    assert out == "http://isure.stream.qqmusic.qq.com/M800.mp3?vkey=k"


def test_local_url_running_points_to_loopback():
    proxy = StreamProxy()
    proxy.start()
    try:
        out = proxy.local_url("https://isure.stream.qqmusic.qq.com/M800.mp3?vkey=k")
        assert out.startswith(f"http://127.0.0.1:{proxy.port}/")
    finally:
        proxy.stop()


class _FakeResp:
    status_code = 206
    headers = {
        "Content-Type": "audio/mpeg",
        "Content-Length": "5",
        "Accept-Ranges": "bytes",
    }

    def iter_content(self, _n=None):
        yield b"AUDIO"

    def close(self):
        pass


class _FakeSession:
    """顶替 curl_cffi Session: 记录 get 调用与 close."""

    def __init__(self) -> None:
        self.gets: list[tuple[str, str | None]] = []
        self.closed = False

    def get(self, url, headers=None, stream=None):
        self.gets.append((url, (headers or {}).get("Range")))
        return _FakeResp()

    def close(self) -> None:
        self.closed = True


def test_proxy_forwards_upstream_with_range():
    session = _FakeSession()
    proxy = StreamProxy(upstream_factory=lambda: session)
    proxy.start()
    try:
        real = "https://isure.stream.qqmusic.qq.com/M800.mp3?vkey=k&uin=1"
        status, body = _get(proxy.local_url(real), headers={"Range": "bytes=0-3"})
        assert status == 206
        assert body == b"AUDIO"
        assert session.gets == [(real, "bytes=0-3")]
    finally:
        proxy.stop()


def test_proxy_reuses_single_upstream_session_across_requests():
    """issue #11 Stage B: 上游会话只建一次, 多请求共用 (连接复用免重复 TLS 握手)."""
    sessions: list[_FakeSession] = []

    def factory():
        sessions.append(_FakeSession())
        return sessions[-1]

    proxy = StreamProxy(upstream_factory=factory)
    proxy.start()
    try:
        real = "https://isure.stream.qqmusic.qq.com/M800.mp3?vkey=k"
        _get(proxy.local_url(real))
        _get(proxy.local_url(real), headers={"Range": "bytes=4-"})
        assert len(sessions) == 1
        assert len(sessions[0].gets) == 2
    finally:
        proxy.stop()


def test_stop_closes_upstream_session():
    session = _FakeSession()
    proxy = StreamProxy(upstream_factory=lambda: session)
    proxy.start()
    proxy.stop()
    assert session.closed is True


def test_default_upstream_session_carries_impersonate_and_timeout():
    """默认工厂建出的 curl_cffi Session 带会话级 impersonate + timeout."""
    proxy = StreamProxy(impersonate="chrome", timeout=7.5)
    proxy.start()
    try:
        assert proxy._upstream is not None
        assert proxy._upstream.impersonate == "chrome"
        assert proxy._upstream.timeout == 7.5
    finally:
        proxy.stop()
    assert proxy._upstream is None


def test_proxy_rejects_bad_token():
    proxy = StreamProxy()
    proxy.start()
    try:
        bad = f"http://127.0.0.1:{proxy.port}/wrongtoken?u=" + urllib.parse.quote(
            "https://isure.stream.qqmusic.qq.com/x.mp3", safe=""
        )
        status, _ = _get(bad)
        assert status == 403
    finally:
        proxy.stop()


def test_proxy_rejects_non_whitelisted_host():
    # 即使 token 正确，非 QQ CDN 的 host 也必须拒绝（防开放代理 / SSRF）
    class _NeverSession(_FakeSession):
        def get(self, url, headers=None, stream=None):
            raise AssertionError("不应到达上游")

    session = _NeverSession()
    proxy = StreamProxy(upstream_factory=lambda: session)
    proxy.start()
    try:
        evil = proxy.local_url("https://evil.example.com/secret")
        # 未运行降级分支不会触发；这里 proxy 在运行，local_url 会指向回环
        status, _ = _get(evil)
        assert status == 403
        assert session.gets == []
    finally:
        proxy.stop()


def test_concurrent_requests_share_session_without_corruption():
    """issue #11 Stage B 回归: 多线程并发经共享 curl_cffi Session 拉不同内容, 数据不串.

    ThreadingHTTPServer 每请求一线程, 全部共享 self._upstream 一个 Session. curl_cffi
    Session 默认 thread-local curl handle 应线程安全 —— 此测真实 Session (非 fake) +
    本地 CDN, 校验并发下各线程拿到对应自己请求的完整内容 (review 指出的覆盖缺口).
    """
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    payloads = {f"/s{i}": (f"body-{i}-".encode() * 1500) for i in range(5)}  # 各 ~12KB

    class _CDN(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):  # noqa: N802
            body = payloads.get(urllib.parse.urlsplit(self.path).path)
            if body is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # noqa: N802
            pass

    cdn = ThreadingHTTPServer(("127.0.0.1", 0), _CDN)
    cdn.daemon_threads = True
    threading.Thread(target=cdn.serve_forever, daemon=True).start()
    cdn_port = cdn.server_address[1]

    proxy = StreamProxy(allowed_suffixes=("127.0.0.1",), impersonate="chrome")
    proxy.start()
    errors: list[str] = []
    lock = threading.Lock()

    def pull(i: int):
        real = f"http://127.0.0.1:{cdn_port}/s{i}"
        status, body = _get(proxy.local_url(real))
        if status != 200 or body != payloads[f"/s{i}"]:
            with lock:
                errors.append(
                    f"s{i}: status={status} len={len(body)} ok={body == payloads[f'/s{i}']}"
                )

    try:
        for _ in range(3):  # 3 轮并发, 复用同一 Session
            threads = [threading.Thread(target=pull, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        assert errors == [], errors
    finally:
        proxy.stop()
        cdn.shutdown()
