"""Song <-> dict 序列化.

state.json (会话快照) 与 home.json (首屏 SWR 缓存) 共用同一套 Song 序列化,
避免两处实现随 Song 字段演进而漂移 (尤其 file_qualities 是 set, JSON 不友好).
"""

from __future__ import annotations

from dataclasses import asdict

from .models import Singer, Song, UserProfile


def song_to_dict(song: Song) -> dict:
    """Song -> JSON 友好 dict (file_qualities set 转 list)."""
    data = asdict(song)
    data["file_qualities"] = list(song.file_qualities)
    return data


def song_from_dict(data: dict) -> Song:
    """dict -> Song; 容忍缺字段 / 多字段."""
    singers = [
        Singer(
            mid=s.get("mid", "") or "",
            name=s.get("name", "") or "",
            avatar_url=s.get("avatar_url", "") or "",
        )
        for s in (data.get("singers") or [])
    ]
    return Song(
        mid=data.get("mid", "") or "",
        name=data.get("name", "") or "",
        singers=singers,
        album_mid=data.get("album_mid", "") or "",
        album_name=data.get("album_name", "") or "",
        cover_url=data.get("cover_url", "") or "",
        duration=int(data.get("duration", 0) or 0),
        pay_play=int(data.get("pay_play", 0) or 0),
        file_qualities=set(data.get("file_qualities") or []),
        media_mid=data.get("media_mid", "") or "",
        id=int(data.get("id", 0) or 0),
    )


def user_profile_to_dict(profile: UserProfile) -> dict:
    """UserProfile -> JSON 友好 dict (home.json 身份区块缓存)."""
    return asdict(profile)


def user_profile_from_dict(data: dict) -> UserProfile:
    """dict -> UserProfile; 容忍缺字段 / 多字段 (旧版缓存升级安全)."""
    return UserProfile(
        nickname=str(data.get("nickname", "") or ""),
        avatar_url=str(data.get("avatar_url", "") or ""),
        vip_kind=str(data.get("vip_kind", "") or ""),
        is_year_vip=bool(data.get("is_year_vip", False)),
        vip_icon_url=str(data.get("vip_icon_url", "") or ""),
    )
