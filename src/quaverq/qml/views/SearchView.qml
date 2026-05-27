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
            color: ThemeTokens.Palette.onPrimary
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
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.h1
                font.weight: ThemeTokens.TypeScale.medium
            }

            Label {
                text: root.serviceController && root.serviceController.songResults.count > 0
                    ? qsTr("%1 首结果").arg(root.serviceController.songResults.count)
                    : qsTr("输入关键词后按 Enter")
                color: ThemeTokens.Palette.onSurfaceVariant
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
                    onActivated: function(songData, row) {
                        if (root.playerController)
                            root.playerController.playFromModel(root.serviceController.songResults, row)
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                visible: root.serviceController
                    && !root.serviceController.loading
                    && root.serviceController.songResults.count === 0
                    && root.serviceController.errorMessage.length === 0
                text: qsTr("输入关键词开始搜索")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }
    }
}
