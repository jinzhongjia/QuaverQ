"""QAbstractListModel adapters for QML."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    Signal,
    Slot,
)

from quaverq.core.models import Album, LyricLine, Playlist, Singer, Song, TopList


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "--:--"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def song_to_map(song: Song) -> dict[str, Any]:
    """Convert a core Song into a QVariantMap-friendly dict."""
    return {
        "mid": song.mid,
        "name": song.name,
        "singers": [
            {"mid": singer.mid, "name": singer.name, "avatarUrl": singer.avatar_url}
            for singer in song.singers
        ],
        "singerNames": [singer.name for singer in song.singers],
        "albumMid": song.album_mid,
        "albumName": song.album_name,
        "coverUrl": song.cover_url,
        "duration": song.duration,
        "durationText": _format_duration(song.duration),
        "payPlay": song.pay_play,
        "mediaMid": song.media_mid,
        "id": song.id,
    }


def song_from_map(data: Mapping[str, Any] | Song) -> Song:
    """Convert a QVariantMap-friendly dict back into a core Song."""
    if isinstance(data, Song):
        return data

    singers_raw = data.get("singers") or []
    singers: list[Singer] = []
    for item in singers_raw:
        if isinstance(item, Mapping):
            singers.append(
                Singer(
                    mid=str(item.get("mid", "") or ""),
                    name=str(item.get("name", "") or ""),
                    avatar_url=str(item.get("avatarUrl", "") or ""),
                )
            )
        else:
            singers.append(Singer(mid="", name=str(item)))

    if not singers:
        singers = [Singer(mid="", name=str(name)) for name in data.get("singerNames", [])]

    return Song(
        mid=str(data.get("mid", "") or ""),
        name=str(data.get("name", "") or ""),
        singers=singers,
        album_mid=str(data.get("albumMid", "") or ""),
        album_name=str(data.get("albumName", "") or ""),
        cover_url=str(data.get("coverUrl", "") or ""),
        duration=int(data.get("duration", 0) or 0),
        pay_play=int(data.get("payPlay", 0) or 0),
        media_mid=str(data.get("mediaMid", "") or ""),
        id=int(data.get("id", 0) or 0),
    )


def _lyric_words_to_maps(line: LyricLine) -> list[dict[str, Any]]:
    """逐字 words -> QVariantMap-friendly dict 列表 (无逐字时为空)."""
    return [
        {"text": w.text, "startMs": w.start_ms, "durationMs": w.duration_ms} for w in line.words
    ]


def lyric_line_to_map(line: LyricLine) -> dict[str, Any]:
    """Convert a core LyricLine into a QVariantMap-friendly dict."""
    return {
        "timestampMs": line.timestamp_ms,
        "lineText": line.text,
        "translation": line.translation,
        "words": _lyric_words_to_maps(line),
    }


class SongListModel(QAbstractListModel):
    """Song list model with role names consumed directly by QML delegates."""

    SongRole = Qt.ItemDataRole.UserRole + 1
    MidRole = Qt.ItemDataRole.UserRole + 2
    NameRole = Qt.ItemDataRole.UserRole + 3
    SingersRole = Qt.ItemDataRole.UserRole + 4
    AlbumNameRole = Qt.ItemDataRole.UserRole + 5
    DurationTextRole = Qt.ItemDataRole.UserRole + 6
    CoverUrlRole = Qt.ItemDataRole.UserRole + 7

    countChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._songs: list[Song] = []

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._songs)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._songs)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._songs)):
            return None

        song = self._songs[index.row()]
        if role == self.SongRole:
            return song_to_map(song)
        if role == self.MidRole:
            return song.mid
        if role == self.NameRole or role == Qt.ItemDataRole.DisplayRole:
            return song.name
        if role == self.SingersRole:
            return " / ".join(song.singer_names)
        if role == self.AlbumNameRole:
            return song.album_name
        if role == self.DurationTextRole:
            return _format_duration(song.duration)
        if role == self.CoverUrlRole:
            return song.cover_url
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.SongRole: QByteArray(b"song"),
            self.MidRole: QByteArray(b"mid"),
            self.NameRole: QByteArray(b"name"),
            self.SingersRole: QByteArray(b"singers"),
            self.AlbumNameRole: QByteArray(b"albumName"),
            self.DurationTextRole: QByteArray(b"durationText"),
            self.CoverUrlRole: QByteArray(b"coverUrl"),
        }

    def set_songs(self, songs: list[Song]) -> None:
        new_songs = list(songs)
        if new_songs == self._songs:
            # 数据未变 (SWR: 网络结果与缓存相同) -> 跳过 reset, 避免列表整体重建闪烁
            return
        self.beginResetModel()
        self._songs = new_songs
        self.endResetModel()
        self.countChanged.emit()

    def songs(self) -> list[Song]:
        return list(self._songs)

    def clear(self) -> None:
        self.set_songs([])

    @Slot(int, result="QVariant")
    def songAt(self, row: int) -> dict[str, Any]:
        if not (0 <= row < len(self._songs)):
            return {}
        return song_to_map(self._songs[row])


def card_to_map(card: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a card mapping for QVariantMap-friendly QML consumption."""
    return {
        "kind": str(card.get("kind", "") or ""),
        "id": str(card.get("id", "") or ""),
        "title": str(card.get("title", "") or ""),
        "subtitle": str(card.get("subtitle", "") or ""),
        "coverUrl": str(card.get("coverUrl", "") or ""),
        "meta": str(card.get("meta", "") or ""),
    }


