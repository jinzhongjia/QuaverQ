pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

ColumnLayout {
    id: root

    property string routeName: "library"
    property var appController
    property var libraryController
    property var playerController
    property int currentTab: 0

    signal loginRequested()
    signal detailRequested(string kind, string detailId, string title, string subtitle)

    spacing: 0

    function refreshCurrentTab() {
        if (!root.libraryController || !root.libraryController.authed)
            return
        if (root.currentTab === 0) {
            root.libraryController.refreshLiked()
        } else if (root.currentTab === 1) {
            root.libraryController.refreshMyPlaylists()
        } else if (root.currentTab === 2) {
            root.libraryController.refreshFavAlbums()
        } else if (root.currentTab === 3) {
            root.libraryController.refreshFollowedSingers()
        }
    }

    Component.onCompleted: root.refreshCurrentTab()

    onCurrentTabChanged: root.refreshCurrentTab()

    Connections {
        target: root.libraryController

        function onAuthStateChanged() {
            root.refreshCurrentTab()
        }
    }

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

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: likedList

                anchors.fill: parent
                clip: true
                spacing: ThemeTokens.Spacing.s2
                model: root.libraryController ? root.libraryController.likedModel : null
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true

                delegate: Components.SongRow {
                    width: ListView.view.width
                    libraryController: root.libraryController
                    onActivated: function(songData, row) {
                        if (root.playerController && root.libraryController)
                            root.playerController.playFromModel(root.libraryController.likedModel, row)
                    }
                }

                ScrollBar.vertical: ScrollBar {}
            }

            ColumnLayout {
                anchors.centerIn: parent
                visible: !root.libraryController
                    || !root.libraryController.authed
                    || (!root.libraryController.loading && root.libraryController.likedCount === 0)
                spacing: ThemeTokens.Spacing.s3

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: root.libraryController && root.libraryController.authed
                        ? qsTr("暂无喜欢的歌曲")
                        : qsTr("登录后显示喜欢的歌曲")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.body
                }

                Button {
                    id: likedLoginButton

                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 112
                    Layout.preferredHeight: 36
                    visible: !root.libraryController || !root.libraryController.authed
                    text: qsTr("登录同步")
                    Accessible.name: qsTr("登录同步喜欢")
                    onClicked: root.loginRequested()

                    contentItem: Label {
                        text: likedLoginButton.text
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: ThemeTokens.Palette.onSurface
                        font.pixelSize: ThemeTokens.TypeScale.caption
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    background: Rectangle {
                        radius: ThemeTokens.Spacing.radiusMd
                        color: likedLoginButton.down
                            ? ThemeTokens.Palette.statePressed
                            : likedLoginButton.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                visible: root.libraryController && root.libraryController.loading
                text: qsTr("正在同步喜欢")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }

        CardListTab {
            model: root.libraryController ? root.libraryController.playlistModel : null
            kindFallback: "playlist"
            iconText: "♬"
            emptyText: qsTr("暂无歌单")
            loggedOutText: qsTr("登录后显示我的歌单")
            onLoginRequested: root.loginRequested()
            onCardRequested: function(kind, detailId, title, subtitle) {
                root.detailRequested(kind, detailId, title, subtitle)
            }
        }

        CardListTab {
            model: root.libraryController ? root.libraryController.albumModel : null
            kindFallback: "album"
            iconText: "◫"
            emptyText: qsTr("暂无专辑")
            loggedOutText: qsTr("登录后显示收藏专辑")
            onLoginRequested: root.loginRequested()
            onCardRequested: function(kind, detailId, title, subtitle) {
                root.detailRequested(kind, detailId, title, subtitle)
            }
        }

        CardListTab {
            model: root.libraryController ? root.libraryController.artistModel : null
            kindFallback: "artist"
            iconText: "◎"
            emptyText: qsTr("暂无艺人")
            loggedOutText: qsTr("登录后显示关注艺人")
            onLoginRequested: root.loginRequested()
            onCardRequested: function(kind, detailId, title, subtitle) {
                root.detailRequested(kind, detailId, title, subtitle)
            }
        }
    }

    component CardListTab: Item {
        id: tab

        property var model
        property string kindFallback: "playlist"
        property string iconText: "♪"
        property string emptyText: ""
        property string loggedOutText: ""
        readonly property bool hasCards: tab.model && tab.model.count > 0

        signal loginRequested()
        signal cardRequested(string kind, string detailId, string title, string subtitle)

        Layout.fillWidth: true
        Layout.fillHeight: true

        ListView {
            id: cardList

            anchors.fill: parent
            clip: true
            spacing: ThemeTokens.Spacing.s2
            model: tab.model
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            delegate: LibraryTile {
                width: ListView.view.width
                iconText: tab.iconText
                fallbackKind: tab.kindFallback
                onActivated: function(kind, detailId, title, subtitle) {
                    tab.cardRequested(kind, detailId, title, subtitle)
                }
            }

            ScrollBar.vertical: ScrollBar {}
        }

        ColumnLayout {
            anchors.centerIn: parent
            visible: !root.libraryController
                || !root.libraryController.authed
                || (!root.libraryController.loading && !tab.hasCards)
            spacing: ThemeTokens.Spacing.s3

            Label {
                Layout.alignment: Qt.AlignHCenter
                text: root.libraryController && root.libraryController.authed
                    ? tab.emptyText
                    : tab.loggedOutText
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.body
            }

            Button {
                id: tabLoginButton

                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 112
                Layout.preferredHeight: 36
                visible: !root.libraryController || !root.libraryController.authed
                text: qsTr("登录同步")
                Accessible.name: text
                onClicked: tab.loginRequested()

                contentItem: Label {
                    text: tabLoginButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: tabLoginButton.down
                        ? ThemeTokens.Palette.statePressed
                        : tabLoginButton.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant
                }
            }
        }

        Label {
            anchors.centerIn: parent
            visible: root.libraryController
                && root.libraryController.authed
                && root.libraryController.loading
                && !tab.hasCards
            text: qsTr("正在同步")
            color: ThemeTokens.Palette.onSurfaceVariant
            font.pixelSize: ThemeTokens.TypeScale.body
        }
    }

    component LibraryTile: Rectangle {
        id: tile

        required property string title
        required property string subtitle
        required property string cardId
        required property string kind
        property string fallbackKind: "playlist"
        property string iconText: ""

        signal activated(string kind, string detailId, string title, string subtitle)

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
            onTapped: tile.activated(tile.kind || tile.fallbackKind, tile.cardId, tile.title, tile.subtitle)
        }

        Keys.onReturnPressed: tile.activated(tile.kind || tile.fallbackKind, tile.cardId, tile.title, tile.subtitle)
        Keys.onSpacePressed: tile.activated(tile.kind || tile.fallbackKind, tile.cardId, tile.title, tile.subtitle)

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
