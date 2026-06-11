pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

ColumnLayout {
    id: root

    property string routeName: "detail"
    property string detailKind: "playlist"
    property string detailId: ""
    property string detailTitle: qsTr("详情")
    property string detailSubtitle: ""
    // 入口卡片的封面 (B1): 详情接口返回前头图立即可显示
    property string detailCoverUrl: ""
    property var coverController
    // 工厂模式: 每个 DetailView 实例自持 controller (见 AGENTS.md 「栈式视图必须自持状态」契约).
    property var detailControllerFactory
    property var detailController: null
    property var playerController
    property var libraryController
    property var songDetailController
    // 2.2: 歌手 tab 索引. 非 artist 时永远 0. 每个 DetailView 实例独立 (pop 回栈时保留).
    property int currentTab: 0

    readonly property string displayKind: root.detailController && root.detailController.kind.length > 0
        ? root.detailController.kind
        : root.detailKind
    readonly property string displayTitle: root.detailController && root.detailController.title.length > 0
        ? root.detailController.title
        : root.detailTitle
    readonly property string displaySubtitle: root.detailController && root.detailController.subtitle.length > 0
        ? root.detailController.subtitle
        : root.detailSubtitle
    readonly property string displayDescription: root.detailController
        ? root.detailController.description
        : ""
    readonly property bool hasSongs: root.detailController
        && root.detailController.songModel
        && root.detailController.songModel.count > 0
    readonly property bool loading: root.detailController ? root.detailController.loading : false
    readonly property string errorMessage: root.detailController ? root.detailController.errorMessage : ""

    signal backRequested()
    signal searchRequested(string keyword)
    signal detailRequested(string kind, string detailId, string title, string subtitle, string coverUrl)
    // 由 root.detailController.errorRaised 透传到 Main 的 globalSnackbar
    signal errorRaised(string message)

    spacing: 0

    function kindLabel(kind) {
        switch (kind) {
        case "album":
            return qsTr("专辑")
        case "artist":
            return qsTr("艺人")
        case "top":
            return qsTr("排行榜")
        default:
            return qsTr("歌单")
        }
    }

    function loadDetail() {
        if (!root.detailController || root.detailId.length <= 0)
            return
        root.detailController.loadDetail(
            root.detailKind,
            root.detailId,
            root.detailTitle,
            root.detailSubtitle,
            root.detailCoverUrl
        )
    }

    // 2.2: 切到歌手 tab 时按需触发后端拉取
    function _ensureSingerTabLoaded(tabIndex) {
        if (!root.detailController || root.displayKind !== "artist") return
        if (tabIndex === 1) root.detailController.loadSingerSongs()
        else if (tabIndex === 2) root.detailController.loadSingerAlbums()
        else if (tabIndex === 3) root.detailController.loadSimilarSingers()
    }

    Component.onCompleted: {
        // 工厂模式: 创建本 View 专属的 controller, parent=root 让 Qt 接管销毁
        if (root.detailControllerFactory) {
            root.detailController = root.detailControllerFactory.create(root)
        }
        root.loadDetail()
    }

    onCurrentTabChanged: root._ensureSingerTabLoaded(root.currentTab)

    // 透传 controller errorRaised 到 view 信号 (Main.qml globalSnackbar 接)
    Connections {
        target: root.detailController
        function onErrorRaised(message) {
            root.errorRaised(message)
        }
    }

    // 页内错误与全局 Banner 同一形态 (W9), 加载失败带「重试」动作
    Components.Banner {
        id: detailErrorBanner

        Layout.fillWidth: true
        kind: "error"
        actionText: qsTr("重试")
        onActionTriggered: root.loadDetail()
    }

    // 显式 Binding: Banner.dismiss() 会写空 message, 直接绑定会被这次写入打断;
    // Binding 元素在 errorMessage 再变化时重新接管 (SettingsView 同款模式)
    Binding {
        target: detailErrorBanner
        property: "message"
        value: root.errorMessage
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s5

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s5

            Components.AlbumArt {
                Layout.preferredWidth: 168
                Layout.preferredHeight: 168
                // 顶部锚定: 文字列加载后变高时封面不再被重新垂直居中 (整个头部"呼吸"一下)
                Layout.alignment: Qt.AlignTop
                circular: root.displayKind === "artist"
                iconText: root.displayKind === "artist" ? "◎" : root.displayKind === "top" ? "↗" : "♪"
                iconSize: ThemeTokens.TypeScale.display
                active: root.hasSongs
                // controller 创建瞬间 coverUrl 为空, 退回卡片封面避免一帧空窗
                coverUrl: root.detailController && root.detailController.coverUrl.length > 0
                    ? root.detailController.coverUrl
                    : root.detailCoverUrl
                // 卡片图 → 接口高清图切换期间保留旧图, 不闪占位
                retainOnSwitch: true
                coverController: root.coverController
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: ThemeTokens.Spacing.s3

                Label {
                    Layout.fillWidth: true
                    text: root.kindLabel(root.displayKind)
                    color: ThemeTokens.Palette.primaryFg
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.displayTitle
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.display
                    font.weight: ThemeTokens.TypeScale.bold
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                Label {
                    // subtitle 与 kind 标签重复 (如"艺人") 时不再显示一遍;
                    // 加载中不冒充"暂无简介" (加载完会换成真值, 文字跳变);
                    // 艺人页 subtitle 为空时直接隐藏, 不显示"暂无简介"占位
                    readonly property string subtitleText: {
                        const value = root.displaySubtitle
                        if (value.length > 0 && value !== root.kindLabel(root.displayKind))
                            return value
                        if (root.loading)
                            return ""
                        return root.displayKind === "artist" ? "" : qsTr("暂无简介")
                    }

                    Layout.fillWidth: true
                    // 加载中即使无文字也占住一行, 防止内容到达时按钮 / 列表跳位
                    visible: root.loading || text.length > 0
                    text: subtitleText
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    // 同上: 加载中预留简介行位, 减小数据到达时的下移幅度
                    visible: root.loading || root.displayDescription.length > 0
                    text: root.displayDescription
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: ThemeTokens.Spacing.s3

                    Button {
                        id: playAllButton

                        Layout.preferredWidth: 132
                        Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                        enabled: root.hasSongs && !root.loading
                        text: qsTr("播放全部")
                        Accessible.name: text
                        onClicked: {
                            if (root.playerController && root.detailController)
                                root.playerController.playFromModel(root.detailController.songModel, 0)
                        }

                        contentItem: RowLayout {
                            spacing: ThemeTokens.Spacing.s2

                            Item { Layout.fillWidth: true }

                            Components.AppIcon {
                                size: 16
                                source: "../icons/play.svg"
                                color: playAllButton.enabled ? ThemeTokens.Palette.primaryText : ThemeTokens.Palette.surfaceVariantText
                            }

                            Label {
                                text: playAllButton.text
                                verticalAlignment: Text.AlignVCenter
                                color: playAllButton.enabled ? ThemeTokens.Palette.primaryText : ThemeTokens.Palette.surfaceVariantText
                                font.pixelSize: ThemeTokens.TypeScale.bodySm
                                font.weight: ThemeTokens.TypeScale.medium
                            }

                            Item { Layout.fillWidth: true }
                        }

                        background: Rectangle {
                            radius: ThemeTokens.Spacing.radiusPill
                            color: !playAllButton.enabled
                                ? ThemeTokens.Palette.surfaceVariant
                                : playAllButton.down ? ThemeTokens.Palette.primaryActive
                                : playAllButton.hovered ? ThemeTokens.Palette.primaryHover
                                : ThemeTokens.Palette.primary
                        }
                    }

                    Button {
                        id: searchButton

                        Layout.preferredWidth: 112
                        Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                        text: qsTr("搜索相关")
                        Accessible.name: text
                        onClicked: root.searchRequested(root.displayTitle)

                        contentItem: Label {
                            text: searchButton.text
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: ThemeTokens.Palette.surfaceText
                            font.pixelSize: ThemeTokens.TypeScale.bodySm
                            font.weight: ThemeTokens.TypeScale.medium
                        }

                        background: Rectangle {
                            radius: ThemeTokens.Spacing.radiusPill
                            color: searchButton.down
                                ? ThemeTokens.Palette.statePressed
                                : searchButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                            border.color: ThemeTokens.Palette.outline
                        }
                    }
                }
            }
        }

        // ===== Section header / Tab bar =====
        // 非 artist: 显示原有的标题 + 计数; artist: 显示 4 个 tab
        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4
            visible: root.displayKind !== "artist"

            Label {
                text: qsTr("曲目")
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.bold
            }

            Label {
                text: root.loading
                    ? qsTr("加载中...")
                    : root.hasSongs
                        ? qsTr("%1 首").arg(root.detailController.songModel.count)
                        : qsTr("暂无曲目")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
            }
        }

        Components.TabRow {
            id: artistTabRow

            Layout.fillWidth: true
            visible: root.displayKind === "artist"
            tabs: [qsTr("热门歌曲"), qsTr("全部歌曲"), qsTr("全部专辑"), qsTr("相似歌手")]
            currentIndex: root.currentTab
            onActivated: function(index) {
                root.currentTab = index
            }
        }

        // ===== 内容区: 非 artist 走 songList; artist 走 4-page StackLayout =====
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.displayKind === "artist" ? root.currentTab : 0

            // ----- Page 0: 热门歌曲 (artist) / 曲目 (其它) — 复用 detailController.songModel -----
            SongListPage {
                model: root.detailController ? root.detailController.songModel : null
                emptyText: root.displayKind === "artist" ? qsTr("暂无热门歌曲") : qsTr("暂无曲目")
                loading: root.loading
                hasItems: root.hasSongs
                showRetry: root.errorMessage.length > 0
                onPlayRequested: function(row) {
                    if (root.playerController && root.detailController)
                        root.playerController.playFromModel(root.detailController.songModel, row)
                }
                onRetryClicked: root.loadDetail()
            }

            // ----- Page 1-3 仅 artist 时实际有内容 -----
            SongListPage {
                visible: root.displayKind === "artist"
                model: root.detailController ? root.detailController.singerSongsModel : null
                emptyText: qsTr("暂无歌曲")
                loading: root.detailController ? root.detailController.singerSongsLoading : false
                hasItems: root.detailController
                    && root.detailController.singerSongsModel
                    && root.detailController.singerSongsModel.count > 0
                showRetry: false
                onPlayRequested: function(row) {
                    if (root.playerController && root.detailController)
                        root.playerController.playFromModel(root.detailController.singerSongsModel, row)
                }
            }

            CardGridPage {
                visible: root.displayKind === "artist"
                model: root.detailController ? root.detailController.singerAlbumsModel : null
                emptyText: qsTr("暂无专辑")
                kindFallback: "album"
                loading: root.detailController ? root.detailController.singerAlbumsLoading : false
                hasItems: root.detailController
                    && root.detailController.singerAlbumsModel
                    && root.detailController.singerAlbumsModel.count > 0
                onCardRequested: function(kind, detailId, title, subtitle, coverUrl) {
                    root.detailRequested(kind, detailId, title, subtitle, coverUrl)
                }
            }

            CardGridPage {
                visible: root.displayKind === "artist"
                model: root.detailController ? root.detailController.similarSingersModel : null
                emptyText: qsTr("暂无相似歌手")
                kindFallback: "artist"
                circular: true
                loading: root.detailController ? root.detailController.similarSingersLoading : false
                hasItems: root.detailController
                    && root.detailController.similarSingersModel
                    && root.detailController.similarSingersModel.count > 0
                onCardRequested: function(kind, detailId, title, subtitle, coverUrl) {
                    root.detailRequested(kind, detailId, title, subtitle, coverUrl)
                }
            }
        }
    }

    // ===== Page 组件 =====

    component SongListPage: Item {
        id: songPage

        property var model
        property string emptyText: qsTr("暂无内容")
        property bool loading: false
        property bool hasItems: false
        property bool showRetry: false

        signal playRequested(int row)
        signal retryClicked()

        ListView {
            anchors.fill: parent
            clip: true
            spacing: ThemeTokens.Spacing.s2
            model: songPage.model
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            delegate: Components.SongRow {
                width: ListView.view.width
                libraryController: root.libraryController
                coverController: root.coverController
                songDetailController: root.songDetailController
                playerController: root.playerController
                selected: root.playerController
                    && root.playerController.currentSong
                    && root.playerController.currentSong.mid === song.mid
                onActivated: function(songData, row) {
                    songPage.playRequested(row)
                }
                onNavigationRequested: function(kind, detailId, title, subtitle, coverUrl) {
                    root.detailRequested(kind, detailId, title, subtitle, coverUrl)
                }
            }

            ScrollBar.vertical: ScrollBar {}
        }

        // 加载骨架: 几何对齐真实歌曲行, 数据到达无跳动
        ColumnLayout {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            visible: songPage.loading && !songPage.hasItems
            spacing: ThemeTokens.Spacing.s2

            Repeater {
                model: 6

                delegate: Components.SongRowSkeleton {
                    required property int index

                    Layout.fillWidth: true
                    titleRatio: 0.3 + (index % 3) * 0.14
                }
            }
        }

        // empty
        ColumnLayout {
            anchors.centerIn: parent
            visible: !songPage.loading && !songPage.hasItems
            spacing: ThemeTokens.Spacing.s3

            Label {
                Layout.alignment: Qt.AlignHCenter
                text: songPage.emptyText
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }

            Button {
                id: emptyRetryButton

                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 112
                Layout.preferredHeight: 36
                visible: songPage.showRetry
                text: qsTr("重试")
                Accessible.name: text
                onClicked: songPage.retryClicked()

                contentItem: Label {
                    text: emptyRetryButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: emptyRetryButton.down
                        ? ThemeTokens.Palette.statePressed
                        : emptyRetryButton.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant
                }
            }
        }
    }

    component CardGridPage: Item {
        id: gridPage

        property var model
        property string emptyText: qsTr("暂无内容")
        property string kindFallback: "playlist"
        property bool circular: false
        property bool loading: false
        property bool hasItems: false

        signal cardRequested(string kind, string detailId, string title, string subtitle, string coverUrl)

        GridView {
            id: gridView

            // 与首页/搜索同一套自适应: 目标卡宽 ~180px, 列数 2..8
            readonly property int cols: Math.max(2, Math.min(8, Math.floor(width / 180)))

            anchors.fill: parent
            clip: true
            cellWidth: gridView.cols > 0 ? Math.floor(width / gridView.cols) : width
            cellHeight: cellWidth + 52
            model: gridPage.model
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            delegate: Item {
                id: cardCell

                required property string kind
                required property string cardId
                required property string title
                required property string subtitle
                required property string coverUrl
                required property string meta

                width: GridView.view.cellWidth
                height: GridView.view.cellHeight

                Components.Card {
                    width: parent.width - ThemeTokens.Spacing.s3
                    anchors.horizontalCenter: parent.horizontalCenter
                    circular: gridPage.circular
                    title: cardCell.title
                    subtitle: cardCell.subtitle
                    coverUrl: cardCell.coverUrl
                    meta: cardCell.meta
                    coverController: root.coverController
                    onActivated: gridPage.cardRequested(cardCell.kind || gridPage.kindFallback, cardCell.cardId, cardCell.title, cardCell.subtitle, cardCell.coverUrl)
                    onPlayRequested: gridPage.cardRequested(cardCell.kind || gridPage.kindFallback, cardCell.cardId, cardCell.title, cardCell.subtitle, cardCell.coverUrl)
                }
            }

            ScrollBar.vertical: ScrollBar {}
        }

        // 加载骨架: 两排卡片占位
        GridLayout {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            visible: gridPage.loading && !gridPage.hasItems
            columns: gridView.cols
            columnSpacing: ThemeTokens.Spacing.s3
            rowSpacing: ThemeTokens.Spacing.s3

            Repeater {
                model: gridView.cols * 2

                delegate: Components.CardSkeleton {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.alignment: Qt.AlignTop
                }
            }
        }

        Label {
            anchors.centerIn: parent
            visible: !gridPage.loading && !gridPage.hasItems
            text: gridPage.emptyText
            color: ThemeTokens.Palette.surfaceVariantText
            font.pixelSize: ThemeTokens.TypeScale.body
        }
    }
}
