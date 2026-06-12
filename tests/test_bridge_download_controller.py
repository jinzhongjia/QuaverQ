"""DownloadController tests."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtCore import QSettings

from quaverq.bridge.download_controller import DownloadController
from quaverq.bridge.models import song_from_map
from quaverq.bridge.service_controller import ServiceController
from quaverq.bridge.settings_controller import SettingsController
from quaverq.core.downloader import DownloadTask
from quaverq.core.models import Lyric, LyricLine, SongUrl

_AUDIO = b"FAKE-AUDIO" * 100
_COVER = b"FAKE-JPEG" * 10


@pytest.fixture
def http_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 约定命名
            if self.path.startswith("/audio"):
                body = _AUDIO
            elif self.path.startswith("/cover"):
                body = _COVER
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # 静默测试输出
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


class _FakeService:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.connected = False
        self.is_authenticated = True
        self.song_url_quality = "MP3_320"
        self.song_url_none = False
        self.lyric_raises = False
        self.audio_path = "/audio"
        self.url_calls: list[tuple[str, str]] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_song_url(self, song, *, quality_preference):
        self.url_calls.append((song.mid, quality_preference))
        if self.song_url_none:
            return None
        return SongUrl(
            mid=song.mid,
            url=f"{self.base_url}{self.audio_path}/{song.mid}",
            quality=self.song_url_quality,
        )

    async def get_lyric(self, mid, *, with_translation=True):
        if self.lyric_raises:
            raise RuntimeError("lyric backend down")
        return Lyric(mid=mid, lines=[LyricLine(timestamp_ms=0, text="第一行")])


def _song_map(mid: str = "m1", name: str = "晴天") -> dict:
    return {
        "mid": mid,
        "name": name,
        "singers": [{"mid": "s1", "name": "周杰伦", "avatarUrl": ""}],
        "singerNames": ["周杰伦"],
        "albumMid": "alb1",
        "albumName": "叶惠美",
        "coverUrl": "",
        "duration": 269,
        "payPlay": 0,
        "mediaMid": "",
        "id": 1,
    }


def _make_controller(tmp_path, http_server, **service_flags):
    service = _FakeService(http_server)
    for key, value in service_flags.items():
        setattr(service, key, value)
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    settings_controller = SettingsController(settings=settings)
    settings_controller.setDownloadDirectory(str(tmp_path / "music"))
    controller = DownloadController(
        service_controller,
        settings_controller,
        cover_url_builder=lambda album_mid: f"{http_server}/cover/{album_mid}",
    )
    return controller, service, settings_controller


async def test_download_song_produces_three_files(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    finished: list[tuple[str, str]] = []
    controller.downloadFinished.connect(lambda name, quality: finished.append((name, quality)))

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    music = tmp_path / "music"
    # 默认嵌入 ID3 标签: 音频本体字节在标签块之后
    assert (music / "周杰伦 - 晴天.mp3").read_bytes().endswith(_AUDIO)
    lrc = (music / "周杰伦 - 晴天.lrc").read_text(encoding="utf-8")
    assert "[00:00.00]第一行" in lrc
    assert "[ti:晴天]" in lrc
    assert (music / "周杰伦 - 晴天.jpg").read_bytes() == _COVER
    assert finished == [("晴天", "MP3 320K")]
    assert controller.downloadModel.task_at(0).status == "done"
    assert controller.activeCount == 0


async def test_download_uses_quality_extension(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server, song_url_quality="FLAC")

    await controller.download_song_async(_song_map(), "high")
    await controller.wait_idle()

    assert (tmp_path / "music" / "周杰伦 - 晴天.flac").exists()


async def test_download_passes_quality_preference(tmp_path, http_server):
    controller, service, settings_controller = _make_controller(tmp_path, http_server)
    settings_controller.setDownloadQuality("standard")

    # 显式档位优先; 不传则用设置默认
    await controller.download_song_async(_song_map("m1"), "high")
    await controller.download_song_async(_song_map("m2", "稻香"))
    await controller.wait_idle()

    assert service.url_calls == [("m1", "high"), ("m2", "standard")]


async def test_download_skips_existing_file(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    notices: list[str] = []
    controller.noticeRaised.connect(notices.append)
    dest = tmp_path / "music" / "周杰伦 - 晴天.mp3"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"old")

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    assert dest.read_bytes() == b"old"  # 不覆盖
    assert controller.downloadModel.task_at(0).status == "exists"
    assert notices


async def test_download_no_url_marks_failed(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server, song_url_none=True)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    task = controller.downloadModel.task_at(0)
    assert task.status == "failed"
    assert task.error
    assert errors


async def test_download_http_error_marks_failed(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server, audio_path="/missing")
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    assert controller.downloadModel.task_at(0).status == "failed"
    assert errors
    assert not (tmp_path / "music" / "周杰伦 - 晴天.mp3").exists()


async def test_lyric_failure_does_not_fail_task(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server, lyric_raises=True)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    music = tmp_path / "music"
    assert (music / "周杰伦 - 晴天.mp3").exists()
    assert not (music / "周杰伦 - 晴天.lrc").exists()
    assert controller.downloadModel.task_at(0).status == "done"


async def test_download_respects_lyric_and_cover_switches(tmp_path, http_server):
    controller, _service, settings_controller = _make_controller(tmp_path, http_server)
    settings_controller.setDownloadWithLyric(False)
    settings_controller.setDownloadWithCover(False)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    music = tmp_path / "music"
    assert (music / "周杰伦 - 晴天.mp3").exists()
    assert not (music / "周杰伦 - 晴天.lrc").exists()
    assert not (music / "周杰伦 - 晴天.jpg").exists()


async def test_download_queue_serializes_multiple_songs(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)

    await controller.download_song_async(_song_map("m1", "晴天"))
    await controller.download_song_async(_song_map("m2", "稻香"))
    await controller.wait_idle()

    music = tmp_path / "music"
    assert (music / "周杰伦 - 晴天.mp3").exists()
    assert (music / "周杰伦 - 稻香.mp3").exists()
    model = controller.downloadModel
    assert model.rowCount() == 2
    assert {model.task_at(i).status for i in range(2)} == {"done"}


async def test_download_invalid_song_data_raises_error_signal(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.download_song_async({"name": "无 mid"})
    await controller.wait_idle()

    assert errors
    assert controller.downloadModel.rowCount() == 0


async def test_cancel_pending_task_skips_processing(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)

    # 直接往 model 塞 pending 行再取消, 不经 worker (worker 未启动)
    task = DownloadTask(song=song_from_map(_song_map("m9", "九首")), quality_preference="balanced")
    row = controller.downloadModel.append_task(task)
    controller.cancelTask(row)

    assert controller.downloadModel.task_at(row).status == "canceled"


async def test_download_songs_batch_enqueues_all(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    notices: list[str] = []
    controller.noticeRaised.connect(notices.append)
    songs = [
        song_from_map(_song_map("m1", "晴天")),
        song_from_map(_song_map("m2", "稻香")),
        song_from_map(_song_map("m3", "七里香")),
    ]

    await controller.download_songs_async(songs)
    await controller.wait_idle()

    music = tmp_path / "music"
    assert (music / "周杰伦 - 晴天.mp3").exists()
    assert (music / "周杰伦 - 稻香.mp3").exists()
    assert (music / "周杰伦 - 七里香.mp3").exists()
    assert notices  # "已加入 N 首" 提示
    assert controller.downloadModel.rowCount() == 3


async def test_download_skips_song_already_queued(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    notices: list[str] = []
    controller.noticeRaised.connect(notices.append)
    # 预放一个同 mid 的 pending 行 (模拟已在队列中)
    task = DownloadTask(song=song_from_map(_song_map("m1", "晴天")), quality_preference="balanced")
    controller.downloadModel.append_task(task)

    await controller.download_song_async(_song_map("m1", "晴天"))

    assert controller.downloadModel.rowCount() == 1  # 没有新增行
    assert notices


async def test_retry_failed_task_redownloads(tmp_path, http_server):
    controller, service, _ = _make_controller(tmp_path, http_server, audio_path="/missing")

    await controller.download_song_async(_song_map())
    await controller.wait_idle()
    assert controller.downloadModel.task_at(0).status == "failed"

    service.audio_path = "/audio"  # "网络恢复"
    controller.retryTask(0)
    await controller.wait_idle()

    task = controller.downloadModel.task_at(0)
    assert task.status == "done"
    assert task.error == ""
    assert (tmp_path / "music" / "周杰伦 - 晴天.mp3").read_bytes().endswith(_AUDIO)


async def test_download_embeds_id3_tags_into_mp3(tmp_path, http_server):
    from mutagen.id3 import ID3

    controller, _service, _ = _make_controller(tmp_path, http_server)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    audio = tmp_path / "music" / "周杰伦 - 晴天.mp3"
    tags = ID3(audio)
    assert str(tags["TIT2"]) == "晴天"
    assert str(tags["TPE1"]) == "周杰伦"
    assert str(tags["TALB"]) == "叶惠美"
    apics = tags.getall("APIC")
    assert apics and apics[0].data == _COVER  # 旁置封面同时内嵌


async def test_download_embed_tags_can_be_disabled(tmp_path, http_server):
    from mutagen.id3 import ID3, ID3NoHeaderError

    controller, _service, settings_controller = _make_controller(tmp_path, http_server)
    settings_controller.setDownloadEmbedTags(False)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    audio = tmp_path / "music" / "周杰伦 - 晴天.mp3"
    assert audio.read_bytes() == _AUDIO  # 原始字节未被改写
    try:
        ID3(audio)
        raise AssertionError("不应有 ID3 块")
    except ID3NoHeaderError:
        pass


async def test_retry_ignores_done_task(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()
    assert controller.downloadModel.task_at(0).status == "done"

    controller.retryTask(0)
    await controller.wait_idle()

    assert controller.downloadModel.task_at(0).status == "done"
    assert controller.downloadModel.rowCount() == 1
