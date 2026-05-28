pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../panels" as Panels
import "../Theme" as ThemeTokens

Item {
    id: root

    property string routeName: "now-playing"
    property var playerController
    property var libraryController
    property var lyricController
    readonly property var currentSong: root.playerController ? root.playerController.currentSong : ({})
    readonly property bool hasSong: currentSong
        && typeof currentSong.name === "string"
        && currentSong.name.length > 0
    readonly property int queueCount: root.playerController && root.playerController.queueModel
        ? root.playerController.queueModel.count
        : 0
    readonly property int headerCoverSize: root.width >= 900 ? 112 : 88

    signal queueRequested()

    function singerText(songData) {
        if (!songData)
            return ""
        if (songData.singerNames && songData.singerNames.length > 0)
            return songData.singerNames.join(" / ")
        if (songData.singers && songData.singers.length > 0)
            return songData.singers.map(function(singer) { return singer.name }).join(" / ")
        return songData.albumName || ""
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s5

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(root.headerCoverSize, 96)
            spacing: ThemeTokens.Spacing.s5

            Components.AlbumArt {
                Layout.preferredWidth: root.headerCoverSize
                Layout.preferredHeight: root.headerCoverSize
                Layout.alignment: Qt.AlignVCenter
                active: root.hasSong
                iconSize: ThemeTokens.TypeScale.h1
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.currentSong.name : qsTr("尚未播放")
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.singerText(root.currentSong) : qsTr("选择一首歌曲后开始")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }
            }

            Components.LikeButton {
                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                Layout.alignment: Qt.AlignVCenter
                libraryController: root.libraryController
                song: root.currentSong
            }

            Button {
                id: queueButton

                Layout.preferredWidth: root.queueCount > 99 ? 96 : 84
                Layout.preferredHeight: 38
                Layout.alignment: Qt.AlignVCenter
                text: root.queueCount > 0 ? qsTr("待播 %1").arg(root.queueCount) : qsTr("待播")
                Accessible.name: qsTr("打开待播列表")
                onClicked: root.queueRequested()

                contentItem: Label {
                    text: queueButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: queueButton.down
                        ? ThemeTokens.Palette.statePressed
                        : queueButton.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant
                    border.color: "transparent"
                }
            }
        }

        Panels.LyricPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            compact: false
            hasSong: root.hasSong
            lyricController: root.lyricController
        }
    }
}
