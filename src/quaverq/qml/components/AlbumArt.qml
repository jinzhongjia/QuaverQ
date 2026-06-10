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
    // 换封面 URL 时保留旧图直到新图就绪 (详情页头图: 卡片图 → 接口高清图的无缝升级);
    // 列表行 delegate 复用时旧图属于别的歌, 保持 false 立即回占位
    property bool retainOnSwitch: false
    // 最近一次"已就绪"的 provider source; retainOnSwitch 时新封面下载期间不清空
    property string displaySource: ""
    readonly property bool coverCached: root.coverUrl.length > 0
        && root.coverController
        && root.imageRevision >= 0
        && root.coverController.isCached(root.coverUrl)
    readonly property string imageSource: root.coverCached
        ? "image://covers/" + encodeURIComponent(root.coverUrl) + "|" + root.imageSize + "|" + root.coverRadius + "|" + root.imageRevision
        : ""
    readonly property bool hasImage: root.displaySource.length > 0 && coverImage.status === Image.Ready

    implicitWidth: compact ? 36 : 52
    implicitHeight: implicitWidth

    function requestCover() {
        if (root.coverUrl.length > 0 && root.coverController)
            root.coverController.fetchCover(root.coverUrl)
    }

    function syncDisplaySource() {
        if (root.imageSource.length > 0) {
            root.displaySource = root.imageSource
        } else if (!root.retainOnSwitch) {
            root.displaySource = ""
        }
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
        root.syncDisplaySource()
    }

    onWidthChanged: root.updateImageSize()
    onHeightChanged: root.updateImageSize()
    onImageSourceChanged: root.syncDisplaySource()

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

    Label {
        anchors.centerIn: parent
        visible: !root.hasImage
        text: root.iconText
        color: root.active ? ThemeTokens.Palette.primaryFg : ThemeTokens.Palette.surfaceVariantText
        font.pixelSize: root.iconSize
        font.weight: ThemeTokens.TypeScale.medium
    }

    Item {
        anchors.fill: parent
        visible: root.displaySource.length > 0

        Image {
            id: coverImage

            anchors.fill: parent
            opacity: root.hasImage ? 1 : 0
            source: root.displaySource
            sourceSize.width: root.imageSize
            sourceSize.height: root.imageSize
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: false
            mipmap: true

            Behavior on opacity {
                NumberAnimation {
                    duration: ThemeTokens.Motion.durFast
                }
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: !root.hasImage
        radius: root.circular ? width / 2 : (root.hasImage ? root.coverRadius : root.placeholderRadius)
        color: "transparent"
        border.color: root.active ? ThemeTokens.Palette.primaryFg : ThemeTokens.Palette.outlineMuted
        border.width: 1
    }
}
