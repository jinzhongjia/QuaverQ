pragma Singleton

import QtQuick
import QtQuick.Controls

QtObject {
    readonly property string systemMode: "system"
    readonly property string lightMode: "light"
    readonly property string darkMode: "dark"

    property string mode: systemMode
    property bool reducedMotion: false

    readonly property bool systemDark: Application.styleHints.colorScheme === Qt.Dark
    readonly property bool dark: mode === darkMode || (mode === systemMode && systemDark)
}
