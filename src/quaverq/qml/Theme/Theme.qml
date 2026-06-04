pragma Singleton

import QtQuick

QtObject {
    readonly property string systemMode: "system"
    readonly property string lightMode: "light"
    readonly property string darkMode: "dark"

    property string mode: systemMode
    property SystemPalette systemPalette: SystemPalette {}

    readonly property bool paletteDark: systemPalette.window.hslLightness < 0.5
    // 默认用 Qt styleHints/palette；运行时由 Main 用 portal color-scheme 覆盖（Qt 的
    // colorScheme 在 GNOME/Wayland 把 portal prefer-dark 错映射成 Light，不可靠）
    property bool systemDark: Application.styleHints.colorScheme === Qt.ColorScheme.Dark
        || (Application.styleHints.colorScheme === Qt.ColorScheme.Unknown && paletteDark)
    readonly property bool dark: mode === darkMode || (mode === systemMode && systemDark)
}
