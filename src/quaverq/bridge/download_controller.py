"""QML-facing music download management.

队列 + 单 worker 串行下载 (并发 1: 避免 vkey/CDN 风控, 也不与播放抢带宽);
每首产出 音频 + .lrc 歌词 + .jpg 封面 三件套, 歌词/封面失败不致命.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices
from qasync import asyncSlot

from quaverq.core.downloader import (
    DownloadCanceled,
    Downloader,
    DownloadTask,
    embed_tags,
    quality_extension,
    sanitize_filename,
)
from quaverq.core.lyric import to_lrc
from quaverq.core.models import Song
from quaverq.core.service import cover_url_for

from .error_utils import log_bridge_error
from .models import SongListModel, song_from_map

if TYPE_CHECKING:
    from .service_controller import ServiceController
    from .settings_controller import SettingsController

logger = logging.getLogger(__name__)

_QUALITY_PREFERENCES = {"standard", "balanced", "high", "master"}
_COVER_SIZE = 500
# 进度回调节流: 每收到 ~256KB 才往主线程发一次 model 更新, 防 UI 刷爆
_PROGRESS_EMIT_STEP = 256 * 1024

_QUALITY_TEXT = {
    "MASTER": "臻品母带",
    "ATMOS_2": "臻品全景声",
    "FLAC": "无损 FLAC",
    "MP3_320": "MP3 320K",
    "OGG_192": "OGG 192K",
    "MP3_128": "MP3 128K",
}

_STATUS_TEXT = {
    "pending": "等待中",
    "running": "下载中",
    "done": "已完成",
    "exists": "已存在",
    "failed": "失败",
    "canceled": "已取消",
}


class DownloadListModel(QAbstractListModel):
    """下载任务列表 model, role 直接供 QML delegate 消费."""

    TitleRole = Qt.ItemDataRole.UserRole + 1
    SingersRole = Qt.ItemDataRole.UserRole + 2
    StatusRole = Qt.ItemDataRole.UserRole + 3
    StatusTextRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    QualityTextRole = Qt.ItemDataRole.UserRole + 6
    ErrorTextRole = Qt.ItemDataRole.UserRole + 7
    DestPathRole = Qt.ItemDataRole.UserRole + 8

    countChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tasks: list[DownloadTask] = []

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._tasks)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._tasks)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._tasks)):
            return None
        task = self._tasks[index.row()]
        if role == self.TitleRole or role == Qt.ItemDataRole.DisplayRole:
            return task.song.name
        if role == self.SingersRole:
            return " / ".join(s.name for s in task.song.singers)
        if role == self.StatusRole:
            return task.status
        if role == self.StatusTextRole:
            return _STATUS_TEXT.get(task.status, task.status)
        if role == self.ProgressRole:
            if task.status in {"done", "exists"}:
                return 1.0
            if task.total > 0:
                return min(1.0, task.received / task.total)
            # 长度未知: running 给 -1 (QML 显示不确定进度), 其他 0
            return -1.0 if task.status == "running" else 0.0
        if role == self.QualityTextRole:
            return _QUALITY_TEXT.get(task.quality_label, task.quality_label)
        if role == self.ErrorTextRole:
            return task.error
        if role == self.DestPathRole:
            return task.dest_path
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.TitleRole: QByteArray(b"title"),
            self.SingersRole: QByteArray(b"singers"),
            self.StatusRole: QByteArray(b"status"),
            self.StatusTextRole: QByteArray(b"statusText"),
            self.ProgressRole: QByteArray(b"progress"),
            self.QualityTextRole: QByteArray(b"qualityText"),
            self.ErrorTextRole: QByteArray(b"errorText"),
            self.DestPathRole: QByteArray(b"destPath"),
        }

    # ---- 任务操作 (行号即任务 id; 列表只增不删, 行号稳定) ----

    def append_task(self, task: DownloadTask) -> int:
        row = len(self._tasks)
        self.beginInsertRows(QModelIndex(), row, row)
        self._tasks.append(task)
        self.endInsertRows()
        self.countChanged.emit()
        return row

    def task_at(self, row: int) -> DownloadTask | None:
        if 0 <= row < len(self._tasks):
            return self._tasks[row]
        return None

    def set_status(self, row: int, status: str, *, error: str = "") -> None:
        task = self.task_at(row)
        if task is None:
            return
        task.status = status
        task.error = error
        self._emit_row_changed(row)

    def set_result(self, row: int, *, quality_label: str, dest_path: str) -> None:
        task = self.task_at(row)
        if task is None:
            return
        task.quality_label = quality_label
        task.dest_path = dest_path
        self._emit_row_changed(row)

    def set_progress(self, row: int, received: int, total: int) -> None:
        task = self.task_at(row)
        if task is None:
            return
        task.received = received
        task.total = total
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self.ProgressRole])

    def active_count(self) -> int:
        return sum(1 for task in self._tasks if task.status in {"pending", "running"})

    def has_active_for(self, mid: str) -> bool:
        """同 mid 的任务已在排队/下载中 (防重复入队; done/failed 不算, 允许重下/重试)."""
        return any(
            task.song.mid == mid and task.status in {"pending", "running"} for task in self._tasks
        )

    def _emit_row_changed(self, row: int) -> None:
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [])


class DownloadController(QObject):
    """歌曲下载编排: 入队 → 取 vkey URL → 流式落盘 → 歌词/封面旁置."""

    activeCountChanged = Signal()
    downloadFinished = Signal(str, str)  # (歌名, 实际命中音质显示文本)
    errorRaised = Signal(str)
    noticeRaised = Signal(str)

    def __init__(
        self,
        service_controller: ServiceController,
        settings_controller: SettingsController,
        *,
        downloader: Downloader | None = None,
        cover_url_builder: Callable[[str], str] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._settings_controller = settings_controller
        self._downloader = downloader or Downloader()
        self._cover_url_builder = cover_url_builder or (
            lambda album_mid: cover_url_for(album_mid, _COVER_SIZE)
        )
        self._model = DownloadListModel(self)
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._cancel_events: dict[int, threading.Event] = {}
        self._closing = False

    # ------------------------------------------------------------------ QML API

    @Property(QObject, constant=True)
    def downloadModel(self) -> DownloadListModel:
        return self._model

    @Property(int, notify=activeCountChanged)
    def activeCount(self) -> int:
        return self._model.active_count()

    @asyncSlot("QVariant")
    async def downloadSong(self, song_data: Any) -> None:
        """单曲下载, 用设置里的默认下载音质."""
        await self.download_song_async(song_data)

    @asyncSlot("QVariant", str)
    async def downloadSongWithQuality(self, song_data: Any, quality: str) -> None:
        """单曲下载, 显式指定三档 profile 之一 (standard/balanced/high)."""
        await self.download_song_async(song_data, quality)

    @asyncSlot(QObject)
    async def downloadFromModel(self, model: QObject) -> None:
        """批量下载一个 SongListModel 的全部歌曲 (详情页"下载全部"), 用默认音质."""
        await self.download_songs_async(self._songs_from_model(model))

    @Slot(int)
    def retryTask(self, row: int) -> None:
        """失败/已取消的任务重新入队下载."""
        task = self._model.task_at(row)
        if task is None or task.status not in {"failed", "canceled"}:
            return
        task.received = 0
        task.total = 0
        self._model.set_status(row, "pending")
        self._queue.put_nowait(row)
        self.activeCountChanged.emit()
        self._ensure_worker()

    @Slot(int)
    def cancelTask(self, row: int) -> None:
        task = self._model.task_at(row)
        if task is None:
            return
        if task.status == "pending":
            self._model.set_status(row, "canceled")
            self.activeCountChanged.emit()
        elif task.status == "running":
            event = self._cancel_events.get(row)
            if event is not None:
                event.set()

    @Slot()
    def openDownloadDirectory(self) -> None:
        directory = Path(self._download_directory())
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.errorRaised.emit(f"无法打开下载目录：{exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    # ------------------------------------------------------------------ 内部编排

    async def download_song_async(self, song_data: Any, quality: str = "") -> None:
        song = song_from_map(song_data if isinstance(song_data, Mapping | Song) else {})
        if not song.mid:
            self.errorRaised.emit("无法下载：歌曲数据不完整")
            return
        if self._model.has_active_for(song.mid):
            self.noticeRaised.emit(f"《{song.name}》已在下载队列中")
            return
        preference = quality if quality in _QUALITY_PREFERENCES else self._default_quality()
        row = self._model.append_task(DownloadTask(song=song, quality_preference=preference))
        self._queue.put_nowait(row)
        self.activeCountChanged.emit()
        self._ensure_worker()

    async def download_songs_async(self, songs: list[Song]) -> None:
        """批量入队 (默认音质); 跳过缺 mid 与已在队列中的曲目."""
        queued = 0
        for song in songs:
            if not song.mid or self._model.has_active_for(song.mid):
                continue
            row = self._model.append_task(
                DownloadTask(song=song, quality_preference=self._default_quality())
            )
            self._queue.put_nowait(row)
            queued += 1
        if not queued:
            self.noticeRaised.emit("没有可下载的歌曲")
            return
        self.activeCountChanged.emit()
        self.noticeRaised.emit(f"已加入 {queued} 首歌曲到下载队列")
        self._ensure_worker()

    @staticmethod
    def _songs_from_model(model: QObject) -> list[Song]:
        if isinstance(model, SongListModel):
            return list(model.songs())
        return []

    async def wait_idle(self) -> None:
        """等当前队列全部处理完 (测试 / 退出前用)."""
        while self._worker is not None and not self._worker.done():
            try:
                await asyncio.shield(self._worker)
            except Exception:
                logger.exception("download worker crashed")

    def shutdown(self) -> None:
        """退出序列调用: 置位所有取消事件, 让下载线程尽快退出并清掉 .part."""
        self._closing = True
        for event in self._cancel_events.values():
            event.set()

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.ensure_future(self._drain_queue())

    async def _drain_queue(self) -> None:
        while not self._closing:
            try:
                row = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            task = self._model.task_at(row)
            if task is None or task.status != "pending":
                continue  # 已被取消等
            await self._process(row, task)

    async def _process(self, row: int, task: DownloadTask) -> None:
        song = task.song
        self._model.set_status(row, "running")
        self.activeCountChanged.emit()

        try:
            song_url = await self._service_controller.get_song_url(
                song, quality_preference=task.quality_preference
            )
        except Exception as exc:
            self._fail(row, log_bridge_error(logger, f"download url {song.name}", exc))
            return
        if song_url is None or not song_url.url:
            self._fail(row, f"《{song.name}》无版权或不可下载")
            return

        quality_label = song_url.quality or ""
        dest = Path(self._download_directory()) / (
            f"{self._file_stem(song)}.{quality_extension(quality_label)}"
        )
        self._model.set_result(row, quality_label=quality_label, dest_path=str(dest))

        if dest.exists():
            self._model.set_status(row, "exists")
            self.activeCountChanged.emit()
            self.noticeRaised.emit(f"已存在，跳过下载:{dest.name}")
            return

        cancel = threading.Event()
        self._cancel_events[row] = cancel
        loop = asyncio.get_running_loop()
        last_emit = 0

        def progress_cb(received: int, total: int) -> None:
            # 跑在 to_thread 的下载线程; 节流后转主线程更新 model
            nonlocal last_emit
            if received - last_emit < _PROGRESS_EMIT_STEP and received != total:
                return
            last_emit = received
            loop.call_soon_threadsafe(self._model.set_progress, row, received, total)

        try:
            await asyncio.to_thread(
                self._downloader.download_file,
                song_url.url,
                dest,
                progress_cb=progress_cb,
                cancel=cancel,
            )
        except DownloadCanceled:
            self._model.set_status(row, "canceled")
            self.activeCountChanged.emit()
            return
        except Exception as exc:
            self._fail(row, log_bridge_error(logger, f"download audio {song.name}", exc))
            return
        finally:
            self._cancel_events.pop(row, None)

        # 歌词 / 封面 / 标签都是附加产物: 单项失败不影响任务成败
        await self._save_lyric(song, dest)
        await self._save_cover(song, dest)
        await self._embed_tags(song, dest)

        self._model.set_status(row, "done")
        self.activeCountChanged.emit()
        self.downloadFinished.emit(song.name, _QUALITY_TEXT.get(quality_label, quality_label))

    async def _save_lyric(self, song: Song, audio_dest: Path) -> None:
        if not bool(getattr(self._settings_controller, "downloadWithLyric", True)):
            return
        try:
            lyric = await self._service_controller.get_lyric(song.mid, with_translation=True)
            text = to_lrc(
                lyric,
                title=song.name,
                artist="、".join(s.name for s in song.singers),
                album=song.album_name,
            )
            if not text:
                return
            path = audio_dest.with_suffix(".lrc")
            await asyncio.to_thread(path.write_text, text, encoding="utf-8")
        except Exception as exc:
            log_bridge_error(logger, f"download lyric {song.name}", exc)

    async def _save_cover(self, song: Song, audio_dest: Path) -> None:
        if not bool(getattr(self._settings_controller, "downloadWithCover", True)):
            return
        url = self._cover_url_builder(song.album_mid) if song.album_mid else ""
        if not url:
            return
        try:
            await asyncio.to_thread(
                self._downloader.download_file, url, audio_dest.with_suffix(".jpg")
            )
        except Exception as exc:
            log_bridge_error(logger, f"download cover {song.name}", exc)

    async def _embed_tags(self, song: Song, audio_dest: Path) -> None:
        if not bool(getattr(self._settings_controller, "downloadEmbedTags", True)):
            return
        cover_path = audio_dest.with_suffix(".jpg")
        try:
            await asyncio.to_thread(
                embed_tags,
                audio_dest,
                title=song.name,
                artists=[s.name for s in song.singers],
                album=song.album_name,
                cover_path=cover_path if cover_path.is_file() else None,
            )
        except Exception as exc:
            # CDN 偶发坏文件 / 容器头异常时标签写不进去, 不影响音频本体
            log_bridge_error(logger, f"embed tags {song.name}", exc)

    def _fail(self, row: int, message: str) -> None:
        self._model.set_status(row, "failed", error=message)
        self.activeCountChanged.emit()
        self.errorRaised.emit(message)

    @staticmethod
    def _file_stem(song: Song) -> str:
        singers = "、".join(s.name for s in song.singers)
        raw = f"{singers} - {song.name}" if singers else song.name
        return sanitize_filename(raw)

    def _download_directory(self) -> str:
        return str(getattr(self._settings_controller, "downloadDirectory", "") or "")

    def _default_quality(self) -> str:
        value = str(getattr(self._settings_controller, "downloadQuality", "balanced") or "")
        return value if value in _QUALITY_PREFERENCES else "balanced"
