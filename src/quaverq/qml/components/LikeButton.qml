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
    text: root.liked ? "♥" : "♡"
    Accessible.name: root.liked ? qsTr("取消喜欢") : qsTr("喜欢")
    onClicked: {
        if (root.libraryController)
            root.libraryController.toggleLike(root.song)
    }

    contentItem: Label {
        text: root.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: root.enabled
            ? (root.liked ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant)
            : ThemeTokens.Palette.stateDisabled
        font.pixelSize: ThemeTokens.TypeScale.h2
        font.weight: root.liked ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
    }

    background: Rectangle {
        radius: width / 2
        color: root.down
            ? ThemeTokens.Palette.statePressed
            : root.hovered ? ThemeTokens.Palette.stateHover : "transparent"
        border.color: "transparent"
    }
}
