pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

Item {
    id: root

    property string routeName: "now-playing"
    property var playerController
    readonly property var currentSong: root.playerController ? root.playerController.currentSong : ({})
    readonly property bool hasSong: currentSong
        && typeof currentSong.name === "string"
        && currentSong.name.length > 0
    readonly property int queueCount: root.playerController && root.playerController.queueModel
        ? root.playerController.queueModel.count
        : 0
    readonly property int coverSize: Math.max(220, Math.min(root.width >= 980 ? 420 : 340, root.height - 220))

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

    RowLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s6

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: ThemeTokens.Spacing.s5

            Rectangle {
                Layout.preferredWidth: root.coverSize
                Layout.preferredHeight: root.coverSize
                Layout.alignment: Qt.AlignHCenter
                radius: ThemeTokens.Spacing.radiusLg
                color: root.hasSong ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.surfaceVariant
                border.color: ThemeTokens.Palette.outline

                Label {
                    anchors.centerIn: parent
                    text: "♪"
                    color: ThemeTokens.Palette.primary
                    font.pixelSize: ThemeTokens.TypeScale.display
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.currentSong.name : qsTr("尚未播放")
                    color: ThemeTokens.Palette.onSurface
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.singerText(root.currentSong) : qsTr("选择一首歌曲后开始")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 104
                radius: ThemeTokens.Spacing.radiusMd
                color: ThemeTokens.Palette.surface
                border.color: ThemeTokens.Palette.outline

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: ThemeTokens.Spacing.s5
                    spacing: ThemeTokens.Spacing.s2

                    Label {
                        Layout.fillWidth: true
                        text: root.hasSong ? root.currentSong.name : qsTr("暂无歌词")
                        color: ThemeTokens.Palette.onSurface
                        horizontalAlignment: Text.AlignHCenter
                        font.pixelSize: ThemeTokens.TypeScale.h2
                        font.weight: ThemeTokens.TypeScale.medium
                        elide: Text.ElideRight
                    }

                    Label {
                        Layout.fillWidth: true
                        text: root.hasSong ? qsTr("暂无歌词") : qsTr("播放后显示歌曲信息")
                        color: ThemeTokens.Palette.onSurfaceVariant
                        horizontalAlignment: Text.AlignHCenter
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Rectangle {
            Layout.preferredWidth: root.width >= 980 ? 340 : 280
            Layout.fillHeight: true
            radius: ThemeTokens.Spacing.radiusMd
            color: ThemeTokens.Palette.surface
            border.color: ThemeTokens.Palette.outline
            visible: root.width >= 760

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: ThemeTokens.Spacing.s4
                spacing: ThemeTokens.Spacing.s3

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    spacing: ThemeTokens.Spacing.s3

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("当前队列")
                            color: ThemeTokens.Palette.onSurface
                            font.pixelSize: ThemeTokens.TypeScale.body
                            font.weight: ThemeTokens.TypeScale.medium
                            elide: Text.ElideRight
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("%1 首歌曲").arg(root.queueCount)
                            color: ThemeTokens.Palette.onSurfaceVariant
                            font.pixelSize: ThemeTokens.TypeScale.caption
                            elide: Text.ElideRight
                        }
                    }

                    Button {
                        id: queueButton

                        Layout.preferredWidth: 68
                        Layout.preferredHeight: 34
                        text: qsTr("待播")
                        Accessible.name: qsTr("打开待播列表")
                        onClicked: root.queueRequested()

                        contentItem: Label {
                            text: queueButton.text
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: ThemeTokens.Palette.onSurface
                            font.pixelSize: ThemeTokens.TypeScale.caption
                        }

                        background: Rectangle {
                            radius: ThemeTokens.Spacing.radiusMd
                            color: queueButton.down
                                ? ThemeTokens.Palette.statePressed
                                : queueButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                            border.color: ThemeTokens.Palette.outline
                        }
                    }
                }

                ListView {
                    id: queueList

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: ThemeTokens.Spacing.s2
                    model: root.playerController ? root.playerController.queueModel : null
                    currentIndex: root.playerController ? root.playerController.currentIndex : -1
                    boundsBehavior: Flickable.StopAtBounds
                    reuseItems: true

                    delegate: Components.QueueRow {
                        id: queueRow

                        width: ListView.view.width
                        current: queueRow.index === queueList.currentIndex
                        onActivated: function(songData, row) {
                            if (root.playerController)
                                root.playerController.playQueueIndex(row)
                        }
                    }

                    ScrollBar.vertical: ScrollBar {}
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.queueCount === 0
                    text: qsTr("暂无待播歌曲")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                }
            }
        }
    }
}
