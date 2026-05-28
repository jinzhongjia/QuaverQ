pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

ScrollView {
    id: root

    property string routeName: "settings"
    property var appController

    signal loginRequested()

    contentWidth: availableWidth

    ColumnLayout {
        width: root.availableWidth
        spacing: ThemeTokens.Spacing.s5

        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: ThemeTokens.Spacing.s6
            spacing: ThemeTokens.Spacing.s2

            Label {
                Layout.fillWidth: true
                text: qsTr("设置")
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.h1
                font.weight: ThemeTokens.TypeScale.medium
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: qsTr("账号、播放和界面偏好")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            Layout.bottomMargin: ThemeTokens.Spacing.s6
            spacing: ThemeTokens.Spacing.s3

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("QQ 音乐账号")
                value: root.appController && root.appController.authed ? qsTr("已登录") : qsTr("未登录")
                actionText: root.appController && root.appController.authed ? qsTr("退出") : qsTr("登录")
                onActionRequested: {
                    if (root.appController && root.appController.authed) {
                        root.appController.logout()
                    } else {
                        root.loginRequested()
                    }
                }
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("音质偏好")
                value: qsTr("均衡")
                actionText: ""
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("外观")
                value: qsTr("跟随系统")
                actionText: ""
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("缓存")
                value: qsTr("自动管理")
                actionText: ""
            }
        }
    }

    component SettingsRow: Rectangle {
        id: row

        property string title: ""
        property string value: ""
        property string actionText: ""

        signal actionRequested()

        implicitHeight: 64
        radius: ThemeTokens.Spacing.radiusMd
        color: ThemeTokens.Palette.surface
        border.color: ThemeTokens.Palette.outline

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s5
            anchors.rightMargin: ThemeTokens.Spacing.s4
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: row.title
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: row.value
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }

            Button {
                id: actionButton

                Layout.preferredWidth: 74
                Layout.preferredHeight: 34
                visible: row.actionText.length > 0
                text: row.actionText
                Accessible.name: text
                onClicked: row.actionRequested()

                contentItem: Label {
                    text: actionButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: actionButton.down
                        ? ThemeTokens.Palette.statePressed
                        : actionButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: ThemeTokens.Palette.outline
                }
            }
        }
    }
}
