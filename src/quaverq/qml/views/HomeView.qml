pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

ScrollView {
    id: root

    property string routeName: "home"
    property var appController
    property var coverController
    property var homeController
    property var libraryController
    property var playerController
    property var songDetailController
    property var downloadController

    readonly property bool hasSong: root.playerController
        && root.playerController.currentSong
        && root.playerController.currentSong.name !== undefined
        ? root.playerController.currentSong.name.length > 0
        : false
    readonly property bool dailyLoading: root.homeController ? root.homeController.dailyLoading : false
    readonly property bool playlistLoading: root.homeController ? root.homeController.playlistLoading : false
    readonly property bool newSongLoading: root.homeController ? root.homeController.newSongLoading : false
    readonly property bool topLoading: root.homeController ? root.homeController.topLoading : false

    signal loginRequested()
    signal searchRequested(string keyword)
    signal detailRequested(string kind, string detailId, string title, string subtitle, string coverUrl)
    signal nowPlayingRequested()

    contentWidth: availableWidth

    function currentSongMatches(song) {
        if (!root.playerController || !song || song.mid === undefined)
            return false
        const current = root.playerController.currentSong
        return current
            && current.mid !== undefined
            && String(current.mid).length > 0
            && String(current.mid) === String(song.mid)
    }

    ColumnLayout {
        width: root.availableWidth
        spacing: ThemeTokens.Spacing.s6

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            Layout.topMargin: ThemeTokens.Spacing.s6
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: qsTr("发现")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.bold
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong
                        ? qsTr("继续听 %1").arg(root.playerController.currentSong.name)
                        : qsTr("每日推荐、新歌和排行榜")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }
            }

            Button {
                id: nowPlayingButton

                Layout.preferredWidth: 112
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                enabled: root.hasSong
                text: qsTr("正在播放")
                Accessible.name: text
                onClicked: root.nowPlayingRequested()

                contentItem: Label {
                    text: nowPlayingButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: nowPlayingButton.enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: nowPlayingButton.down
                        ? ThemeTokens.Palette.statePressed
                        : nowPlayingButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: ThemeTokens.Palette.outline
                }
            }
        }

        DailyRecommendCard {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            previewSong: root.homeController ? root.homeController.dailyPreviewSong : ({})
            currentSong: root.playerController ? root.playerController.currentSong : ({})
            playbackState: root.playerController ? root.playerController.playbackState : "stopped"
            coverController: root.coverController
            loading: root.dailyLoading
            requiresLogin: root.homeController ? root.homeController.dailyRequiresLogin : false
            errorMessage: root.homeController ? root.homeController.dailyErrorMessage : ""
            onPlayRequested: {
                if (root.homeController && root.homeController.dailyRequiresLogin) {
                    root.loginRequested()
                } else if (root.playerController && root.homeController && root.homeController.dailyModel.count > 0) {
                    if (root.currentSongMatches(root.homeController.dailyPreviewSong)) {
                        root.playerController.togglePlayPause()
                    } else {
                        root.playerController.playSourceFromModel(root.homeController.dailyModel, 0, "daily")
                    }
                }
            }
        }

        CardSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            title: qsTr("今日推荐")
            subtitle: qsTr("适合现在打开的歌单")
            model: root.homeController ? root.homeController.playlistModel : null
            loading: root.playlistLoading
            errorMessage: root.homeController ? root.homeController.playlistErrorMessage : ""
            emptyText: qsTr("暂无推荐歌单")
            coverController: root.coverController
            onCardRequested: function(kind, detailId, title, subtitle, coverUrl) {
                root.detailRequested(kind, detailId, title, subtitle, coverUrl)
            }
        }

        SongSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            title: qsTr("新歌速递")
            subtitle: qsTr("最近更新的歌曲")
            model: root.homeController ? root.homeController.newSongModel : null
            loading: root.newSongLoading
            errorMessage: root.homeController ? root.homeController.newSongErrorMessage : ""
            emptyText: qsTr("暂无新歌")
            actionText: qsTr("播放全部")
            actionEnabled: root.homeController && root.homeController.newSongModel.count > 0
            libraryController: root.libraryController
            coverController: root.coverController
            songDetailController: root.songDetailController
            onActionRequested: {
                if (root.playerController && root.homeController && root.homeController.newSongModel.count > 0)
                    root.playerController.playFromModel(root.homeController.newSongModel, 0)
            }
            onSongRequested: function(row) {
                if (root.playerController && root.homeController)
                    root.playerController.playFromModel(root.homeController.newSongModel, row)
            }
            onNavigationRequested: function(kind, detailId, title, subtitle, coverUrl) {
                root.detailRequested(kind, detailId, title, subtitle, coverUrl)
            }
        }

        CardSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            Layout.bottomMargin: ThemeTokens.Spacing.s6
            title: qsTr("排行榜")
            subtitle: qsTr("正在流行的榜单")
            model: root.homeController ? root.homeController.topModel : null
            loading: root.topLoading
            errorMessage: root.homeController ? root.homeController.topErrorMessage : ""
            emptyText: qsTr("暂无排行榜")
            coverController: root.coverController
            onCardRequested: function(kind, detailId, title, subtitle, coverUrl) {
                root.detailRequested(kind, detailId, title, subtitle, coverUrl)
            }
        }
    }

    component SectionHeader: RowLayout {
        id: header

        property string title: ""
        property string subtitle: ""
        property string actionText: ""
        property bool actionEnabled: false

        signal actionRequested()

        spacing: ThemeTokens.Spacing.s4

        ColumnLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s2

            Label {
                Layout.fillWidth: true
                text: header.title
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.bold
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: header.subtitle
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }
        }

        Button {
            id: actionButton

            Layout.preferredWidth: 96
            Layout.preferredHeight: 34
            visible: header.actionText.length > 0
            enabled: header.actionEnabled
            text: header.actionText
            Accessible.name: text
            onClicked: header.actionRequested()

            contentItem: Label {
                text: actionButton.text
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                color: actionButton.enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.caption
                font.weight: ThemeTokens.TypeScale.medium
            }

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: actionButton.down
                    ? ThemeTokens.Palette.statePressed
                    : actionButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                border.color: ThemeTokens.Palette.outline
            }
        }
    }

    component DailyRecommendCard: Rectangle {
        id: section

        property var previewSong: ({})
        property var currentSong: ({})
        property string playbackState: "stopped"
        property var coverController
        property bool loading: false
        property bool requiresLogin: false
        property string errorMessage: ""
        readonly property bool hasPreview: section.previewSong
            && section.previewSong.name !== undefined
            && section.previewSong.name.length > 0
        readonly property string singerText: section.hasPreview
            && section.previewSong.singerNames !== undefined
            ? section.previewSong.singerNames.join(" / ")
            : ""
        readonly property bool isCurrentPreview: section.hasPreview
            && section.currentSong
            && section.currentSong.mid !== undefined
            && section.previewSong.mid !== undefined
            && String(section.currentSong.mid).length > 0
            && String(section.currentSong.mid) === String(section.previewSong.mid)
        readonly property bool showsPause: section.isCurrentPreview
            && section.playbackState === "playing"
        readonly property string statusText: section.requiresLogin
            ? qsTr("登录后获取你的猜你喜欢")
            : section.hasPreview
                ? section.singerText
                : section.errorMessage.length > 0
                    ? section.errorMessage
                    : qsTr("暂无推荐")

        signal playRequested()

        Layout.preferredHeight: root.availableWidth < 720 ? 184 : 156
        Layout.minimumHeight: Layout.preferredHeight
        radius: ThemeTokens.Spacing.radiusLg
        // 同色系微渐变 (上亮下沉): 暗色模式下整块 primaryContainer 平涂偏闷
        gradient: Gradient {
            GradientStop { position: 0; color: ThemeTokens.Palette.primaryContainerHi }
            GradientStop { position: 1; color: ThemeTokens.Palette.primaryContainer }
        }
        border.color: ThemeTokens.Palette.outlineMuted

        RowLayout {
            anchors.fill: parent
            anchors.margins: ThemeTokens.Spacing.s5
            spacing: ThemeTokens.Spacing.s5

            // 封面放文字侧: 原"文字贴左、封面贴右"在宽窗下两端无限拉开, 卡片断成两截;
            // 封面+文字成一组后, 右侧只剩常规右锚的播放键
            Components.AlbumArt {
                Layout.preferredWidth: root.availableWidth < 720 ? 72 : 92
                Layout.preferredHeight: root.availableWidth < 720 ? 72 : 92
                Layout.alignment: Qt.AlignVCenter
                active: section.hasPreview
                coverUrl: section.hasPreview && section.previewSong.coverUrl ? section.previewSong.coverUrl : ""
                coverController: section.coverController
                iconText: "♪"
                iconSize: ThemeTokens.TypeScale.h1
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: ThemeTokens.Spacing.s3

                Label {
                    Layout.fillWidth: true
                    text: qsTr("猜你喜欢")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h2
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: section.hasPreview ? section.previewSong.name : qsTr("每日推荐")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: section.statusText
                    color: section.errorMessage.length > 0
                        ? ThemeTokens.Palette.error
                        : ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }

            }

            Button {
                id: dailyPlayButton

                Layout.preferredWidth: 56
                Layout.preferredHeight: 56
                enabled: section.requiresLogin || section.hasPreview
                text: section.requiresLogin
                    ? qsTr("登录")
                    : section.showsPause ? qsTr("暂停猜你喜欢") : qsTr("播放猜你喜欢")
                Accessible.name: text
                onClicked: section.playRequested()

                contentItem: Item {
                    Components.AppIcon {
                        anchors.centerIn: parent
                        anchors.horizontalCenterOffset: section.showsPause ? 0 : 1
                        visible: !section.requiresLogin
                        size: 22
                        source: section.showsPause ? "../icons/pause.svg" : "../icons/play.svg"
                        color: dailyPlayButton.enabled
                            ? ThemeTokens.Palette.primaryText
                            : ThemeTokens.Palette.surfaceVariantText
                    }

                    Label {
                        anchors.centerIn: parent
                        visible: section.requiresLogin
                        text: qsTr("登录")
                        color: ThemeTokens.Palette.primaryText
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        font.weight: ThemeTokens.TypeScale.medium
                    }
                }

                background: Rectangle {
                    radius: width / 2
                    color: dailyPlayButton.enabled
                        ? ThemeTokens.Palette.primary
                        : ThemeTokens.Palette.surfaceVariant
                }
            }
        }
    }

    component SongSection: Rectangle {
        id: section

        property string title: ""
        property string subtitle: ""
        property var model
        property bool loading: false
        property string errorMessage: ""
        property string emptyText: ""
        property string actionText: ""
        property bool actionEnabled: false
        property var libraryController
        property var coverController
        property var songDetailController
        readonly property bool hasRows: section.model && section.model.count > 0

        signal actionRequested()
        signal songRequested(int row)
        signal navigationRequested(string kind, string detailId, string title, string subtitle, string coverUrl)

        Layout.preferredHeight: songColumn.implicitHeight
        Layout.minimumHeight: Layout.preferredHeight
        radius: 0
        color: "transparent"
        border.color: "transparent"

        ColumnLayout {
            id: songColumn

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 0
            spacing: ThemeTokens.Spacing.s4

            SectionHeader {
                Layout.fillWidth: true
                title: section.title
                subtitle: section.subtitle
                actionText: section.actionText
                actionEnabled: section.actionEnabled
                onActionRequested: section.actionRequested()
            }

            Label {
                Layout.fillWidth: true
                visible: !section.loading && section.errorMessage.length > 0
                text: section.errorMessage
                color: ThemeTokens.Palette.error
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                wrapMode: Text.WordWrap
            }

            Label {
                Layout.fillWidth: true
                visible: !section.loading && section.errorMessage.length === 0 && !section.hasRows
                text: section.emptyText
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                horizontalAlignment: Text.AlignHCenter
            }

            // 冷启动骨架: 无缓存数据时的加载占位 (SWR 有缓存直出, 不闪骨架)
            ColumnLayout {
                Layout.fillWidth: true
                visible: section.loading && !section.hasRows
                spacing: ThemeTokens.Spacing.s2

                Repeater {
                    model: 3

                    delegate: Components.SongRowSkeleton {
                        required property int index

                        Layout.fillWidth: true
                        titleRatio: 0.3 + (index % 3) * 0.14
                    }
                }
            }

            Repeater {
                model: section.hasRows ? section.model : null

                delegate: Components.SongRow {
                    Layout.fillWidth: true
                    libraryController: section.libraryController
                    coverController: section.coverController
                    songDetailController: section.songDetailController
                    playerController: root.playerController
                    downloadController: root.downloadController
                    selected: root.playerController
                        && root.playerController.currentSong
                        && root.playerController.currentSong.mid === song.mid
                    onActivated: function(songData, row) {
                        section.songRequested(row)
                    }
                    onNavigationRequested: function(kind, detailId, title, subtitle, coverUrl) {
                        section.navigationRequested(kind, detailId, title, subtitle, coverUrl)
                    }
                }
            }
        }
    }

    component CardSection: Rectangle {
        id: section

        property string title: ""
        property string subtitle: ""
        property var model
        property bool loading: false
        property string errorMessage: ""
        property string emptyText: ""
        property var coverController
        readonly property bool hasCards: section.model && section.model.count > 0

        signal cardRequested(string kind, string detailId, string title, string subtitle, string coverUrl)

        Layout.preferredHeight: cardColumn.implicitHeight
        Layout.minimumHeight: Layout.preferredHeight
        radius: 0
        color: "transparent"
        border.color: "transparent"

        ColumnLayout {
            id: cardColumn

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 0
            spacing: ThemeTokens.Spacing.s4

            SectionHeader {
                Layout.fillWidth: true
                title: section.title
                subtitle: section.subtitle
            }

            Label {
                Layout.fillWidth: true
                visible: !section.loading && section.errorMessage.length > 0
                text: section.errorMessage
                color: ThemeTokens.Palette.error
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                wrapMode: Text.WordWrap
            }

            Label {
                Layout.fillWidth: true
                visible: !section.loading && section.errorMessage.length === 0 && !section.hasCards
                text: section.emptyText
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                horizontalAlignment: Text.AlignHCenter
            }

            // 冷启动骨架: 一排卡片占位
            GridLayout {
                id: cardSkeletonGrid

                Layout.fillWidth: true
                visible: section.loading && !section.hasCards
                columns: Math.max(2, Math.min(8, Math.floor(width / 180)))
                columnSpacing: ThemeTokens.Spacing.s5
                rowSpacing: ThemeTokens.Spacing.s5

                Repeater {
                    model: cardSkeletonGrid.columns

                    delegate: Components.CardSkeleton {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.alignment: Qt.AlignTop
                    }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                visible: section.hasCards
                // 目标卡宽 ~180px 自适应列数 (2..8): 最大化窗口加列, 不再 4 列巨图
                columns: Math.max(2, Math.min(8, Math.floor(width / 180)))
                columnSpacing: ThemeTokens.Spacing.s5
                rowSpacing: ThemeTokens.Spacing.s5

                Repeater {
                    model: section.hasCards ? section.model : null

                    delegate: Item {
                        id: cardCell

                        required property string kind
                        required property string cardId
                        required property string title
                        required property string subtitle
                        required property string coverUrl
                        required property string meta

                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.alignment: Qt.AlignTop
                        implicitHeight: cardItem.implicitHeight

                        Components.Card {
                            id: cardItem

                            width: parent.width
                            circular: cardCell.kind === "artist"
                            title: cardCell.title
                            subtitle: cardCell.subtitle
                            coverUrl: cardCell.coverUrl
                            meta: cardCell.meta
                            coverController: section.coverController
                            onActivated: section.cardRequested(cardCell.kind, cardCell.cardId, cardCell.title, cardCell.subtitle, cardCell.coverUrl)
                            onPlayRequested: section.cardRequested(cardCell.kind, cardCell.cardId, cardCell.title, cardCell.subtitle, cardCell.coverUrl)
                        }
                    }
                }
            }
        }
    }

}
