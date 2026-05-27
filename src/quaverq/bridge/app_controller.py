"""Application-level QObject exposed to QML."""

from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot


class AppController(QObject):
    """Small QML-facing app state holder.

    Login wiring lands in the later auth phase; Q2 only exposes stable properties
    so QML can bind against the final controller shape.
    """

    authedChanged = Signal()
    authChanged = Signal(bool, str)
    credExpired = Signal()
    darkModeChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._authed = False
        self._dark_mode = False

    @Property(bool, notify=authedChanged)
    def authed(self) -> bool:
        return self._authed

    @Property(bool, notify=darkModeChanged)
    def darkMode(self) -> bool:
        return self._dark_mode

    @Slot()
    def loginByQrCode(self) -> None:
        self.credExpired.emit()

    @Slot()
    def logout(self) -> None:
        if not self._authed:
            return
        self._authed = False
        self.authedChanged.emit()
        self.authChanged.emit(False, "logout")
