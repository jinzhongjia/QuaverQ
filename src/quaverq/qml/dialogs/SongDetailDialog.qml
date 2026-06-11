pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

// 第二档 2.1: 歌曲详情弹窗 (相似歌曲 + 相关歌单)
// 触发: SongRow 右键 / 菜单键 → controller.open(song)
// 关闭: ESC / 点窗外 / 右上角关闭按钮 → controller.close()
Dialog {
    id: root

    property var songDetailController
    property var coverController
    property var libraryController
    property var playerController

    signal detailRequested(string kind, string detailId, string title, string subtitle, string coverUrl)

    objectName: "songDetailDialog"
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    // 模态遮罩走 scrim token (W13): Basic 默认跟系统 palette.shadow, 暗色下偏弱
    Overlay.modal: Rectangle { color: ThemeTokens.Palette.scrim }
    width: Math.min(parent ? parent.width - ThemeTokens.Spacing.s8 : 720, 720)
    height: Math.min(parent ? parent.height - ThemeTokens.Spacing.s8 : 560, 560)
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? Math.round((parent.height - height) / 2) : 0
    padding: ThemeTokens.Spacing.s5

    readonly property var current: root.songDetailController ? root.songDetailController.currentSong : ({})
    readonly property bool hasSong: !!(root.current
        && typeof root.current.mid === "string"
        && root.current.mid.length > 0)
    readonly property string singerText: {
        if (!root.hasSong) return ""
        const names = root.current.singerNames
        // PySide6 list 是 QVariantList, Array.isArray 不灵; 用 length 直接判
        if (names && names.length !== undefined && names.length > 0) {
            const arr = []
            for (let i = 0; i < names.length; ++i) arr.push(names[i])
            return arr.join("、")
        }
        return ""
    }

    // ===== 三态判定 =====
    readonly property bool isLoading: !!(root.songDetailController && root.songDetailController.loading)
    readonly property bool hasError: !!(root.songDetailController
        && !root.songDetailController.loading
        && root.songDetailController.errorMessage.length > 0)
    readonly property bool similarHasItems: !!(root.songDetailController
        && root.songDetailController.similarSongsModel
        && root.songDetailController.similarSongsModel.count > 0)
    readonly property bool relatedHasItems: !!(root.songDetailController
        && root.songDetailController.relatedPlaylistsModel
        && root.songDetailController.relatedPlaylistsModel.count > 0)
    // 2.4 歌曲附加信息
    readonly property var songInfo: root.songDetailController
        ? root.songDetailController.songInfo
        : ({})
    readonly property string infoFactsLine: {
        if (!root.songInfo) return ""
        const parts = []
        if (root.songInfo.language) parts.push(root.songInfo.language)
        if (root.songInfo.genre) parts.push(root.songInfo.genre)
        if (root.songInfo.company) parts.push(root.songInfo.company)
        if (root.songInfo.publishTime) parts.push(root.songInfo.publishTime)
        return parts.join(" · ")
    }
    readonly property bool hasInfoFacts: root.infoFactsLine.length > 0
    // 注意: PySide6 list 经 QVariant 转成 QML 时是 QVariantList, Array.isArray() 对它返回 false.
    // 用 length 直接判断 (truthy check 走 != undefined && length > 0).
    readonly property bool hasProducers: !!(root.songInfo
        && root.songInfo.producers
        && root.songInfo.producers.length > 0)
    readonly property bool hasTags: !!(root.songInfo
        && root.songInfo.tags
        && root.songInfo.tags.length > 0)
    readonly property bool hasIntro: !!(root.songInfo
        && typeof root.songInfo.intro === "string"
        && root.songInfo.intro.length > 0)
    readonly property bool hasAnySongInfo: root.hasInfoFacts
        || root.hasProducers
        || root.hasTags
        || root.hasIntro
    readonly property bool isLoaded: !root.isLoading && !root.hasError
    readonly property bool isLoadedAndAllEmpty: root.isLoaded
        && !root.similarHasItems
        && !root.relatedHasItems
        && !root.hasAnySongInfo

    Connections {
        target: root.songDetailController

        function onVisibleChanged() {
            if (root.songDetailController && root.songDetailController.visible) {
                if (!root.visible)
                    root.open()
            } else if (root.visible) {
                root.close()
            }
        }
    }

    onClosed: {
        if (root.songDetailController && root.songDetailController.visible)
            root.songDetailController.close()
    }

    background: Rectangle {
        radius: ThemeTokens.Spacing.radiusLg
        color: ThemeTokens.Palette.surface
        border.color: ThemeTokens.Palette.outline
    }

    contentItem: ColumnLayout {
        spacing: ThemeTokens.Spacing.s5

        // ===== 顶部: 歌曲信息 =====
        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            Components.AlbumArt {
                Layout.preferredWidth: 80
                Layout.preferredHeight: 80
                active: root.hasSong
                coverUrl: root.hasSong && root.current.coverUrl ? root.current.coverUrl : ""
                coverController: root.coverController
                iconSize: ThemeTokens.TypeScale.h2
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.current.name : qsTr("歌曲详情")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h2
                    font.weight: ThemeTokens.TypeScale.bold
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.hasSong
                    text: root.singerText
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.body
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.hasSong && root.current.albumName && root.current.albumName.length > 0
                    text: root.hasSong ? qsTr("专辑：%1").arg(root.current.albumName) : ""
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }

            Components.IconButton {
                Layout.alignment: Qt.AlignTop
                text: qsTr("关闭")
                iconText: "✕"
                iconColor: ThemeTokens.Palette.surfaceVariantText
                onClicked: root.close()
            }
        }

        // 分隔线: 只在 loaded 且有内容时显示
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            visible: root.isLoaded && !root.isLoadedAndAllEmpty
            color: ThemeTokens.Palette.outlineMuted
        }

        // ===== 内容区: 三态互斥 =====
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // --- 态 1: loading ---
            ColumnLayout {
                anchors.centerIn: parent
                visible: root.isLoading
                spacing: ThemeTokens.Spacing.s3

                Components.Spinner {
                    Layout.alignment: Qt.AlignHCenter
                    size: 36
                }

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("加载中...")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                }
            }

            // --- 态 2: error ---
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - ThemeTokens.Spacing.s6, 400)
                visible: root.hasError
                spacing: ThemeTokens.Spacing.s4

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: "⚠"
                    color: ThemeTokens.Palette.error
                    font.pixelSize: ThemeTokens.TypeScale.h1
                }

                Label {
                    Layout.fillWidth: true
                    text: root.songDetailController ? root.songDetailController.errorMessage : ""
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }

                Button {
                    id: retryButton

                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 96
                    Layout.preferredHeight: 36
                    text: qsTr("重试")
                    Accessible.name: qsTr("重试加载相似与相关歌单")
                    onClicked: {
                        if (root.songDetailController)
                            root.songDetailController.retry()
                    }

                    contentItem: Label {
                        text: retryButton.text
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: ThemeTokens.Palette.primaryText
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    background: Rectangle {
                        radius: ThemeTokens.Spacing.radiusMd
                        color: retryButton.down
                            ? ThemeTokens.Palette.primaryActive
                            : retryButton.hovered ? ThemeTokens.Palette.primaryHover : ThemeTokens.Palette.primary
                    }
                }
            }

            // --- 态 3a: loaded 且全部为空 ---
            Label {
                anchors.centerIn: parent
                visible: root.isLoadedAndAllEmpty
                text: qsTr("暂无相似歌曲和相关歌单")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
            }

            // --- 态 3b: loaded 有内容 (歌曲信息 / 相似 / 相关; 空 section 隐藏) ---
            // 内容超出 dialog 时 ScrollView 滚动, 防止专辑卡片被裁掉
            ScrollView {
                id: loadedScroll

                anchors.fill: parent
                visible: root.isLoaded && !root.isLoadedAndAllEmpty
                clip: true
                contentWidth: loadedScroll.availableWidth
                // 给右侧滚动条预留 gutter, 内容不会被压在滚动条下
                rightPadding: ThemeTokens.Spacing.s4
                // 内容超高时滚动条常显: AsNeeded 不滚不出现, 用户发现不了下面还有内容
                ScrollBar.vertical.policy: loadedScroll.contentHeight > loadedScroll.height
                    ? ScrollBar.AlwaysOn
                    : ScrollBar.AlwaysOff

                ColumnLayout {
                    width: loadedScroll.availableWidth
                    spacing: ThemeTokens.Spacing.s5

                // --- 歌曲信息 (2.4 加入: 语种/流派/制作人/标签/简介) ---
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.hasAnySongInfo
                    spacing: ThemeTokens.Spacing.s2

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("歌曲信息")
                        color: ThemeTokens.Palette.surfaceText
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    // 单行 facts: 语种 · 流派 · 公司 · 发布时间
                    Label {
                        Layout.fillWidth: true
                        visible: root.hasInfoFacts
                        text: root.infoFactsLine
                        color: ThemeTokens.Palette.surfaceVariantText
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        elide: Text.ElideRight
                    }

                    // 制作人: 把 producers groups 紧凑成一行字符串
                    Label {
                        id: producerLabel

                        Layout.fillWidth: true
                        visible: root.hasProducers
                        text: {
                            if (!root.hasProducers) return ""
                            const parts = []
                            for (let i = 0; i < root.songInfo.producers.length; ++i) {
                                const g = root.songInfo.producers[i]
                                let namesStr = ""
                                if (g.names && g.names.length !== undefined) {
                                    const arr = []
                                    for (let j = 0; j < g.names.length; ++j) arr.push(g.names[j])
                                    namesStr = arr.join("、")
                                }
                                if (g.title && namesStr)
                                    parts.push(g.title + "：" + namesStr)
                            }
                            return parts.join(" / ")
                        }
                        color: ThemeTokens.Palette.surfaceVariantText
                        font.pixelSize: ThemeTokens.TypeScale.caption
                        wrapMode: Text.WordWrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                    }

                    // 标签: chips 紧凑横排
                    Flow {
                        Layout.fillWidth: true
                        visible: root.hasTags
                        spacing: ThemeTokens.Spacing.s2

                        Repeater {
                            model: root.hasTags ? root.songInfo.tags : []

                            delegate: Rectangle {
                                id: tagChip

                                required property string modelData
                                implicitWidth: tagLabel.implicitWidth + ThemeTokens.Spacing.s4 * 2
                                implicitHeight: tagLabel.implicitHeight + ThemeTokens.Spacing.s2 * 2
                                radius: implicitHeight / 2
                                color: ThemeTokens.Palette.surfaceVariant

                                Label {
                                    id: tagLabel
                                    anchors.centerIn: parent
                                    text: tagChip.modelData
                                    color: ThemeTokens.Palette.surfaceVariantText
                                    font.pixelSize: ThemeTokens.TypeScale.caption
                                }
                            }
                        }
                    }

                    // 简介: 折叠成最多 2 行
                    Label {
                        Layout.fillWidth: true
                        visible: root.hasIntro
                        text: root.hasIntro ? root.songInfo.intro : ""
                        color: ThemeTokens.Palette.surfaceVariantText
                        font.pixelSize: ThemeTokens.TypeScale.caption
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }

                // --- 相似歌曲 (横向, 只在有数据时显示) ---
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.similarHasItems
                    spacing: ThemeTokens.Spacing.s3

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("相似歌曲")
                        color: ThemeTokens.Palette.surfaceText
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 96
                        orientation: ListView.Horizontal
                        spacing: ThemeTokens.Spacing.s3
                        clip: true
                        model: root.songDetailController ? root.songDetailController.similarSongsModel : null
                        boundsBehavior: Flickable.StopAtBounds
                        reuseItems: true

                        delegate: Rectangle {
                            id: simCell

                            required property int index
                            required property string mid
                            required property string name
                            required property string singers
                            required property string coverUrl

                            width: 240
                            height: 80
                            radius: ThemeTokens.Spacing.radiusMd
                            color: simHover.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                            border.color: ThemeTokens.Palette.outlineMuted

                            Accessible.role: Accessible.Button
                            Accessible.name: qsTr("播放 %1").arg(simCell.name)

                            HoverHandler { id: simHover }

                            // 点击播放该相似歌曲 (以相似列表为队列), 并关闭弹窗
                            TapHandler {
                                onTapped: {
                                    if (root.playerController && root.songDetailController) {
                                        root.playerController.playFromModel(
                                            root.songDetailController.similarSongsModel,
                                            simCell.index
                                        )
                                        root.close()
                                    }
                                }
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: ThemeTokens.Spacing.s2
                                spacing: ThemeTokens.Spacing.s3

                                Components.AlbumArt {
                                    Layout.preferredWidth: 56
                                    Layout.preferredHeight: 56
                                    active: false
                                    coverUrl: simCell.coverUrl
                                    coverController: root.coverController
                                    iconSize: ThemeTokens.TypeScale.body
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: ThemeTokens.Spacing.s2

                                    Label {
                                        Layout.fillWidth: true
                                        text: simCell.name
                                        color: ThemeTokens.Palette.surfaceText
                                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                                        font.weight: ThemeTokens.TypeScale.medium
                                        elide: Text.ElideRight
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        text: simCell.singers
                                        color: ThemeTokens.Palette.surfaceVariantText
                                        font.pixelSize: ThemeTokens.TypeScale.caption
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }

                        ScrollBar.horizontal: ScrollBar {}
                    }
                }

                // --- 相关歌单 (横向 Card, 只在有数据时显示) ---
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.relatedHasItems
                    spacing: ThemeTokens.Spacing.s3

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("包含此曲的歌单")
                        color: ThemeTokens.Palette.surfaceText
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    ListView {
                        Layout.fillWidth: true
                        // 160 封面 (=width) + s3 + 标题 + s3 + 创作者 + 给 hover 角标留点空间
                        // 在 ScrollView 内 fillHeight 没意义, 用足够大的 preferredHeight
                        Layout.preferredHeight: 240
                        orientation: ListView.Horizontal
                        spacing: ThemeTokens.Spacing.s4
                        clip: true
                        model: root.songDetailController ? root.songDetailController.relatedPlaylistsModel : null
                        boundsBehavior: Flickable.StopAtBounds
                        reuseItems: true

                        delegate: Item {
                            id: relCell

                            required property string kind
                            required property string cardId
                            required property string title
                            required property string subtitle
                            required property string coverUrl
                            required property string meta

                            width: 160
                            height: ListView.view.height

                            Components.Card {
                                width: parent.width
                                title: relCell.title
                                subtitle: relCell.subtitle
                                coverUrl: relCell.coverUrl
                                meta: relCell.meta
                                coverController: root.coverController
                                onActivated: {
                                    root.detailRequested(relCell.kind, relCell.cardId, relCell.title, relCell.subtitle, relCell.coverUrl)
                                    root.close()
                                }
                                onPlayRequested: {
                                    root.detailRequested(relCell.kind, relCell.cardId, relCell.title, relCell.subtitle, relCell.coverUrl)
                                    root.close()
                                }
                            }
                        }

                        ScrollBar.horizontal: ScrollBar {}
                    }
                }
                }
            }
        }
    }
}
