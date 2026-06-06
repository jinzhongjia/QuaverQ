"""封面磁盘缓存单元测试.

设计:
- get_path(url): 同步检查本地是否已下载, 命中返 Path; 未命中返 None
- fetch(url):    异步下载到本地, 返回 Path; 失败返 None, 容忍网络错
- 文件名:        sha1(url) + URL 末尾的扩展名 (.jpg/.png), 同 URL 多次 fetch 复用
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from quaverq.core.cover_cache import CoverCache


@pytest.fixture
def cover_cache(tmp_path: Path) -> CoverCache:
    return CoverCache(tmp_path / "covers")


# ============================================================== get_path

def test_get_path_returns_none_when_not_cached(cover_cache: CoverCache):
    assert cover_cache.get_path("https://x/c.jpg") is None


def test_get_path_returns_none_for_empty_url(cover_cache: CoverCache):
    assert cover_cache.get_path("") is None
    assert cover_cache.get_path(None) is None


# ============================================================== fetch

async def test_fetch_downloads_and_caches(cover_cache: CoverCache, monkeypatch):
    """fetch 调用 niquests, 写文件, 之后 get_path 返本地路径."""
    import niquests

    fake_bytes = b"\xff\xd8\xff\xe0fakejpegbody"

    class _FakeResp:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_content(self, n): yield fake_bytes

    class _FakeSession:
        def get(self, *args, **kwargs): return _FakeResp()

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())

    url = "https://y.qq.com/cover/abc.jpg"
    path = await cover_cache.fetch(url)
    assert path is not None
    assert path.exists()
    assert path.read_bytes() == fake_bytes
    # 命中本地
    assert cover_cache.get_path(url) == path


async def test_fetch_dedupes_by_url(cover_cache: CoverCache, monkeypatch):
    """同 URL 重复 fetch 复用文件, 不重复下载."""
    import niquests
    download_count = [0]

    class _FakeResp:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_content(self, n): yield b"img"

    class _FakeSession:
        def get(self, *args, **kwargs):
            download_count[0] += 1
            return _FakeResp()

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())

    url = "https://y.qq.com/c.jpg"
    p1 = await cover_cache.fetch(url)
    p2 = await cover_cache.fetch(url)
    assert p1 == p2
    assert download_count[0] == 1  # 第二次直接命中


async def test_fetch_returns_none_on_404(cover_cache: CoverCache, monkeypatch):
    import niquests

    class _FakeResp:
        status_code = 404
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_content(self, n): yield b""

    class _FakeSession:
        def get(self, *args, **kwargs): return _FakeResp()

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())
    p = await cover_cache.fetch("https://x/missing.jpg")
    assert p is None


async def test_fetch_returns_none_on_network_error(cover_cache: CoverCache, monkeypatch):
    import niquests

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, *args, **kwargs):
            raise ConnectionError("network down")

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())
    p = await cover_cache.fetch("https://x/c.jpg")
    assert p is None


async def test_fetch_empty_url_returns_none(cover_cache: CoverCache):
    assert await cover_cache.fetch("") is None
    assert await cover_cache.fetch(None) is None


async def test_close_aborts_in_flight_download(cover_cache: CoverCache, monkeypatch):
    """close() 置 _closing 后, 在途下载在分块间放弃 (退出时下载线程秒退)."""
    import niquests

    class _FakeResp:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_content(self, n): yield b"cover-bytes"

    class _FakeSession:
        def get(self, *args, **kwargs): return _FakeResp()

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())
    cover_cache.close()
    assert await cover_cache.fetch("https://y.qq.com/c.jpg") is None


def test_session_reused_keeps_connection_alive(cover_cache: CoverCache, monkeypatch):
    """同线程内复用同一个 Session (keep-alive), 不每张图新建 -> 省 TLS 握手."""
    import niquests

    created: list[object] = []

    class _FakeSession:
        def get(self, *args, **kwargs):
            return None

    def factory():
        session = _FakeSession()
        created.append(session)
        return session

    monkeypatch.setattr(niquests, "Session", factory)

    assert cover_cache._session() is cover_cache._session()
    assert len(created) == 1


# ============================================================== 文件名

def test_filename_keeps_jpg_extension(cover_cache: CoverCache):
    name = cover_cache._filename_for("https://x/T002R500x500M000abc.jpg")
    assert name.endswith(".jpg")


def test_filename_keeps_png_extension(cover_cache: CoverCache):
    name = cover_cache._filename_for("https://x/a.png?param=1")
    assert name.endswith(".png")


def test_filename_unknown_extension_defaults_jpg(cover_cache: CoverCache):
    """没有 .jpg/.png 时默认 .jpg (QQ 封面绝大多数是 jpg)."""
    name = cover_cache._filename_for("https://x/cover")
    assert name.endswith(".jpg")


def test_filename_sha1_stable(cover_cache: CoverCache):
    """同 URL 两次生成同样的文件名 (sha1 稳定)."""
    a = cover_cache._filename_for("https://x/cover.jpg")
    b = cover_cache._filename_for("https://x/cover.jpg")
    assert a == b


def test_filename_different_urls_different(cover_cache: CoverCache):
    a = cover_cache._filename_for("https://x/a.jpg")
    b = cover_cache._filename_for("https://x/b.jpg")
    assert a != b


# ============================================================== to_file_uri

def test_to_file_uri_returns_file_scheme(cover_cache: CoverCache, tmp_path: Path):
    p = tmp_path / "covers" / "x.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    uri = cover_cache.to_file_uri(p)
    assert uri.startswith("file://")
    assert str(p) in uri


# ============================================================== size / clear

def test_size_bytes_sums_cached_files(cover_cache: CoverCache):
    cover_cache.dir.mkdir(parents=True)
    (cover_cache.dir / "a.jpg").write_bytes(b"abc")
    nested = cover_cache.dir / "nested"
    nested.mkdir()
    (nested / "b.jpg").write_bytes(b"de")

    assert cover_cache.size_bytes() == 5


def test_clear_removes_cached_files_and_returns_size(cover_cache: CoverCache):
    cover_cache.dir.mkdir(parents=True)
    (cover_cache.dir / "a.jpg").write_bytes(b"abc")
    nested = cover_cache.dir / "nested"
    nested.mkdir()
    (nested / "b.jpg").write_bytes(b"de")

    assert cover_cache.clear() == 5
    assert cover_cache.size_bytes() == 0
    assert list(cover_cache.dir.iterdir()) == []


# ============================================================== max_bytes / LRU

def _seed(cover_cache: CoverCache, name: str, data: bytes, mtime: float) -> Path:
    """Write a file directly into the cache dir with a controlled mtime."""
    cover_cache.dir.mkdir(parents=True, exist_ok=True)
    path = cover_cache.dir / name
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


def test_max_bytes_unlimited_by_default(cover_cache: CoverCache):
    assert cover_cache.max_bytes == 0


def test_set_max_bytes_updates_value(cover_cache: CoverCache):
    cover_cache.set_max_bytes(123)
    assert cover_cache.max_bytes == 123


def test_set_max_bytes_clamps_negative_to_zero(cover_cache: CoverCache):
    cover_cache.set_max_bytes(-5)
    assert cover_cache.max_bytes == 0


def test_enforce_limit_noop_when_unlimited(cover_cache: CoverCache):
    _seed(cover_cache, "a.jpg", b"aaaa", mtime=1000)
    _seed(cover_cache, "b.jpg", b"bbbb", mtime=2000)
    assert cover_cache.enforce_limit() == 0
    assert cover_cache.size_bytes() == 8


def test_enforce_limit_noop_when_under_limit(cover_cache: CoverCache):
    cover_cache.max_bytes = 100
    _seed(cover_cache, "a.jpg", b"aaaa", mtime=1000)
    assert cover_cache.enforce_limit() == 0
    assert cover_cache.size_bytes() == 4


def test_enforce_limit_evicts_oldest_first(cover_cache: CoverCache):
    cover_cache.max_bytes = 6
    a = _seed(cover_cache, "a.jpg", b"aaaa", mtime=1000)  # oldest
    b = _seed(cover_cache, "b.jpg", b"bbbb", mtime=2000)
    c = _seed(cover_cache, "c.jpg", b"cccc", mtime=3000)  # newest

    removed = cover_cache.enforce_limit()

    assert removed == 8  # evicted a + b until under 6
    assert not a.exists()
    assert not b.exists()
    assert c.exists()  # newest kept
    assert cover_cache.size_bytes() == 4


def test_enforce_limit_keeps_newest_even_if_it_exceeds_limit(cover_cache: CoverCache):
    cover_cache.max_bytes = 2
    big = _seed(cover_cache, "big.jpg", b"abcdef", mtime=1000)  # 6 bytes, only file
    assert cover_cache.enforce_limit() == 0
    assert big.exists()  # never delete the sole/newest entry


def test_set_max_bytes_triggers_immediate_eviction(cover_cache: CoverCache):
    a = _seed(cover_cache, "a.jpg", b"aaaa", mtime=1000)
    b = _seed(cover_cache, "b.jpg", b"bbbb", mtime=2000)

    removed = cover_cache.set_max_bytes(4)

    assert removed == 4
    assert not a.exists()
    assert b.exists()


def test_get_path_bumps_stale_access_time(cover_cache: CoverCache):
    """A cache hit on a stale file refreshes its recency (real LRU on display)."""
    url = "https://x/a.jpg"
    cover_cache.dir.mkdir(parents=True, exist_ok=True)
    path = cover_cache.dir / cover_cache._filename_for(url)
    path.write_bytes(b"x")
    stale = time.time() - 10_000
    os.utime(path, (stale, stale))

    assert cover_cache.get_path(url) == path
    assert path.stat().st_mtime > stale + 1  # bumped toward now


def test_get_path_does_not_bump_fresh_access_time(cover_cache: CoverCache):
    """Hot render path stays write-free within the throttle window."""
    url = "https://x/b.jpg"
    cover_cache.dir.mkdir(parents=True, exist_ok=True)
    path = cover_cache.dir / cover_cache._filename_for(url)
    path.write_bytes(b"x")
    fresh = time.time()
    os.utime(path, (fresh, fresh))

    cover_cache.get_path(url)

    assert abs(path.stat().st_mtime - fresh) < 5  # unchanged (tolerate fs rounding)


async def test_fetch_runs_eviction_after_download(cover_cache: CoverCache, monkeypatch):
    import niquests

    class _FakeResp:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_content(self, n): yield b"imgbytes"

    class _FakeSession:
        def get(self, *args, **kwargs): return _FakeResp()

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())
    cover_cache.max_bytes = 100
    calls: list[bool] = []
    monkeypatch.setattr(cover_cache, "enforce_limit", lambda: calls.append(True) or 0)

    await cover_cache.fetch("https://x/a.jpg")
    assert calls  # eviction ran after a successful download


async def test_fetch_skips_eviction_when_unlimited(cover_cache: CoverCache, monkeypatch):
    import niquests

    class _FakeResp:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_content(self, n): yield b"imgbytes"

    class _FakeSession:
        def get(self, *args, **kwargs): return _FakeResp()

    monkeypatch.setattr(niquests, "Session", lambda: _FakeSession())
    # max_bytes stays 0 (unlimited) -> no eviction work on the common path
    calls: list[bool] = []
    monkeypatch.setattr(cover_cache, "enforce_limit", lambda: calls.append(True) or 0)

    await cover_cache.fetch("https://x/a.jpg")
    assert not calls
