"""DetailController tests."""

from __future__ import annotations

from quaverq.bridge.detail_controller import DetailController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.models import Album, ArtistDetail, Playlist, Singer, Song


class _FakeDetailService:
    def __init__(self) -> None:
        self.connected = False
        self.is_authenticated = True
        self.similar_singers_calls: list[str] = []
        self.singer_songs_calls: list[str] = []
        self.singer_albums_calls: list[str] = []
        self.similar_singers_result: list[Singer] = []
        self.singer_songs_result: list[Song] = []
        self.singer_albums_result: list[Album] = []

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

    # ----- 2.2 歌手 tab 懒加载 -----
    async def get_similar_singers(self, singer_mid: str) -> list[Singer]:
        self.similar_singers_calls.append(singer_mid)
        return self.similar_singers_result

    async def get_singer_songs(self, singer_mid: str) -> list[Song]:
        self.singer_songs_calls.append(singer_mid)
        return self.singer_songs_result

    async def get_singer_albums(self, singer_mid: str) -> list[Album]:
        self.singer_albums_calls.append(singer_mid)
        return self.singer_albums_result

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


# ============================================================== 2.2 歌手 tab 懒加载


async def _open_artist(service):
    sc = ServiceController(service=service)  # type: ignore[arg-type]
    ctrl = DetailController(sc)
    await ctrl.load_detail_async("artist", "s1")
    return ctrl


async def test_singer_tabs_not_loaded_until_explicitly_requested():
    service = _FakeDetailService()
    service.similar_singers_result = [Singer(mid="x", name="X")]
    service.singer_songs_result = [Song(mid="y", name="Y")]
    service.singer_albums_result = [Album(mid="z", name="Z")]
    ctrl = await _open_artist(service)

    # 只加载了热门歌曲, 3 个 tab 都没动
    assert service.similar_singers_calls == []
    assert service.singer_songs_calls == []
    assert service.singer_albums_calls == []
    assert ctrl.similarSingersLoaded is False
    assert ctrl.singerSongsLoaded is False
    assert ctrl.singerAlbumsLoaded is False


async def test_load_similar_singers_populates_card_model():
    service = _FakeDetailService()
    service.similar_singers_result = [
        Singer(mid="m1", name="林俊杰", avatar_url="http://a/1.jpg"),
        Singer(mid="m2", name="王力宏", avatar_url="http://a/2.jpg"),
    ]
    ctrl = await _open_artist(service)

    await ctrl.loadSimilarSingers()

    assert service.similar_singers_calls == ["s1"]
    assert ctrl.similarSingersModel.count == 2
    card = ctrl.similarSingersModel.cardAt(0)
    assert card["kind"] == "artist"
    assert card["title"] == "林俊杰"
    assert ctrl.similarSingersLoaded is True
    assert ctrl.similarSingersLoading is False


async def test_load_similar_singers_idempotent():
    """二次调用不应再发请求 (避免每次切回 tab 重拉)."""
    service = _FakeDetailService()
    service.similar_singers_result = [Singer(mid="m1", name="A")]
    ctrl = await _open_artist(service)
    await ctrl.loadSimilarSingers()
    await ctrl.loadSimilarSingers()
    assert service.similar_singers_calls == ["s1"]


async def test_load_singer_songs_populates_song_model():
    service = _FakeDetailService()
    service.singer_songs_result = [
        Song(mid="m1", name="晴天", singers=[Singer(mid="s1", name="周杰伦")]),
        Song(mid="m2", name="七里香", singers=[Singer(mid="s1", name="周杰伦")]),
    ]
    ctrl = await _open_artist(service)

    await ctrl.loadSingerSongs()

    assert service.singer_songs_calls == ["s1"]
    assert ctrl.singerSongsModel.count == 2
    assert ctrl.singerSongsLoaded is True


async def test_load_singer_albums_populates_card_model():
    service = _FakeDetailService()
    service.singer_albums_result = [
        Album(mid="a1", name="叶惠美", publish_date="2003-07-29", song_count=11),
        Album(mid="a2", name="我很忙", publish_date="2007-11-02", song_count=10),
    ]
    ctrl = await _open_artist(service)

    await ctrl.loadSingerAlbums()

    assert service.singer_albums_calls == ["s1"]
    assert ctrl.singerAlbumsModel.count == 2
    card = ctrl.singerAlbumsModel.cardAt(0)
    assert card["kind"] == "album"
    assert card["title"] == "叶惠美"
    assert ctrl.singerAlbumsLoaded is True


