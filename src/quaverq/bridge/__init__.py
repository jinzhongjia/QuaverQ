"""Qt bridge objects exposed to QML."""

from __future__ import annotations

from .app_controller import AppController
from .cover_provider import CoverController, CoverImageProvider
from .detail_controller import DetailController, DetailControllerFactory
from .home_controller import HomeController
from .library_controller import LibraryController
from .lyric_controller import LyricController
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
    "CoverController",
    "CoverImageProvider",
    "DetailController",
    "DetailControllerFactory",
    "HomeController",
    "LibraryController",
    "LyricController",
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
