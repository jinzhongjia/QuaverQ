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
    signal detailRequested(string kind, string detailId, string title, string subtitle)
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
                    font.weight: ThemeTokens.TypeScale.medium
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
            queueCount: root.homeController ? root.homeController.dailyModel.count : 0
            onPlayRequested: {
                if (root.homeController && root.homeController.dailyRequiresLogin) {
                    root.loginRequested()
                } else if (root.playerController && root.homeController && root.homeController.dailyModel.count > 0) {
                    if (root.currentSongMatches(root.homeController.dailyPreviewSong)) {
                        root.playerController.togglePlayPause()
                    } else {
                        root.playerController.playFromModel(root.homeController.dailyModel, 0)
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
            onCardRequested: function(kind, detailId, title, subtitle) {
                root.detailRequested(kind, detailId, title, subtitle)
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
            onActionRequested: {
                if (root.playerController && root.homeController && root.homeController.newSongModel.count > 0)
                    root.playerController.playFromModel(root.homeController.newSongModel, 0)
            }
            onSongRequested: function(row) {
                if (root.playerController && root.homeController)
                    root.playerController.playFromModel(root.homeController.newSongModel, row)
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
            onCardRequested: function(kind, detailId, title, subtitle) {
                root.detailRequested(kind, detailId, title, subtitle)
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
                font.weight: ThemeTokens.TypeScale.medium
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
        property int queueCount: 0
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
            : section.loading
                ? qsTr("正在加载...")
                : section.errorMessage.length > 0
                    ? section.errorMessage
                    : section.hasPreview
                        ? section.singerText
                        : qsTr("暂无推荐")

        signal playRequested()

        Layout.preferredHeight: root.availableWidth < 720 ? 184 : 156
        Layout.minimumHeight: Layout.preferredHeight
        radius: ThemeTokens.Spacing.radiusLg
        color: ThemeTokens.Palette.primaryContainer
        border.color: ThemeTokens.Palette.outlineMuted

        RowLayout {
            anchors.fill: parent
            anchors.margins: ThemeTokens.Spacing.s5
            spacing: ThemeTokens.Spacing.s5

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

                Label {
                    Layout.fillWidth: true
                    visible: section.hasPreview && section.queueCount > 1
                    text: qsTr("今日队列 · %1 首").arg(section.queueCount)
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }

            Components.AlbumArt {
                Layout.preferredWidth: root.availableWidth < 720 ? 72 : 92
                Layout.preferredHeight: root.availableWidth < 720 ? 72 : 92
                active: section.hasPreview
                coverUrl: section.hasPreview && section.previewSong.coverUrl ? section.previewSong.coverUrl : ""
                coverController: section.coverController
                iconText: "♪"
                iconSize: ThemeTokens.TypeScale.h1
            }

            Button {
                id: dailyPlayButton

                Layout.preferredWidth: 56
                Layout.preferredHeight: 56
                enabled: section.requiresLogin || section.hasPreview
                text: section.requiresLogin ? qsTr("登录") : section.showsPause ? "Ⅱ" : "▶"
                Accessible.name: section.requiresLogin
                    ? qsTr("登录")
                    : section.showsPause ? qsTr("暂停猜你喜欢") : qsTr("播放猜你喜欢")
                onClicked: section.playRequested()

                contentItem: Label {
                    text: dailyPlayButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: dailyPlayButton.enabled
                        ? ThemeTokens.Palette.primaryText
                        : ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: section.requiresLogin
                        ? ThemeTokens.TypeScale.bodySm
                        : ThemeTokens.TypeScale.h2
                    font.weight: ThemeTokens.TypeScale.medium
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
        readonly property bool hasRows: section.model && section.model.count > 0

        signal actionRequested()
        signal songRequested(int row)

        Layout.preferredHeight: songColumn.implicitHeight + ThemeTokens.Spacing.s6 * 2
        Layout.minimumHeight: Layout.preferredHeight
        radius: ThemeTokens.Spacing.radiusLg
        color: ThemeTokens.Palette.surfaceElevated
        border.color: ThemeTokens.Palette.outlineMuted

        ColumnLayout {
            id: songColumn

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: ThemeTokens.Spacing.s5
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
                visible: section.loading
                text: qsTr("正在加载...")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
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

            Repeater {
                model: section.hasRows ? section.model : null

                delegate: Components.SongRow {
                    Layout.fillWidth: true
                    libraryController: section.libraryController
                    coverController: section.coverController
                    onActivated: function(songData, row) {
                        section.songRequested(row)
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

        signal cardRequested(string kind, string detailId, string title, string subtitle)

        Layout.preferredHeight: cardColumn.implicitHeight + ThemeTokens.Spacing.s6 * 2
        Layout.minimumHeight: Layout.preferredHeight
        radius: ThemeTokens.Spacing.radiusLg
        color: ThemeTokens.Palette.surfaceElevated
        border.color: ThemeTokens.Palette.outlineMuted

        ColumnLayout {
            id: cardColumn

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: ThemeTokens.Spacing.s5
            spacing: ThemeTokens.Spacing.s4

            SectionHeader {
                Layout.fillWidth: true
                title: section.title
                subtitle: section.subtitle
            }

            Label {
                Layout.fillWidth: true
                visible: section.loading
                text: qsTr("正在加载...")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
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

            GridLayout {
                Layout.fillWidth: true
                visible: section.hasCards
                columns: root.availableWidth > 980 ? 3 : root.availableWidth > 680 ? 2 : 1
                columnSpacing: ThemeTokens.Spacing.s3
                rowSpacing: ThemeTokens.Spacing.s3

                Repeater {
                    model: section.hasCards ? section.model : null

                    delegate: CardTile {
                        Layout.fillWidth: true
                        coverController: section.coverController
                        onActivated: section.cardRequested(kind, cardId, title, subtitle)
                    }
                }
            }
        }
    }

    component CardTile: Rectangle {
        id: tile

        required property string kind
        required property string cardId
        required property string title
        required property string subtitle
        required property string coverUrl
        required property string meta
        property var coverController

        signal activated()

        implicitHeight: 84
        radius: ThemeTokens.Spacing.radiusMd
        color: cardHover.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surface
        border.color: ThemeTokens.Palette.outlineMuted
        Accessible.role: Accessible.Button
        Accessible.name: tile.title
        activeFocusOnTab: true

        HoverHandler {
            id: cardHover
        }

        TapHandler {
            onTapped: tile.activated()
        }

        Keys.onReturnPressed: tile.activated()
        Keys.onSpacePressed: tile.activated()

        Rectangle {
            anchors.fill: parent
            visible: parent.activeFocus
            radius: parent.radius
            color: "transparent"
            border.color: ThemeTokens.Palette.focusRing
            border.width: 2
            z: 1
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: ThemeTokens.Spacing.s4
            spacing: ThemeTokens.Spacing.s4

            Components.AlbumArt {
                Layout.preferredWidth: 52
                Layout.preferredHeight: 52
                iconText: tile.kind === "artist" ? "◎" : tile.kind === "top" ? "↗" : "♪"
                coverUrl: tile.coverUrl
                coverController: tile.coverController
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: tile.title
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: tile.subtitle
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }

            Label {
                Layout.preferredWidth: 48
                text: tile.meta
                color: ThemeTokens.Palette.surfaceVariantText
                horizontalAlignment: Text.AlignRight
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }
        }
    }
}
