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

from quaverq.core.models import (
    Album,
    DirectHit,
    LyricLine,
    Playlist,
    RelatedWord,
    Singer,
    Song,
    TopList,
)


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


def lyric_line_to_map(line: LyricLine, *, include_translation: bool = True) -> dict[str, Any]:
    """Convert a core LyricLine into a QVariantMap-friendly dict."""
    return {
        "timestampMs": line.timestamp_ms,
        "lineText": line.text,
        "translation": line.translation if include_translation else "",
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

    # ---- 粒度操作 (待播队列增删挪) ----
    # 整表 reset 会让 ListView 销毁全部 delegate 并滚回顶部 (待播面板开着时观感极差);
    # 队列的单点变动必须走 insert/remove/move 粒度信号, reset 仅用于整队列替换.

    def append_songs(self, songs: list[Song]) -> None:
        if not songs:
            return
        start = len(self._songs)
        self.beginInsertRows(QModelIndex(), start, start + len(songs) - 1)
        self._songs.extend(songs)
        self.endInsertRows()
        self.countChanged.emit()

    def insert_song(self, row: int, song: Song) -> None:
        row = max(0, min(int(row), len(self._songs)))
        self.beginInsertRows(QModelIndex(), row, row)
        self._songs.insert(row, song)
        self.endInsertRows()
        self.countChanged.emit()

    def remove_row(self, row: int) -> None:
        if not (0 <= row < len(self._songs)):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._songs[row]
        self.endRemoveRows()
        self.countChanged.emit()

    def move_row(self, from_row: int, to_row: int) -> None:
        """挪一行到目标位置 (语义同 list.pop(from) + insert(to)).

        beginMoveRows 的 destinationChild 语义: 向下移动时目标必须给"最终位置 + 1"
        (Qt 文档明确的经典坑), 这里统一换算, 调用方只管最终下标.
        """
        n = len(self._songs)
        if not (0 <= from_row < n) or not (0 <= to_row < n) or from_row == to_row:
            return
        dest = to_row + 1 if to_row > from_row else to_row
        if not self.beginMoveRows(QModelIndex(), from_row, from_row, QModelIndex(), dest):
            return
        song = self._songs.pop(from_row)
        self._songs.insert(to_row, song)
        self.endMoveRows()

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


# 综合搜索"直达"的 kind -> detailRequested 导航 kind (singer 走 artist 详情页).
_DIRECT_KIND_TO_DETAIL = {"singer": "artist", "album": "album"}
_DIRECT_KIND_LABEL = {"singer": "歌手", "album": "专辑"}


def direct_hit_to_map(hit: DirectHit) -> dict[str, Any]:
    """综合搜索直达 -> card 形态 (kind 已映射成 detailRequested 用的 artist/album)。"""
    return card_to_map(
        {
            "kind": _DIRECT_KIND_TO_DETAIL.get(hit.kind, hit.kind),
            "id": hit.mid,
            "title": hit.name,
            "subtitle": _DIRECT_KIND_LABEL.get(hit.kind, ""),
            "coverUrl": hit.cover_url,
            "meta": "",
        }
    )


def related_word_to_map(word: RelatedWord) -> dict[str, Any]:
    """综合搜索相关词 -> {display, keyword} (可点 chip)。"""
    return {"display": str(word.display or ""), "keyword": str(word.keyword or "")}


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
        self._translation_visible = True

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
            return lyric_line_to_map(line, include_translation=self._translation_visible)
        if role == self.TimestampMsRole:
            return line.timestamp_ms
        if role == self.LineTextRole or role == Qt.ItemDataRole.DisplayRole:
            return line.text
        if role == self.TranslationRole:
            return line.translation if self._translation_visible else ""
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

    def set_translation_visible(self, visible: bool) -> None:
        value = bool(visible)
        if self._translation_visible == value:
            return
        self._translation_visible = value
        if not self._lines:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._lines) - 1, 0)
        self.dataChanged.emit(top_left, bottom_right, [self.LineRole, self.TranslationRole])

    def lines(self) -> list[LyricLine]:
        return list(self._lines)

    def clear(self) -> None:
        self.set_lines([])

    @Slot(int, result="QVariant")
    def lineAt(self, row: int) -> dict[str, Any]:
        if not (0 <= row < len(self._lines)):
            return {}
        return lyric_line_to_map(
            self._lines[row],
            include_translation=self._translation_visible,
        )
