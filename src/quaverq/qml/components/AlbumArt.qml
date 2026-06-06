import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

Item {
    id: root

    property bool active: false
    property bool compact: false
    property bool circular: false
    property string coverUrl: ""
    property var coverController
    property string iconText: "♪"
    property int iconSize: compact ? ThemeTokens.TypeScale.body : ThemeTokens.TypeScale.h2
    property int imageSize: compact ? 96 : 512
    property int imageRevision: 0
    property int coverRadius: root.circular
        ? Math.round(root.imageSize * 4)
        : compact
            ? ThemeTokens.Spacing.radiusSm
            : Math.max(ThemeTokens.Spacing.radiusSm, Math.min(6, Math.round(root.imageSize * 0.1)))
    readonly property int placeholderRadius: compact ? ThemeTokens.Spacing.radiusMd : ThemeTokens.Spacing.radiusLg
    readonly property bool coverCached: root.coverUrl.length > 0
        && root.coverController
        && root.imageRevision >= 0
        && root.coverController.isCached(root.coverUrl)
    readonly property string imageSource: root.coverCached
        ? "image://covers/" + encodeURIComponent(root.coverUrl) + "|" + root.imageSize + "|" + root.coverRadius + "|" + root.imageRevision
        : ""
    readonly property bool hasImage: root.coverCached && coverImage.status === Image.Ready

    implicitWidth: compact ? 36 : 52
    implicitHeight: implicitWidth

    function requestCover() {
        if (root.coverUrl.length > 0 && root.coverController)
            root.coverController.fetchCover(root.coverUrl)
    }

    function updateImageSize() {
        const nextSize = Math.max(
            1,
            Math.round(Math.max(root.width, root.height, root.implicitWidth, root.implicitHeight))
        )
        if (root.imageSize !== nextSize)
            root.imageSize = nextSize
    }

    Component.onCompleted: {
        root.updateImageSize()
        root.requestCover()
    }

    onWidthChanged: root.updateImageSize()
    onHeightChanged: root.updateImageSize()

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
        anchors.fill: parent
        visible: !root.hasImage
        radius: root.circular ? width / 2 : root.placeholderRadius
        color: root.active ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.albumSurface
    }

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.min(34, Math.max(4, parent.width * 0.1))
        visible: !root.hasImage && !root.circular
        radius: root.placeholderRadius
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.accent
    }

    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: Math.max(5, parent.width * 0.12)
        anchors.bottomMargin: Math.max(5, parent.height * 0.12)
        width: Math.max(8, parent.width * 0.24)
        height: width
        visible: !root.hasImage && !root.circular
        radius: width / 2
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.accent
    }

    Label {
        anchors.centerIn: parent
        visible: !root.hasImage
        text: root.iconText
        color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.surfaceVariantText
        font.pixelSize: root.iconSize
        font.weight: ThemeTokens.TypeScale.medium
    }

    Item {
        anchors.fill: parent
        visible: root.coverCached

        Image {
            id: coverImage

            anchors.fill: parent
            opacity: root.hasImage ? 1 : 0
            source: root.imageSource
            sourceSize.width: root.imageSize
            sourceSize.height: root.imageSize
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: false
            mipmap: true
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: !root.hasImage
        radius: root.circular ? width / 2 : (root.hasImage ? root.coverRadius : root.placeholderRadius)
        color: "transparent"
        border.color: root.active ? ThemeTokens.Palette.primary : ThemeTokens.Palette.outlineMuted
        border.width: 1
    }
}
