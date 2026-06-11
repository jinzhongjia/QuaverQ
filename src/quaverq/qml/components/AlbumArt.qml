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
    // 双缓冲前层标记: 换 source 时新图先在后台层解码, 就绪后才换层显示,
    // 避免单 Image 换源瞬间清空画面导致占位图闪一下.
    // frontSource/backSource 是我们自己的记账串 —— 不能反读 Image.source 比较,
    // image:// URL 的百分号转义会被 QUrl 规范化, 字符串对不上 (换层判定会永远失败)
    property bool frontIsA: true
    property string frontSource: ""
    property string backSource: ""
    readonly property bool hasImage: root.frontSource.length > 0
        && (root.frontIsA ? coverImageA.status : coverImageB.status) === Image.Ready

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

    function applyDisplaySource() {
        const target = root.displaySource
        if (target.length === 0) {
            coverImageA.source = ""
            coverImageB.source = ""
            root.frontSource = ""
            root.backSource = ""
            root.frontIsA = true
            return
        }
        if (root.frontSource === target) {
            root.backSource = ""
            return
        }
        const front = root.frontIsA ? coverImageA : coverImageB
        const back = root.frontIsA ? coverImageB : coverImageA
        // 前层还没有可展示的图: 直接加载进前层 (首图路径)
        if (front.status !== Image.Ready || root.frontSource.length === 0) {
            front.source = target
            root.frontSource = target
            root.backSource = ""
            return
        }
        // 前层有图: 新图进后台层, promoteBack 在其就绪后换层
        back.source = target
        root.backSource = target
    }

    // back 层就绪且仍是当前目标 → 换层 (isA: 触发方是否为 A 层)
    function promoteBack(isA) {
        if (root.frontIsA === isA)
            return
        if (root.backSource.length === 0 || root.backSource !== root.displaySource)
            return
        const back = isA ? coverImageA : coverImageB
        if (back.status !== Image.Ready)
            return
        root.frontIsA = isA
        root.frontSource = root.backSource
        root.backSource = ""
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
    onDisplaySourceChanged: root.applyDisplaySource()

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

        // 双缓冲层 A/B: source 由 applyDisplaySource 显式赋值 (不绑定),
        // 缩放交给 provider id 里的 size 段, 不设 sourceSize (避免其变化触发重载)
        Image {
            id: coverImageA

            anchors.fill: parent
            opacity: root.frontIsA && coverImageA.status === Image.Ready ? 1 : 0
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: false
            mipmap: true
            onStatusChanged: root.promoteBack(true)

            Behavior on opacity {
                NumberAnimation {
                    duration: ThemeTokens.Motion.durFast
                }
            }
        }

        Image {
            id: coverImageB

            anchors.fill: parent
            opacity: !root.frontIsA && coverImageB.status === Image.Ready ? 1 : 0
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: false
            mipmap: true
            onStatusChanged: root.promoteBack(false)

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
