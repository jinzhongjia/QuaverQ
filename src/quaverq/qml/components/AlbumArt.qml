import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property bool active: false
    property bool compact: false
    property string coverUrl: ""
    property var coverController
    property string iconText: "♪"
    property int iconSize: compact ? ThemeTokens.TypeScale.body : ThemeTokens.TypeScale.h2
    property int imageSize: compact ? 96 : 512
    property int imageRevision: 0
    readonly property bool coverCached: root.coverUrl.length > 0
        && root.coverController
        && root.imageRevision >= 0
        && root.coverController.isCached(root.coverUrl)
    readonly property string imageSource: root.coverCached
        ? "image://covers/" + encodeURIComponent(root.coverUrl) + "|" + root.imageSize + "|" + root.imageRevision
        : ""
    readonly property bool hasImage: root.coverCached && coverImage.status === Image.Ready

    implicitWidth: compact ? 36 : 52
    implicitHeight: implicitWidth
    radius: compact ? ThemeTokens.Spacing.radiusMd : ThemeTokens.Spacing.radiusLg
    clip: true
    color: root.active ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.albumSurface
    border.color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.outlineMuted

    function requestCover() {
        if (root.coverUrl.length > 0 && root.coverController)
            root.coverController.fetchCover(root.coverUrl)
    }

    Component.onCompleted: root.requestCover()

    onCoverUrlChanged: {
        root.imageRevision += 1
        root.requestCover()
    }

    Connections {
        target: root.coverController

        function onCoverReady(url) {
            if (url === root.coverUrl)
                root.imageRevision += 1
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.min(34, Math.max(4, parent.width * 0.1))
        visible: !root.hasImage
        radius: parent.radius
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.accent
    }

    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: Math.max(5, parent.width * 0.12)
        anchors.bottomMargin: Math.max(5, parent.height * 0.12)
        width: Math.max(8, parent.width * 0.24)
        height: width
        visible: !root.hasImage
        radius: width / 2
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.accent
    }

    Label {
        anchors.centerIn: parent
        visible: !root.hasImage
        text: root.iconText
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
        font.pixelSize: root.iconSize
        font.weight: ThemeTokens.TypeScale.medium
    }

    Image {
        id: coverImage

        anchors.fill: parent
        visible: root.coverCached
        opacity: root.hasImage ? 1 : 0
        source: root.imageSource
        sourceSize.width: root.imageSize
        sourceSize.height: root.imageSize
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: false
        mipmap: true
    }

    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: "transparent"
        border.color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.outlineMuted
        border.width: 1
    }
}
