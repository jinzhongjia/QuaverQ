import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

ColumnLayout {
    id: root

    spacing: 0

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: ServiceController.errorMessage ? 44 : 0
        visible: ServiceController.errorMessage.length > 0
        color: ThemeTokens.Palette.error

        Label {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: ThemeTokens.Spacing.s5
            anchors.rightMargin: ThemeTokens.Spacing.s5
            text: ServiceController.errorMessage
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
                text: ServiceController.songResults.count > 0
                    ? qsTr("%1 首结果").arg(ServiceController.songResults.count)
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
                model: ServiceController.songResults

                delegate: Components.SongRow {
                    width: ListView.view.width
                    name: model.name
                    singers: model.singers
                    albumName: model.albumName
                    durationText: model.durationText
                    rowNumber: model.index + 1
                }
            }

            Label {
                anchors.centerIn: parent
                visible: !ServiceController.loading
                    && ServiceController.songResults.count === 0
                    && ServiceController.errorMessage.length === 0
                text: qsTr("输入关键词开始搜索")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }
    }
}
