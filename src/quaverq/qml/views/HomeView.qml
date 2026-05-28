pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

ScrollView {
    id: root

    property string routeName: "home"
    property var playerController
    readonly property bool hasSong: root.playerController
        && root.playerController.currentSong
        && root.playerController.currentSong.name

    signal searchRequested(string keyword)
    signal detailRequested(string kind, string title, string subtitle)
    signal nowPlayingRequested()

    contentWidth: availableWidth

    ColumnLayout {
        width: root.availableWidth
        spacing: ThemeTokens.Spacing.s6

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            Layout.topMargin: ThemeTokens.Spacing.s6
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: qsTr("发现")
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong
                        ? qsTr("继续听 %1").arg(root.playerController.currentSong.name)
                        : qsTr("从搜索或资料库开始播放")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }
            }

            Button {
                id: nowPlayingButton

                Layout.preferredWidth: 112
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                enabled: root.hasSong
                text: qsTr("正在播放")
                Accessible.name: text
                onClicked: root.nowPlayingRequested()

                contentItem: Label {
                    text: nowPlayingButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: nowPlayingButton.enabled ? ThemeTokens.Palette.onSurface : ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: nowPlayingButton.down
                        ? ThemeTokens.Palette.statePressed
                        : nowPlayingButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: ThemeTokens.Palette.outline
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            columns: root.availableWidth > 900 ? 3 : root.availableWidth > 560 ? 2 : 1
            columnSpacing: ThemeTokens.Spacing.s4
            rowSpacing: ThemeTokens.Spacing.s4

            Repeater {
                model: [
                    {
                        title: qsTr("今日推荐"),
                        subtitle: qsTr("适合现在打开的歌单"),
                        kind: "playlist"
                    },
                    {
                        title: qsTr("新歌速递"),
                        subtitle: qsTr("按更新时间浏览"),
                        kind: "playlist"
                    },
                    {
                        title: qsTr("排行榜"),
                        subtitle: qsTr("热门歌曲入口"),
                        kind: "playlist"
                    }
                ]

                delegate: Rectangle {
                    id: detailCard

                    required property var modelData

                    Layout.fillWidth: true
                    Layout.preferredHeight: 132
                    radius: ThemeTokens.Spacing.radiusMd
                    color: detailHover.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceElevated
                    border.color: ThemeTokens.Palette.outlineMuted
                    Accessible.role: Accessible.Button
                    Accessible.name: detailCard.modelData.title
                    activeFocusOnTab: true

                    HoverHandler {
                        id: detailHover
                    }

                    TapHandler {
                        onTapped: root.detailRequested(detailCard.modelData.kind, detailCard.modelData.title, detailCard.modelData.subtitle)
                    }

                    Keys.onReturnPressed: root.detailRequested(detailCard.modelData.kind, detailCard.modelData.title, detailCard.modelData.subtitle)
                    Keys.onSpacePressed: root.detailRequested(detailCard.modelData.kind, detailCard.modelData.title, detailCard.modelData.subtitle)

                    Rectangle {
                        anchors.fill: parent
                        visible: parent.activeFocus
                        radius: parent.radius
                        color: "transparent"
                        border.color: ThemeTokens.Palette.focusRing
                        border.width: 2
                        z: 1
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: ThemeTokens.Spacing.s5
                        spacing: ThemeTokens.Spacing.s3

                        Components.AlbumArt {
                            Layout.preferredWidth: 44
                            Layout.preferredHeight: 44
                        }

                        Label {
                            Layout.fillWidth: true
                            text: detailCard.modelData.title
                            color: ThemeTokens.Palette.onSurface
                            font.pixelSize: ThemeTokens.TypeScale.body
                            font.weight: ThemeTokens.TypeScale.medium
                            elide: Text.ElideRight
                        }

                        Label {
                            Layout.fillWidth: true
                            text: detailCard.modelData.subtitle
                            color: ThemeTokens.Palette.onSurfaceVariant
                            font.pixelSize: ThemeTokens.TypeScale.caption
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            Layout.bottomMargin: ThemeTokens.Spacing.s6
            Layout.preferredHeight: 88
            radius: ThemeTokens.Spacing.radiusMd
            color: ThemeTokens.Palette.surfaceElevated
            border.color: ThemeTokens.Palette.outlineMuted

            RowLayout {
                anchors.fill: parent
                anchors.margins: ThemeTokens.Spacing.s5
                spacing: ThemeTokens.Spacing.s4

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: ThemeTokens.Spacing.s2

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("打开搜索")
                        color: ThemeTokens.Palette.onSurface
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: ThemeTokens.TypeScale.medium
                        elide: Text.ElideRight
                    }

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("查找歌曲、歌手或专辑")
                        color: ThemeTokens.Palette.onSurfaceVariant
                        font.pixelSize: ThemeTokens.TypeScale.caption
                        elide: Text.ElideRight
                    }
                }

                Button {
                    id: searchButton

                    Layout.preferredWidth: 96
                    Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                    text: qsTr("搜索")
                    Accessible.name: text
                    onClicked: root.searchRequested("")

                    contentItem: Label {
                        text: searchButton.text
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: ThemeTokens.Palette.onPrimary
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    background: Rectangle {
                        radius: ThemeTokens.Spacing.radiusMd
                        color: ThemeTokens.Palette.primary
                    }
                }
            }
        }
    }
}
