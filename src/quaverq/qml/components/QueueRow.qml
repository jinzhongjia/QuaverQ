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
    property bool current: false
    property var coverController
    readonly property string coverUrl: root.song && root.song.coverUrl ? root.song.coverUrl : ""

    readonly property string metaText: root.albumName
        ? qsTr("%1 · %2").arg(root.singers).arg(root.albumName)
        : root.singers
    readonly property string accessibleText: root.albumName
        ? qsTr("%1, %2, %3").arg(root.name).arg(root.singers).arg(root.albumName)
        : qsTr("%1, %2").arg(root.name).arg(root.singers)

    signal activated(var songData, int row)

    implicitHeight: 56
    radius: ThemeTokens.Spacing.radiusMd
    color: root.current
        ? ThemeTokens.Palette.stateSelected
        : hoverHandler.hovered ? ThemeTokens.Palette.stateHover : "transparent"

    Accessible.role: Accessible.ListItem
    Accessible.name: root.current
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
        visible: root.current
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
        anchors.rightMargin: ThemeTokens.Spacing.s3
        spacing: ThemeTokens.Spacing.s3

        Label {
            Layout.preferredWidth: 24
            text: root.current ? "♪" : (root.index >= 0 ? String(root.index + 1) : "")
            color: root.current ? ThemeTokens.Palette.primary : ThemeTokens.Palette.surfaceVariantText
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
            font.weight: root.current ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
        }

        AlbumArt {
            Layout.preferredWidth: 38
            Layout.preferredHeight: 38
            compact: true
            active: root.current
            coverUrl: root.coverUrl
            coverController: root.coverController
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s2

            RowLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: root.name
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: root.current ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
                    elide: Text.ElideRight
                }

                Rectangle {
                    Layout.preferredWidth: 58
                    Layout.preferredHeight: 22
                    visible: root.current
                    radius: ThemeTokens.Spacing.radiusSm
                    color: ThemeTokens.Palette.primaryContainer

                    Label {
                        anchors.centerIn: parent
                        text: qsTr("播放中")
                        color: ThemeTokens.Palette.primary
                        font.pixelSize: ThemeTokens.TypeScale.caption
                        font.weight: ThemeTokens.TypeScale.medium
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                text: root.metaText
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }
        }

        Label {
            Layout.preferredWidth: 42
            text: root.durationText
            color: ThemeTokens.Palette.surfaceVariantText
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
        }
    }
}
