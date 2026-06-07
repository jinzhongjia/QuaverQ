"""SWR 接线测试: HomeController / LibraryController 与 HomeCache 协作.

覆盖: 刷新成功回写缓存 (公共无账号 / 私有带账号隔离)、启动 prime 填模型、
prime 不覆盖已到达的网络数据 (count>0 guard)、登出清私有、account_key 派生.
"""

from __future__ import annotations

from pathlib import Path

from quaverq.bridge.home_controller import HomeController
from quaverq.bridge.library_controller import LibraryController
from quaverq.bridge.service_controller import ServiceController
from quaverq.core.home_cache import HomeCache
from quaverq.core.models import Playlist, Singer, Song, TopList


class _FakeCred:
    def __init__(self, musicid: int) -> None:
        self.musicid = musicid
        self.musickey = "key"


class _FakeService:
    def __init__(self, *, authed: bool = True, musicid: int = 12345) -> None:
        self.is_authenticated = authed
        self._cred = _FakeCred(musicid) if authed else None
        self.connected = False
        self.daily_calls = 0

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    def _effective_credential(self) -> _FakeCred | None:
        return self._cred

    # --- Home ---
    async def get_daily_recommend_songs(self, *, limit: int = 30) -> list[Song]:
        self.daily_calls += 1
        return [
            Song(
                mid=f"d{i}",
                name=f"每日{i}",
                singers=[Singer(mid="s", name="歌手")],
                media_mid=f"m{i}",
                id=i,
            )
            for i in range(3)
        ]

    async def get_recommend_playlists(self, *, limit: int = 8) -> list[Playlist]:
        return [Playlist(pid="p1", name="今日推荐", creator="QQ", song_count=30)]

    async def get_recommend_new_songs(self, *, limit: int = 12) -> list[Song]:
        return [Song(mid="n1", name="新歌", singers=[Singer(mid="s", name="歌手")])]

    async def get_top_categories(self, *, limit_per_group: int | None = None) -> list[TopList]:
        return [TopList(top_id=4, name="流行榜", total_num=100)]

    # --- Library ---
    async def get_my_playlists(self) -> list[Playlist]:
        return [Playlist(pid="mine1", name="我的歌单", creator="me", song_count=10, is_mine=True)]

    async def get_liked_songs(self) -> list[Song]:
        return []


def _card(title: str, kind: str = "playlist", cid: str = "x") -> dict:
    return {"kind": kind, "id": cid, "title": title, "subtitle": "", "coverUrl": "", "meta": ""}


# ----------------------------------------------------------------- account_key
def test_account_key_stable_and_distinct() -> None:
    sc = ServiceController(service=_FakeService(authed=True, musicid=999))  # type: ignore[arg-type]
    key = sc.account_key()
    assert key
    assert sc.account_key() == key  # 稳定
    other = ServiceController(service=_FakeService(authed=True, musicid=1000))  # type: ignore[arg-type]
    assert other.account_key() != key  # 不同账号不同


def test_account_key_empty_when_logged_out() -> None:
    sc = ServiceController(service=_FakeService(authed=False))  # type: ignore[arg-type]
    assert sc.account_key() == ""


# ----------------------------------------------------------------- Home: 回写
async def test_refresh_persists_public_and_private(tmp_path: Path) -> None:
    cache = HomeCache(tmp_path / "home.json")
    sc = ServiceController(service=_FakeService(authed=True, musicid=42))  # type: ignore[arg-type]
    home = HomeController(sc, home_cache=cache)

    await home.refresh_home_async()

    key = sc.account_key()
    snap = cache.load(key)
    assert [s.mid for s in snap.daily] == ["d0", "d1", "d2"]
    assert snap.playlists[0]["title"] == "今日推荐"
    assert snap.new_songs[0].mid == "n1"
    assert snap.tops[0]["title"] == "流行榜"
    # daily 私有: 换账号读不到, 但公共仍在
    other = cache.load("other-key")
    assert other.daily == []
    assert other.playlists and other.tops


# ----------------------------------------------------------------- Home: prime
async def test_prime_public_fills_models_without_network(tmp_path: Path) -> None:
    cache = HomeCache(tmp_path / "home.json")
    cache.update(
        playlists=[_card("缓存歌单")],
        new_songs=[Song(mid="c1", name="缓存新歌")],
        tops=[_card("缓存榜", kind="top", cid="t")],
    )
    sc = ServiceController(service=_FakeService(authed=True))  # type: ignore[arg-type]
    home = HomeController(sc, home_cache=cache)

    home.prime_public_from_cache()

    assert home.playlistModel.cardAt(0)["title"] == "缓存歌单"
    assert home.newSongModel.count == 1
    assert home.topModel.count == 1
    assert home.dailyModel.count == 0  # daily 私有, prime_public 不碰


async def test_prime_private_respects_account(tmp_path: Path) -> None:
    cache = HomeCache(tmp_path / "home.json")
    sc = ServiceController(service=_FakeService(authed=True, musicid=7))  # type: ignore[arg-type]
    key = sc.account_key()
    cache.update(daily=[Song(mid="cd1", name="缓存每日")], account_key=key)

    matched = HomeController(sc, home_cache=cache)
    matched.prime_private_from_cache(key)
    assert matched.dailyModel.count == 1
    assert matched.dailyPreviewSong["name"] == "缓存每日"

    mismatched = HomeController(sc, home_cache=cache)
    mismatched.prime_private_from_cache("wrong-key")
    assert mismatched.dailyModel.count == 0


