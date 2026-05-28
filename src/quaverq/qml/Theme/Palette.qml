pragma Singleton

import QtQuick

QtObject {
    readonly property color background: Theme.dark ? "#101115" : "#f5f7fb"
    readonly property color surface: Theme.dark ? "#17191f" : "#fbfcff"
    readonly property color surfaceElevated: Theme.dark ? "#1d2027" : "#ffffff"
    readonly property color surfaceVariant: Theme.dark ? "#242833" : "#eef2f7"
    readonly property color surfaceContainerHigh: Theme.dark ? "#2b303b" : "#e6ebf2"
    readonly property color sidebar: Theme.dark ? "#14161b" : "#f0f3f8"
    readonly property color onSurface: Theme.dark ? "#f1f3f6" : "#171a22"
    readonly property color onSurfaceVariant: Theme.dark ? "#a9b0bd" : "#626b7a"
    readonly property color outline: Theme.dark ? "#303744" : "#dfe5ee"
    readonly property color outlineMuted: Theme.dark ? "#252b35" : "#edf1f6"
    readonly property color windowBorder: Theme.dark ? "#444b57" : "#aeb8c5"
    readonly property color windowBorderInactive: Theme.dark ? "#313842" : "#d2d8e1"
    readonly property color primary: Theme.dark ? "#32d296" : "#12805c"
    readonly property color onPrimary: Theme.dark ? "#08130e" : "#ffffff"
    readonly property color primaryContainer: Theme.dark ? "#163c31" : "#dff7ec"
    readonly property color accent: Theme.dark ? "#8ea7ff" : "#4f67d8"
    readonly property color accentContainer: Theme.dark ? "#202a4c" : "#e8edff"
    readonly property color onAccent: Theme.dark ? "#0b1022" : "#ffffff"
    readonly property color albumSurface: Theme.dark ? "#273043" : "#e9edf7"
    readonly property color albumAccent: Theme.dark ? "#32d296" : "#12805c"
    readonly property color error: Theme.dark ? "#ef4444" : "#b91c1c"
    readonly property color warning: Theme.dark ? "#f59e0b" : "#b45309"

    readonly property color stateHover: Theme.dark ? "#222630" : "#edf2f8"
    readonly property color statePressed: Theme.dark ? "#2c3240" : "#e4ebf4"
    readonly property color stateSelected: primaryContainer
    readonly property color stateDisabled: Theme.dark ? "#30343d" : "#d8dee8"
    readonly property color focusRing: primary
    readonly property color scrim: Theme.dark ? "#99000000" : "#66000000"
}
