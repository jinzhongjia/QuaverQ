"""Player QObject exposed to QML."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QMediaPlayer
from qasync import asyncSlot

from quaverq.core.models import Song, SongUrl
from quaverq.core.queue import PlayMode, PlayQueue
from quaverq.core.state import SessionState

from .error_utils import log_bridge_error
from .models import SongListModel, song_from_map, song_to_map
from .service_controller import ServiceController

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .settings_controller import SettingsController


_MODE_TO_NAME = {
    PlayMode.SEQUENCE: "sequence",
    PlayMode.REPEAT_ALL: "repeat_all",
    PlayMode.REPEAT_ONE: "repeat_one",
    PlayMode.SHUFFLE: "shuffle",
}
_NAME_TO_MODE = {value: key for key, value in _MODE_TO_NAME.items()}

# 这些媒体错误多为瞬态 (CDN 偶发 401 / 网络抖动 / vkey 边缘节点延迟), 重取链 (现签新 vkey)
# 通常即恢复; FormatError 等解码类错误重试无意义, 不在此列.
_RETRYABLE_MEDIA_ERRORS = frozenset(
    {
        QMediaPlayer.Error.ResourceError.value,
        QMediaPlayer.Error.NetworkError.value,
        QMediaPlayer.Error.AccessDeniedError.value,
    }
)
_MAX_MEDIA_RETRIES = 1
# 流末尾解码错误豁免窗口: QQ CDN 的音频文件 (尤其 FLAC) 尾部常带坏帧, 播到末尾时
# QMediaPlayer emit FormatError, 但歌已实际播完 (EndOfMedia 随后 ~0.4s 接管切歌).
# position 落在 duration 最后这段内的 FormatError 视为"正常播完", 静默忽略, 不误报
# "播放失败" (见 handle_media_error_async). 取 5s 容差: 覆盖坏帧位置波动 + position
# 回传滞后, 又不至于把末尾前的真损坏也吞掉.
_END_OF_STREAM_TOLERANCE_MS = 5000


class PlayerController(QObject):
    """QML-facing playback state and command controller."""

    currentSongChanged = Signal()
    currentIndexChanged = Signal()
    sourceUrlChanged = Signal()
    playbackStateChanged = Signal()
    positionMsChanged = Signal()
    durationMsChanged = Signal()
    volumeChanged = Signal()
    mutedChanged = Signal()
    modeChanged = Signal()
    queueChanged = Signal()
    loadingChanged = Signal()
    errorMessageChanged = Signal()
    errorRaised = Signal(str)
    # 非错误级轻提示 (Snackbar info): 如自动跳过无版权曲目
    noticeRaised = Signal(str)

    playRequested = Signal()
    pauseRequested = Signal()
    stopRequested = Signal()
    seekRequested = Signal(int)
    # 切歌淡出 (issue #11): 参数为淡出时长 ms, QML 把 fadeFactor 动画到 0;
    # 淡入由 QML 在转入 PlayingState 时自治, 无需 Python 信号
    fadeOutRequested = Signal(int)
    queueSourceChanged = Signal()
    # 队列自然播完信号: 参数为 source 标识 (e.g. "daily"), 由订阅方决定是否续接
    queueExhausted = Signal(str)

    # 连续自动跳过上限 (服务端拒发场景), 见 _load_current
    _URL_FAILURE_STREAK_LIMIT = 5

    def __init__(
        self,
        service_controller: ServiceController,
        settings_controller: SettingsController | None = None,
        session_state: SessionState | None = None,
        stream_proxy: Any = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_controller = service_controller
        self._settings_controller = settings_controller
        self._session_state = session_state
        self._stream_proxy = stream_proxy
        # 本地优先播放: mid -> 已下载且文件仍在的本地路径 (or "")。由 DownloadController
        # 提供, 延迟注入 (set_local_resolver) 避免与其创建顺序耦合。
        self._local_resolver: Callable[[str], str] | None = None
        self._queue = PlayQueue()
        self._queue_model = SongListModel(self)
        self._source_url = ""
        self._playback_state = "stopped"
        self._position_ms = 0
        self._duration_ms = 0
        self._volume = 0.8
        # 静音是独立标志 (不清零 volume): 恢复时天然回到原音量; 不随会话快照持久化
        self._muted = False
        self._loading = False
        self._error_message = ""
        self._load_generation = 0
        # 瞬态媒体错误 (CDN 401 等) 的自动重试: 按当前曲 mid 计数, 成功播放清零
        self._media_retry_count = 0
        self._media_retry_mid = ""
        # 服务端拒发 (vkey 104003 无版权等) 的连续自动跳过计数: 防全队列不可播时
        # REPEAT_ALL 绕圈无限空转, 到上限停下报错; 任一首成功取链即清零
        self._url_failure_streak = 0
        # issue #11 Stage A2: 起播稳定后后台预取下一首链接, 切歌时免 vkey 往返.
        # 缓存单条 (mid, 音质偏好, SongUrl); 消费即清, 失配即弃.
        self._prefetched: tuple[str, str, SongUrl] | None = None
        self._prefetch_task: asyncio.Task[None] | None = None
        self._prefetch_handle: asyncio.TimerHandle | None = None
        # 延迟到起播稳定后再预取, 避免与当前曲起播缓冲争带宽; 测试注 0 立即执行
        self._prefetch_delay_s: float = 5.0
        # 当前挂在播放器上的曲 mid (sourceUrl 对应); REPEAT_ONE EOS 短路判据
        self._loaded_mid = ""
        # 切歌淡出窗口内冻结 QML 进度回传: UI 已显示新歌, 不让旧歌 (还在响)
        # 的 position 把进度条拽回去 (issue #11 Stage C2)
        self._suppress_position_updates = False
        # 加载/淡出窗口内的暂停意图: fade 淡出 sleep 期间用户按暂停, 醒来后的
        # playRequested 不能覆盖它 (review 发现). play() 清, 新 load 重置.
        self._pause_pending = False
        self._restore_session_snapshot()

    def set_local_resolver(self, resolver: Callable[[str], str] | None) -> None:
        """注入本地文件解析器 (mid -> 本地路径 or "")，供本地优先播放; 延迟注入。"""
        self._local_resolver = resolver

    def _resolve_local(self, mid: str) -> str:
        """查已下载的本地文件路径; 无解析器 / 未命中 / 异常都返 "" (回退在线)。"""
        if self._local_resolver is None or not mid:
            return ""
        try:
            return self._local_resolver(mid) or ""
        except Exception:
            logger.warning("本地文件解析失败 mid=%s", mid)
            return ""

    @Property("QVariant", notify=currentSongChanged)
    def currentSong(self) -> dict[str, Any]:
        song = self._queue.current()
        return song_to_map(song) if song else {}

    @Property(int, notify=currentIndexChanged)
    def currentIndex(self) -> int:
        return self._queue.current_index

    @Property(str, notify=sourceUrlChanged)
    def sourceUrl(self) -> str:
        return self._source_url

    @Property(str, notify=playbackStateChanged)
    def playbackState(self) -> str:
        return self._playback_state

    @Property(int, notify=positionMsChanged)
    def positionMs(self) -> int:
        return self._position_ms

    @Property(int, notify=durationMsChanged)
    def durationMs(self) -> int:
        return self._duration_ms

    @Property(float, notify=volumeChanged)
    def volume(self) -> float:
        return self._volume

    @Property(bool, notify=mutedChanged)
    def muted(self) -> bool:
        return self._muted

    @Property(str, notify=modeChanged)
    def mode(self) -> str:
        return _MODE_TO_NAME[self._queue.mode]

    @Property(QObject, notify=queueChanged)
    def queueModel(self) -> SongListModel:
        return self._queue_model

    @Property(str, notify=queueSourceChanged)
    def queueSource(self) -> str:
        return self._queue.source

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @asyncSlot("QVariant")
    async def pushAndPlay(self, song_data: Any) -> None:
        await self.push_and_play_async(song_data)

    async def push_and_play_async(self, song_data: Any) -> None:
        song = song_from_map(song_data if isinstance(song_data, Mapping) else {})
        if not song.mid:
            message = "无法播放：歌曲数据不完整"
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        await self.play_songs_async([song], 0)

    @asyncSlot(QObject, int)
    async def playFromModel(self, model: QObject, row: int) -> None:
        await self.play_from_model_async(model, row)

    @asyncSlot(QObject, int, str)
    async def playSourceFromModel(self, model: QObject, row: int, source: str) -> None:
        await self.play_from_model_async(model, row, source=source)

    async def play_from_model_async(
        self,
        model: QObject,
        row: int,
        *,
        source: str = "",
    ) -> None:
        songs = self._songs_from_model(model)
        await self.play_songs_async(songs, row, source=source)

    @asyncSlot(int)
    async def playQueueIndex(self, index: int) -> None:
        await self.play_queue_index_async(index)

    async def play_queue_index_async(self, index: int) -> None:
        song = self._queue.jump_to(index)
        if song is None:
            message = "无法播放：队列项不存在"
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        self._emit_current_changed()
        await self._load_current(play_when_ready=True)

    async def play_songs_async(
        self,
        songs: list[Song],
        start_index: int,
        *,
        source: str = "",
    ) -> None:
        if not songs or not (0 <= start_index < len(songs)):
            message = "无法播放：队列数据不完整"
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return
        requested_song = songs[start_index]
        current_song = self._queue.current()
        if (
            self._loading
            and current_song is not None
            and current_song.mid == requested_song.mid
            and self._queue.current_index == start_index
            and len(self._queue.songs) == len(songs)
            and self._queue.source == source
        ):
            return
        previous_source = self._queue.source
        self._queue.push(songs, play_now=True, start_index=start_index, source=source)
        self._sync_queue_model()
        if previous_source != self._queue.source:
            self.queueSourceChanged.emit()
        self._emit_current_changed()
        await self._load_current(play_when_ready=True)

    @Slot("QVariantList")
    def appendToQueue(self, songs_data: Any) -> None:
        """QML/Python 端追加歌曲到当前队列; 自动去重."""
        items = songs_data if isinstance(songs_data, list) else []
        songs = [song_from_map(item) for item in items if isinstance(item, Mapping)]
        self.append_to_queue(songs)

    def append_to_queue(self, songs: list[Song]) -> list[Song]:
        """追加歌曲到当前队列, 返回真正加入的那些 (已去重).

        若播放器因为队列空而停下 (current_index 越界), 自动跳到第一首新加曲并续播.
        """
        if not songs:
            return []
        was_exhausted = (
            not self._queue.songs
            or self._queue.current_index < 0
            or self._queue.current_index >= len(self._queue.songs)
        )
        added = self._queue.append(songs)
        if not added:
            return added
        # 粒度插入而非整表 reset: 待播面板开着时 reset 会重建 ListView 并滚回顶部
        self._queue_model.append_songs(added)
        if was_exhausted:
            # 跳到第一首新加曲并续播 (handleEndOfMedia 走完整批后续接的场景)
            self._queue.current_index = len(self._queue.songs) - len(added)
            self._emit_current_changed()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return added
            loop.create_task(self._load_current(play_when_ready=True))
        return added

    @Slot("QVariant")
    def playSongNext(self, song_data: Any) -> None:
        """把一首歌排到当前曲之后 (下一首播放); 已在队列中则挪位, 空队列直接起播."""
        song = song_from_map(song_data if isinstance(song_data, Mapping) else {})
        if not song.mid:
            return
        current = self._queue.current()
        if current is not None and current.mid == song.mid:
            return
        existing = next(
            (i for i, s in enumerate(self._queue.songs) if s.mid == song.mid),
            -1,
        )
        if existing >= 0:
            self._queue.remove_at(existing)
        was_empty = self._queue.current() is None
        self._queue.insert_next(song)
        # 粒度挪位/插入而非整表 reset (保住待播面板滚动位置)
        new_row = next(
            (i for i, s in enumerate(self._queue.songs) if s.mid == song.mid),
            -1,
        )
        if existing >= 0:
            self._queue_model.move_row(existing, new_row)
        else:
            self._queue_model.insert_song(new_row, song)
        if was_empty:
            self._emit_current_changed()
            self._spawn_load_current(play_when_ready=True)
        else:
            # 当前曲继续播, 但下一首换成了新插的 -> 预取失效重取
            self._refresh_prefetch()

    @Slot(int)
    def removeQueueIndex(self, row: int) -> None:
        """移除待播列表中的一行; 移除当前曲时顶上下一首续播, 队列清空则停."""
        was_current = row == self._queue.current_index
        was_active = self._loading or self._playback_state in ("playing", "loading")
        removed = self._queue.remove_at(row)
        if removed is None:
            return
        # 粒度移除而非整表 reset (保住待播面板滚动位置)
        self._queue_model.remove_row(row)
        self._emit_current_changed()
        if not was_current:
            # 移除的可能正是已预取的下一首 -> 预取失效重取 (当前曲不受影响)
            self._refresh_prefetch()
            return
        if self._queue.current() is None:
            self.stop()
            return
        self._spawn_load_current(play_when_ready=was_active)

    @Slot()
    def clearQueue(self) -> None:
        """清空待播列表并停止播放."""
        had_source = bool(self._queue.source)
        self._queue.clear()
        self._sync_queue_model()
        self._emit_current_changed()
        if had_source:
            self.queueSourceChanged.emit()
        self.stop()

    def _spawn_load_current(self, *, play_when_ready: bool) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._load_current(play_when_ready=play_when_ready))

    @asyncSlot()
    async def next(self) -> None:  # noqa: A003
        song = self._queue.next()
        if song is None:
            self._handle_queue_exhausted()
            return
        self._emit_current_changed()
        await self._load_current(play_when_ready=True)

    @asyncSlot()
    async def prev(self) -> None:
        song = self._queue.prev()
        if song is None:
            return
        self._emit_current_changed()
        await self._load_current(play_when_ready=True)

    @asyncSlot()
    async def handleEndOfMedia(self) -> None:
        song = self._queue.on_song_end()
        if song is None:
            self._handle_queue_exhausted()
            return
        self._emit_current_changed()
        # 单曲循环 (含单曲 REPEAT_ALL): 链接未变, 回卷重播即可, 不重取链 (issue #11).
        # 长时间循环后链接过期的极端情况由媒体错误重试 (重取链) 兜底.
        if song.mid == self._loaded_mid and self._source_url:
            self._set_position_ms(0)
            self.seekRequested.emit(0)
            self.playRequested.emit()
            return
        await self._load_current(play_when_ready=True)

    def _handle_queue_exhausted(self) -> None:
        """队列自然耗尽: 停下当前播放; 若 source 设置则广播以触发外部续接 (e.g. 猜你喜欢续取下一批).

        source 设置时 current_index 推过末尾, 让 appendToQueue 识别为耗尽状态自动续播第一首新加曲.
        无 source 时保留 current_index 在最后一首, 与历史 stop() 行为一致.
        """
        source = self._queue.source
        if source and self._queue.songs:
            self._queue.current_index = len(self._queue.songs)
            self._emit_current_changed()
        self.stop()
        if source:
            self.queueExhausted.emit(source)

    @Slot()
    def play(self) -> None:
        self._pause_pending = False  # 用户主动播放 -> 撤销加载窗口内的暂停意图
        if self._source_url:
            self.playRequested.emit()
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.play_async())

    async def play_async(self) -> None:
        self._pause_pending = False
        if not self._source_url:
            if self._queue.current() is not None:
                await self._load_current(
                    play_when_ready=True,
                    resume_position_ms=self._position_ms,
                )
            return
        self.playRequested.emit()

    @Slot()
    def pause(self) -> None:
        self.pauseRequested.emit()
        # 加载/淡出窗口内暂停: 记住意图, _load_current 起播前会尊重它, 否则 fade
        # 淡出 sleep 醒来的 playRequested 会覆盖用户刚按下的暂停 (review 发现).
        if self._loading or self._suppress_position_updates:
            self._pause_pending = True

    @Slot()
    def togglePlayPause(self) -> None:
        if self._playback_state == "playing":
            self.pause()
        else:
            self.play()

    @Slot()
    def stop(self) -> None:
        self._cancel_prefetch()
        self._suppress_position_updates = False
        self._pause_pending = False
        self._set_source_url("")
        self._set_position_ms(0)
        self._set_playback_state("stopped")
        self.stopRequested.emit()

    @Slot(int)
    def seek(self, position_ms: int) -> None:
        self.seekRequested.emit(max(0, int(position_ms)))

    @Slot(float)
    def setVolume(self, volume: float) -> None:
        # 用户主动调音量 = 想听到声音, 自动解除静音 (平台标准行为);
        # 解除要在同值早退之前, 否则"拖回原音量"无法解除静音
        if self._muted:
            self._muted = False
            self.mutedChanged.emit()
        value = min(1.0, max(0.0, float(volume)))
        if self._volume == value:
            return
        self._volume = value
        self.volumeChanged.emit()

    @Slot(float)
    def nudgeVolume(self, delta: float) -> None:
        """音量步进 (快捷键 Ctrl+↑/↓ 用), 钳位 [0,1] 并解除静音."""
        self.setVolume(self._volume + float(delta))

    @Slot()
    def toggleMute(self) -> None:
        self._muted = not self._muted
        self.mutedChanged.emit()

    @Slot(str)
    def setMode(self, mode: str) -> None:
        next_mode = _NAME_TO_MODE.get(mode)
        if next_mode is None:
            return
        self._queue.set_mode(next_mode)
        self.modeChanged.emit()
        # 模式变 (尤其 ↔SHUFFLE) 直接改 peek_next 结果, 旧预取多半作废 -> 失效重取
        self._refresh_prefetch()

    @Slot(int)
    def updatePosition(self, position_ms: int) -> None:
        if self._suppress_position_updates:
            return
        self._set_position_ms(position_ms)

    @Slot(int)
    def updateDuration(self, duration_ms: int) -> None:
        if self._duration_ms == duration_ms:
            return
        self._duration_ms = max(0, int(duration_ms))
        self.durationMsChanged.emit()

    @Slot(str)
    def updatePlaybackState(self, state: str) -> None:
        if state == "playing":
            self._media_retry_count = 0  # 成功播放 -> 清零, 允许后续 (如 vkey 过期) 再重试
            self._schedule_prefetch_next()
        self._set_playback_state(state)

    @asyncSlot(int, str)
    async def handleMediaError(self, error: int, error_string: str) -> None:
        await self.handle_media_error_async(error, error_string)

    async def handle_media_error_async(self, error: int, error_string: str) -> None:
        """QML MediaPlayer 报错回调: 瞬态错误 (CDN 401 等) 重取链重试当前曲一次."""
        song = self._queue.current()
        if song is None:
            return
        # 流末尾解码错误豁免: CDN FLAC 尾部坏帧让 QMediaPlayer 在播到末尾时 emit
        # FormatError, 但歌已播完 (EndOfMedia 随后接管切歌). 静默忽略, 否则会误报
        # "播放失败" + 让 UI 闪错误又被切歌 (真机暴露的诡异 UI). 仅 FormatError +
        # 接近末尾; 网络/资源类错误即便在末尾也照常重取链重试 (可能是真断流).
        # 下限取 max(duration - 容差, duration//2): 长歌是末尾 5s 窗口; 短歌 (duration
        # < 2×容差) 时 `duration - 容差` 会退化成负数/全程, 用 duration//2 兜底, 保证
        # 短歌开头/中段的真损坏仍照常报错, 只豁免后半段真到末尾的坏帧 (review 发现).
        if (
            int(error) == QMediaPlayer.Error.FormatError.value
            and self._duration_ms > 0
            and self._position_ms
            >= max(self._duration_ms - _END_OF_STREAM_TOLERANCE_MS, self._duration_ms // 2)
        ):
            logger.debug(
                "忽略流末尾解码错误 (歌已近播完, 由 EndOfMedia 接管): %s @%d/%dms",
                song.name,
                self._position_ms,
                self._duration_ms,
            )
            return
        if song.mid != self._media_retry_mid:  # 换了曲 -> 重置计数
            self._media_retry_mid = song.mid
            self._media_retry_count = 0
        if int(error) in _RETRYABLE_MEDIA_ERRORS and self._media_retry_count < _MAX_MEDIA_RETRIES:
            self._media_retry_count += 1
            logger.warning(
                "媒体错误 (code=%s: %s), 重取链重试 %d/%d: %s",
                error,
                error_string,
                self._media_retry_count,
                _MAX_MEDIA_RETRIES,
                song.name,
            )
            await self._load_current(
                play_when_ready=True,
                resume_position_ms=self._position_ms,
            )
            return
        # 不可重试 或 重试已用尽 -> 报错停下, 交给用户
        self._media_retry_count = 0
        self._media_retry_mid = ""
        self._set_playback_state("stopped")
        message = f"播放失败：{song.name}"
        self._set_error_message(message)
        self.errorRaised.emit(message)

    @Slot()
    def saveSessionSnapshot(self) -> None:
        if self._session_state is None:
            return
        self._session_state.save(
            self._queue,
            position_ms=self._position_ms,
            volume=self._volume,
        )

    async def _load_current(
        self,
        *,
        play_when_ready: bool,
        resume_position_ms: int = 0,
    ) -> None:
        song = self._queue.current()
        if song is None:
            self.stop()
            return
        self._cancel_prefetch()
        # 新一轮加载 = 用户想播这首; 重置上一轮残留的暂停意图 (play_when_ready 时若
        # 淡出窗口内又被 pause 会重新置上).
        self._pause_pending = False
        self._load_generation += 1
        generation = self._load_generation
        resume_position_ms = max(0, int(resume_position_ms))
        # 切歌淡出 (issue #11 Stage C2): 正在出声时先发淡出, 取链与淡出并行
        # (fade 时长掩盖网络延迟). 淡出期间不清 source (清了立即哑), 并冻结
        # 进度回传; 淡出播完才换源. 非出声态 (停止/加载/EOS 后) 保持旧行为.
        fade_out_ms = 0
        if self._playback_state == "playing" and self._fade_enabled():
            fade_out_ms = max(0, self._fade_duration_ms())
        fade_deadline = 0.0
        if fade_out_ms > 0:
            self._suppress_position_updates = True
            self.fadeOutRequested.emit(fade_out_ms)
            fade_deadline = asyncio.get_running_loop().time() + fade_out_ms / 1000
        else:
            self._suppress_position_updates = False
            self._set_source_url("")
        self._set_position_ms(resume_position_ms)
        self.updateDuration(song.duration * 1000)
        self._set_error_message("")
        # 本地优先: 已下载且文件仍在 → 直接播本地文件, 跳过预取消费 / vkey 取链 /
        # stream_proxy (离线 / 未登录也能播下载好的歌). 文件失效时 resolver 返 ""
        # → 回落在线流程。淡出等待与挂源走下方公共尾部, 与在线路径行为一致。
        local_path = self._resolve_local(song.mid)
        song_url = None
        if local_path:
            logger.info("本地播放: %s (mid=%s)", song.name, song.mid)
        else:
            song_url = self._take_prefetched(song.mid, self._quality_preference())
        if song_url is not None:
            # 预取命中: 免 vkey 往返, 直接挂源 (issue #11)
            logger.debug("命中预取链接: %s (mid=%s)", song.name, song.mid)
        elif not local_path:
            self._set_loading(True)
            self._set_playback_state("loading")
            try:
                song_url = await self._service_controller.get_song_url(
                    song,
                    quality_preference=self._quality_preference(),
                )
            except Exception as exc:
                raw_message = str(exc) or exc.__class__.__name__
                if raw_message == "播放需要先登录 QQ 音乐":
                    message = raw_message
                    logger.warning("%s: %s", message, song.name)
                else:
                    message = log_bridge_error(
                        logger,
                        f"load song url failed: {song.name}",
                        exc,
                    )
                if generation != self._load_generation:
                    return
                # 淡出路径上旧源还挂着 (静音空转), 报错停下时一并卸掉
                self._suppress_position_updates = False
                self._set_source_url("")
                self._set_playback_state("stopped")
                self._set_error_message(message)
                self.errorRaised.emit(message)
                return
            finally:
                if generation == self._load_generation:
                    self._set_loading(False)

            if generation != self._load_generation:
                return

        if fade_out_ms > 0:
            # 取链先于淡出完成时, 等淡出播完再换源 (听感: 渐弱到无声才接新歌)
            remaining = fade_deadline - asyncio.get_running_loop().time()
            if remaining > 0:
                await asyncio.sleep(remaining)
            if generation != self._load_generation:
                return
            self._suppress_position_updates = False
            self._set_position_ms(resume_position_ms)

        if not local_path and (song_url is None or not song_url.url):
            # None = 服务端明确拒发 (vkey 104003 无版权等), 是单曲属性 → 自动跳下一首,
            # 与官方客户端对灰色歌曲的行为一致. 传输层异常走上面的 except 分支停住报错
            # (断网时绝不能把整个队列"跳"光). 连跳上限防 REPEAT_ALL 全队列不可播时绕圈空转.
            self._url_failure_streak += 1
            if self._url_failure_streak < self._URL_FAILURE_STREAK_LIMIT:
                logger.info(
                    "自动跳过不可播曲目: %s (mid=%s, 连续第 %d 首)",
                    song.name,
                    song.mid,
                    self._url_failure_streak,
                )
                self.noticeRaised.emit(f"已跳过无法播放的歌曲：{song.name}")
                # next() 在队列尽头 (SEQUENCE) 走 exhausted → 自然停, 不挂错误
                await self.next()
                return
            message = f"无法获取播放链接：{song.name}"
            self._set_source_url("")  # 淡出路径上旧源可能还挂着, 停下时一并卸掉
            self._set_playback_state("stopped")
            self._set_error_message(message)
            self.errorRaised.emit(message)
            return

        self._url_failure_streak = 0

        if local_path:
            playback_url = QUrl.fromLocalFile(local_path).toString()
        else:
            playback_url = song_url.url
            if self._stream_proxy is not None:
                # 反风控 U2: 经本机回环代理拉流（出网走 curl_cffi 官方指纹 https）
                self._start_stream_proxy_if_available()
                playback_url = self._stream_proxy.local_url(playback_url)
        self._loaded_mid = song.mid
        self._set_source_url(playback_url)
        if resume_position_ms > 0:
            self.seekRequested.emit(resume_position_ms)
        if play_when_ready and not self._pause_pending:
            self.playRequested.emit()
        elif self._pause_pending:
            # 淡出窗口内用户暂停了: 源已挂好但停在暂停态, 不强行起播 (review 发现)
            self._set_playback_state("paused")

    # ------------------------------------------------------------------ 预取下一首 (issue #11)

    def _start_stream_proxy_if_available(self) -> None:
        """按需启动 StreamProxy；失败时保留 local_url 的直连降级语义。"""
        if self._stream_proxy is None or bool(getattr(self._stream_proxy, "running", False)):
            return
        start = getattr(self._stream_proxy, "start", None)
        if not callable(start):
            return
        try:
            start()
        except Exception as exc:
            logger.warning("StreamProxy 懒启动失败, 将降级为直连: %s", exc)

    def _schedule_prefetch_next(self) -> None:
        """起播稳定后预取下一首链接 (best-effort); 重复触发时重置延迟."""
        self._cancel_prefetch()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._prefetch_delay_s > 0:
            self._prefetch_handle = loop.call_later(
                self._prefetch_delay_s,
                self._spawn_prefetch_task,
            )
        else:
            self._spawn_prefetch_task()

    def _spawn_prefetch_task(self) -> None:
        self._prefetch_handle = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._prefetch_task = loop.create_task(self._prefetch_next())

    def _refresh_prefetch(self) -> None:
        """队列结构/模式变化后让旧预取失效, 播放中则按新的下一首重新预取.

        mid+偏好双匹配本已防止消费错歌 (失配即丢弃走正常取链), 这里只是避免白白
        留着一份作废预取 / 及时为变更后的新下一首预取 (review: 效率).
        """
        self._cancel_prefetch()
        self._prefetched = None
        if self._playback_state == "playing":
            self._schedule_prefetch_next()

    def _cancel_prefetch(self) -> None:
        """取消计划中/在途的预取; 不动已落地的 _prefetched (消费时按 mid+偏好校验)."""
        if self._prefetch_handle is not None:
            self._prefetch_handle.cancel()
            self._prefetch_handle = None
        task = self._prefetch_task
        if task is not None and not task.done():
            task.cancel()
        self._prefetch_task = None

    async def _prefetch_next(self) -> None:
        """预取"自然播完后的下一首"的播放链接 (仅 1 次 musicu.fcg POST, 不开流).

        失败/拒发一律静默: 预取是 best-effort, 自动跳过通知与连跳计数等
        用户可见逻辑留给 _load_current 正常链路. 整个函数体包 try (除 CancelledError):
        peek_next / song_url 属性访问等任何异常都不该冒泡成 asyncio "Task exception
        was never retrieved" (review 发现 —— 原来只包了 get_song_url).
        """
        try:
            song = self._queue.peek_next()
            if song is None or not song.mid:
                return
            if song.mid == self._loaded_mid and self._source_url:
                return  # REPEAT_ONE 自循环: 链接已挂在播放器上, EOS 走短路重播
            preference = self._quality_preference()
            cached = self._prefetched
            if cached is not None and cached[0] == song.mid and cached[1] == preference:
                return
            song_url = await self._service_controller.get_song_url(
                song,
                quality_preference=preference,
            )
            if song_url is None or not song_url.url:
                return
            self._prefetched = (song.mid, preference, song_url)
            logger.debug("已预取下一首链接: %s (mid=%s, %s)", song.name, song.mid, song_url.quality)
        except asyncio.CancelledError:
            raise  # _cancel_prefetch 取消时正常传播, 不当失败吞掉
        except Exception as exc:
            logger.debug("预取下一首链接失败 (忽略): %s", exc)

    def _take_prefetched(self, mid: str, preference: str) -> SongUrl | None:
        """取走预取缓存: mid+音质偏好双匹配才命中; 无论命中与否消费即清.

        清空保证媒体错误重试路径再进 _load_current 时必然现签新链.
        """
        cached = self._prefetched
        self._prefetched = None
        if cached is None:
            return None
        cached_mid, cached_pref, url = cached
        if cached_mid == mid and cached_pref == preference:
            return url
        return None

    def _restore_session_snapshot(self) -> None:
        if self._session_state is None:
            return
        snapshot = self._session_state.restore()
        if snapshot is None:
            return
        snapshot.apply_to(self._queue)
        self._sync_queue_model()
        self._set_position_ms(snapshot.position_ms)
        self.setVolume(snapshot.volume)
        song = self._queue.current()
        if song is not None:
            self.updateDuration(song.duration * 1000)
        self._emit_current_changed()
        self.modeChanged.emit()

    def _quality_preference(self) -> str:
        value = getattr(self._settings_controller, "qualityPreference", "balanced")
        return value if value in {"standard", "balanced", "high"} else "balanced"

    def _fade_enabled(self) -> bool:
        return bool(getattr(self._settings_controller, "fadeEnabled", False))

    def _fade_duration_ms(self) -> int:
        try:
            return int(getattr(self._settings_controller, "fadeDurationMs", 0))
        except (TypeError, ValueError):
            return 0

    def _songs_from_model(self, model: QObject) -> list[Song]:
        if isinstance(model, SongListModel):
            return model.songs()
        count = int(getattr(model, "count", 0) or 0)
        if not hasattr(model, "songAt"):
            return []
        songs: list[Song] = []
        for row in range(count):
            song = song_from_map(model.songAt(row))
            if song.mid:
                songs.append(song)
        return songs

    def _sync_queue_model(self) -> None:
        self._queue_model.set_songs(self._queue.songs)
        self.queueChanged.emit()

    def _emit_current_changed(self) -> None:
        self.currentSongChanged.emit()
        self.currentIndexChanged.emit()

    def _set_source_url(self, value: str) -> None:
        if self._source_url == value:
            return
        self._source_url = value
        self.sourceUrlChanged.emit()

    def _set_playback_state(self, value: str) -> None:
        if self._playback_state == value:
            return
        self._playback_state = value
        self.playbackStateChanged.emit()

    def _set_position_ms(self, value: int) -> None:
        value = max(0, int(value))
        if self._position_ms == value:
            return
        self._position_ms = value
        self.positionMsChanged.emit()

    def _set_loading(self, value: bool) -> None:
        if self._loading == value:
            return
        self._loading = value
        self.loadingChanged.emit()

    def _set_error_message(self, value: str) -> None:
        if self._error_message == value:
            return
        self._error_message = value
        self.errorMessageChanged.emit()
