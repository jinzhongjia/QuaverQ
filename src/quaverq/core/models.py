"""数据模型.

所有模型均为 dataclass，保持轻量、可序列化。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Singer:
    """歌手 (轻量引用, 用于嵌入 Song/Album)."""

    mid: str
    name: str
    avatar_url: str = ""


@dataclass
class Song:
    """歌曲."""

    mid: str
    name: str
    singers: list[Singer] = field(default_factory=list)
    album_mid: str = ""
    album_name: str = ""
    cover_url: str = ""
    duration: int = 0          # 秒
    pay_play: int = 0          # 0 免费 / 1 VIP / 2 单独购买
    file_qualities: set[str] = field(default_factory=set)  # {"MP3_128", "FLAC", ...}
    media_mid: str = ""        # get_song_urls 所需
    id: int = 0                # QQ 数字 ID, like/unlike API 需要 (mid 不够)

    @property
    def singer_names(self) -> list[str]:
        """便捷属性: 仅取歌手名 (向后兼容旧调用点)."""
        return [s.name for s in self.singers]


@dataclass
class SongUrl:
    """歌曲播放地址."""

    mid: str
    url: str
    quality: str = ""          # "MP3_128" / "MP3_320" / "FLAC" / ...
    expires_at: int = 0        # unix 时间戳, 0 = 未知
    size: int = 0              # 字节


@dataclass
class LyricLine:
    """单行歌词 (带可选翻译)."""

    timestamp_ms: int
    text: str
    translation: str = ""


@dataclass
class Lyric:
    """歌词."""

    mid: str
    lines: list[LyricLine] = field(default_factory=list)
    has_translation: bool = False
    has_romanji: bool = False


@dataclass
class Album:
    """专辑."""

    mid: str
    name: str
    singers: list[Singer] = field(default_factory=list)
    cover_url: str = ""
    publish_date: str = ""
    description: str = ""
    song_count: int = 0
    songs: list[Song] = field(default_factory=list)

    @property
    def singer_name(self) -> str:
        """便捷属性: 主歌手名 (向后兼容)."""
        return self.singers[0].name if self.singers else ""


@dataclass
class ArtistDetail:
    """歌手详情 = 基本信息 + 热门歌曲 + 专辑列表."""

    singer: "Singer"
    description: str = ""
    hot_songs: list["Song"] = field(default_factory=list)
    albums: list["Album"] = field(default_factory=list)


@dataclass
class Playlist:
    """歌单."""

    pid: str
    name: str
    cover_url: str = ""
    description: str = ""
    creator: str = ""
    song_count: int = 0
    play_count: int = 0
    songs: list[Song] = field(default_factory=list)
    is_mine: bool = False      # True = 我创建的; False = 收藏的 / 外部


__all__ = [
    "Singer",
    "Song",
    "SongUrl",
    "Lyric",
    "LyricLine",
    "Album",
    "ArtistDetail",
    "Playlist",
]
