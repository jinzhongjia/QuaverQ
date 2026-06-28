pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

// 雷达推荐整页: 侧栏「雷达」入口进入. 个性化推荐歌曲流, 实时拉取不缓存.
// header(标题 + 换一批 + 播放全部) + ListView(SongRow) + 登录/加载/空态; 滚到底自动加载下一页.
// 播放统一走 playSourceFromModel(..., "radar") 才能触发队列耗尽自动续接.
Item {
    id: root

    property string routeName: "radar"
    property var radarController
    property var coverController
    property var playerController
    property var libraryController
    property var songDetailController
    property var downloadController

    signal loginRequested()
    signal detailRequested(string kind, string detailId, string title, string subtitle, string coverUrl)

    readonly property var radarModel: root.radarController ? root.radarController.radarModel : null
    readonly property int songCount: root.radarModel ? root.radarModel.count : 0
    readonly property bool requiresLogin: root.radarController ? root.radarController.radarRequiresLogin : false
    readonly property bool loading: root.radarController ? root.radarController.loading : false
    readonly property bool hasMore: root.radarController ? root.radarController.hasMore : false
    readonly property bool hasRows: root.songCount > 0

    // 首次进入: 无数据才拉, 避免每次切回都重置流 (单例 controller 持有 model)
    Component.onCompleted: {
        if (root.radarController && root.songCount === 0 && !root.requiresLogin)
            root.radarController.refresh()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s5

        // ===== header =====
        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: qsTr("雷达")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.bold
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.requiresLogin
                        ? qsTr("登录后开启个性化推荐")
                        : (root.loading && !root.hasRows)
                            ? qsTr("正在生成推荐…")
                            : root.hasRows
                                ? qsTr("根据你的口味实时推荐 · 共 %1 首").arg(root.songCount)
                                : qsTr("根据你的口味实时推荐")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }
            }

            // 换一批: 重 roll 推荐流 (refresh, page=1)
            Components.IconButton {
                visible: !root.requiresLogin && root.hasRows
                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                text: qsTr("换一批")
                iconSource: "../icons/refresh.svg"
                iconSize: 18
                enabled: !root.loading
                onClicked: {
                    if (root.radarController)
                        root.radarController.refresh()
                }
            }

            // 播放全部: 带 source="radar", 队列耗尽才自动续接下一页
            Button {
                id: playAllButton

                Layout.preferredWidth: 56
                Layout.preferredHeight: 56
                enabled: root.requiresLogin || root.hasRows
                text: root.requiresLogin ? qsTr("登录") : qsTr("播放全部")
                Accessible.name: text
                onClicked: {
                    if (root.requiresLogin) {
                        root.loginRequested()
                        return
                    }
                    if (root.playerController && root.radarModel)
                        root.playerController.playSourceFromModel(root.radarModel, 0, "radar")
                }

                contentItem: Item {
                    Components.AppIcon {
                        anchors.centerIn: parent
                        anchors.horizontalCenterOffset: 1
                        visible: !root.requiresLogin
                        size: 22
                        source: "../icons/play.svg"
                        color: playAllButton.enabled
                            ? ThemeTokens.Palette.primaryText
                            : ThemeTokens.Palette.surfaceVariantText
                    }

                    Label {
                        anchors.centerIn: parent
                        visible: root.requiresLogin
                        text: qsTr("登录")
                        color: ThemeTokens.Palette.primaryText
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        font.weight: ThemeTokens.TypeScale.medium
                    }
                }

                background: Rectangle {
                    radius: width / 2
                    color: playAllButton.enabled
                        ? ThemeTokens.Palette.primary
                        : ThemeTokens.Palette.surfaceVariant
                }
            }
        }

        // ===== list =====
        ListView {
            id: radarList

            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.hasRows
            clip: true
            spacing: ThemeTokens.Spacing.s2
            model: root.radarModel
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            ScrollBar.vertical: ScrollBar {}

            // 滚到底 + 还有更多 + 不在加载 → 拉下一页 (事件驱动, 非轮询)
            onAtYEndChanged: {
                if (radarList.atYEnd && root.hasMore && !root.loading && root.radarController)
                    root.radarController.loadNextPage()
            }

            delegate: Components.SongRow {
                width: ListView.view.width
                libraryController: root.libraryController
                coverController: root.coverController
                songDetailController: root.songDetailController
                playerController: root.playerController
                downloadController: root.downloadController
                selected: root.playerController
                    && root.playerController.currentSong
                    && root.playerController.currentSong.mid === song.mid
                onActivated: function(songData, row) {
                    if (root.playerController && root.radarModel)
                        root.playerController.playSourceFromModel(root.radarModel, row, "radar")
                }
                onNavigationRequested: function(kind, detailId, title, subtitle, coverUrl) {
                    root.detailRequested(kind, detailId, title, subtitle, coverUrl)
                }
            }

            // 底部: 加载更多指示 / 到底提示
            footer: Item {
                width: ListView.view.width
                implicitHeight: 48

                Label {
                    anchors.centerIn: parent
                    text: root.loading
                        ? qsTr("加载更多…")
                        : (root.hasMore ? "" : qsTr("没有更多推荐了"))
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                }
            }
        }

        // ===== 首屏加载骨架 (无缓存数据时占位) =====
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.loading && !root.hasRows && !root.requiresLogin
            spacing: ThemeTokens.Spacing.s2

            Repeater {
                model: 6

                delegate: Components.SongRowSkeleton {
                    required property int index

                    Layout.fillWidth: true
                    titleRatio: 0.3 + (index % 3) * 0.14
                }
            }

            Item {
                Layout.fillHeight: true
            }
        }

        // ===== 未登录 / 已登录空态 (居中提示, 同 DownloadsView 空态) =====
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.requiresLogin || (!root.loading && !root.hasRows)

            ColumnLayout {
                anchors.centerIn: parent
                spacing: ThemeTokens.Spacing.s3

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: root.requiresLogin ? qsTr("登录后开启雷达推荐") : qsTr("暂无推荐")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                }

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: root.requiresLogin
                        ? qsTr("根据你的收藏与播放记录实时生成专属推荐")
                        : qsTr("多听多收藏，雷达会更懂你")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                }

                Button {
                    id: loginCta

                    visible: root.requiresLogin
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: ThemeTokens.Spacing.s2
                    Layout.preferredHeight: 40
                    Layout.preferredWidth: 120
                    text: qsTr("登录")
                    Accessible.name: text
                    onClicked: root.loginRequested()

                    contentItem: Label {
                        text: loginCta.text
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: ThemeTokens.Palette.primaryText
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    background: Rectangle {
                        radius: ThemeTokens.Spacing.radiusPill
                        color: loginCta.down
                            ? ThemeTokens.Palette.primaryActive
                            : loginCta.hovered ? ThemeTokens.Palette.primaryHover : ThemeTokens.Palette.primary
                    }
                }
            }
        }
    }
}
