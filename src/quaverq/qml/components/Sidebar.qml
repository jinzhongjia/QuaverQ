import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property bool compact: false
    property string selectedRoute: "search"

    color: ThemeTokens.Palette.surface
    border.color: ThemeTokens.Palette.outline

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s4

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
                    Layout.fillWidth: true
                    text: modelData.label
                    iconText: modelData.icon
                    compact: root.compact
                    selected: modelData.route === root.selectedRoute
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.topMargin: ThemeTokens.Spacing.s2
            Layout.bottomMargin: ThemeTokens.Spacing.s2
            color: ThemeTokens.Palette.outline
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
                text: qsTr("登录后同步")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
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
            selected: false
        }
    }
}
