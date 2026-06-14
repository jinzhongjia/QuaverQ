"""LyricsDBusController tests.

不启真 D-Bus, 用 _FakeLyricsService 验证:
- start_async 后 sync 当前状态
- lyric_controller.lyricChanged 触发 push_lyric
- activeIndex / positionMs 变化触发 push_position + push_active (含 active_word 计算)
- 切歌后旧的 active 清掉
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from quaverq.bridge.lyric_controller import LyricController
from quaverq.bridge.lyric_dbus_controller import LyricsDBusController
from quaverq.bridge.player_controller import PlayerController
from quaverq.bridge.service_controller import ServiceController
from quaverq.bridge.settings_controller import SettingsController
from quaverq.core.models import Lyric, LyricLine, LyricWord, Song, SongUrl


class _FakeAudioService:
    async def get_song_url(self, song: Song, *, quality_preference: str) -> SongUrl:
        return SongUrl(mid=song.mid, url=f"https://x/{song.mid}.mp3")


class _FakeLyricsService:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.start_result = True
        self.lyrics: list[Lyric | None] = []
        self.positions: list[int] = []
        self.actives: list[tuple[int, int]] = []
        self.include_translation: list[bool] = []

    async def start(self) -> bool:
        self.started = True
        return self.start_result

    async def stop(self) -> None:
        self.stopped = True

    def push_lyric(self, lyric: Lyric | None, *, include_translation: bool = True) -> None:
        self.lyrics.append(lyric)
        self.include_translation.append(include_translation)

    def push_position(self, position_ms: int) -> None:
        self.positions.append(position_ms)

    def push_active(self, line_index: int, word_index: int) -> None:
        self.actives.append((line_index, word_index))


def _make_qrc_lyric(mid: str = "m1") -> Lyric:
    return Lyric(
        mid=mid,
        lines=[
            LyricLine(
                timestamp_ms=1000,
                text="你好",
                words=[
                    LyricWord(text="你", start_ms=1000, duration_ms=200),
                    LyricWord(text="好", start_ms=1200, duration_ms=200),
                ],
            ),
            LyricLine(
                timestamp_ms=3000,
                text="世界",
                words=[
                    LyricWord(text="世", start_ms=3000, duration_ms=300),
                    LyricWord(text="界", start_ms=3300, duration_ms=300),
                ],
            ),
        ],
        has_translation=False,
    )


def _build(
    *,
    with_lyric: Lyric | None = None,
    settings_controller: SettingsController | None = None,
) -> tuple[LyricsDBusController, _FakeLyricsService, LyricController, PlayerController]:
    service_controller = ServiceController()
    player = PlayerController(_FakeAudioService())  # type: ignore[arg-type]
    lyric_controller = LyricController(
        service_controller,
        player,
        settings_controller=settings_controller,
    )

    if with_lyric is not None:
        lyric_controller._set_lyric(with_lyric)  # noqa: SLF001
    fake = _FakeLyricsService()
    controller = LyricsDBusController(
        lyric_controller=lyric_controller,
        player_controller=player,
        service_factory=lambda: fake,
    )
    return controller, fake, lyric_controller, player


async def test_start_syncs_current_lyric_and_position():
    lyric = _make_qrc_lyric()
    controller, fake, lc, player = _build(with_lyric=lyric)
    player.updatePosition(1300)  # 第一行第二字

    started = await controller.start_async()

    assert started is True
    assert controller.started is True
    # sync_all: push 当前 lyric + position + active
    assert fake.lyrics[-1] is lyric
    assert fake.positions[-1] == 1300
    # 1300ms 落在第一行 (ts=1000), 词索引 1 (第二字 1200-1399)
    assert fake.actives[-1] == (0, 1)


async def test_lyric_changed_signal_pushes_new_lyric():
    controller, fake, lc, _ = _build()
    await controller.start_async()

    new_lyric = _make_qrc_lyric(mid="m2")
    lc._set_lyric(new_lyric)  # noqa: SLF001

    assert fake.lyrics[-1] is new_lyric


async def test_translation_visibility_flag_follows_lyric_controller_setting(tmp_path):
    settings = SettingsController(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    )
    settings.setLyricTranslationVisible(False)
    lyric = Lyric(
        mid="m1",
        lines=[LyricLine(timestamp_ms=0, text="原文", translation="translation")],
        has_translation=True,
    )
    controller, fake, _, _ = _build(with_lyric=lyric, settings_controller=settings)

    await controller.start_async()

    assert fake.lyrics[-1] is lyric
    assert fake.include_translation[-1] is False

    settings.setLyricTranslationVisible(True)

    assert fake.lyrics[-1] is lyric
    assert fake.include_translation[-1] is True


async def test_position_change_updates_active_word_within_line():
    lyric = _make_qrc_lyric()
    controller, fake, _, player = _build(with_lyric=lyric)
    await controller.start_async()
    fake.actives.clear()

    player.updatePosition(1000)  # 第一字
    player.updatePosition(1250)  # 第二字
    player.updatePosition(3050)  # 第二行第一字

    # 每次 (line, word) 变化都应 push
    assert (0, 0) in fake.actives
    assert (0, 1) in fake.actives
    assert (1, 0) in fake.actives


async def test_position_does_not_push_active_if_word_unchanged():
    """连续两次 position 都落在同一字时, push_active 不重复发."""
    lyric = _make_qrc_lyric()
    controller, fake, _, player = _build(with_lyric=lyric)
    await controller.start_async()
    fake.actives.clear()

    player.updatePosition(1050)  # 第一字
    player.updatePosition(1100)  # 仍在第一字
    player.updatePosition(1150)  # 仍在第一字

    # 只 push 一次 (0, 0)
    assert fake.actives == [(0, 0)]


async def test_plain_lrc_pushes_minus_one_word():
    """无逐字时 active_word 恒为 -1."""
    plain = Lyric(
        mid="m",
        lines=[LyricLine(timestamp_ms=0, text="a"), LyricLine(timestamp_ms=2000, text="b")],
    )
    controller, fake, _, player = _build(with_lyric=plain)
    player.updatePosition(500)
    await controller.start_async()
    fake.actives.clear()

    player.updatePosition(2500)

    assert fake.actives[-1] == (1, -1)


async def test_before_first_line_pushes_minus_one():
    lyric = _make_qrc_lyric()
    controller, fake, _, player = _build(with_lyric=lyric)
    player.updatePosition(500)  # 第一行 1000 之前
    await controller.start_async()

    # active line = -1, word = -1
    assert fake.actives[-1] == (-1, -1)


async def test_start_failure_does_not_push():
    fake = _FakeLyricsService()
    fake.start_result = False
    service_controller = ServiceController()
    player = PlayerController(_FakeAudioService())  # type: ignore[arg-type]
    lyric_controller = LyricController(service_controller, player)
    lyric_controller._set_lyric(_make_qrc_lyric())  # noqa: SLF001
    controller = LyricsDBusController(
        lyric_controller=lyric_controller,
        player_controller=player,
        service_factory=lambda: fake,
    )

    started = await controller.start_async()
    player.updatePosition(1300)

    assert started is False
    assert controller.started is False
    # start 失败后不再 push 任何状态
    assert fake.lyrics == []
    assert fake.positions == []
    assert fake.actives == []


async def test_stop_async_clears_started():
    controller, fake, _, _ = _build()
    await controller.start_async()
    assert controller.started is True
    await controller.stop_async()
    assert fake.stopped is True
    assert controller.started is False
