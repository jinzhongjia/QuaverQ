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
    signal openPlaylistRequested(string pid, string title, string coverUrl)

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

        // 0) account identity (C4): 头像 + 昵称 + VIP 徽章; 未登录时即登录入口
        IdentityArea {
            objectName: "identityArea"
            Layout.fillWidth: true
            onActivated: root.authed ? root.routeRequested("library") : root.loginRequested()
        }

        // 1) primary navigation
        ColumnLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s2

            Repeater {
                model: [
                    { route: "home", label: qsTr("发现"), icon: "../icons/home.svg" },
                    { route: "search", label: qsTr("搜索"), icon: "../icons/search.svg" },
                    { route: "library", label: qsTr("资料库"), icon: "../icons/library.svg" }
                ]

                delegate: NavItem {
                    required property var modelData

                    Layout.fillWidth: true
                    text: modelData.label
                    iconSource: modelData.icon
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
            iconSource: "../icons/heart-filled.svg"
            iconColor: ThemeTokens.Palette.primaryFg
            label: qsTr("我喜欢")
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
                onActivated: root.openPlaylistRequested(cardId, title, coverUrl)
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
                        : qsTr("点击上方头像登录，同步你的歌单"))
                color: root.appController && root.appController.loginState === "expired"
                    ? ThemeTokens.Palette.error
                    : ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.caption
                wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }
        }

        // 4c) 紧凑模式: 歌单区整体隐藏后没有弹性项, 多余空间会被平摊到各格子
        // 把图标拉散; 这里补一个占位, 让导航钉在顶部 / 设置钉在底部
        Item {
            visible: root.compact
            Layout.fillWidth: true
            Layout.fillHeight: true
        }

        // 5) settings pinned at bottom
        NavItem {
            Layout.fillWidth: true
            text: qsTr("设置")
            iconSource: "../icons/settings.svg"
            compact: root.compact
            selected: root.selectedRoute === "settings"
            onActivated: root.routeRequested("settings")
        }
    }

    // ---- inline components ----

    component IdentityArea: Rectangle {
        id: ia

        readonly property bool loggedIn: root.authed
        readonly property string nickname: root.appController ? (root.appController.nickname || "") : ""
        // 已登录但画像还没拉到 (加载中 / 拉取失败) 时回退「已登录」
        readonly property string displayName: ia.loggedIn
            ? (ia.nickname.length > 0 ? ia.nickname : qsTr("已登录"))
            : qsTr("点击登录")
        readonly property string avatarUrl: ia.loggedIn && root.appController
            ? (root.appController.avatarUrl || "") : ""
        readonly property string vipKind: ia.loggedIn && root.appController
            ? (root.appController.vipKind || "") : ""
        readonly property string vipLabel: ia.vipKind === "svip"
            ? qsTr("SVIP")
            : ia.vipKind === "hugevip"
                ? qsTr("豪华绿钻")
                : ia.vipKind === "vip" ? qsTr("绿钻") : ""

        signal activated()

        implicitHeight: root.compact ? 48 : 56
        radius: ThemeTokens.Spacing.radiusMd
        color: iaHover.hovered ? ThemeTokens.Palette.stateHover : "transparent"

        Accessible.role: Accessible.Button
        Accessible.name: ia.loggedIn
            ? ia.displayName + (ia.vipLabel.length > 0 ? " " + ia.vipLabel : "")
            : qsTr("点击登录")
        activeFocusOnTab: true

        HoverHandler {
            id: iaHover

            cursorShape: Qt.PointingHandCursor
        }
        TapHandler { onTapped: ia.activated() }
        Keys.onReturnPressed: ia.activated()
        Keys.onSpacePressed: ia.activated()

        Rectangle {
            anchors.fill: parent
            // Rectangle 无 visualFocus (Control 专属); TapHandler 点击不夺焦,
            // activeFocus 实际只在键盘 Tab 聚焦时为真, 同 FunctionRow/PlaylistRow
            visible: ia.activeFocus
            radius: parent.radius
            color: "transparent"
            border.color: ThemeTokens.Palette.focusRing
            border.width: 2
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: root.compact ? 0 : ThemeTokens.Spacing.s3
            anchors.rightMargin: root.compact ? 0 : ThemeTokens.Spacing.s3
            spacing: ThemeTokens.Spacing.s3

            Item {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                Layout.alignment: Qt.AlignVCenter
                // 紧凑态只剩头像, 占满整行居中
                Layout.fillWidth: root.compact

                AlbumArt {
                    width: 36
                    height: 36
                    anchors.centerIn: parent
                    visible: ia.loggedIn
                    circular: true
                    compact: true
                    coverUrl: ia.avatarUrl
                    coverController: root.coverController
                    // 头像没加载出来时回退昵称首字 (Array.from 防截断代理对)
                    iconText: ia.displayName.length > 0 ? Array.from(ia.displayName)[0] : "♪"
                    iconSize: ThemeTokens.TypeScale.bodySm
                }

                Rectangle {
                    width: 36
                    height: 36
                    anchors.centerIn: parent
                    visible: !ia.loggedIn
                    radius: width / 2
                    color: ThemeTokens.Palette.albumSurface
                    border.color: ThemeTokens.Palette.outlineMuted
                    border.width: 1

                    AppIcon {
                        anchors.centerIn: parent
                        size: 18
                        source: "../icons/user.svg"
                        color: ThemeTokens.Palette.surfaceVariantText
                    }
                }
            }

            ColumnLayout {
                visible: !root.compact
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 2

                Label {
                    Layout.fillWidth: true
                    text: ia.displayName
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                RowLayout {
                    visible: ia.vipLabel.length > 0
                    spacing: ThemeTokens.Spacing.s2

                    // 文字 pill 按 vipKind 种类显示 (SVIP > 豪华绿钻 > 绿钻).
                    // 故意不用服务端 identity.icon 图: 那是"绿钻等级"徽章
                    // (lv_N.png 绿钻图标), 不表达会员种类 —— SVIP 账号会被它
                    // 显示成绿钻 (真机验收踩过). vipIconUrl 数据保留备用.
                    Rectangle {
                        implicitHeight: 16
                        implicitWidth: vipBadgeLabel.implicitWidth + ThemeTokens.Spacing.s2 * 2
                        radius: height / 2
                        color: ia.vipKind === "vip"
                            ? ThemeTokens.Palette.primaryContainer
                            : ThemeTokens.Palette.vipGoldContainer

                        Label {
                            id: vipBadgeLabel

                            objectName: "vipBadgeLabel"
                            anchors.centerIn: parent
                            text: ia.vipLabel
                            color: ia.vipKind === "vip"
                                ? ThemeTokens.Palette.primaryFg
                                : ThemeTokens.Palette.vipGold
                            font.pixelSize: ThemeTokens.TypeScale.caption
                            font.weight: ThemeTokens.TypeScale.medium
                        }
                    }

                    Item { Layout.fillWidth: true }
                }
            }
        }
    }

    component FunctionRow: Rectangle {
        id: fr

        property url iconSource: ""
        property color iconColor: ThemeTokens.Palette.surfaceVariantText
        property string label: ""

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

            AppIcon {
                Layout.preferredWidth: ThemeTokens.Spacing.s5
                size: 16
                source: fr.iconSource
                color: fr.iconColor
            }

            Label {
                Layout.fillWidth: true
                text: fr.label
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
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
