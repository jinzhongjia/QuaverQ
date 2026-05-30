pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property bool compact: false
    property string selectedRoute: "search"
    property var appController

    signal loginRequested()
    signal routeRequested(string route)

    color: ThemeTokens.Palette.sidebar
    border.color: "transparent"

    Rectangle {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: 1
        color: ThemeTokens.Palette.outlineMuted
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s5
        spacing: ThemeTokens.Spacing.s5

        ColumnLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s2

            Repeater {
                model: [
                    { route: "home", label: qsTr("发现"), icon: "⌂" },
                    { route: "search", label: qsTr("搜索"), icon: "⌕" },
                    { route: "library", label: qsTr("资料库"), icon: "♬" }
                ]

                delegate: NavItem {
                    required property var modelData

                    Layout.fillWidth: true
                    text: modelData.label
                    iconText: modelData.icon
                    compact: root.compact
                    selected: modelData.route === root.selectedRoute
                    onActivated: root.routeRequested(modelData.route)
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.topMargin: ThemeTokens.Spacing.s2
            Layout.bottomMargin: ThemeTokens.Spacing.s2
            color: ThemeTokens.Palette.outlineMuted
            visible: !root.compact
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: !root.compact
            spacing: ThemeTokens.Spacing.s2

            Label {
                text: qsTr("我的歌单")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.caption
                font.weight: ThemeTokens.TypeScale.medium
            }

            Label {
                Layout.fillWidth: true
                text: root.appController && root.appController.authed
                    ? qsTr("已同步账号")
                    : root.appController && root.appController.loginState === "expired"
                        ? qsTr("登录已过期")
                        : qsTr("登录后同步")
                color: root.appController && root.appController.loginState === "expired"
                    ? ThemeTokens.Palette.error
                    : ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }

            Button {
                id: loginButton

                Layout.fillWidth: true
                Layout.preferredHeight: 36
                text: root.appController && root.appController.authed ? qsTr("退出登录") : qsTr("登录同步")
                Accessible.name: text
                onClicked: {
                    if (root.appController && root.appController.authed) {
                        root.appController.logout()
                    } else {
                        root.loginRequested()
                    }
                }

                contentItem: Label {
                    text: loginButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: loginButton.enabled ? ThemeTokens.Palette.onSurface : ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: loginButton.down
                        ? ThemeTokens.Palette.statePressed
                        : loginButton.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceElevated
                    border.color: ThemeTokens.Palette.outlineMuted
                }
            }
        }

        Item {
            Layout.fillHeight: true
        }

        NavItem {
            Layout.fillWidth: true
            text: qsTr("设置")
            iconText: "⚙"
            compact: root.compact
            selected: root.selectedRoute === "settings"
            onActivated: root.routeRequested("settings")
        }
    }
}
