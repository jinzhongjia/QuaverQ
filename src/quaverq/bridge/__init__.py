"""Qt bridge objects exposed to QML."""

from __future__ import annotations

from .app_controller import AppController
from .audio_device_controller import AudioDeviceController
from .cover_provider import CoverController, CoverImageProvider
from .detail_controller import DetailController, DetailControllerFactory
from .home_controller import HomeController
from .library_controller import LibraryController
from .lyric_controller import LyricController
from .lyric_dbus_controller import LyricsDBusController
from .models import (
    CardListModel,
    LyricLineListModel,
    SongListModel,
    card_to_map,
    song_from_map,
    song_to_map,
)
from .mpris_controller import MprisController
from .player_controller import PlayerController
from .service_controller import ServiceController
from .settings_controller import SettingsController
from .song_detail_controller import SongDetailController

__all__ = [
    "AppController",
    "AudioDeviceController",
    "CoverController",
    "CoverImageProvider",
    "DetailController",
    "DetailControllerFactory",
    "HomeController",
    "LibraryController",
    "LyricController",
    "LyricsDBusController",
    "MprisController",
    "PlayerController",
    "ServiceController",
    "SettingsController",
    "SongDetailController",
    "CardListModel",
    "LyricLineListModel",
    "SongListModel",
    "card_to_map",
    "song_from_map",
    "song_to_map",
]
