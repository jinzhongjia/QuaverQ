"""core.downloader 单元测试: 文件名清洗 + 流式下载器."""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from quaverq.core.downloader import (
    DownloadCanceled,
    Downloader,
    DownloadError,
    sanitize_filename,
)

# ============================================================== sanitize_filename


def test_sanitize_keeps_plain_name():
    assert sanitize_filename("周杰伦 - 晴天") == "周杰伦 - 晴天"


def test_sanitize_replaces_windows_invalid_chars():
    # Windows 非法字符 \ / : * ? " < > | 全部替换为下划线
    assert sanitize_filename('a\\b/c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_sanitize_strips_control_chars():
    assert sanitize_filename("he\x00llo\x1fworld\n") == "he_llo_world"


def test_sanitize_strips_trailing_dots_and_spaces():
    # Windows 不允许文件名以点 / 空格结尾
    assert sanitize_filename("name.. ") == "name"
    assert sanitize_filename("  name  ") == "name"


def test_sanitize_empty_falls_back_to_untitled():
    assert sanitize_filename("") == "untitled"
    assert sanitize_filename("   ") == "untitled"
    assert sanitize_filename("...") == "untitled"


def test_sanitize_windows_reserved_names_prefixed():
    # CON / PRN / AUX / NUL / COM1-9 / LPT1-9 是 Windows 保留设备名
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("con") == "_con"
    assert sanitize_filename("LPT3") == "_LPT3"
    # 仅整名匹配, 含保留名子串不受影响
    assert sanitize_filename("CONCERT") == "CONCERT"


def test_sanitize_truncates_by_utf8_bytes_without_breaking_chars():
    # 中文 3 字节/字; 100 字节上限只装得下 33 个完整汉字
    name = "歌" * 50
    result = sanitize_filename(name, max_bytes=100)
    assert result == "歌" * 33
    assert len(result.encode("utf-8")) <= 100


def test_sanitize_truncation_strips_dangling_trailer():
    # 截断后若尾部恰为点/空格, 仍需去掉
    result = sanitize_filename("a" * 99 + " b", max_bytes=100)
    assert result == "a" * 99


# ============================================================== quality_extension


def test_quality_extension_known_labels():
    from quaverq.core.downloader import quality_extension

    assert quality_extension("FLAC") == "flac"
    assert quality_extension("MP3_320") == "mp3"
    assert quality_extension("MP3_128") == "mp3"
    assert quality_extension("OGG_192") == "ogg"
    # 臻品母带 / 臻品全景声: AI00 / Q000 前缀, flac 容器
    assert quality_extension("MASTER") == "flac"
    assert quality_extension("ATMOS_2") == "flac"
    assert quality_extension("UNKNOWN_FUTURE") == "mp3"


# ============================================================== Downloader.download_file

_PAYLOAD = bytes(range(256)) * 64  # 16 KB


@pytest.fixture
def http_server():
    """本地 HTTP 服务器: /ok 定长内容, /nolen 无 Content-Length, /slow 分段慢发."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 约定命名
            if self.path == "/ok":
                self.send_response(200)
                self.send_header("Content-Length", str(len(_PAYLOAD)))
                self.end_headers()
                self.wfile.write(_PAYLOAD)
            elif self.path == "/nolen":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"hello")
            elif self.path == "/resume":
                # 只接受 Range 请求 (强制测试走续传路径; 无 Range 一律 500)
                rng = self.headers.get("Range", "")
                if not rng:
                    self.send_response(500)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start = int(rng.split("=")[1].rstrip("-"))
                body = _PAYLOAD[start:]
                self.send_response(206)
                self.send_header(
                    "Content-Range", f"bytes {start}-{len(_PAYLOAD) - 1}/{len(_PAYLOAD)}"
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/resume-or-full":
                rng = self.headers.get("Range", "")
                if rng:
                    start = int(rng.split("=")[1].rstrip("-"))
                    if start >= len(_PAYLOAD):
                        self.send_response(416)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    body = _PAYLOAD[start:]
                    self.send_response(206)
                    self.send_header(
                        "Content-Range", f"bytes {start}-{len(_PAYLOAD) - 1}/{len(_PAYLOAD)}"
                    )
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(_PAYLOAD)))
                self.end_headers()
                self.wfile.write(_PAYLOAD)
            elif self.path == "/slow":
                self.send_response(200)
                self.send_header("Content-Length", str(len(_PAYLOAD) * 4))
                self.end_headers()
                try:
                    for _ in range(4):
                        self.wfile.write(_PAYLOAD)
                        self.wfile.flush()
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # 客户端取消下载时正常断开
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, *args):  # 静默测试输出
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


def test_download_file_writes_content_atomically(http_server, tmp_path):
    dest = tmp_path / "song.mp3"
    Downloader().download_file(f"{http_server}/ok", dest)

    assert dest.read_bytes() == _PAYLOAD
    assert not list(tmp_path.glob("*.part"))


def test_download_file_creates_parent_dirs(http_server, tmp_path):
    dest = tmp_path / "deep" / "nested" / "song.mp3"
    Downloader().download_file(f"{http_server}/ok", dest)
    assert dest.read_bytes() == _PAYLOAD


def test_download_file_reports_monotonic_progress(http_server, tmp_path):
    events: list[tuple[int, int]] = []
    Downloader().download_file(
        f"{http_server}/ok",
        tmp_path / "song.mp3",
        progress_cb=lambda received, total: events.append((received, total)),
    )

    assert events, "至少回调一次"
    assert all(total == len(_PAYLOAD) for _, total in events)
    received_seq = [received for received, _ in events]
    assert received_seq == sorted(received_seq)
    assert received_seq[-1] == len(_PAYLOAD)


def test_download_file_unknown_length_total_zero(http_server, tmp_path):
    events: list[tuple[int, int]] = []
    dest = tmp_path / "blob.bin"
    Downloader().download_file(
        f"{http_server}/nolen",
        dest,
        progress_cb=lambda received, total: events.append((received, total)),
    )

    assert dest.read_bytes() == b"hello"
    assert all(total == 0 for _, total in events)


def test_download_file_http_error_raises_and_cleans_up(http_server, tmp_path):
    dest = tmp_path / "song.mp3"
    with pytest.raises(DownloadError, match="404"):
        Downloader().download_file(f"{http_server}/missing", dest)

    assert not dest.exists()
    assert not list(tmp_path.glob("*.part"))


def test_download_file_pre_canceled_raises_immediately(http_server, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DownloadCanceled):
        Downloader().download_file(f"{http_server}/ok", tmp_path / "song.mp3", cancel=cancel)
    assert not list(tmp_path.iterdir())


def test_download_file_cancel_midway_cleans_part(http_server, tmp_path):
    cancel = threading.Event()
    dest = tmp_path / "song.mp3"

    def cancel_after_first_chunk(received: int, total: int) -> None:
        cancel.set()

    with pytest.raises(DownloadCanceled):
        Downloader().download_file(
            f"{http_server}/slow",
            dest,
            progress_cb=cancel_after_first_chunk,
            cancel=cancel,
        )

    assert not dest.exists()
    # 取消保留 .part: 重试时从断点续传
    assert (tmp_path / "song.mp3.part").exists()


def test_download_file_resumes_from_existing_part(http_server, tmp_path):
    dest = tmp_path / "song.mp3"
    part = tmp_path / "song.mp3.part"
    half = len(_PAYLOAD) // 2
    part.write_bytes(_PAYLOAD[:half])
    events: list[tuple[int, int]] = []

    # /resume 对无 Range 的请求返 500 -> 只有真正续传才能通过
    Downloader().download_file(
        f"{http_server}/resume",
        dest,
        progress_cb=lambda received, total: events.append((received, total)),
    )

    assert dest.read_bytes() == _PAYLOAD
    assert not part.exists()
    # 进度从断点起算, 总量为全量大小
    assert events[0][0] > half
    assert all(total == len(_PAYLOAD) for _, total in events)


def test_download_file_discards_stale_part_on_416(http_server, tmp_path):
    dest = tmp_path / "song.mp3"
    part = tmp_path / "song.mp3.part"
    part.write_bytes(b"x" * (len(_PAYLOAD) + 10))  # 比远端还大: 无效断点

    Downloader().download_file(f"{http_server}/resume-or-full", dest)

    assert dest.read_bytes() == _PAYLOAD
    assert not part.exists()


# ============================================================== embed_tags


def test_embed_tags_mp3_writes_id3_with_cover(tmp_path):
    from mutagen.id3 import ID3

    from quaverq.core.downloader import embed_tags

    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"\xff\xfb" + b"\x00" * 64)  # 裸 MP3 帧头占位即可, ID3 块前置写入
    cover = tmp_path / "song.jpg"
    cover.write_bytes(b"\xff\xd8FAKEJPEG")

    embed_tags(audio, title="晴天", artists=["周杰伦"], album="叶惠美", cover_path=cover)

    tags = ID3(audio)
    assert str(tags["TIT2"]) == "晴天"
    assert str(tags["TPE1"]) == "周杰伦"
    assert str(tags["TALB"]) == "叶惠美"
    apics = tags.getall("APIC")
    assert apics and apics[0].data == b"\xff\xd8FAKEJPEG"


def test_embed_tags_mp3_without_cover(tmp_path):
    from mutagen.id3 import ID3

    from quaverq.core.downloader import embed_tags

    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"\xff\xfb" + b"\x00" * 64)

    embed_tags(audio, title="稻香", artists=["周杰伦", "费玉清"], album="")

    tags = ID3(audio)
    assert str(tags["TIT2"]) == "稻香"
    assert "TALB" not in tags  # 空专辑不写空帧
    assert not tags.getall("APIC")


def test_embed_tags_invalid_flac_raises(tmp_path):
    # FLAC 容器要求合法头; 垃圾字节应抛错 (调用方按"非致命"吞掉)
    from quaverq.core.downloader import embed_tags

    audio = tmp_path / "song.flac"
    audio.write_bytes(b"NOT-A-FLAC")

    with pytest.raises(Exception):  # noqa: B017 - mutagen 抛自有 error 类型, 这里只关心会抛
        embed_tags(audio, title="x", artists=["y"])


def test_embed_tags_unknown_extension_noop(tmp_path):
    from quaverq.core.downloader import embed_tags

    audio = tmp_path / "song.xyz"
    audio.write_bytes(b"data")

    embed_tags(audio, title="x", artists=["y"])  # 不识别的扩展名静默跳过

    assert audio.read_bytes() == b"data"
