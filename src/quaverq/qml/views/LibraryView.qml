pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

ColumnLayout {
    id: root

    property string routeName: "library"
    property var appController
    property int currentTab: 0

    signal loginRequested()
    signal detailRequested(string kind, string title, string subtitle)

    spacing: 0

    ColumnLayout {
        Layout.fillWidth: true
        Layout.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s4

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: qsTr("资料库")
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.appController && root.appController.authed
                        ? qsTr("已同步账号")
                        : qsTr("登录后显示账号资料")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }
            }

            Button {
                id: authButton

                Layout.preferredWidth: 112
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                text: root.appController && root.appController.authed ? qsTr("退出登录") : qsTr("登录")
                Accessible.name: text
                onClicked: {
                    if (root.appController && root.appController.authed) {
                        root.appController.logout()
                    } else {
                        root.loginRequested()
                    }
                }

                contentItem: Label {
                    text: authButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: authButton.down
                        ? ThemeTokens.Palette.statePressed
                        : authButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: ThemeTokens.Palette.outline
                }
            }
        }

        RowLayout {
            id: libraryTabs

            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s2

            Button {
                id: likedTab

                Layout.fillWidth: true
                Layout.preferredHeight: 38
                text: qsTr("我喜欢")
                onClicked: root.currentTab = 0
                contentItem: Label {
                    text: likedTab.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: root.currentTab === 0 ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: root.currentTab === 0 ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
                }
                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: root.currentTab === 0 ? ThemeTokens.Palette.primaryContainer : "transparent"
                    border.color: root.currentTab === 0 ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.outline
                }
            }
            Button {
                id: playlistTab

                Layout.fillWidth: true
                Layout.preferredHeight: 38
                text: qsTr("歌单")
                onClicked: root.currentTab = 1
                contentItem: Label {
                    text: playlistTab.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: root.currentTab === 1 ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: root.currentTab === 1 ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
                }
                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: root.currentTab === 1 ? ThemeTokens.Palette.primaryContainer : "transparent"
                    border.color: root.currentTab === 1 ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.outline
                }
            }
            Button {
                id: albumTab

                Layout.fillWidth: true
                Layout.preferredHeight: 38
                text: qsTr("专辑")
                onClicked: root.currentTab = 2
                contentItem: Label {
                    text: albumTab.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: root.currentTab === 2 ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: root.currentTab === 2 ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
                }
                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: root.currentTab === 2 ? ThemeTokens.Palette.primaryContainer : "transparent"
                    border.color: root.currentTab === 2 ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.outline
                }
            }
            Button {
                id: artistTab

                Layout.fillWidth: true
                Layout.preferredHeight: 38
                text: qsTr("艺人")
                onClicked: root.currentTab = 3
                contentItem: Label {
                    text: artistTab.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: root.currentTab === 3 ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: root.currentTab === 3 ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
                }
                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: root.currentTab === 3 ? ThemeTokens.Palette.primaryContainer : "transparent"
                    border.color: root.currentTab === 3 ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.outline
                }
            }
        }
    }

    StackLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.leftMargin: ThemeTokens.Spacing.s6
        Layout.rightMargin: ThemeTokens.Spacing.s6
        Layout.bottomMargin: ThemeTokens.Spacing.s6
        currentIndex: root.currentTab

        ColumnLayout {
            spacing: ThemeTokens.Spacing.s3

            LibraryTile {
                Layout.fillWidth: true
                title: qsTr("我喜欢的音乐")
                subtitle: root.appController && root.appController.authed
                    ? qsTr("暂无账号歌曲")
                    : qsTr("登录后显示喜欢的歌曲")
                iconText: "♥"
                onActivated: root.detailRequested("playlist", title, subtitle)
            }

            LibraryTile {
                Layout.fillWidth: true
                title: qsTr("最近播放")
                subtitle: qsTr("本机播放历史")
                iconText: "↻"
                onActivated: root.detailRequested("playlist", title, subtitle)
            }

            Item {
                Layout.fillHeight: true
            }
        }

        ColumnLayout {
            spacing: ThemeTokens.Spacing.s3

            LibraryTile {
                Layout.fillWidth: true
                title: qsTr("默认歌单")
                subtitle: root.appController && root.appController.authed
                    ? qsTr("暂无歌单")
                    : qsTr("登录后显示我的歌单")
                iconText: "♬"
                onActivated: root.detailRequested("playlist", title, subtitle)
            }

            Item {
                Layout.fillHeight: true
            }
        }

        ColumnLayout {
            spacing: ThemeTokens.Spacing.s3

            LibraryTile {
                Layout.fillWidth: true
                title: qsTr("收藏专辑")
                subtitle: qsTr("暂无专辑")
                iconText: "◫"
                onActivated: root.detailRequested("album", title, subtitle)
            }

            Item {
                Layout.fillHeight: true
            }
        }

        ColumnLayout {
            spacing: ThemeTokens.Spacing.s3

            LibraryTile {
                Layout.fillWidth: true
                title: qsTr("关注艺人")
                subtitle: qsTr("暂无艺人")
                iconText: "◎"
                onActivated: root.detailRequested("artist", title, subtitle)
            }

            Item {
                Layout.fillHeight: true
            }
        }
    }

    component LibraryTile: Rectangle {
        id: tile

        property string title: ""
        property string subtitle: ""
        property string iconText: ""

        signal activated()

        implicitHeight: 72
        radius: ThemeTokens.Spacing.radiusMd
        color: tileHover.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surface
        border.color: ThemeTokens.Palette.outline
        Accessible.role: Accessible.Button
        Accessible.name: title
        activeFocusOnTab: true

        HoverHandler {
            id: tileHover
        }

        TapHandler {
            onTapped: tile.activated()
        }

        Keys.onReturnPressed: tile.activated()
        Keys.onSpacePressed: tile.activated()

        Rectangle {
            anchors.fill: parent
            visible: parent.activeFocus
            radius: parent.radius
            color: "transparent"
            border.color: ThemeTokens.Palette.focusRing
            border.width: 2
            z: 1
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: ThemeTokens.Spacing.s4
            spacing: ThemeTokens.Spacing.s4

            Rectangle {
                Layout.preferredWidth: 44
                Layout.preferredHeight: 44
                radius: ThemeTokens.Spacing.radiusMd
                color: ThemeTokens.Palette.surfaceVariant

                Label {
                    anchors.centerIn: parent
                    text: tile.iconText
                    color: ThemeTokens.Palette.primary
                    font.pixelSize: ThemeTokens.TypeScale.h2
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: tile.title
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: tile.subtitle
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }
        }
    }
}
