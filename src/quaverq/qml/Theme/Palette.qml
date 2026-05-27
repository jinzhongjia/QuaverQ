pragma Singleton

import QtQuick

QtObject {
    readonly property color background: Theme.dark ? "#0d0d10" : "#ffffff"
    readonly property color surface: Theme.dark ? "#161618" : "#f7f7f9"
    readonly property color surfaceVariant: Theme.dark ? "#1f2024" : "#ececf0"
    readonly property color surfaceContainerHigh: Theme.dark ? "#26272c" : "#e2e2e7"
    readonly property color onSurface: Theme.dark ? "#ececf1" : "#1a1a1f"
    readonly property color onSurfaceVariant: Theme.dark ? "#a3a3ad" : "#5e5e68"
    readonly property color outline: Theme.dark ? "#34353c" : "#d4d4d8"
    readonly property color primary: Theme.dark ? "#22c55e" : "#15803d"
    readonly property color onPrimary: Theme.dark ? "#0a0f0c" : "#ffffff"
    readonly property color primaryContainer: Theme.dark ? "#143524" : "#dcfce7"
    readonly property color error: Theme.dark ? "#ef4444" : "#b91c1c"
    readonly property color warning: Theme.dark ? "#f59e0b" : "#b45309"

    readonly property color stateHover: Theme.dark ? "#24252a" : "#ececf0"
    readonly property color statePressed: Theme.dark ? "#2d2f35" : "#e2e2e7"
    readonly property color stateSelected: primaryContainer
    readonly property color stateDisabled: Theme.dark ? "#303137" : "#dadade"
    readonly property color focusRing: primary
    readonly property color scrim: Theme.dark ? "#99000000" : "#66000000"
}
