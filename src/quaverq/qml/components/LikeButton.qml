import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

Button {
    id: root

    property var libraryController
    property var song: ({})
    readonly property string mid: root.song && typeof root.song.mid === "string" ? root.song.mid : ""
    readonly property bool hasSong: root.mid.length > 0
    readonly property bool liked: root.libraryController
        && root.libraryController.likedRevision >= 0
        && root.libraryController.isLiked(root.mid)

    implicitWidth: ThemeTokens.Spacing.toolHitSize
    implicitHeight: ThemeTokens.Spacing.toolHitSize
    enabled: root.hasSong && root.libraryController && root.libraryController.authed && !root.libraryController.loading
    text: root.liked ? qsTr("取消喜欢") : qsTr("喜欢")
    Accessible.name: root.text
    onClicked: {
        if (root.libraryController)
            root.libraryController.toggleLike(root.song)
    }

    contentItem: Item {
        AppIcon {
            anchors.centerIn: parent
            size: 20
            source: root.liked ? "../icons/heart-filled.svg" : "../icons/heart.svg"
            color: root.enabled
                ? (root.liked ? ThemeTokens.Palette.primaryFg : ThemeTokens.Palette.surfaceVariantText)
                : ThemeTokens.Palette.stateDisabled
        }
    }

    background: Rectangle {
        radius: width / 2
        color: root.down
            ? ThemeTokens.Palette.statePressed
            : root.hovered ? ThemeTokens.Palette.stateHover : "transparent"
        border.color: "transparent"
    }
}
