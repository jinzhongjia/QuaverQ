"""DetailController tests."""

from __future__ import annotations

from quaverq.bridge.detail_controller import DetailController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Album, ArtistDetail, Playlist, Singer, Song


class _FakeDetailService:
    def __init__(self) -> None:
        self.connected = False
        self.is_authenticated = True

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_playlist_detail(self, pid: str) -> Playlist:
        return Playlist(
            pid=pid,
            name="百听不厌",
            description="经典歌单",
            creator="编辑",
            song_count=2,
            songs=[
                Song(mid="p1", name="七里香", singers=[Singer(mid="s1", name="周杰伦")]),
                Song(mid="p2", name="晴天", singers=[Singer(mid="s1", name="周杰伦")]),
            ],
        )

    async def get_album_detail(self, album_mid: str) -> Album:
        return Album(
            mid=album_mid,
            name="叶惠美",
            singers=[Singer(mid="s1", name="周杰伦")],
            publish_date="2003-07-29",
            description="专辑简介",
            songs=[Song(mid="a1", name="以父之名")],
        )

    async def get_artist_detail(self, singer_mid: str) -> ArtistDetail:
        return ArtistDetail(
            singer=Singer(mid=singer_mid, name="周杰伦", avatar_url="http://a.jpg"),
            description="艺人简介",
            hot_songs=[Song(mid="ar1", name="稻香")],
        )

    async def get_top_detail(self, top_id: int) -> Playlist:
        return Playlist(
            pid=str(top_id),
            name="飙升榜",
            description="排行榜说明",
            song_count=1,
            songs=[Song(mid="t1", name="排行第 1")],
        )


async def test_load_playlist_detail_populates_song_model():
    service = _FakeDetailService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = DetailController(service_controller)

    await controller.load_detail_async("playlist", "p1")

    assert service.connected is True
    assert controller.kind == "playlist"
    assert controller.title == "百听不厌"
    assert controller.subtitle == "编辑"
    assert controller.description == "经典歌单"
    assert controller.songModel.count == 2
    assert controller.songModel.songAt(0)["name"] == "七里香"


async def test_load_album_detail_populates_album_metadata():
    service = _FakeDetailService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = DetailController(service_controller)

    await controller.load_detail_async("album", "a1")

    assert controller.kind == "album"
    assert controller.title == "叶惠美"
    assert controller.subtitle == "周杰伦 · 2003-07-29"
    assert controller.songModel.songAt(0)["name"] == "以父之名"


async def test_load_artist_detail_uses_hot_songs():
    service = _FakeDetailService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = DetailController(service_controller)

    await controller.load_detail_async("artist", "s1")

    assert controller.kind == "artist"
    assert controller.title == "周杰伦"
    assert controller.subtitle == "艺人"
    assert controller.coverUrl == "http://a.jpg"
    assert controller.songModel.songAt(0)["name"] == "稻香"


async def test_load_top_detail_preserves_top_kind():
    service = _FakeDetailService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = DetailController(service_controller)

    await controller.load_detail_async("top", "62")

    assert controller.kind == "top"
    assert controller.detailId == "62"
    assert controller.title == "飙升榜"
    assert controller.songModel.songAt(0)["mid"] == "t1"


async def test_load_detail_empty_id_sets_error():
    service = _FakeDetailService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = DetailController(service_controller)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    await controller.load_detail_async("playlist", "")

    assert controller.errorMessage == "详情 ID 为空"
    assert errors == ["详情 ID 为空"]
    assert controller.songModel.count == 0


async def test_load_detail_empty_id_resets_loading_state():
    service = _FakeDetailService()
    service_controller = ServiceController(service=service)  # type: ignore[arg-type]
    controller = DetailController(service_controller)
    controller._set_loading(True)  # noqa: SLF001

    await controller.load_detail_async("playlist", "")

    assert controller.loading is False