def playlist_to_card(playlist: Playlist) -> dict[str, Any]:
    """Convert a Playlist into a generic card."""
    subtitle = playlist.creator or playlist.description
    meta = f"{playlist.song_count} 首" if playlist.song_count else ""
    return card_to_map(
        {
            "kind": "playlist",
            "id": playlist.pid,
            "title": playlist.name,
            "subtitle": subtitle,
            "coverUrl": playlist.cover_url,
            "meta": meta,
        }
    )


def album_to_card(album: Album) -> dict[str, Any]:
    """Convert an Album into a generic card."""
    subtitle = album.singer_name or album.publish_date
    meta = f"{album.song_count} 首" if album.song_count else album.publish_date
    return card_to_map(
        {
            "kind": "album",
            "id": album.mid,
            "title": album.name,
            "subtitle": subtitle,
            "coverUrl": album.cover_url,
            "meta": meta,
        }
    )


def singer_to_card(singer: Singer) -> dict[str, Any]:
    """Convert a Singer into a generic card."""
    return card_to_map(
        {
            "kind": "artist",
            "id": singer.mid,
            "title": singer.name,
            "subtitle": "艺人",
            "coverUrl": singer.avatar_url,
            "meta": "",
        }
    )


def top_to_card(top: TopList) -> dict[str, Any]:
    """Convert a TopList into a generic card."""
    meta = f"{top.total_num} 首" if top.total_num else ""
    return card_to_map(
        {
            "kind": "top",
            "id": top.top_id,
            "title": top.name,
            "subtitle": top.intro or "排行榜",
            "coverUrl": top.cover_url,
            "meta": meta,
        }
    )


class CardListModel(QAbstractListModel):
    """Generic card model for playlists, albums, artists and top lists."""

    CardRole = Qt.ItemDataRole.UserRole + 1
    KindRole = Qt.ItemDataRole.UserRole + 2
    IdRole = Qt.ItemDataRole.UserRole + 3
    TitleRole = Qt.ItemDataRole.UserRole + 4
    SubtitleRole = Qt.ItemDataRole.UserRole + 5
    CoverUrlRole = Qt.ItemDataRole.UserRole + 6
    MetaRole = Qt.ItemDataRole.UserRole + 7

    countChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cards: list[dict[str, Any]] = []

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._cards)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._cards)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._cards)):
            return None

        card = self._cards[index.row()]
        if role == self.CardRole:
            return dict(card)
        if role == self.KindRole:
            return card["kind"]
        if role == self.IdRole:
            return card["id"]
        if role == self.TitleRole or role == Qt.ItemDataRole.DisplayRole:
            return card["title"]
        if role == self.SubtitleRole:
            return card["subtitle"]
        if role == self.CoverUrlRole:
            return card["coverUrl"]
        if role == self.MetaRole:
            return card["meta"]
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.CardRole: QByteArray(b"card"),
            self.KindRole: QByteArray(b"kind"),
            self.IdRole: QByteArray(b"cardId"),
            self.TitleRole: QByteArray(b"title"),
            self.SubtitleRole: QByteArray(b"subtitle"),
            self.CoverUrlRole: QByteArray(b"coverUrl"),
            self.MetaRole: QByteArray(b"meta"),
        }

    def set_cards(self, cards: list[Mapping[str, Any]]) -> None:
        new_cards = [card_to_map(card) for card in cards]
        if new_cards == self._cards:
            # 数据未变 (SWR: 网络结果与缓存相同) -> 跳过 reset, 避免网格整体重建闪烁
            return
        self.beginResetModel()
        self._cards = new_cards
        self.endResetModel()
        self.countChanged.emit()

    def cards(self) -> list[dict[str, Any]]:
        return [dict(card) for card in self._cards]

    def clear(self) -> None:
        self.set_cards([])

    @Slot(int, result="QVariant")
    def cardAt(self, row: int) -> dict[str, Any]:
        if not (0 <= row < len(self._cards)):
            return {}
        return dict(self._cards[row])


class LyricLineListModel(QAbstractListModel):
    """Lyric line model consumed by synchronized lyric views."""

    LineRole = Qt.ItemDataRole.UserRole + 1
    TimestampMsRole = Qt.ItemDataRole.UserRole + 2
    LineTextRole = Qt.ItemDataRole.UserRole + 3
    TranslationRole = Qt.ItemDataRole.UserRole + 4
    WordsRole = Qt.ItemDataRole.UserRole + 5

    countChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lines: list[LyricLine] = []

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._lines)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._lines)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._lines)):
            return None

        line = self._lines[index.row()]
        if role == self.LineRole:
            return lyric_line_to_map(line)
        if role == self.TimestampMsRole:
            return line.timestamp_ms
        if role == self.LineTextRole or role == Qt.ItemDataRole.DisplayRole:
            return line.text
        if role == self.TranslationRole:
            return line.translation
        if role == self.WordsRole:
            return _lyric_words_to_maps(line)
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.LineRole: QByteArray(b"line"),
            self.TimestampMsRole: QByteArray(b"timestampMs"),
            self.LineTextRole: QByteArray(b"lineText"),
            self.TranslationRole: QByteArray(b"translation"),
            self.WordsRole: QByteArray(b"words"),
        }

    def set_lines(self, lines: list[LyricLine]) -> None:
        self.beginResetModel()
        self._lines = list(lines)
        self.endResetModel()
        self.countChanged.emit()

    def lines(self) -> list[LyricLine]:
        return list(self._lines)

    def clear(self) -> None:
        self.set_lines([])

    @Slot(int, result="QVariant")
    def lineAt(self, row: int) -> dict[str, Any]:
        if not (0 <= row < len(self._lines)):
            return {}
        return lyric_line_to_map(self._lines[row])
