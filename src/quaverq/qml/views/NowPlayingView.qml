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
    property var coverController
    property var playerController
    property var libraryController
    property var lyricController
    property var settingsController
    readonly property var currentSong: root.playerController ? root.playerController.currentSong : ({})
    readonly property bool hasSong: currentSong
        && typeof currentSong.name === "string"
        && currentSong.name.length > 0

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

    Rectangle {
        anchors.fill: parent
        color: ThemeTokens.Palette.background
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s5

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s5

            Components.AlbumArt {
                Layout.preferredWidth: 72
                Layout.preferredHeight: 72
                Layout.alignment: Qt.AlignVCenter
                active: root.hasSong
                coverUrl: root.hasSong && root.currentSong.coverUrl ? root.currentSong.coverUrl : ""
                coverController: root.coverController
                iconSize: ThemeTokens.TypeScale.h2
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.currentSong.name : qsTr("尚未播放")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.bold
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.singerText(root.currentSong) : qsTr("选择一首歌曲后开始")
                    color: ThemeTokens.Palette.surfaceVariantText
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

            Components.IconButton {
                Layout.alignment: Qt.AlignVCenter
                text: qsTr("待播列表")
                iconText: "☰"
                iconColor: ThemeTokens.Palette.surfaceVariantText
                onClicked: root.queueRequested()
            }
        }

        Panels.LyricPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            compact: false
            hasSong: root.hasSong
            lyricController: root.lyricController
            settingsController: root.settingsController
        }
    }
}
