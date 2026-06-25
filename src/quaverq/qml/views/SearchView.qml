pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

ColumnLayout {
    id: root

    property var serviceController
    property var playerController
    property var libraryController
    property var coverController
    property var songDetailController
    property var downloadController
    property string routeName: "search"

    signal detailRequested(string kind, string detailId, string title, string subtitle, string coverUrl)
    signal searchRequested(string keyword)

    readonly property string searchType: root.serviceController ? root.serviceController.searchType : "general"
    readonly property bool isGeneral: root.searchType === "general"
    readonly property bool isSongs: root.searchType === "songs"
    // 综合 + 歌曲 都用歌曲列表渲染 songResults; 其余(歌手/专辑/歌单)走卡片网格
    readonly property bool showsList: root.isGeneral || root.isSongs
    readonly property var directHitData: root.serviceController ? root.serviceController.directHit : null
    readonly property var relatedWordsData: root.serviceController ? root.serviceController.relatedWords : []
    readonly property var hotSearchesData: root.serviceController ? root.serviceController.hotSearches : []
    // 未搜索 + 非加载 + 有热搜词 -> 空状态展示热门搜索
    readonly property bool showsHotSearch: root.serviceController
        && !root.hasSearched
        && !root.serviceController.loading
        && root.hotSearchesData.length > 0
    readonly property bool hasSearched: root.serviceController
        && root.serviceController.currentPage > 0
    readonly property bool canGoPrevious: root.serviceController
        && root.serviceController.currentPage > 1
        && !root.serviceController.loading
    readonly property bool canGoNext: root.serviceController
        && root.serviceController.hasNextPage
        && !root.serviceController.loading

    readonly property var searchTabs: [
        { key: "general", label: qsTr("综合") },
        { key: "songs", label: qsTr("歌曲") },
        { key: "singers", label: qsTr("歌手") },
        { key: "albums", label: qsTr("专辑") },
        { key: "playlists", label: qsTr("歌单") }
    ]

    function resultCount() {
        if (!root.serviceController)
            return 0
        return root.showsList
            ? root.serviceController.songResults.count
            : root.serviceController.cardResults.count
    }

    function statusText() {
        if (!root.serviceController)
            return ""
        if (root.resultCount() > 0) {
            if (root.isGeneral)
                return qsTr("综合 · %1 首").arg(root.serviceController.songResults.count)
            return root.isSongs
                ? qsTr("第 %1 页 · 本页 %2 首")
                    .arg(root.serviceController.currentPage)
                    .arg(root.serviceController.songResults.count)
                : qsTr("%1 个结果").arg(root.serviceController.cardResults.count)
        }
        return root.hasSearched ? qsTr("没有结果") : qsTr("输入关键词后按 Enter")
    }

    // 进搜索页懒加载热搜词 (服务层带 10 分钟缓存, 重复进入开销极小)
    Component.onCompleted: {
        if (root.serviceController)
            root.serviceController.loadHotSearches()
    }

    spacing: 0

    // 页内错误与全局 Banner 同一形态 (W9): 红底白字通栏的视觉烈度等同"危险操作", 加载失败不配
    Components.Banner {
        id: searchErrorBanner

        Layout.fillWidth: true
        kind: "error"
    }

    // 显式 Binding: Banner.dismiss() 会写空 message, 直接绑定会被这次写入打断;
    // Binding 元素在 errorMessage 再变化时重新接管 (SettingsView 同款模式)
    Binding {
        target: searchErrorBanner
        property: "message"
        value: root.serviceController ? root.serviceController.errorMessage : ""
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s4

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            Label {
                text: qsTr("搜索")
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.h1
                font.weight: ThemeTokens.TypeScale.bold
            }

            Label {
                Layout.fillWidth: true
                text: root.statusText()
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }
        }

        Components.TabRow {
            id: searchTabRow

            Layout.fillWidth: true
            tabs: root.searchTabs
            currentIndex: {
                for (let i = 0; i < root.searchTabs.length; ++i) {
                    if (root.searchTabs[i].key === root.searchType)
                        return i
                }
                return 0
            }
            onActivated: function(index) {
                if (root.serviceController)
                    root.serviceController.setSearchType(root.searchTabs[index].key)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: ThemeTokens.Palette.outlineMuted
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: resultList
                anchors.fill: parent
                visible: root.showsList
                clip: true
                spacing: ThemeTokens.Spacing.s2
                model: root.serviceController ? root.serviceController.songResults : null

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                // 综合页头: 直达卡 + 相关搜索词 chips (随列表滚动); 其他 tab 无头部
                header: ColumnLayout {
                    width: resultList.width
                    visible: root.isGeneral && (!!root.directHitData || root.relatedWordsData.length > 0)
                    height: visible ? implicitHeight : 0
                    spacing: ThemeTokens.Spacing.s3

                    // 直达
                    Rectangle {
                        objectName: "searchDirectHit"
                        Layout.fillWidth: true
                        Layout.bottomMargin: ThemeTokens.Spacing.s2
                        Layout.preferredHeight: visible ? 64 : 0
                        visible: !!root.directHitData
                        radius: ThemeTokens.Spacing.radiusMd
                        color: directHitArea.containsMouse ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: ThemeTokens.Spacing.s3
                            anchors.rightMargin: ThemeTokens.Spacing.s4
                            spacing: ThemeTokens.Spacing.s3

                            Components.AlbumArt {
                                Layout.preferredWidth: 44
                                Layout.preferredHeight: 44
                                compact: true
                                circular: !!root.directHitData && root.directHitData.kind === "artist"
                                coverUrl: root.directHitData ? root.directHitData.coverUrl : ""
                                coverController: root.coverController
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0

                                Label {
                                    text: qsTr("★ 直达 · %1").arg(root.directHitData ? root.directHitData.subtitle : "")
                                    color: ThemeTokens.Palette.primary
                                    font.pixelSize: ThemeTokens.TypeScale.caption
                                    font.weight: ThemeTokens.TypeScale.medium
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: root.directHitData ? root.directHitData.title : ""
                                    color: ThemeTokens.Palette.surfaceText
                                    font.pixelSize: ThemeTokens.TypeScale.body
                                    font.weight: ThemeTokens.TypeScale.bold
                                    elide: Text.ElideRight
                                }
                            }

                            Label {
                                text: "→"
                                color: ThemeTokens.Palette.surfaceVariantText
                                font.pixelSize: ThemeTokens.TypeScale.h2
                            }
                        }

                        MouseArea {
                            id: directHitArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.directHitData)
                                    root.detailRequested(root.directHitData.kind, root.directHitData.id, root.directHitData.title, root.directHitData.subtitle, root.directHitData.coverUrl)
                            }
                        }
                    }

                    // 相关搜索词 chips
                    Flow {
                        objectName: "searchRelatedChips"
                        Layout.fillWidth: true
                        visible: root.relatedWordsData.length > 0
                        spacing: ThemeTokens.Spacing.s2

                        Repeater {
                            model: root.relatedWordsData

                            delegate: Components.SearchChip {
                                required property var modelData

                                text: modelData.display
                                onClicked: root.searchRequested(modelData.keyword)
                            }
                        }
                    }
                }

                delegate: Components.SongRow {
                    width: ListView.view.width
                    libraryController: root.libraryController
                    coverController: root.coverController
                    songDetailController: root.songDetailController
                    playerController: root.playerController
                    downloadController: root.downloadController
                    onActivated: function(songData, row) {
                        if (root.playerController)
                            root.playerController.playFromModel(root.serviceController.songResults, row)
                    }
                    onNavigationRequested: function(kind, detailId, title, subtitle, coverUrl) {
                        root.detailRequested(kind, detailId, title, subtitle, coverUrl)
                    }
                }

                footer: Item {
                    width: ListView.view ? ListView.view.width : 0
                    height: root.isSongs && root.resultCount() > 0 ? 64 : 0
                    visible: root.isSongs && root.resultCount() > 0

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: ThemeTokens.Spacing.s3

                        Button {
                            id: previousPageButton
                            Layout.preferredWidth: 88
                            Layout.preferredHeight: 34
                            enabled: root.canGoPrevious
                            text: qsTr("上一页")
                            Accessible.name: qsTr("上一页搜索结果")
                            onClicked: {
                                if (root.serviceController)
                                    root.serviceController.previousPage()
                            }
                            contentItem: Label {
                                text: previousPageButton.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                color: previousPageButton.enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                                font.pixelSize: ThemeTokens.TypeScale.caption
                            }
                            background: Rectangle {
                                radius: ThemeTokens.Spacing.radiusMd
                                color: previousPageButton.down ? ThemeTokens.Palette.statePressed : previousPageButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                                border.color: ThemeTokens.Palette.outline
                            }
                        }

                        Label {
                            Layout.preferredWidth: 128
                            text: root.serviceController && root.serviceController.loading
                                ? qsTr("加载中...")
                                : qsTr("第 %1 页").arg(root.serviceController ? root.serviceController.currentPage : 0)
                            horizontalAlignment: Text.AlignHCenter
                            color: ThemeTokens.Palette.surfaceText
                            font.pixelSize: ThemeTokens.TypeScale.bodySm
                            font.weight: ThemeTokens.TypeScale.medium
                        }

                        Button {
                            id: nextPageButton
                            Layout.preferredWidth: 88
                            Layout.preferredHeight: 34
                            enabled: root.canGoNext
                            text: qsTr("下一页")
                            Accessible.name: qsTr("下一页搜索结果")
                            onClicked: {
                                if (root.serviceController)
                                    root.serviceController.nextPage()
                            }
                            contentItem: Label {
                                text: nextPageButton.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                color: nextPageButton.enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                                font.pixelSize: ThemeTokens.TypeScale.caption
                            }
                            background: Rectangle {
                                radius: ThemeTokens.Spacing.radiusMd
                                color: nextPageButton.down ? ThemeTokens.Palette.statePressed : nextPageButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                                border.color: ThemeTokens.Palette.outline
                            }
                        }
                    }
                }
            }

            GridView {
                id: cardGrid

                anchors.fill: parent
                visible: !root.showsList
                clip: true

                readonly property int cols: Math.max(2, Math.min(8, Math.floor(width / 180)))
                cellWidth: cardGrid.cols > 0 ? Math.floor(width / cardGrid.cols) : width
                cellHeight: cellWidth + 44
                model: root.serviceController ? root.serviceController.cardResults : null

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Item {
                    id: cardCell

                    required property string kind
                    required property string cardId
                    required property string title
                    required property string subtitle
                    required property string coverUrl
                    required property string meta

                    width: cardGrid.cellWidth
                    height: cardGrid.cellHeight

                    Components.Card {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: ThemeTokens.Spacing.s2
                        anchors.rightMargin: ThemeTokens.Spacing.s2
                        circular: cardCell.kind === "artist"
                        title: cardCell.title
                        subtitle: cardCell.subtitle
                        coverUrl: cardCell.coverUrl
                        meta: cardCell.meta
                        coverController: root.coverController
                        onActivated: root.detailRequested(cardCell.kind, cardCell.cardId, cardCell.title, cardCell.subtitle, cardCell.coverUrl)
                        onPlayRequested: root.detailRequested(cardCell.kind, cardCell.cardId, cardCell.title, cardCell.subtitle, cardCell.coverUrl)
                    }
                }
            }

            Connections {
                target: root.serviceController

                function onLoadingChanged() {
                    if (root.serviceController && root.serviceController.loading) {
                        resultList.positionViewAtBeginning()
                        cardGrid.positionViewAtBeginning()
                    } else {
                        // 结果就绪后综合页 header (直达/相关词) 才拿到最终高度; ListView 会
                        // 锚定首个 item 导致 header 被顶到视口上方 (看着像自动下滚). 延后到
                        // 布局结算后再归位一次, 让 header 完整露出.
                        Qt.callLater(function() { resultList.positionViewAtBeginning() })
                    }
                }
            }

            // 首屏搜索骨架 (翻页时旧结果保留 + 底部"加载中", 不走骨架)
            ColumnLayout {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                visible: root.showsList
                    && root.serviceController
                    && root.serviceController.loading
                    && root.serviceController.songResults.count === 0
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

            GridLayout {
                id: searchSkeletonGrid

                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                visible: !root.showsList
                    && root.serviceController
                    && root.serviceController.loading
                    && root.serviceController.cardResults.count === 0
                columns: Math.max(2, Math.min(8, Math.floor(width / 180)))
                columnSpacing: ThemeTokens.Spacing.s3
                rowSpacing: ThemeTokens.Spacing.s3

                Repeater {
                    model: searchSkeletonGrid.columns

                    delegate: Components.CardSkeleton {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.alignment: Qt.AlignTop
                    }
                }
            }

            // 空搜索页热门搜索
            ColumnLayout {
                objectName: "searchHotPanel"
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                visible: root.showsHotSearch
                spacing: ThemeTokens.Spacing.s4

                Label {
                    text: qsTr("热门搜索")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h2
                    font.weight: ThemeTokens.TypeScale.bold
                }

                // 编号榜单 (QQ 音乐风): 前 3 名序号品牌绿, 行 hover 高亮; 宽屏两列
                GridLayout {
                    Layout.fillWidth: true
                    columns: width >= 680 ? 2 : 1
                    columnSpacing: ThemeTokens.Spacing.s6
                    rowSpacing: 0

                    Repeater {
                        model: root.hotSearchesData

                        delegate: Rectangle {
                            id: hotRow

                            required property int index
                            required property var modelData

                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            Layout.preferredHeight: 40
                            radius: ThemeTokens.Spacing.radiusSm
                            color: hotRowArea.containsMouse ? ThemeTokens.Palette.stateHover : "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: ThemeTokens.Spacing.s3
                                anchors.rightMargin: ThemeTokens.Spacing.s3
                                spacing: ThemeTokens.Spacing.s4

                                Label {
                                    Layout.preferredWidth: 20
                                    horizontalAlignment: Text.AlignHCenter
                                    text: hotRow.index + 1
                                    color: hotRow.index < 3 ? ThemeTokens.Palette.primary : ThemeTokens.Palette.surfaceVariantText
                                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                                    font.weight: hotRow.index < 3 ? ThemeTokens.TypeScale.bold : ThemeTokens.TypeScale.medium
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: hotRow.modelData
                                    color: ThemeTokens.Palette.surfaceText
                                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                                    elide: Text.ElideRight
                                }
                            }

                            MouseArea {
                                id: hotRowArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.searchRequested(hotRow.modelData)
                            }
                        }
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                width: parent.width - ThemeTokens.Spacing.s8
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                visible: root.serviceController
                    && !root.serviceController.loading
                    && root.resultCount() === 0
                    && root.serviceController.errorMessage.length === 0
                    && !(root.isGeneral && (root.directHitData || root.relatedWordsData.length > 0))
                    && !root.showsHotSearch
                text: root.hasSearched ? qsTr("没有搜索结果") : qsTr("输入关键词开始搜索")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }
    }
}
