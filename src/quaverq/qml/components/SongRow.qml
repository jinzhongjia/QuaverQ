import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    required property var song
    required property string name
    required property string singers
    required property string albumName
    required property string durationText
    required property int index
    property bool selected: false

    readonly property string accessibleText: root.albumName
        ? qsTr("%1, %2, %3").arg(root.name).arg(root.singers).arg(root.albumName)
        : qsTr("%1, %2").arg(root.name).arg(root.singers)

    signal activated(var songData, int row)

    implicitHeight: 64
    radius: ThemeTokens.Spacing.radiusMd
    color: root.selected
        ? ThemeTokens.Palette.stateSelected
        : hoverHandler.hovered ? ThemeTokens.Palette.stateHover : "transparent"

    Accessible.role: Accessible.ListItem
    Accessible.name: root.selected
        ? qsTr("正在播放，%1").arg(root.accessibleText)
        : root.accessibleText
    activeFocusOnTab: true

    HoverHandler {
        id: hoverHandler
    }

    TapHandler {
        onTapped: root.activated(root.song, root.index)
    }

    Keys.onReturnPressed: root.activated(root.song, root.index)
    Keys.onSpacePressed: root.activated(root.song, root.index)

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 3
        visible: root.selected
        radius: width / 2
        color: ThemeTokens.Palette.primary
    }

    Rectangle {
        anchors.fill: parent
        visible: root.activeFocus
        radius: parent.radius
        color: "transparent"
        border.color: ThemeTokens.Palette.focusRing
        border.width: 2
        z: 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s4
        anchors.rightMargin: ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s4

        Label {
            Layout.preferredWidth: 28
            text: root.selected ? "♪" : (root.index >= 0 ? String(root.index + 1) : "")
            color: root.selected ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
            font.weight: root.selected ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
        }

        AlbumArt {
            Layout.preferredWidth: 46
            Layout.preferredHeight: 46
            active: root.selected
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s2

            Label {
                Layout.fillWidth: true
                text: root.name
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.body
                font.weight: root.selected ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: root.albumName ? qsTr("%1 · %2").arg(root.singers).arg(root.albumName) : root.singers
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }
        }

        Label {
            Layout.preferredWidth: 52
            text: root.durationText
            color: ThemeTokens.Palette.onSurfaceVariant
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
        }
    }
}
