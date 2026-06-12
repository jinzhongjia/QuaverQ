"""首屏发现页快照 (home.json) 单测 — SWR: 先显缓存再后台刷新.

公共区块 (playlists/new_songs/tops): 无条件恢复.
私有区块 (daily/my_playlists): 仅 account_key 匹配才恢复 (跨账号隔离).
容错: 缺失/损坏/版本不符 -> 空快照, 不抛.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quaverq.core.home_cache import HomeCache, HomeSnapshot
from quaverq.core.models import Singer, Song, UserProfile

ACC = "acc-123"
OTHER = "acc-999"


@pytest.fixture
def home_cache(tmp_path: Path) -> HomeCache:
    return HomeCache(tmp_path / "home.json")


def _song(mid: str, name: str = "歌") -> Song:
    return Song(
        mid=mid,
        name=name,
        singers=[Singer(mid="s", name="歌手")],
        cover_url=f"http://c/{mid}.jpg",
        media_mid=f"m{mid}",
        id=int(mid) if mid.isdigit() else 0,
    )


def _card(kind: str, cid: str) -> dict:
    return {
        "kind": kind,
        "id": cid,
        "title": f"{kind}-{cid}",
        "subtitle": "副标题",
        "coverUrl": f"http://c/{cid}.jpg",
        "meta": "10 首",
    }


# ----------------------------------------------------------------- 缺失 / 空
def test_load_missing_file_returns_empty(home_cache: HomeCache) -> None:
    snap = home_cache.load(account_key=ACC)
    assert isinstance(snap, HomeSnapshot)
    assert snap.is_empty()


# ----------------------------------------------------------------- 往返
def test_update_then_load_round_trips_all_sections(home_cache: HomeCache) -> None:
    home_cache.update(
        daily=[_song("001")],
        new_songs=[_song("002")],
        playlists=[_card("playlist", "p1")],
        tops=[_card("top", "t1")],
        my_playlists=[_card("playlist", "mine1")],
        account_key=ACC,
    )
    snap = home_cache.load(account_key=ACC)
    assert [s.mid for s in snap.daily] == ["001"]
    assert [s.mid for s in snap.new_songs] == ["002"]
    assert snap.playlists == [_card("playlist", "p1")]
    assert snap.tops == [_card("top", "t1")]
    assert snap.my_playlists == [_card("playlist", "mine1")]


def test_daily_song_playback_fields_survive(home_cache: HomeCache) -> None:
    # 播放依赖 mid/media_mid/id; 必须完整往返
    home_cache.update(daily=[_song("123")], account_key=ACC)
    song = home_cache.load(account_key=ACC).daily[0]
    assert song.mid == "123"
    assert song.media_mid == "m123"
    assert song.id == 123


# ----------------------------------------------------------------- 账号隔离
def test_private_sections_dropped_on_account_mismatch(home_cache: HomeCache) -> None:
    home_cache.update(
        daily=[_song("1")],
        my_playlists=[_card("playlist", "mine")],
        playlists=[_card("playlist", "pub")],
        account_key=ACC,
    )
    snap = home_cache.load(account_key=OTHER)
    assert snap.daily == []
    assert snap.my_playlists == []
    assert snap.playlists == [_card("playlist", "pub")]


def test_private_sections_dropped_when_no_account(home_cache: HomeCache) -> None:
    home_cache.update(daily=[_song("1")], tops=[_card("top", "t")], account_key=ACC)
    snap = home_cache.load(account_key="")
    assert snap.daily == []
    assert snap.tops == [_card("top", "t")]


def test_private_sections_have_independent_account_keys(home_cache: HomeCache) -> None:
    # 账号切换: daily 已属新账号, my_playlists 仍属旧账号 -> 各自独立判定
    home_cache.update(my_playlists=[_card("playlist", "old")], account_key=OTHER)
    home_cache.update(daily=[_song("1")], account_key=ACC)
    snap = home_cache.load(account_key=ACC)
    assert [s.mid for s in snap.daily] == ["1"]  # 属 ACC -> 恢复
    assert snap.my_playlists == []  # 属 OTHER -> 丢弃


def test_public_sections_restore_regardless_of_account(home_cache: HomeCache) -> None:
    home_cache.update(
        playlists=[_card("playlist", "p")],
        new_songs=[_song("9")],
        tops=[_card("top", "t")],
    )
    snap = home_cache.load(account_key=OTHER)
    assert snap.playlists and snap.new_songs and snap.tops


# ----------------------------------------------------------------- 合并写
def test_update_merges_only_provided_sections(home_cache: HomeCache) -> None:
    home_cache.update(playlists=[_card("playlist", "p1")], tops=[_card("top", "t1")])
    # 第二次只更新 tops (模拟 playlists 刷新失败 -> 不传该 section)
    home_cache.update(tops=[_card("top", "t2")])
    snap = home_cache.load(account_key=ACC)
    assert snap.playlists == [_card("playlist", "p1")]  # 旧值保留
    assert snap.tops == [_card("top", "t2")]  # 新值覆盖


def test_update_empty_list_clears_section(home_cache: HomeCache) -> None:
    # 空 list = 明确"本次结果为空" (区别于 None = 不更新)
    home_cache.update(tops=[_card("top", "t1")])
    home_cache.update(tops=[])
    assert home_cache.load(account_key=ACC).tops == []


def test_update_creates_parent_dirs(tmp_path: Path) -> None:
    cache = HomeCache(tmp_path / "nested" / "deep" / "home.json")
    cache.update(tops=[_card("top", "t")])
    assert cache.path.exists()


# ----------------------------------------------------------------- 容错
def test_corrupt_json_returns_empty(home_cache: HomeCache) -> None:
    home_cache.path.write_text("{ not json", encoding="utf-8")
    assert home_cache.load(account_key=ACC).is_empty()


def test_version_mismatch_returns_empty(home_cache: HomeCache) -> None:
    home_cache.path.write_text(
        json.dumps({"version": 999, "sections": {"tops": {"cards": [_card("top", "t")]}}}),
        encoding="utf-8",
    )
    assert home_cache.load(account_key=ACC).is_empty()


# ----------------------------------------------------------------- 登出 / 清理
def test_clear_private_keeps_public(home_cache: HomeCache) -> None:
    home_cache.update(
        daily=[_song("1")],
        my_playlists=[_card("playlist", "mine")],
        playlists=[_card("playlist", "pub")],
        tops=[_card("top", "t")],
        account_key=ACC,
    )
    home_cache.clear_private()
    snap = home_cache.load(account_key=ACC)  # 即便账号匹配, 私有已被抹掉
    assert snap.daily == []
    assert snap.my_playlists == []
    assert snap.playlists and snap.tops


def test_clear_removes_file(home_cache: HomeCache) -> None:
    home_cache.update(tops=[_card("top", "t")])
    assert home_cache.path.exists()
    home_cache.clear()
    assert not home_cache.path.exists()
    assert home_cache.load(account_key=ACC).is_empty()


# ============================================================== profile 私有区块 (C4 身份缓存)


def _profile(nickname: str = "影翼") -> UserProfile:
    return UserProfile(
        nickname=nickname,
        avatar_url="http://thirdqq.qlogo.cn/g?k=abc",
        vip_kind="svip",
        is_year_vip=True,
        vip_icon_url="http://y.gtimg.cn/mediastyle/global/vip_icon/lv_7.png",
    )


def test_profile_round_trips(home_cache: HomeCache) -> None:
    home_cache.update(profile=_profile(), account_key=ACC)
    snap = home_cache.load(account_key=ACC)
    assert snap.profile == _profile()


def test_profile_dropped_on_account_mismatch(home_cache: HomeCache) -> None:
    home_cache.update(profile=_profile(), account_key=ACC)
    assert home_cache.load(account_key=OTHER).profile is None
    assert home_cache.load(account_key="").profile is None


def test_profile_none_keeps_existing(home_cache: HomeCache) -> None:
    """profile=None 表示"本次不更新" (与 daily 的 None 语义一致)."""
    home_cache.update(profile=_profile(), account_key=ACC)
    home_cache.update(daily=[_song("1")], account_key=ACC)  # 不带 profile
    assert home_cache.load(account_key=ACC).profile == _profile()


def test_clear_private_wipes_profile(home_cache: HomeCache) -> None:
    home_cache.update(profile=_profile(), account_key=ACC)
    home_cache.clear_private()
    assert home_cache.load(account_key=ACC).profile is None


def test_profile_tolerates_missing_fields(home_cache: HomeCache) -> None:
    """旧版缓存 / 手工损坏的 profile 块: 缺字段回默认值, 不抛."""
    home_cache.update(profile=_profile(), account_key=ACC)
    raw = json.loads(home_cache.path.read_text(encoding="utf-8"))
    raw["sections"]["profile"]["data"] = {"nickname": "只有昵称"}
    home_cache.path.write_text(json.dumps(raw), encoding="utf-8")

    snap = home_cache.load(account_key=ACC)
    assert snap.profile is not None
    assert snap.profile.nickname == "只有昵称"
    assert snap.profile.vip_kind == ""
    assert snap.profile.is_year_vip is False