async def test_singer_tabs_skipped_when_kind_not_artist():
    """playlist 详情页时即使 QML 错调 loadSimilarSingers 也不应发请求."""
    service = _FakeDetailService()
    sc = ServiceController(service=service)  # type: ignore[arg-type]
    ctrl = DetailController(sc)
    await ctrl.load_detail_async("playlist", "p1")
    await ctrl.loadSimilarSingers()
    await ctrl.loadSingerSongs()
    await ctrl.loadSingerAlbums()
    assert service.similar_singers_calls == []
    assert service.singer_songs_calls == []
    assert service.singer_albums_calls == []


async def test_switching_artists_resets_tabs():
    """切到另一个歌手时, 之前已加载的 tab 应当 loaded=False, model 清空, 再 load 会发新请求."""
    service = _FakeDetailService()
    service.similar_singers_result = [Singer(mid="X", name="X")]
    ctrl = await _open_artist(service)
    await ctrl.loadSimilarSingers()
    assert ctrl.similarSingersLoaded is True
    assert ctrl.similarSingersModel.count == 1

    # 切到另一个 artist
    service.similar_singers_result = [Singer(mid="Y", name="Y"), Singer(mid="Z", name="Z")]
    await ctrl.load_detail_async("artist", "s2")
    assert ctrl.similarSingersLoaded is False
    assert ctrl.similarSingersModel.count == 0

    await ctrl.loadSimilarSingers()
    assert service.similar_singers_calls == ["s1", "s2"]
    assert ctrl.similarSingersModel.count == 2


async def test_singer_tab_load_error_results_in_empty_but_loaded():
    """service 抛错时 controller 应吞并设 loaded=True 让 UI 显示「暂无」而不是反复 loading."""

    async def _raise(_):
        raise RuntimeError("boom")

    service = _FakeDetailService()
    service.get_similar_singers = _raise  # type: ignore[assignment]
    ctrl = await _open_artist(service)

    await ctrl.loadSimilarSingers()

    assert ctrl.similarSingersLoading is False
    assert ctrl.similarSingersLoaded is True
    assert ctrl.similarSingersModel.count == 0


# ============================================================== A. Factory 模式
# 见 AGENTS.md「栈式视图必须自持状态」契约


def test_factory_creates_independent_controllers():
    """factory.create() 每次都返回新实例, 两个实例的 state 互相隔离."""
    from quaverq.bridge.detail_controller import DetailControllerFactory

    service = _FakeDetailService()
    sc = ServiceController(service=service)  # type: ignore[arg-type]
    factory = DetailControllerFactory(sc)

    ctrl_a = factory.create(None)
    ctrl_b = factory.create(None)

    assert ctrl_a is not ctrl_b
    assert isinstance(ctrl_a, DetailController)
    assert isinstance(ctrl_b, DetailController)

    # 隔离: 改 a 的 song model 不影响 b
    ctrl_a._set_songs([Song(mid="x", name="X")])  # noqa: SLF001
    assert ctrl_a.songModel.count == 1
    assert ctrl_b.songModel.count == 0


async def test_factory_created_controller_loads_detail_independently():
    """两个并存 controller 加载不同详情, 互不覆写."""
    from quaverq.bridge.detail_controller import DetailControllerFactory

    service = _FakeDetailService()
    sc = ServiceController(service=service)  # type: ignore[arg-type]
    factory = DetailControllerFactory(sc)

    ctrl_a = factory.create(None)
    ctrl_b = factory.create(None)

    await ctrl_a.load_detail_async("playlist", "p1")
    await ctrl_b.load_detail_async("album", "a1")

    # 各自加载完后, state 互不污染
    assert ctrl_a.kind == "playlist"
    assert ctrl_a.title == "百听不厌"
    assert ctrl_b.kind == "album"
    assert ctrl_b.title == "叶惠美"
