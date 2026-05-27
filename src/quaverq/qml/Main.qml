import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components" as Components
import "Theme" as ThemeTokens
import "views" as Views

ApplicationWindow {
    id: root

    width: ThemeTokens.Spacing.windowWidth
    height: ThemeTokens.Spacing.windowHeight
    minimumWidth: ThemeTokens.Spacing.minWindowWidth
    minimumHeight: ThemeTokens.Spacing.minWindowHeight
    visible: true
    title: qsTr("QuaverQ")
    color: ThemeTokens.Palette.background

    Shortcut {
        sequence: "Ctrl+F"
        onActivated: searchField.focusInput()
    }

    Rectangle {
        id: headerBar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: ThemeTokens.Spacing.headerHeight
        color: ThemeTokens.Palette.surface

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s5
            anchors.rightMargin: ThemeTokens.Spacing.s5
            spacing: ThemeTokens.Spacing.s5

            Label {
                text: qsTr("QuaverQ")
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.medium
            }

            Components.SearchField {
                id: searchField

                Layout.fillWidth: true
                Layout.maximumWidth: 520
                placeholderText: qsTr("搜索歌曲、歌手、专辑")
                text: "周杰伦"
                loading: ServiceController.loading
                onSearchRequested: function(keyword) {
                    ServiceController.search(keyword)
                }
            }
        }
    }

    RowLayout {
        anchors.top: headerBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: playerBar.top
        spacing: 0

        Components.Sidebar {
            Layout.preferredWidth: root.width < 920 ? 64 : 240
            Layout.fillHeight: true
            compact: root.width < 920
            selectedRoute: "search"
        }

        Views.SearchView {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }

    Components.PlayerBar {
        id: playerBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
    }
}
