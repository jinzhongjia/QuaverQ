pragma Singleton

import QtQuick

QtObject {
    readonly property string systemMode: "system"
    readonly property string lightMode: "light"
    readonly property string darkMode: "dark"

    property string mode: systemMode
    property SystemPalette systemPalette: SystemPalette {}

    readonly property bool paletteDark: systemPalette.window.hslLightness < 0.5
    readonly property bool systemDark: Application.styleHints.colorScheme === Qt.ColorScheme.Dark
        || (Application.styleHints.colorScheme === Qt.ColorScheme.Unknown && paletteDark)
    readonly property bool dark: mode === darkMode || (mode === systemMode && systemDark)
}
