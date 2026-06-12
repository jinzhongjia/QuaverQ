pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

ColumnLayout {
    id: root

    property var serviceController
    property var playerController
    property var libraryController
    property var coverController
    property var songDetailController
    property var downloadController
    property string routeName: "search"

    signal detailRequested(string kind, string detailId, string title, string subtitle, string coverUrl)

    readonly property string searchType: root.serviceController ? root.serviceController.searchType : "songs"
    readonly property bool isSongs: root.searchType === "songs"
    readonly property bool hasSearched: root.serviceController
        && root.serviceController.currentPage > 0
    readonly property bool canGoPrevious: root.serviceController
        && root.serviceController.currentPage > 1
        && !root.serviceController.loading
    readonly property bool canGoNext: root.serviceController
        && root.serviceController.hasNextPage
        && !root.serviceController.loading

    readonly property var searchTabs: [
        { key: "songs", label: qsTr("歌曲") },
        { key: "singers", label: qsTr("歌手") },
        { key: "albums", label: qsTr("专辑") },
        { key: "playlists", label: qsTr("歌单") }
    ]

    function resultCount() {
        if (!root.serviceController)
            return 0
        return root.isSongs
            ? root.serviceController.songResults.count
            : root.serviceController.cardResults.count
    }

    function statusText() {
        if (!root.serviceController)
            return ""
        if (root.resultCount() > 0) {
            return root.isSongs
                ? qsTr("第 %1 页 · 本页 %2 首")
                    .arg(root.serviceController.currentPage)
                    .arg(root.serviceController.songResults.count)
                : qsTr("%1 个结果").arg(root.serviceController.cardResults.count)
        }
        return root.hasSearched ? qsTr("没有结果") : qsTr("输入关键词后按 Enter")
    }

    spacing: 0

    // 页内错误与全局 Banner 同一形态 (W9): 红底白字通栏的视觉烈度等同"危险操作", 加载失败不配
    Components.Banner {
        id: searchErrorBanner

        Layout.fillWidth: true
        kind: "error"
    }

    // 显式 Binding: Banner.dismiss() 会写空 message, 直接绑定会被这次写入打断;
    // Binding 元素在 errorMessage 再变化时重新接管 (SettingsView 同款模式)
    Binding {
        target: searchErrorBanner
        property: "message"
        value: root.serviceController ? root.serviceController.errorMessage : ""
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s4

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            Label {
                text: qsTr("搜索")
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.h1
                font.weight: ThemeTokens.TypeScale.bold
            }

            Label {
                Layout.fillWidth: true
                text: root.statusText()
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }
        }

        Components.TabRow {
            id: searchTabRow

            Layout.fillWidth: true
            tabs: root.searchTabs
            currentIndex: {
                for (let i = 0; i < root.searchTabs.length; ++i) {
                    if (root.searchTabs[i].key === root.searchType)
                        return i
                }
                return 0
            }
            onActivated: function(index) {
                if (root.serviceController)
                    root.serviceController.setSearchType(root.searchTabs[index].key)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: ThemeTokens.Palette.outlineMuted
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: resultList
                anchors.fill: parent
                visible: root.isSongs
                clip: true
                spacing: ThemeTokens.Spacing.s2
                model: root.serviceController ? root.serviceController.songResults : null

                delegate: Components.SongRow {
                    width: ListView.view.width
                    libraryController: root.libraryController
                    coverController: root.coverController
                    songDetailController: root.songDetailController
                    playerController: root.playerController
                    downloadController: root.downloadController
                    onActivated: function(songData, row) {
                        if (root.playerController)
                            root.playerController.playFromModel(root.serviceController.songResults, row)
                    }
                    onNavigationRequested: function(kind, detailId, title, subtitle, coverUrl) {
                        root.detailRequested(kind, detailId, title, subtitle, coverUrl)
                    }
                }

                footer: Item {
                    width: ListView.view ? ListView.view.width : 0
                    height: root.isSongs && root.resultCount() > 0 ? 64 : 0
                    visible: root.isSongs && root.resultCount() > 0

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: ThemeTokens.Spacing.s3

                        Button {
                            id: previousPageButton
                            Layout.preferredWidth: 88
                            Layout.preferredHeight: 34
                            enabled: root.canGoPrevious
                            text: qsTr("上一页")
                            Accessible.name: qsTr("上一页搜索结果")
                            onClicked: {
                                if (root.serviceController)
                                    root.serviceController.previousPage()
                            }
                            contentItem: Label {
                                text: previousPageButton.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                color: previousPageButton.enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                                font.pixelSize: ThemeTokens.TypeScale.caption
                            }
                            background: Rectangle {
                                radius: ThemeTokens.Spacing.radiusMd
                                color: previousPageButton.down ? ThemeTokens.Palette.statePressed : previousPageButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                                border.color: ThemeTokens.Palette.outline
                            }
                        }

                        Label {
                            Layout.preferredWidth: 128
                            text: root.serviceController && root.serviceController.loading
                                ? qsTr("加载中...")
                                : qsTr("第 %1 页").arg(root.serviceController ? root.serviceController.currentPage : 0)
                            horizontalAlignment: Text.AlignHCenter
                            color: ThemeTokens.Palette.surfaceText
                            font.pixelSize: ThemeTokens.TypeScale.bodySm
                            font.weight: ThemeTokens.TypeScale.medium
                        }

                        Button {
                            id: nextPageButton
                            Layout.preferredWidth: 88
                            Layout.preferredHeight: 34
                            enabled: root.canGoNext
                            text: qsTr("下一页")
                            Accessible.name: qsTr("下一页搜索结果")
                            onClicked: {
                                if (root.serviceController)
                                    root.serviceController.nextPage()
                            }
                            contentItem: Label {
                                text: nextPageButton.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                color: nextPageButton.enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                                font.pixelSize: ThemeTokens.TypeScale.caption
                            }
                            background: Rectangle {
                                radius: ThemeTokens.Spacing.radiusMd
                                color: nextPageButton.down ? ThemeTokens.Palette.statePressed : nextPageButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                                border.color: ThemeTokens.Palette.outline
                            }
                        }
                    }
                }
            }

            GridView {
                id: cardGrid

                anchors.fill: parent
                visible: !root.isSongs
                clip: true

                readonly property int cols: Math.max(2, Math.min(8, Math.floor(width / 180)))
                cellWidth: cardGrid.cols > 0 ? Math.floor(width / cardGrid.cols) : width
                cellHeight: cellWidth + 44
                model: root.serviceController ? root.serviceController.cardResults : null

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Item {
                    id: cardCell

                    required property string kind
                    required property string cardId
                    required property string title
                    required property string subtitle
                    required property string coverUrl
                    required property string meta

                    width: cardGrid.cellWidth
                    height: cardGrid.cellHeight

                    Components.Card {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: ThemeTokens.Spacing.s2
                        anchors.rightMargin: ThemeTokens.Spacing.s2
                        circular: cardCell.kind === "artist"
                        title: cardCell.title
                        subtitle: cardCell.subtitle
                        coverUrl: cardCell.coverUrl
                        meta: cardCell.meta
                        coverController: root.coverController
                        onActivated: root.detailRequested(cardCell.kind, cardCell.cardId, cardCell.title, cardCell.subtitle, cardCell.coverUrl)
                        onPlayRequested: root.detailRequested(cardCell.kind, cardCell.cardId, cardCell.title, cardCell.subtitle, cardCell.coverUrl)
                    }
                }
            }

            Connections {
                target: root.serviceController

                function onLoadingChanged() {
                    if (root.serviceController && root.serviceController.loading) {
                        resultList.positionViewAtBeginning()
                        cardGrid.positionViewAtBeginning()
                    }
                }
            }

            // 首屏搜索骨架 (翻页时旧结果保留 + 底部"加载中", 不走骨架)
            ColumnLayout {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                visible: root.isSongs
                    && root.serviceController
                    && root.serviceController.loading
                    && root.serviceController.songResults.count === 0
                spacing: ThemeTokens.Spacing.s2

                Repeater {
                    model: 6

                    delegate: Components.SongRowSkeleton {
                        required property int index

                        Layout.fillWidth: true
                        titleRatio: 0.3 + (index % 3) * 0.14
                    }
                }
            }

            GridLayout {
                id: searchSkeletonGrid

                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                visible: !root.isSongs
                    && root.serviceController
                    && root.serviceController.loading
                    && root.serviceController.cardResults.count === 0
                columns: Math.max(2, Math.min(8, Math.floor(width / 180)))
                columnSpacing: ThemeTokens.Spacing.s3
                rowSpacing: ThemeTokens.Spacing.s3

                Repeater {
                    model: searchSkeletonGrid.columns

                    delegate: Components.CardSkeleton {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.alignment: Qt.AlignTop
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                width: parent.width - ThemeTokens.Spacing.s8
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                visible: root.serviceController
                    && !root.serviceController.loading
                    && root.resultCount() === 0
                    && root.serviceController.errorMessage.length === 0
                text: root.hasSearched ? qsTr("没有搜索结果") : qsTr("输入关键词开始搜索")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }
    }
}
