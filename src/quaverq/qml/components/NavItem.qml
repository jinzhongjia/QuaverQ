import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property string text: ""
    property string iconText: ""
    property bool selected: false
    property bool compact: false

    signal activated()

    implicitHeight: ThemeTokens.Spacing.toolHitSize
    radius: ThemeTokens.Spacing.radiusMd
    color: selected
        ? ThemeTokens.Palette.stateSelected
        : (hoverHandler.hovered ? ThemeTokens.Palette.stateHover : "transparent")

    Accessible.role: Accessible.Button
    Accessible.name: text

    HoverHandler {
        id: hoverHandler
    }

    TapHandler {
        onTapped: root.activated()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: compact ? 0 : ThemeTokens.Spacing.s4
        anchors.rightMargin: compact ? 0 : ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s3

        Label {
            Layout.alignment: Qt.AlignVCenter
            Layout.preferredWidth: compact ? parent.width : ThemeTokens.Spacing.s5
            text: iconText || text.slice(0, 1)
            horizontalAlignment: Text.AlignHCenter
            color: selected ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
            font.pixelSize: ThemeTokens.TypeScale.body
            font.weight: ThemeTokens.TypeScale.medium
        }

        Label {
            Layout.fillWidth: true
            visible: !compact
            text: root.text
            color: selected ? ThemeTokens.Palette.onSurface : ThemeTokens.Palette.onSurfaceVariant
            font.pixelSize: ThemeTokens.TypeScale.bodySm
            font.weight: selected ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
            elide: Text.ElideRight
        }
    }
}
