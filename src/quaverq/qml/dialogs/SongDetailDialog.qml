pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

// 第二档 2.1: 歌曲详情弹窗 (相似歌曲 + 相关歌单)
// 触发: SongRow 右键 / 菜单键 → controller.open(song)
// 关闭: ESC / 点窗外 / 右上角关闭按钮 → controller.close()
Dialog {
    id: root

    property var songDetailController
    property var coverController
    property var libraryController
    property var playerController

    signal detailRequested(string kind, string detailId, string title, string subtitle)

    objectName: "songDetailDialog"
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: Math.min(parent ? parent.width - ThemeTokens.Spacing.s8 : 720, 720)
    height: Math.min(parent ? parent.height - ThemeTokens.Spacing.s8 : 560, 560)
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? Math.round((parent.height - height) / 2) : 0
    padding: ThemeTokens.Spacing.s5

    readonly property var current: root.songDetailController ? root.songDetailController.currentSong : ({})
    readonly property bool hasSong: !!(root.current
        && typeof root.current.mid === "string"
        && root.current.mid.length > 0)
    readonly property string singerText: {
        if (!root.hasSong) return ""
        const names = root.current.singerNames
        return Array.isArray(names) ? names.join("、") : ""
    }

    // ===== 三态判定 =====
    readonly property bool isLoading: !!(root.songDetailController && root.songDetailController.loading)
    readonly property bool hasError: !!(root.songDetailController
        && !root.songDetailController.loading
        && root.songDetailController.errorMessage.length > 0)
    readonly property bool similarHasItems: !!(root.songDetailController
        && root.songDetailController.similarSongsModel
        && root.songDetailController.similarSongsModel.count > 0)
    readonly property bool relatedHasItems: !!(root.songDetailController
        && root.songDetailController.relatedPlaylistsModel
        && root.songDetailController.relatedPlaylistsModel.count > 0)
    readonly property bool isLoaded: !root.isLoading && !root.hasError
    readonly property bool isLoadedAndAllEmpty: root.isLoaded
        && !root.similarHasItems
        && !root.relatedHasItems

    Connections {
        target: root.songDetailController

        function onVisibleChanged() {
            if (root.songDetailController && root.songDetailController.visible) {
                if (!root.visible)
                    root.open()
            } else if (root.visible) {
                root.close()
            }
        }
    }

    onClosed: {
        if (root.songDetailController && root.songDetailController.visible)
            root.songDetailController.close()
    }

    background: Rectangle {
        radius: ThemeTokens.Spacing.radiusLg
        color: ThemeTokens.Palette.surface
        border.color: ThemeTokens.Palette.outline
    }

    contentItem: ColumnLayout {
        spacing: ThemeTokens.Spacing.s5

        // ===== 顶部: 歌曲信息 =====
        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            Components.AlbumArt {
                Layout.preferredWidth: 80
                Layout.preferredHeight: 80
                active: root.hasSong
                coverUrl: root.hasSong && root.current.coverUrl ? root.current.coverUrl : ""
                coverController: root.coverController
                iconSize: ThemeTokens.TypeScale.h2
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.current.name : qsTr("歌曲详情")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h2
                    font.weight: ThemeTokens.TypeScale.bold
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.hasSong
                    text: root.singerText
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.body
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.hasSong && root.current.albumName && root.current.albumName.length > 0
                    text: root.hasSong ? qsTr("专辑：%1").arg(root.current.albumName) : ""
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }

            Components.IconButton {
                Layout.alignment: Qt.AlignTop
                text: qsTr("关闭")
                iconText: "✕"
                iconColor: ThemeTokens.Palette.surfaceVariantText
                onClicked: root.close()
            }
        }

        // 分隔线: 只在 loaded 且有内容时显示
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            visible: root.isLoaded && !root.isLoadedAndAllEmpty
            color: ThemeTokens.Palette.outlineMuted
        }

        // ===== 内容区: 三态互斥 =====
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // --- 态 1: loading ---
            ColumnLayout {
                anchors.centerIn: parent
                visible: root.isLoading
                spacing: ThemeTokens.Spacing.s3

                BusyIndicator {
                    Layout.alignment: Qt.AlignHCenter
                    implicitWidth: 40
                    implicitHeight: 40
                    running: root.isLoading
                }

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("加载中...")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                }
            }

            // --- 态 2: error ---
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - ThemeTokens.Spacing.s6, 400)
                visible: root.hasError
                spacing: ThemeTokens.Spacing.s4

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: "⚠"
                    color: ThemeTokens.Palette.error
                    font.pixelSize: ThemeTokens.TypeScale.h1
                }

                Label {
                    Layout.fillWidth: true
                    text: root.songDetailController ? root.songDetailController.errorMessage : ""
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }

                Button {
                    id: retryButton

                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 96
                    Layout.preferredHeight: 36
                    text: qsTr("重试")
                    Accessible.name: qsTr("重试加载相似与相关歌单")
                    onClicked: {
                        if (root.songDetailController)
                            root.songDetailController.retry()
                    }

                    contentItem: Label {
                        text: retryButton.text
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: ThemeTokens.Palette.primaryText
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    background: Rectangle {
                        radius: ThemeTokens.Spacing.radiusMd
                        color: retryButton.down
                            ? ThemeTokens.Palette.primaryActive
                            : retryButton.hovered ? ThemeTokens.Palette.primaryHover : ThemeTokens.Palette.primary
                    }
                }
            }

            // --- 态 3a: loaded 且全部为空 ---
            Label {
                anchors.centerIn: parent
                visible: root.isLoadedAndAllEmpty
                text: qsTr("暂无相似歌曲和相关歌单")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
            }

            // --- 态 3b: loaded 有内容 (相似 / 相关; 空 section 隐藏) ---
            ColumnLayout {
                anchors.fill: parent
                visible: root.isLoaded && !root.isLoadedAndAllEmpty
                spacing: ThemeTokens.Spacing.s5

                // --- 相似歌曲 (横向, 只在有数据时显示) ---
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.similarHasItems
                    spacing: ThemeTokens.Spacing.s3

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("相似歌曲")
                        color: ThemeTokens.Palette.surfaceText
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 96
                        orientation: ListView.Horizontal
                        spacing: ThemeTokens.Spacing.s3
                        clip: true
                        model: root.songDetailController ? root.songDetailController.similarSongsModel : null
                        boundsBehavior: Flickable.StopAtBounds
                        reuseItems: true

                        delegate: Rectangle {
                            id: simCell

                            required property string mid
                            required property string name
                            required property string singers
                            required property string coverUrl

                            width: 240
                            height: 80
                            radius: ThemeTokens.Spacing.radiusMd
                            color: simHover.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                            border.color: ThemeTokens.Palette.outlineMuted

                            HoverHandler { id: simHover }

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: ThemeTokens.Spacing.s2
                                spacing: ThemeTokens.Spacing.s3

                                Components.AlbumArt {
                                    Layout.preferredWidth: 56
                                    Layout.preferredHeight: 56
                                    active: false
                                    coverUrl: simCell.coverUrl
                                    coverController: root.coverController
                                    iconSize: ThemeTokens.TypeScale.body
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: ThemeTokens.Spacing.s2

                                    Label {
                                        Layout.fillWidth: true
                                        text: simCell.name
                                        color: ThemeTokens.Palette.surfaceText
                                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                                        font.weight: ThemeTokens.TypeScale.medium
                                        elide: Text.ElideRight
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        text: simCell.singers
                                        color: ThemeTokens.Palette.surfaceVariantText
                                        font.pixelSize: ThemeTokens.TypeScale.caption
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }

                        ScrollBar.horizontal: ScrollBar {}
                    }
                }

                // --- 相关歌单 (横向 Card, 只在有数据时显示) ---
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.relatedHasItems
                    spacing: ThemeTokens.Spacing.s3

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("包含此曲的歌单")
                        color: ThemeTokens.Palette.surfaceText
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 200
                        orientation: ListView.Horizontal
                        spacing: ThemeTokens.Spacing.s4
                        clip: true
                        model: root.songDetailController ? root.songDetailController.relatedPlaylistsModel : null
                        boundsBehavior: Flickable.StopAtBounds
                        reuseItems: true

                        delegate: Item {
                            id: relCell

                            required property string kind
                            required property string cardId
                            required property string title
                            required property string subtitle
                            required property string coverUrl
                            required property string meta

                            width: 160
                            height: ListView.view.height

                            Components.Card {
                                width: parent.width
                                title: relCell.title
                                subtitle: relCell.subtitle
                                coverUrl: relCell.coverUrl
                                meta: relCell.meta
                                coverController: root.coverController
                                onActivated: {
                                    root.detailRequested(relCell.kind, relCell.cardId, relCell.title, relCell.subtitle)
                                    root.close()
                                }
                                onPlayRequested: {
                                    root.detailRequested(relCell.kind, relCell.cardId, relCell.title, relCell.subtitle)
                                    root.close()
                                }
                            }
                        }

                        ScrollBar.horizontal: ScrollBar {}
                    }
                }
            }
        }
    }
}
