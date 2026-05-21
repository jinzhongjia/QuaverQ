"""封面磁盘缓存 (P1.5) 单元测试.

设计:
- get_path(url): 同步检查本地是否已下载, 命中返 Path; 未命中返 None
- fetch(url):    异步下载到本地, 返回 Path; 失败返 None, 容忍网络错
- 文件名:        sha1(url) + URL 末尾的扩展名 (.jpg/.png), 同 URL 多次 fetch 复用
"""

from __future__ import annotations

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
        content = fake_bytes

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
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
        content = b"img"

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
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
        content = b""

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
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
