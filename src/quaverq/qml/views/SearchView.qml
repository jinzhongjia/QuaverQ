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
    readonly property bool hasSearched: root.serviceController
        && root.serviceController.currentPage > 0
    readonly property bool hasResults: root.serviceController
        && root.serviceController.songResults.count > 0
    readonly property bool canGoPrevious: root.serviceController
        && root.serviceController.currentPage > 1
        && !root.serviceController.loading
    readonly property bool canGoNext: root.serviceController
        && root.serviceController.hasNextPage
        && !root.serviceController.loading

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
                text: root.hasResults
                    ? qsTr("第 %1 页 · 本页 %2 首")
                        .arg(root.serviceController.currentPage)
                        .arg(root.serviceController.songResults.count)
                    : root.hasSearched ? qsTr("没有结果")
                    : qsTr("输入关键词后按 Enter")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: resultList
                anchors.fill: parent
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
                    height: root.hasResults ? 64 : 0
                    visible: root.hasResults

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

                        Label {
                            Layout.preferredWidth: 84
                            text: qsTr("每页 %1 首").arg(root.serviceController ? root.serviceController.pageSize : 30)
                            color: ThemeTokens.Palette.surfaceVariantText
                            font.pixelSize: ThemeTokens.TypeScale.caption
                        }
                    }
                }
            }

            Connections {
                target: root.serviceController

                function onLoadingChanged() {
                    if (root.serviceController && root.serviceController.loading)
                        resultList.positionViewAtBeginning()
                }
            }

            Label {
                anchors.centerIn: parent
                visible: root.serviceController
                    && !root.serviceController.loading
                    && root.serviceController.songResults.count === 0
                    && root.serviceController.errorMessage.length === 0
                text: root.hasSearched ? qsTr("没有搜索结果") : qsTr("输入关键词开始搜索")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }
    }
}