async def test_prime_does_not_clobber_fresh_data(tmp_path: Path) -> None:
    cache = HomeCache(tmp_path / "home.json")
    cache.update(tops=[_card("旧榜", kind="top", cid="old")])
    sc = ServiceController(service=_FakeService(authed=True))  # type: ignore[arg-type]
    home = HomeController(sc, home_cache=cache)

    await home.refresh_top_lists_async()  # 网络数据先到
    assert home.topModel.cardAt(0)["title"] == "流行榜"

    home.prime_public_from_cache()  # 再 prime 不应覆盖 (count>0)
    assert home.topModel.cardAt(0)["title"] == "流行榜"


async def test_logout_clears_private_cache(tmp_path: Path) -> None:
    cache = HomeCache(tmp_path / "home.json")
    sc = ServiceController(service=_FakeService(authed=True, musicid=5))  # type: ignore[arg-type]
    key = sc.account_key()
    cache.update(
        daily=[Song(mid="d", name="每日")],
        my_playlists=[_card("我的", cid="m")],
        tops=[_card("榜", kind="top", cid="t")],
        account_key=key,
    )
    # HomeController 订阅 sc.authStateChanged, 登出时清理私有缓存; 必须持有引用否则 GC 立即断开 slot
    _home = HomeController(sc, home_cache=cache)  # noqa: F841

    sc._service.is_authenticated = False  # type: ignore[attr-defined]
    sc.authStateChanged.emit()  # 登出

    snap = cache.load(key)
    assert snap.daily == []
    assert snap.my_playlists == []
    assert snap.tops and snap.tops[0]["title"] == "榜"  # 公共保留


# ----------------------------------------------------------------- Library
async def test_library_refresh_persists_my_playlists(tmp_path: Path) -> None:
    cache = HomeCache(tmp_path / "home.json")
    sc = ServiceController(service=_FakeService(authed=True, musicid=8))  # type: ignore[arg-type]
    lib = LibraryController(sc, home_cache=cache)

    await lib.refresh_my_playlists_async()

    key = sc.account_key()
    assert cache.load(key).my_playlists[0]["title"] == "我的歌单"
    assert cache.load("other").my_playlists == []  # 账号隔离


# ----------------------------------------------------------------- daily TTL
async def test_daily_cache_records_and_returns_updated_at(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """HomeCache.update(daily=...) 写入 updated_at; load 私有匹配时返回."""
    monkeypatch.setattr("time.time", lambda: 1700000000.0)
    cache = HomeCache(tmp_path / "home.json")
    cache.update(daily=[Song(mid="x", name="x")], account_key="k1")
    snap = cache.load("k1")
    assert snap.daily_updated_at == 1700000000.0
    # 账号不匹配 -> 私有信息全部丢弃, 时间戳也置 0
    other = cache.load("k2")
    assert other.daily_updated_at == 0.0


async def test_refresh_daily_skips_when_cache_within_ttl(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """缓存 < 6h 时, refresh_daily_thirty_async 不发网络请求, 保留缓存内容."""
    monkeypatch.setattr("time.time", lambda: 1000.0)
    cache = HomeCache(tmp_path / "home.json")
    service = _FakeService(authed=True, musicid=42)
    sc = ServiceController(service=service)  # type: ignore[arg-type]
    key = sc.account_key()
    cache.update(daily=[Song(mid="cached", name="缓存歌")], account_key=key)

    monkeypatch.setattr("time.time", lambda: 1000.0 + 5 * 3600)  # 5h 后, 仍新鲜
    home = HomeController(sc, home_cache=cache)
    home.prime_private_from_cache(key)
    assert service.daily_calls == 0

    await home.refresh_daily_thirty_async()

    assert service.daily_calls == 0
    assert home.dailyModel.count == 1
    assert home.dailyModel.songAt(0)["mid"] == "cached"


async def test_refresh_daily_runs_when_cache_stale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """缓存 > 6h 时, refresh_daily_thirty_async 拉取新数据并覆盖."""
    monkeypatch.setattr("time.time", lambda: 1000.0)
    cache = HomeCache(tmp_path / "home.json")
    service = _FakeService(authed=True, musicid=42)
    sc = ServiceController(service=service)  # type: ignore[arg-type]
    key = sc.account_key()
    cache.update(daily=[Song(mid="cached", name="缓存歌")], account_key=key)

    monkeypatch.setattr("time.time", lambda: 1000.0 + 7 * 3600)  # 7h 后, 过期
    home = HomeController(sc, home_cache=cache)
    home.prime_private_from_cache(key)

    await home.refresh_daily_thirty_async()

    assert service.daily_calls == 1
    assert home.dailyModel.songAt(0)["mid"] == "d0"


async def test_refresh_daily_force_overrides_freshness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """force=True (用户主动下拉刷新) 即使缓存新鲜也强制拉网络."""
    monkeypatch.setattr("time.time", lambda: 1000.0)
    cache = HomeCache(tmp_path / "home.json")
    service = _FakeService(authed=True, musicid=42)
    sc = ServiceController(service=service)  # type: ignore[arg-type]
    key = sc.account_key()
    cache.update(daily=[Song(mid="cached", name="缓存歌")], account_key=key)

    monkeypatch.setattr("time.time", lambda: 1000.0 + 60)  # 1 分钟后
    home = HomeController(sc, home_cache=cache)
    home.prime_private_from_cache(key)

    await home.refresh_daily_thirty_async(force=True)

    assert service.daily_calls == 1


async def test_library_prime_fills_my_playlists(tmp_path: Path) -> None:
    cache = HomeCache(tmp_path / "home.json")
    sc = ServiceController(service=_FakeService(authed=True, musicid=8))  # type: ignore[arg-type]
    key = sc.account_key()
    cache.update(my_playlists=[_card("缓存我的", cid="m")], account_key=key)
    lib = LibraryController(sc, home_cache=cache)

    lib.prime_from_cache(key)

    assert lib.playlistModel.cardAt(0)["title"] == "缓存我的"
