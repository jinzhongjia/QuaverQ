import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    required property var song
    required property string name
    required property string singers
    required property string albumName
    required property string durationText
    required property int index
    property var libraryController
    property var coverController
    property var songDetailController
    property var playerController
    property bool selected: false
    readonly property string coverUrl: root.song && root.song.coverUrl ? root.song.coverUrl : ""
    readonly property var firstSinger: {
        if (!root.song || !root.song.singers || root.song.singers.length === 0)
            return null
        return root.song.singers[0]
    }
    readonly property bool hasArtistNav: !!(root.firstSinger
        && root.firstSinger.mid
        && root.firstSinger.mid.length > 0)
    readonly property bool hasAlbumNav: !!(root.song
        && root.song.albumMid
        && root.song.albumMid.length > 0)
    readonly property bool isLiked: !!(root.libraryController
        && root.song
        && root.song.mid
        && root.libraryController.isLiked(root.song.mid))

    readonly property string accessibleText: root.albumName
        ? qsTr("%1, %2, %3").arg(root.name).arg(root.singers).arg(root.albumName)
        : qsTr("%1, %2").arg(root.name).arg(root.singers)

    signal activated(var songData, int row)
    // 菜单里"查看歌手 / 查看专辑"的导航请求, 各 view 接到 detailRequested 上 → 走 root.pushDetail
    signal navigationRequested(string kind, string detailId, string title, string subtitle, string coverUrl)

    implicitHeight: 64
    radius: ThemeTokens.Spacing.radiusMd
    color: root.selected
        ? ThemeTokens.Palette.stateSelected
        : hoverHandler.hovered ? ThemeTokens.Palette.stateHover : "transparent"

    Accessible.role: Accessible.ListItem
    Accessible.name: root.selected
        ? qsTr("正在播放，%1").arg(root.accessibleText)
        : root.accessibleText
    activeFocusOnTab: true

    HoverHandler {
        id: hoverHandler
    }

    TapHandler {
        onTapped: root.activated(root.song, root.index)
    }

    // 桌面惯例: 右键在光标处弹出操作菜单 (与 "⋯" 同一个菜单)
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: function(eventPoint) {
            contextMenu.x = eventPoint.position.x
            contextMenu.y = eventPoint.position.y
            contextMenu.open()
        }
    }

    Keys.onReturnPressed: root.activated(root.song, root.index)
    Keys.onSpacePressed: root.activated(root.song, root.index)

    component StyledMenuItem: MenuItem {
        id: mi

        implicitWidth: 180
        implicitHeight: 36
        leftPadding: ThemeTokens.Spacing.s4
        rightPadding: ThemeTokens.Spacing.s5
        topPadding: 0
        bottomPadding: 0

        contentItem: Label {
            text: mi.text
            color: mi.enabled
                ? ThemeTokens.Palette.surfaceText
                : ThemeTokens.Palette.surfaceVariantText
            font.pixelSize: ThemeTokens.TypeScale.bodySm
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: ThemeTokens.Spacing.radiusSm
            color: mi.highlighted
                ? ThemeTokens.Palette.stateHover
                : "transparent"
        }
    }

    component StyledMenuSeparator: MenuSeparator {
        padding: ThemeTokens.Spacing.s2
        topPadding: ThemeTokens.Spacing.s2
        bottomPadding: ThemeTokens.Spacing.s2

        contentItem: Rectangle {
            implicitHeight: 1
            color: ThemeTokens.Palette.outlineMuted
        }
    }

    Menu {
        id: contextMenu
        modal: false
        dim: false
        padding: ThemeTokens.Spacing.s2

        background: Rectangle {
            implicitWidth: 180
            radius: ThemeTokens.Spacing.radiusMd
            color: ThemeTokens.Palette.surfaceElevated
            border.color: ThemeTokens.Palette.outline

            // 落影 (轻投影提升感)
            Rectangle {
                anchors.fill: parent
                anchors.margins: -1
                radius: parent.radius + 1
                color: "transparent"
                border.color: Qt.rgba(0, 0, 0, 0.06)
                z: -1
            }
        }

        StyledMenuItem {
            text: qsTr("播放")
            onTriggered: root.activated(root.song, root.index)
        }

        StyledMenuItem {
            text: qsTr("下一首播放")
            enabled: !!(root.playerController && root.song && root.song.mid)
            onTriggered: {
                if (root.playerController)
                    root.playerController.playSongNext(root.song)
            }
        }

        StyledMenuItem {
            text: qsTr("添加到待播列表")
            enabled: !!(root.playerController && root.song && root.song.mid)
            onTriggered: {
                if (root.playerController)
                    root.playerController.appendToQueue([root.song])
            }
        }

        StyledMenuSeparator {}

        StyledMenuItem {
            text: root.isLiked ? qsTr("取消收藏") : qsTr("收藏")
            enabled: !!(root.libraryController
                && root.libraryController.authed
                && root.song
                && root.song.mid)
            onTriggered: {
                if (root.libraryController)
                    root.libraryController.toggleLike(root.song)
            }
        }

        StyledMenuItem {
            text: qsTr("查看歌手")
            enabled: root.hasArtistNav
            onTriggered: {
                if (root.firstSinger) {
                    root.navigationRequested(
                        "artist",
                        root.firstSinger.mid,
                        root.firstSinger.name || "",
                        "",
                        ""
                    )
                }
            }
        }

        StyledMenuItem {
            text: qsTr("查看专辑")
            enabled: root.hasAlbumNav
            onTriggered: {
                if (root.song) {
                    root.navigationRequested(
                        "album",
                        root.song.albumMid,
                        root.song.albumName || "",
                        "",
                        root.coverUrl
                    )
                }
            }
        }

        StyledMenuSeparator {}

        StyledMenuItem {
            text: qsTr("歌曲详情")
            enabled: !!root.songDetailController
            onTriggered: {
                if (root.songDetailController)
                    root.songDetailController.open(root.song)
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 3
        visible: root.selected
        radius: width / 2
        color: ThemeTokens.Palette.primaryFg
    }

    Rectangle {
        anchors.fill: parent
        visible: root.activeFocus
        radius: parent.radius
        color: "transparent"
        border.color: ThemeTokens.Palette.focusRing
        border.width: 2
        z: 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s4
        anchors.rightMargin: ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s4

        Label {
            Layout.preferredWidth: 28
            text: root.selected
                ? "♪"
                : (hoverHandler.hovered ? "▶" : (root.index >= 0 ? String(root.index + 1) : ""))
            color: (root.selected || hoverHandler.hovered)
                ? ThemeTokens.Palette.primaryFg
                : ThemeTokens.Palette.surfaceVariantText
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
            font.weight: root.selected ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
        }

        AlbumArt {
            Layout.preferredWidth: 46
            Layout.preferredHeight: 46
            active: root.selected
            coverUrl: root.coverUrl
            coverController: root.coverController
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s2

            Label {
                Layout.fillWidth: true
                text: root.name
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.body
                font.weight: root.selected ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: root.albumName ? qsTr("%1 · %2").arg(root.singers).arg(root.albumName) : root.singers
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }
        }

        LikeButton {
            Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
            Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
            libraryController: root.libraryController
            song: root.song
        }

        Label {
            Layout.preferredWidth: 52
            text: root.durationText
            color: ThemeTokens.Palette.surfaceVariantText
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
        }

        IconButton {
            id: moreButton

            Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
            Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
            text: qsTr("更多操作")
            iconSource: "../icons/more-horizontal.svg"
            iconSize: 18
            onClicked: {
                // 把菜单挂在按钮下方左对齐, 跟主流播放器一致
                contextMenu.x = moreButton.x + moreButton.width - contextMenu.width
                contextMenu.y = moreButton.y + moreButton.height
                contextMenu.open()
            }
        }
    }
}
