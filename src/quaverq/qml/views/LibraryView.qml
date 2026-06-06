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
    property var coverController
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
            root.libraryController.refreshFavSonglists()
        } else if (root.currentTab === 3) {
            root.libraryController.refreshFavAlbums()
        } else if (root.currentTab === 4) {
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
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.bold
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.appController && root.appController.authed
                        ? qsTr("已同步账号")
                        : qsTr("登录后显示账号资料")
                    color: ThemeTokens.Palette.surfaceVariantText
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
                    color: ThemeTokens.Palette.surfaceText
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
            spacing: ThemeTokens.Spacing.s6

            Repeater {
                model: [qsTr("我喜欢"), qsTr("我的歌单"), qsTr("收藏歌单"), qsTr("专辑"), qsTr("艺人")]

                delegate: Item {
                    id: libTab

                    required property int index
                    required property string modelData
                    readonly property bool current: root.currentTab === libTab.index

                    Layout.preferredHeight: 38
                    implicitWidth: libTabText.implicitWidth

                    Accessible.role: Accessible.Button
                    Accessible.name: libTab.modelData
                    activeFocusOnTab: true

                    HoverHandler { id: libTabHover }
                    TapHandler { onTapped: root.currentTab = libTab.index }
                    Keys.onReturnPressed: root.currentTab = libTab.index
                    Keys.onSpacePressed: root.currentTab = libTab.index

                    Label {
                        id: libTabText
                        anchors.top: parent.top
                        anchors.topMargin: ThemeTokens.Spacing.s2
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: libTab.modelData
                        color: libTab.current
                            ? ThemeTokens.Palette.primary
                            : (libTabHover.hovered ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText)
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: libTab.current ? ThemeTokens.TypeScale.bold : ThemeTokens.TypeScale.regular
                    }

                    Rectangle {
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: libTabText.implicitWidth
                        height: 2
                        radius: 1
                        visible: libTab.current
                        color: ThemeTokens.Palette.primary
                    }

                    Rectangle {
                        anchors.fill: parent
                        visible: libTab.activeFocus
                        radius: ThemeTokens.Spacing.radiusSm
                        color: "transparent"
                        border.color: ThemeTokens.Palette.focusRing
                        border.width: 2
                    }
                }
            }

            Item { Layout.fillWidth: true }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: ThemeTokens.Palette.outlineMuted
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
                    coverController: root.coverController
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
                    color: ThemeTokens.Palette.surfaceVariantText
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
                        color: ThemeTokens.Palette.surfaceText
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
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }

        CardListTab {
            model: root.libraryController ? root.libraryController.playlistModel : null
            coverController: root.coverController
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
            model: root.libraryController ? root.libraryController.favPlaylistModel : null
            coverController: root.coverController
            kindFallback: "playlist"
            iconText: "❤"
            emptyText: qsTr("暂无收藏歌单")
            loggedOutText: qsTr("登录后显示收藏歌单")
            onLoginRequested: root.loginRequested()
            onCardRequested: function(kind, detailId, title, subtitle) {
                root.detailRequested(kind, detailId, title, subtitle)
            }
        }

        CardListTab {
            model: root.libraryController ? root.libraryController.albumModel : null
            coverController: root.coverController
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
            coverController: root.coverController
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
        property var coverController
        property string kindFallback: "playlist"
        property string iconText: "♪"
        property string emptyText: ""
        property string loggedOutText: ""
        readonly property bool hasCards: tab.model && tab.model.count > 0

        signal loginRequested()
        signal cardRequested(string kind, string detailId, string title, string subtitle)

        Layout.fillWidth: true
        Layout.fillHeight: true

        GridView {
            id: cardGrid

            anchors.fill: parent
            clip: true

            readonly property int cols: Math.max(2, Math.ceil(width / 180))
            cellWidth: cardGrid.cols > 0 ? Math.floor(width / cardGrid.cols) : width
            cellHeight: cellWidth + 44
            model: tab.model
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                id: libCell

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
                    circular: (libCell.kind || tab.kindFallback) === "artist"
                    title: libCell.title
                    subtitle: libCell.subtitle
                    coverUrl: libCell.coverUrl
                    meta: libCell.meta
                    coverController: tab.coverController
                    onActivated: tab.cardRequested(libCell.kind || tab.kindFallback, libCell.cardId, libCell.title, libCell.subtitle)
                    onPlayRequested: tab.cardRequested(libCell.kind || tab.kindFallback, libCell.cardId, libCell.title, libCell.subtitle)
                }
            }
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
                color: ThemeTokens.Palette.surfaceVariantText
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
                    color: ThemeTokens.Palette.surfaceText
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
            color: ThemeTokens.Palette.surfaceVariantText
            font.pixelSize: ThemeTokens.TypeScale.body
        }
    }

}
