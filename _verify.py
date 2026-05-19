"""Quick import verification for QuaverQ."""
from quaverq import __version__
print(f"quaverq version: {__version__}")

from quaverq.core.models import Song, Playlist, Album, Lyric, SongUrl, Singer
print("models: OK")

from quaverq.config import load
cfg = load()
print(f"config: OK (backend={cfg['ui']['backend']})")

from quaverq.ui import resolve_backend, check_availability
be = resolve_backend()
print(f"UI backend: {be}, available: {check_availability(be)}")

from quaverq.core.service import QuaverService
print("service: OK")

from quaverq.core.player import PlayState, create_player
player = create_player()
print(f"player: OK (type={type(player).__name__})")

from quaverq import config
print(f"config dir: {config.CONFIG_DIR}")

print("\nAll imports passed.")
