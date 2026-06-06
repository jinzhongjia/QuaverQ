pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property bool compact: false
    property string selectedRoute: "home"
    property var appController
    property var libraryController
    property var coverController

    signal loginRequested()
    signal routeRequested(string route)
    signal openPlaylistRequested(string pid, string title)

    readonly property bool authed: root.appController ? root.appController.authed : false
    readonly property var playlistModel: root.libraryController ? root.libraryController.playlistModel : null
    readonly property int playlistCount: root.playlistModel ? root.playlistModel.count : 0

    color: ThemeTokens.Palette.sidebar

    function refreshPlaylists() {
        if (root.authed && root.libraryController)
            root.libraryController.refreshMyPlaylists()
    }

    Component.onCompleted: root.refreshPlaylists()

    Connections {
        target: root.appController
        ignoreUnknownSignals: true
        function onAuthedChanged() { root.refreshPlaylists() }
    }

    // right edge divider
    Rectangle {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: 1
        color: ThemeTokens.Palette.outlineMuted
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: ThemeTokens.Spacing.s4
        anchors.bottomMargin: ThemeTokens.Spacing.s4
        anchors.leftMargin: root.compact ? ThemeTokens.Spacing.s2 : ThemeTokens.Spacing.s4
        anchors.rightMargin: root.compact ? ThemeTokens.Spacing.s2 : ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s4

        // 1) primary navigation
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
            color: ThemeTokens.Palette.outlineMuted
            visible: !root.compact
        }

        // 2) function list (real data only)
        FunctionRow {
            Layout.fillWidth: true
            visible: !root.compact
            iconText: "♥"
            iconColor: ThemeTokens.Palette.primary
            label: qsTr("我喜欢的音乐")
            count: root.libraryController ? root.libraryController.likedCount : -1
            onActivated: root.routeRequested("library")
        }

        // 3) my playlists header
        Label {
            Layout.fillWidth: true
            Layout.topMargin: ThemeTokens.Spacing.s2
            visible: !root.compact
            text: qsTr("我的歌单")
            color: ThemeTokens.Palette.surfaceVariantText
            font.pixelSize: ThemeTokens.TypeScale.caption
            font.weight: ThemeTokens.TypeScale.medium
        }

        // 4) playlist list (shows whenever any are loaded)
        ListView {
            id: playlistList

            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.compact && root.playlistCount > 0
            clip: true
            spacing: 2
            model: root.playlistModel
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: PlaylistRow {
                required property string title
                required property string coverUrl
                required property string cardId

                width: ListView.view ? ListView.view.width : implicitWidth
                rowTitle: title
                rowCover: coverUrl
                onActivated: root.openPlaylistRequested(cardId, title)
            }
        }

        // 4b) login / empty hint when no playlists shown
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: !playlistList.visible
            visible: !root.compact && !playlistList.visible
            spacing: ThemeTokens.Spacing.s3

            Label {
                Layout.fillWidth: true
                text: root.authed
                    ? qsTr("还没有歌单")
                    : (root.appController && root.appController.loginState === "expired"
                        ? qsTr("登录已过期，请重新登录")
                        : qsTr("登录后在这里看到你的歌单"))
                color: root.appController && root.appController.loginState === "expired"
                    ? ThemeTokens.Palette.error
                    : ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.caption
                wrapMode: Text.WordWrap
            }

            Button {
                id: loginButton

                Layout.fillWidth: true
                Layout.preferredHeight: 36
                visible: !root.authed
                text: qsTr("登录同步")
                Accessible.name: text
                onClicked: root.loginRequested()

                contentItem: Label {
                    text: loginButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.primaryText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusPill
                    color: loginButton.down
                        ? ThemeTokens.Palette.primaryActive
                        : loginButton.hovered ? ThemeTokens.Palette.primaryHover : ThemeTokens.Palette.primary
                }
            }

            Item { Layout.fillHeight: true }
        }

        // 5) settings pinned at bottom
        NavItem {
            Layout.fillWidth: true
            text: qsTr("设置")
            iconText: "⚙"
            compact: root.compact
            selected: root.selectedRoute === "settings"
            onActivated: root.routeRequested("settings")
        }
    }

    // ---- inline components ----

    component FunctionRow: Rectangle {
        id: fr

        property string iconText: ""
        property color iconColor: ThemeTokens.Palette.surfaceVariantText
        property string label: ""
        property int count: -1

        signal activated()

        implicitHeight: 40
        radius: ThemeTokens.Spacing.radiusMd
        color: frHover.hovered ? ThemeTokens.Palette.stateHover : "transparent"

        Accessible.role: Accessible.Button
        Accessible.name: fr.label
        activeFocusOnTab: true

        HoverHandler { id: frHover }
        TapHandler { onTapped: fr.activated() }
        Keys.onReturnPressed: fr.activated()
        Keys.onSpacePressed: fr.activated()

        Rectangle {
            anchors.fill: parent
            visible: fr.activeFocus
            radius: parent.radius
            color: "transparent"
            border.color: ThemeTokens.Palette.focusRing
            border.width: 2
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s4
            anchors.rightMargin: ThemeTokens.Spacing.s4
            spacing: ThemeTokens.Spacing.s3

            Label {
                Layout.preferredWidth: ThemeTokens.Spacing.s5
                horizontalAlignment: Text.AlignHCenter
                text: fr.iconText
                color: fr.iconColor
                font.pixelSize: ThemeTokens.TypeScale.body
            }

            Label {
                Layout.fillWidth: true
                text: fr.label
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }

            Label {
                visible: fr.count >= 0
                text: fr.count
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.caption
            }
        }
    }

    component PlaylistRow: Rectangle {
        id: pr

        property string rowTitle: ""
        property string rowCover: ""

        signal activated()

        implicitHeight: 44
        radius: ThemeTokens.Spacing.radiusMd
        color: prHover.hovered ? ThemeTokens.Palette.stateHover : "transparent"

        Accessible.role: Accessible.Button
        Accessible.name: pr.rowTitle
        activeFocusOnTab: true

        HoverHandler { id: prHover }
        TapHandler { onTapped: pr.activated() }
        Keys.onReturnPressed: pr.activated()
        Keys.onSpacePressed: pr.activated()

        Rectangle {
            anchors.fill: parent
            visible: pr.activeFocus
            radius: parent.radius
            color: "transparent"
            border.color: ThemeTokens.Palette.focusRing
            border.width: 2
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s3
            anchors.rightMargin: ThemeTokens.Spacing.s3
            spacing: ThemeTokens.Spacing.s3

            AlbumArt {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                compact: true
                coverUrl: pr.rowCover
                coverController: root.coverController
            }

            Label {
                Layout.fillWidth: true
                text: pr.rowTitle
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }
        }
    }
}
