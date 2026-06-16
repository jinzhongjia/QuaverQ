"""DownloadController tests."""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PySide6.QtCore import Property, QObject, QSettings, Signal

from quaverq.bridge.download_controller import DownloadController, DownloadListModel
from quaverq.bridge.models import song_from_map
from quaverq.bridge.service_controller import ServiceController
from quaverq.bridge.settings_controller import SettingsController
from quaverq.core.download_store import DownloadRecord, DownloadStore
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


class _FakePlayer(QObject):
    onlineStreamActiveChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._online_stream_active = False

    @Property(bool, notify=onlineStreamActiveChanged)
    def onlineStreamActive(self) -> bool:
        return self._online_stream_active

    def set_online_stream_active(self, value: bool) -> None:
        if self._online_stream_active == value:
            return
        self._online_stream_active = value
        self.onlineStreamActiveChanged.emit()


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


def _make_controller(tmp_path, http_server, *, player_controller=None, **service_flags):
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
        store=DownloadStore(tmp_path / "downloads.json"),
        cover_url_builder=lambda album_mid: f"{http_server}/cover/{album_mid}",
        player_controller=player_controller,
    )
    return controller, service, settings_controller


async def test_download_song_produces_three_files(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    finished: list[str] = []
    controller.downloadFinished.connect(lambda message: finished.append(message))

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    music = tmp_path / "music"
    # 默认嵌入 ID3 标签: 音频本体字节在标签块之后
    assert (music / "周杰伦 - 晴天 [320K].mp3").read_bytes().endswith(_AUDIO)
    lrc = (music / "周杰伦 - 晴天 [320K].lrc").read_text(encoding="utf-8")
    assert "[00:00.00]第一行" in lrc
    assert "[ti:晴天]" in lrc
    assert (music / "周杰伦 - 晴天 [320K].jpg").read_bytes() == _COVER
    assert finished == ["已下载：晴天（MP3 320K）"]
    assert controller.downloadModel.task_at(0).status == "done"
    assert controller.activeCount == 0


async def test_download_uses_quality_extension(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server, song_url_quality="FLAC")

    await controller.download_song_async(_song_map(), "high")
    await controller.wait_idle()

    assert (tmp_path / "music" / "周杰伦 - 晴天 [无损].flac").exists()


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
    dest = tmp_path / "music" / "周杰伦 - 晴天 [320K].mp3"
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
    assert not (tmp_path / "music" / "周杰伦 - 晴天 [320K].mp3").exists()


async def test_lyric_failure_does_not_fail_task(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server, lyric_raises=True)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    music = tmp_path / "music"
    assert (music / "周杰伦 - 晴天 [320K].mp3").exists()
    assert not (music / "周杰伦 - 晴天 [320K].lrc").exists()
    assert controller.downloadModel.task_at(0).status == "done"


async def test_download_respects_lyric_and_cover_switches(tmp_path, http_server):
    controller, _service, settings_controller = _make_controller(tmp_path, http_server)
    settings_controller.setDownloadWithLyric(False)
    settings_controller.setDownloadWithCover(False)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    music = tmp_path / "music"
    assert (music / "周杰伦 - 晴天 [320K].mp3").exists()
    assert not (music / "周杰伦 - 晴天 [320K].lrc").exists()
    assert not (music / "周杰伦 - 晴天 [320K].jpg").exists()


async def test_download_queue_serializes_multiple_songs(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)

    await controller.download_song_async(_song_map("m1", "晴天"))
    await controller.download_song_async(_song_map("m2", "稻香"))
    await controller.wait_idle()

    music = tmp_path / "music"
    assert (music / "周杰伦 - 晴天 [320K].mp3").exists()
    assert (music / "周杰伦 - 稻香 [320K].mp3").exists()
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


async def test_worker_survives_unexpected_process_crash(tmp_path, http_server):
    """_process 裸露区抛未捕获异常时: 该任务转 failed, worker 不死, 队列继续推进."""
    controller, _service, _ = _make_controller(tmp_path, http_server)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    # 让第一个任务在 _process 的非 try 区段 (Path(self._download_directory())) 炸掉
    calls = {"n": 0}
    original = controller._download_directory  # noqa: SLF001

    def flaky_directory() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return original()

    controller._download_directory = flaky_directory  # noqa: SLF001

    await controller.download_song_async(_song_map("m1", "晴天"))
    await controller.download_song_async(_song_map("m2", "稻香"))
    await controller.wait_idle()

    model = controller.downloadModel
    first = model.task_at(0)
    assert first.status == "failed"
    assert first.error
    assert errors  # 用户能看到错误提示, 而不是行永远卡在"下载中"
    # 第二个任务不受影响, worker 继续跑完
    assert model.task_at(1).status == "done"
    assert (tmp_path / "music" / "周杰伦 - 稻香 [320K].mp3").exists()
    assert controller.activeCount == 0


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
    assert (music / "周杰伦 - 晴天 [320K].mp3").exists()
    assert (music / "周杰伦 - 稻香 [320K].mp3").exists()
    assert (music / "周杰伦 - 七里香 [320K].mp3").exists()
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
    assert (tmp_path / "music" / "周杰伦 - 晴天 [320K].mp3").read_bytes().endswith(_AUDIO)


async def test_download_embeds_id3_tags_into_mp3(tmp_path, http_server):
    from mutagen.id3 import ID3

    controller, _service, _ = _make_controller(tmp_path, http_server)

    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    audio = tmp_path / "music" / "周杰伦 - 晴天 [320K].mp3"
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

    audio = tmp_path / "music" / "周杰伦 - 晴天 [320K].mp3"
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


# ============================================================== 持久化 (阶段 8)


def test_model_exposes_cover_and_song_roles():
    model = DownloadListModel()
    model.append_task(DownloadTask(song=song_from_map(_song_map()), quality_preference="balanced"))
    role_names = {bytes(v).decode() for v in model.roleNames().values()}
    assert "coverUrl" in role_names
    assert "song" in role_names


async def test_download_persists_record(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    # 独立 store 读盘验证 (downloads.json 落在 tmp_path 根)
    store = DownloadStore(tmp_path / "downloads.json")
    store.load()
    rec = store.find("m1")
    assert rec is not None
    assert rec.song.name == "晴天"
    assert rec.path.endswith("周杰伦 - 晴天 [320K].mp3")
    assert rec.quality_label == "MP3_320"
    assert rec.size > 0


async def test_history_loaded_on_startup(tmp_path, http_server):
    c1, _s, _ = _make_controller(tmp_path, http_server)
    await c1.download_song_async(_song_map("m1", "晴天"))
    await c1.wait_idle()

    # 模拟重启: 同 tmp_path 新建 controller, 应从 downloads.json 加载历史
    c2, _s2, _ = _make_controller(tmp_path, http_server)
    model = c2.downloadModel
    assert model.rowCount() == 1
    task = model.task_at(0)
    assert task.status == "done"
    assert task.song.name == "晴天"
    assert task.dest_path.endswith("周杰伦 - 晴天 [320K].mp3")


async def test_local_path_for_returns_existing_file(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    path = controller.local_path_for("m1")
    assert path.endswith("周杰伦 - 晴天 [320K].mp3")
    assert Path(path).is_file()


async def test_local_path_for_empty_when_not_downloaded(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    assert controller.local_path_for("nope") == ""


async def test_local_path_for_empty_when_file_removed(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    Path(controller.local_path_for("m1")).unlink()  # 用户在外部删了文件
    assert controller.local_path_for("m1") == ""


# ============================================================== 失效标记 + 清理


def test_missing_status_text():
    from quaverq.bridge.download_controller import _STATUS_TEXT

    assert _STATUS_TEXT["missing"] == "文件已删除"


async def test_history_marks_missing_when_file_gone(tmp_path, http_server):
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(
        DownloadRecord(
            song=song_from_map(_song_map()),
            path=str(tmp_path / "gone.mp3"),
            quality_label="FLAC",
        )
    )
    controller, _service, _ = _make_controller(tmp_path, http_server)
    assert controller.downloadModel.task_at(0).status == "missing"


async def test_history_done_when_file_exists(tmp_path, http_server):
    real = tmp_path / "song.flac"
    real.write_bytes(b"x")
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(
        DownloadRecord(
            song=song_from_map(_song_map()),
            path=str(real),
            quality_label="FLAC",
        )
    )
    controller, _service, _ = _make_controller(tmp_path, http_server)
    assert controller.downloadModel.task_at(0).status == "done"


async def test_remove_task_clears_model_and_store(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    await controller.download_song_async(_song_map())
    await controller.wait_idle()
    assert controller.downloadModel.rowCount() == 1

    controller.removeTask(0)
    assert controller.downloadModel.rowCount() == 0
    store = DownloadStore(tmp_path / "downloads.json")
    store.load()
    assert store.find("m1") is None


async def test_remove_task_ignores_running_task(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    task = DownloadTask(
        song=song_from_map(_song_map()), quality_preference="balanced", status="running"
    )
    row = controller.downloadModel.append_task(task)
    controller.removeTask(row)
    assert controller.downloadModel.rowCount() == 1  # 进行中不直接移除


async def test_retry_missing_redownloads(tmp_path, http_server):
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(
        DownloadRecord(
            song=song_from_map(_song_map()),
            path=str(tmp_path / "music" / "gone.mp3"),
            quality_label="FLAC",
        )
    )
    controller, _service, _ = _make_controller(tmp_path, http_server)
    assert controller.downloadModel.task_at(0).status == "missing"

    controller.retryTask(0)
    await controller.wait_idle()

    task = controller.downloadModel.task_at(0)
    assert task.status == "done"
    assert Path(task.dest_path).is_file()


async def test_cancel_uses_mid_not_row(tmp_path, http_server):
    # _cancel_events 按 mid 存: 即便前面的行被移除导致 row 偏移, 取消仍命中正确任务
    controller, _service, _ = _make_controller(tmp_path, http_server)
    cancel_seen: list[str] = []

    # 注入一个永不结束的下载, 验证 cancelTask 能按 mid 找到事件
    import threading

    started = threading.Event()
    release = threading.Event()

    def _slow_download(url, dest, *, progress_cb=None, cancel=None):
        started.set()
        # 等取消信号或释放; 取消时抛 DownloadCanceled (与真实 Downloader 一致)
        while not release.wait(0.02):
            if cancel is not None and cancel.is_set():
                cancel_seen.append("canceled")
                from quaverq.core.downloader import DownloadCanceled

                raise DownloadCanceled
        from pathlib import Path as _P

        _P(dest).write_bytes(b"x")

    controller._downloader.download_file = _slow_download  # noqa: SLF001

    await controller.download_song_async(_song_map("m1", "晴天"))
    # 等下载线程真正开始
    for _ in range(200):
        if started.is_set():
            break
        await asyncio.sleep(0.02)

    controller.cancelTask(0)
    await controller.wait_idle()

    assert cancel_seen == ["canceled"]
    assert controller.downloadModel.task_at(0).status == "canceled"


async def test_download_waits_until_online_playback_idle(tmp_path, http_server):
    player = _FakePlayer()
    player.set_online_stream_active(True)
    controller, service, _ = _make_controller(tmp_path, http_server, player_controller=player)

    await controller.download_song_async(_song_map("m1", "晴天"))
    await asyncio.sleep(0.05)

    task = controller.downloadModel.task_at(0)
    assert task.status == "pending"
    assert service.url_calls == []

    player.set_online_stream_active(False)
    await controller.wait_idle()

    assert controller.downloadModel.task_at(0).status == "done"
    assert service.url_calls == [("m1", "balanced")]


async def test_cancel_pending_download_waiting_for_playback_unblocks_worker(tmp_path, http_server):
    player = _FakePlayer()
    player.set_online_stream_active(True)
    controller, service, _ = _make_controller(tmp_path, http_server, player_controller=player)

    await controller.download_song_async(_song_map("m1", "晴天"))
    await asyncio.sleep(0.05)

    controller.cancelTask(0)
    await controller.wait_idle()

    assert controller.downloadModel.task_at(0).status == "canceled"
    assert service.url_calls == []


async def test_waiting_download_survives_history_row_removal(tmp_path, http_server):
    player = _FakePlayer()
    player.set_online_stream_active(True)
    controller, service, _ = _make_controller(tmp_path, http_server, player_controller=player)
    history = DownloadTask(song=song_from_map(_song_map("old", "旧歌")), quality_preference="")
    history.status = "done"
    controller.downloadModel.append_task(history)

    await controller.download_song_async(_song_map("m1", "晴天"))
    await asyncio.sleep(0.05)
    controller.removeTask(0)

    player.set_online_stream_active(False)
    await controller.wait_idle()

    task = controller.downloadModel.task_at(0)
    assert task.song.mid == "m1"
    assert task.status == "done"
    assert service.url_calls == [("m1", "balanced")]


async def test_running_download_survives_history_row_removal(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    history = DownloadTask(song=song_from_map(_song_map("old", "旧歌")), quality_preference="")
    history.status = "done"
    controller.downloadModel.append_task(history)
    started = threading.Event()
    release = threading.Event()

    def _download_after_row_shift(url, dest, *, progress_cb=None, cancel=None):
        started.set()
        release.wait(5)
        if progress_cb is not None:
            progress_cb(10, 10)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"x")

    controller._downloader.download_file = _download_after_row_shift  # noqa: SLF001

    await controller.download_song_async(_song_map("m1", "晴天"))
    for _ in range(200):
        if started.is_set():
            break
        await asyncio.sleep(0.02)
    assert started.is_set()

    controller.removeTask(0)
    release.set()
    await controller.wait_idle()
    await asyncio.sleep(0)

    task = controller.downloadModel.task_at(0)
    assert task.song.mid == "m1"
    assert task.status == "done"
    assert task.received == 10
    assert task.total == 10


async def test_online_playback_preempts_active_download_and_requeues(tmp_path, http_server):
    player = _FakePlayer()
    controller, _service, _ = _make_controller(tmp_path, http_server, player_controller=player)
    started = threading.Event()
    canceled = threading.Event()
    release = threading.Event()
    audio_attempts = 0

    def _slow_then_finish(url, dest, *, progress_cb=None, cancel=None):
        nonlocal audio_attempts
        is_audio = "/audio" in url
        if is_audio:
            audio_attempts += 1
        if is_audio and audio_attempts == 1:
            started.set()
            while not release.wait(0.02):
                if cancel is not None and cancel.is_set():
                    canceled.set()
                    from quaverq.core.downloader import DownloadCanceled

                    raise DownloadCanceled
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"x")

    controller._downloader.download_file = _slow_then_finish  # noqa: SLF001

    await controller.download_song_async(_song_map("m1", "晴天"))
    for _ in range(200):
        if started.is_set():
            break
        await asyncio.sleep(0.02)
    assert started.is_set()

    player.set_online_stream_active(True)
    for _ in range(200):
        if canceled.is_set():
            break
        await asyncio.sleep(0.02)

    task = controller.downloadModel.task_at(0)
    assert canceled.is_set()
    assert task.status == "pending"

    player.set_online_stream_active(False)
    release.set()
    await controller.wait_idle()

    assert audio_attempts == 2
    assert controller.downloadModel.task_at(0).status == "done"


# ============================================================== UX: 即时反馈 / 聚合 / 防冲突


async def test_single_download_emits_enqueue_notice(tmp_path, http_server):
    # 点下载即时反馈: 入队就发 notice, 不必等完成 (大文件等待期不至于"点了没反应")
    controller, _service, _ = _make_controller(tmp_path, http_server)
    notices: list[str] = []
    controller.noticeRaised.connect(notices.append)

    await controller.download_song_async(_song_map())

    assert any("已加入下载" in n and "晴天" in n for n in notices)


async def test_batch_completion_aggregates_to_single_message(tmp_path, http_server):
    # 批量完成只发一次聚合提示, 不每首刷屏
    controller, _service, _ = _make_controller(tmp_path, http_server)
    finished: list[str] = []
    controller.downloadFinished.connect(finished.append)

    await controller.download_songs_async(
        [
            song_from_map(_song_map("m1", "晴天")),
            song_from_map(_song_map("m2", "稻香")),
            song_from_map(_song_map("m3", "七里香")),
        ]
    )
    await controller.wait_idle()

    assert finished == ["已下载 3 首"]


async def test_different_quality_no_filename_collision(tmp_path, http_server):
    # 同一首下两种音质 (都 mp3): 文件名带音质后缀, 不互相误判"已存在"跳过
    controller, service, _ = _make_controller(tmp_path, http_server, song_url_quality="MP3_128")
    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    service.song_url_quality = "MP3_320"
    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    music = tmp_path / "music"
    assert (music / "周杰伦 - 晴天 [128K].mp3").exists()
    assert (music / "周杰伦 - 晴天 [320K].mp3").exists()
    # 两次都真下载了 (没有第二次被跳过)
    assert {controller.downloadModel.task_at(i).status for i in range(2)} == {"done"}


# ============================================================== 删除已下载音乐


async def test_delete_task_removes_files_record_and_row(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    await controller.download_song_async(_song_map())
    await controller.wait_idle()

    music = tmp_path / "music"
    audio = music / "周杰伦 - 晴天 [320K].mp3"
    lrc = music / "周杰伦 - 晴天 [320K].lrc"
    jpg = music / "周杰伦 - 晴天 [320K].jpg"
    assert audio.exists() and lrc.exists() and jpg.exists()

    controller.deleteTask(0)

    # 音频 + 旁置歌词/封面全删, 记录与列表行清除
    assert not audio.exists()
    assert not lrc.exists()
    assert not jpg.exists()
    assert controller.downloadModel.rowCount() == 0
    store = DownloadStore(tmp_path / "downloads.json")
    store.load()
    assert store.find("m1") is None


async def test_delete_task_ignores_running(tmp_path, http_server):
    controller, _service, _ = _make_controller(tmp_path, http_server)
    task = DownloadTask(
        song=song_from_map(_song_map()), quality_preference="balanced", status="running"
    )
    row = controller.downloadModel.append_task(task)
    controller.deleteTask(row)
    assert controller.downloadModel.rowCount() == 1  # 进行中不删


async def test_delete_task_tolerates_already_gone_files(tmp_path, http_server):
    # 文件已被外部删除 (missing) 时, deleteTask 仍清记录 + 行, 不抛
    store = DownloadStore(tmp_path / "downloads.json")
    store.add(
        DownloadRecord(
            song=song_from_map(_song_map()),
            path=str(tmp_path / "music" / "gone.mp3"),
            quality_label="FLAC",
        )
    )
    controller, _service, _ = _make_controller(tmp_path, http_server)
    assert controller.downloadModel.task_at(0).status == "missing"

    controller.deleteTask(0)

    assert controller.downloadModel.rowCount() == 0
    store2 = DownloadStore(tmp_path / "downloads.json")
    store2.load()
    assert store2.find("m1") is None
