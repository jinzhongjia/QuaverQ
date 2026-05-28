"""QAbstractListModel adapters for QML."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from quaverq.core.models import LyricLine, Singer, Song


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


def lyric_line_to_map(line: LyricLine) -> dict[str, Any]:
    """Convert a core LyricLine into a QVariantMap-friendly dict."""
    return {
        "timestampMs": line.timestamp_ms,
        "lineText": line.text,
        "translation": line.translation,
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
        self.beginResetModel()
        self._songs = list(songs)
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


class LyricLineListModel(QAbstractListModel):
    """Lyric line model consumed by synchronized lyric views."""

    LineRole = Qt.ItemDataRole.UserRole + 1
    TimestampMsRole = Qt.ItemDataRole.UserRole + 2
    LineTextRole = Qt.ItemDataRole.UserRole + 3
    TranslationRole = Qt.ItemDataRole.UserRole + 4

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
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.LineRole: QByteArray(b"line"),
            self.TimestampMsRole: QByteArray(b"timestampMs"),
            self.LineTextRole: QByteArray(b"lineText"),
            self.TranslationRole: QByteArray(b"translation"),
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
