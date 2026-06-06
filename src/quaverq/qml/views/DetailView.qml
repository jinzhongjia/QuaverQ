pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

ColumnLayout {
    id: root

    property string routeName: "detail"
    property string detailKind: "playlist"
    property string detailId: ""
    property string detailTitle: qsTr("详情")
    property string detailSubtitle: ""
    property var coverController
    property var detailController
    property var playerController
    property var libraryController
    property bool completed: false

    readonly property string displayKind: root.detailController && root.detailController.kind.length > 0
        ? root.detailController.kind
        : root.detailKind
    readonly property string displayTitle: root.detailController && root.detailController.title.length > 0
        ? root.detailController.title
        : root.detailTitle
    readonly property string displaySubtitle: root.detailController && root.detailController.subtitle.length > 0
        ? root.detailController.subtitle
        : root.detailSubtitle
    readonly property string displayDescription: root.detailController
        ? root.detailController.description
        : ""
    readonly property bool hasSongs: root.detailController
        && root.detailController.songModel
        && root.detailController.songModel.count > 0
    readonly property bool loading: root.detailController ? root.detailController.loading : false
    readonly property string errorMessage: root.detailController ? root.detailController.errorMessage : ""

    signal backRequested()
    signal searchRequested(string keyword)

    spacing: 0

    function kindLabel(kind) {
        switch (kind) {
        case "album":
            return qsTr("专辑")
        case "artist":
            return qsTr("艺人")
        case "top":
            return qsTr("排行榜")
        default:
            return qsTr("歌单")
        }
    }

    function loadDetail() {
        if (!root.detailController || root.detailId.length <= 0)
            return
        root.detailController.loadDetail(
            root.detailKind,
            root.detailId,
            root.detailTitle,
            root.detailSubtitle
        )
    }

    Component.onCompleted: {
        root.completed = true
        root.loadDetail()
    }

    onDetailIdChanged: {
        if (root.completed)
            root.loadDetail()
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: root.errorMessage.length > 0 ? 44 : 0
        visible: root.errorMessage.length > 0
        color: ThemeTokens.Palette.error

        Label {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: ThemeTokens.Spacing.s5
            anchors.rightMargin: ThemeTokens.Spacing.s5
            text: root.errorMessage
            color: ThemeTokens.Palette.primaryText
            elide: Text.ElideRight
            font.pixelSize: ThemeTokens.TypeScale.bodySm
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s5

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s5

            Components.AlbumArt {
                Layout.preferredWidth: 168
                Layout.preferredHeight: 168
                iconText: root.displayKind === "artist" ? "◎" : root.displayKind === "top" ? "↗" : "♪"
                iconSize: ThemeTokens.TypeScale.display
                active: root.hasSongs
                coverUrl: root.detailController ? root.detailController.coverUrl : ""
                coverController: root.coverController
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s3

                Label {
                    Layout.fillWidth: true
                    text: root.kindLabel(root.displayKind)
                    color: ThemeTokens.Palette.primary
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.displayTitle
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.display
                    font.weight: ThemeTokens.TypeScale.bold
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.displaySubtitle.length > 0
                        ? root.displaySubtitle
                        : qsTr("暂无简介")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.displayDescription.length > 0
                    text: root.displayDescription
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: ThemeTokens.Spacing.s3

                    Button {
                        id: playAllButton

                        Layout.preferredWidth: 132
                        Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                        enabled: root.hasSongs && !root.loading
                        text: qsTr("播放全部")
                        Accessible.name: text
                        onClicked: {
                            if (root.playerController && root.detailController)
                                root.playerController.playFromModel(root.detailController.songModel, 0)
                        }

                        contentItem: Label {
                            text: "▶  " + playAllButton.text
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: playAllButton.enabled ? ThemeTokens.Palette.primaryText : ThemeTokens.Palette.surfaceVariantText
                            font.pixelSize: ThemeTokens.TypeScale.bodySm
                            font.weight: ThemeTokens.TypeScale.medium
                        }

                        background: Rectangle {
                            radius: ThemeTokens.Spacing.radiusPill
                            color: !playAllButton.enabled
                                ? ThemeTokens.Palette.surfaceVariant
                                : playAllButton.down ? ThemeTokens.Palette.primaryActive
                                : playAllButton.hovered ? ThemeTokens.Palette.primaryHover
                                : ThemeTokens.Palette.primary
                        }
                    }

                    Button {
                        id: searchButton

                        Layout.preferredWidth: 112
                        Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                        text: qsTr("搜索相关")
                        Accessible.name: text
                        onClicked: root.searchRequested(root.displayTitle)

                        contentItem: Label {
                            text: searchButton.text
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: ThemeTokens.Palette.surfaceText
                            font.pixelSize: ThemeTokens.TypeScale.bodySm
                            font.weight: ThemeTokens.TypeScale.medium
                        }

                        background: Rectangle {
                            radius: ThemeTokens.Spacing.radiusPill
                            color: searchButton.down
                                ? ThemeTokens.Palette.statePressed
                                : searchButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                            border.color: ThemeTokens.Palette.outline
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            Label {
                text: root.displayKind === "artist" ? qsTr("热门歌曲") : qsTr("曲目")
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.bold
            }

            Label {
                text: root.loading
                    ? qsTr("加载中...")
                    : root.hasSongs
                        ? qsTr("%1 首").arg(root.detailController.songModel.count)
                        : qsTr("暂无曲目")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: songList

                anchors.fill: parent
                clip: true
                spacing: ThemeTokens.Spacing.s2
                model: root.detailController ? root.detailController.songModel : null
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true

                delegate: Components.SongRow {
                    width: ListView.view.width
                    libraryController: root.libraryController
                    coverController: root.coverController
                    selected: root.playerController
                        && root.playerController.currentSong
                        && root.playerController.currentSong.mid === song.mid
                    onActivated: function(songData, row) {
                        if (root.playerController && root.detailController)
                            root.playerController.playFromModel(root.detailController.songModel, row)
                    }
                }

                ScrollBar.vertical: ScrollBar {}
            }

            ColumnLayout {
                anchors.centerIn: parent
                visible: !root.loading && !root.hasSongs
                spacing: ThemeTokens.Spacing.s3

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: root.errorMessage.length > 0
                        ? qsTr("详情加载失败")
                        : qsTr("暂无曲目")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.body
                }

                Button {
                    id: retryButton

                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 112
                    Layout.preferredHeight: 36
                    visible: root.errorMessage.length > 0
                    text: qsTr("重试")
                    Accessible.name: text
                    onClicked: root.loadDetail()

                    contentItem: Label {
                        text: retryButton.text
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: ThemeTokens.Palette.surfaceText
                        font.pixelSize: ThemeTokens.TypeScale.caption
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    background: Rectangle {
                        radius: ThemeTokens.Spacing.radiusMd
                        color: retryButton.down
                            ? ThemeTokens.Palette.statePressed
                            : retryButton.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                visible: root.loading && !root.hasSongs
                text: qsTr("正在加载详情")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }
    }
}
