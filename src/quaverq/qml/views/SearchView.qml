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
    property string routeName: "search"

    signal detailRequested(string kind, string detailId, string title, string subtitle)

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

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: root.serviceController && root.serviceController.errorMessage ? 44 : 0
        visible: root.serviceController && root.serviceController.errorMessage.length > 0
        color: ThemeTokens.Palette.error

        Label {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: ThemeTokens.Spacing.s5
            anchors.rightMargin: ThemeTokens.Spacing.s5
            text: root.serviceController ? root.serviceController.errorMessage : ""
            color: ThemeTokens.Palette.primaryText
            elide: Text.ElideRight
            font.pixelSize: ThemeTokens.TypeScale.bodySm
        }
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
                font.weight: ThemeTokens.TypeScale.medium
            }

            Label {
                Layout.fillWidth: true
                text: root.statusText()
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s6

            Repeater {
                model: root.searchTabs

                delegate: Item {
                    id: typeTab

                    required property var modelData
                    readonly property bool current: root.searchType === typeTab.modelData.key

                    Layout.preferredHeight: 36
                    implicitWidth: tabText.implicitWidth

                    Accessible.role: Accessible.Button
                    Accessible.name: typeTab.modelData.label
                    activeFocusOnTab: true

                    HoverHandler { id: tabHover }
                    TapHandler {
                        onTapped: {
                            if (root.serviceController)
                                root.serviceController.setSearchType(typeTab.modelData.key)
                        }
                    }
                    Keys.onReturnPressed: {
                        if (root.serviceController)
                            root.serviceController.setSearchType(typeTab.modelData.key)
                    }
                    Keys.onSpacePressed: {
                        if (root.serviceController)
                            root.serviceController.setSearchType(typeTab.modelData.key)
                    }

                    Label {
                        id: tabText
                        anchors.top: parent.top
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: typeTab.modelData.label
                        color: typeTab.current
                            ? ThemeTokens.Palette.primary
                            : (tabHover.hovered ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText)
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: typeTab.current ? ThemeTokens.TypeScale.bold : ThemeTokens.TypeScale.regular
                    }

                    Rectangle {
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: tabText.implicitWidth
                        height: 2
                        radius: 1
                        visible: typeTab.current
                        color: ThemeTokens.Palette.primary
                    }

                    Rectangle {
                        anchors.fill: parent
                        visible: typeTab.activeFocus
                        radius: ThemeTokens.Spacing.radiusSm
                        color: "transparent"
                        border.color: ThemeTokens.Palette.focusRing
                        border.width: 2
                    }
                }
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
                    onActivated: function(songData, row) {
                        if (root.playerController)
                            root.playerController.playFromModel(root.serviceController.songResults, row)
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

                readonly property int cols: Math.max(2, Math.ceil(width / 180))
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
                        onActivated: root.detailRequested(cardCell.kind, cardCell.cardId, cardCell.title, cardCell.subtitle)
                        onPlayRequested: root.detailRequested(cardCell.kind, cardCell.cardId, cardCell.title, cardCell.subtitle)
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
