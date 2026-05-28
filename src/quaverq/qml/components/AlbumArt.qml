import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property bool active: false
    property bool compact: false
    property string iconText: "♪"
    property int iconSize: compact ? ThemeTokens.TypeScale.body : ThemeTokens.TypeScale.h2

    implicitWidth: compact ? 36 : 52
    implicitHeight: implicitWidth
    radius: compact ? ThemeTokens.Spacing.radiusMd : ThemeTokens.Spacing.radiusLg
    color: root.active ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.albumSurface
    border.color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.outlineMuted

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.min(34, Math.max(4, parent.width * 0.1))
        radius: parent.radius
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.accent
    }

    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: Math.max(5, parent.width * 0.12)
        anchors.bottomMargin: Math.max(5, parent.height * 0.12)
        width: Math.max(8, parent.width * 0.24)
        height: width
        radius: width / 2
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.accent
    }

    Label {
        anchors.centerIn: parent
        text: root.iconText
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
        font.pixelSize: root.iconSize
        font.weight: ThemeTokens.TypeScale.medium
    }
}
