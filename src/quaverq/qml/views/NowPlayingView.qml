pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import QtQuick.Layouts
import "../components" as Components
import "../panels" as Panels
import "../Theme" as ThemeTokens

// 正在播放沉浸页 (由 Main.qml 以整宽浮层承载, 盖侧栏 + 内容区):
// ≥920 双栏 = 左大封面 + 信息组 / 右歌词; <920 单栏 = 顶部信息行 + 歌词.
Item {
    id: root

    property var coverController
    property var playerController
    property var libraryController
    property var lyricController
    property var settingsController
    readonly property var currentSong: root.playerController ? root.playerController.currentSong : ({})
    readonly property bool hasSong: currentSong
        && typeof currentSong.name === "string"
        && currentSong.name.length > 0
    // 浮层盖住侧栏后自宽 ≈ 窗宽, 与全局唯一断点 920 对齐
    readonly property bool wideLayout: root.width >= 920

    signal queueRequested()
    signal backRequested()
    signal downloadRequested()

    // 清空队列 (无歌) 时头图回占位: retainOnSwitch 的"换曲保留旧图"语义只该作用于
    // 换曲过渡, "没歌了"必须显式清掉, 否则上一首封面残留 (真机验收反馈)
    onHasSongChanged: {
        if (!root.hasSong)
            heroArt.displaySource = ""
    }

    function singerText(songData) {
        if (!songData)
            return ""
        if (songData.singerNames && songData.singerNames.length > 0)
            return songData.singerNames.join(" / ")
        if (songData.singers && songData.singers.length > 0)
            return songData.singers.map(function(singer) { return singer.name }).join(" / ")
        return songData.albumName || ""
    }

    Rectangle {
        anchors.fill: parent
        color: ThemeTokens.Palette.background
    }

    // 浮层事件屏障: 本页盖在侧栏 + 内容区上方, 无交互处理器的空白区域会让
    // 点击 / 滚轮 / 悬停穿透到底下的页面, 必须整层吞掉 (页内控件声明在后, 不受影响)
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
        onWheel: function(wheel) {
            wheel.accepted = true
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s5

        // 顶行: 收起常驻; 窄屏时小封面 + 歌曲信息 + 操作也收在这一行 (宽屏移入左栏)
        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s5

            // 收起入口 (对应 QQ 音乐歌词页左上角 ˅): Esc / 顶栏返回 / 再点播放栏封面均可退出
            Components.IconButton {
                Layout.alignment: Qt.AlignVCenter
                text: qsTr("收起")
                iconSource: "../icons/chevron-down.svg"
                iconSize: 20
                iconColor: ThemeTokens.Palette.surfaceText
                onClicked: root.backRequested()
            }

            Components.AlbumArt {
                visible: !root.wideLayout
                Layout.preferredWidth: 72
                Layout.preferredHeight: 72
                Layout.alignment: Qt.AlignVCenter
                active: root.hasSong
                coverUrl: root.hasSong && root.currentSong.coverUrl ? root.currentSong.coverUrl : ""
                coverController: root.coverController
                iconSize: ThemeTokens.TypeScale.h2
            }

            ColumnLayout {
                visible: !root.wideLayout
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.currentSong.name : qsTr("尚未播放")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.bold
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.hasSong ? root.singerText(root.currentSong) : qsTr("选择一首歌曲后开始")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }
            }

            // 宽屏顶行只有收起按钮, 用弹性占位顶满剩余宽度
            Item {
                visible: root.wideLayout
                Layout.fillWidth: true
                Layout.preferredHeight: 1
            }

            Components.LikeButton {
                visible: !root.wideLayout
                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                Layout.alignment: Qt.AlignVCenter
                libraryController: root.libraryController
                song: root.currentSong
            }

            Components.IconButton {
                visible: !root.wideLayout
                Layout.alignment: Qt.AlignVCenter
                text: qsTr("下载当前歌曲")
                iconSource: "../icons/download.svg"
                iconSize: 18
                iconColor: ThemeTokens.Palette.surfaceVariantText
                enabled: root.hasSong
                onClicked: root.downloadRequested()
            }

            Components.IconButton {
                visible: !root.wideLayout
                Layout.alignment: Qt.AlignVCenter
                text: qsTr("待播列表")
                iconSource: "../icons/queue.svg"
                iconSize: 18
                iconColor: ThemeTokens.Palette.surfaceVariantText
                onClicked: root.queueRequested()
            }
        }

        // 主体: 内容块限宽 1280 居中 (超宽窗口下双栏不散架), 内部双栏 / 单栏切换
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            RowLayout {
                id: contentBlock

                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width, 1280)
                height: parent.height
                spacing: ThemeTokens.Spacing.s7

                // 左栏 (~40%, 仅宽屏): 大封面 + 信息组整体垂直居中, 居中对齐呼应右侧居中歌词
                Item {
                    id: heroColumn

                    visible: root.wideLayout
                    Layout.fillHeight: true
                    Layout.preferredWidth: Math.round(contentBlock.width * 0.4)

                    // 封面边长: 不超过栏宽, 给下方信息组留约一半高度, 钳在 200~400
                    readonly property int coverSize: Math.max(200, Math.min(
                        400,
                        Math.min(heroColumn.width - ThemeTokens.Spacing.s7, Math.round(heroColumn.height * 0.5))
                    ))

                    ColumnLayout {
                        anchors.centerIn: parent
                        width: parent.width
                        spacing: ThemeTokens.Spacing.s5

                        Item {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: heroColumn.coverSize
                            Layout.preferredHeight: heroColumn.coverSize

                            // 朴素底色上的大封面需要分量感: 柔投影 + 1px 描边兜底
                            // (浅色封面 × 亮色主题时不与背景融掉)
                            RectangularShadow {
                                anchors.fill: parent
                                radius: ThemeTokens.Spacing.radiusLg
                                blur: ThemeTokens.Spacing.s7
                                offset.y: ThemeTokens.Spacing.s2
                                color: ThemeTokens.Palette.scrim
                            }

                            Components.AlbumArt {
                                id: heroArt

                                anchors.fill: parent
                                coverRadius: ThemeTokens.Spacing.radiusLg
                                // 换曲时保留旧图直到新图就绪, 大封面不闪占位
                                retainOnSwitch: true
                                coverUrl: root.hasSong && root.currentSong.coverUrl ? root.currentSong.coverUrl : ""
                                coverController: root.coverController
                                iconSize: ThemeTokens.TypeScale.display
                            }

                            Rectangle {
                                anchors.fill: parent
                                radius: ThemeTokens.Spacing.radiusLg
                                color: "transparent"
                                border.width: 1
                                border.color: ThemeTokens.Palette.outlineMuted
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.topMargin: ThemeTokens.Spacing.s3
                            text: root.hasSong ? root.currentSong.name : qsTr("尚未播放")
                            color: ThemeTokens.Palette.surfaceText
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: ThemeTokens.TypeScale.h1
                            font.weight: ThemeTokens.TypeScale.bold
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: root.hasSong ? root.singerText(root.currentSong) : qsTr("选择一首歌曲后开始")
                            color: ThemeTokens.Palette.surfaceVariantText
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: ThemeTokens.TypeScale.body
                            elide: Text.ElideRight
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: root.hasSong && text.length > 0
                            text: root.hasSong && root.currentSong.albumName ? root.currentSong.albumName : ""
                            color: ThemeTokens.Palette.surfaceVariantText
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: ThemeTokens.TypeScale.caption
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.topMargin: ThemeTokens.Spacing.s2
                            spacing: ThemeTokens.Spacing.s4

                            Components.LikeButton {
                                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                                libraryController: root.libraryController
                                song: root.currentSong
                            }

                            Components.IconButton {
                                text: qsTr("下载当前歌曲")
                                iconSource: "../icons/download.svg"
                                iconSize: 18
                                iconColor: ThemeTokens.Palette.surfaceVariantText
                                enabled: root.hasSong
                                onClicked: root.downloadRequested()
                            }

                            Components.IconButton {
                                text: qsTr("待播列表")
                                iconSource: "../icons/queue.svg"
                                iconSize: 18
                                iconColor: ThemeTokens.Palette.surfaceVariantText
                                onClicked: root.queueRequested()
                            }
                        }
                    }
                }

                // 右栏 (宽屏 ~60%) / 单栏 (窄屏整宽): 同一个 LyricPanel 实例, 滚动状态不随断点丢失
                Panels.LyricPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    compact: false
                    hasSong: root.hasSong
                    lyricController: root.lyricController
                    settingsController: root.settingsController
                    playerController: root.playerController
                }
            }
        }
    }
}
