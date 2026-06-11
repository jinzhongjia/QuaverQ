import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

// 内容卡片（歌单 / 专辑 / 艺人 / 排行榜）：方形封面 + 播放量角标 + hover 播放浮层 + 标题副标题。
// 整卡点击 → activated()（进详情）；hover 播放键 → playRequested()（播放）。
Item {
    id: root

    property string title: ""
    property string subtitle: ""
    property string coverUrl: ""
    property string meta: ""          // 播放量等角标文案；空则不显示
    property bool circular: false      // 艺人卡用圆形封面
    property var coverController

    signal activated()
    signal playRequested()

    implicitWidth: 160
    implicitHeight: column.implicitHeight

    Accessible.role: Accessible.Button
    Accessible.name: root.subtitle.length > 0 ? (root.title + "，" + root.subtitle) : root.title
    activeFocusOnTab: true

    HoverHandler { id: hover }
    // 整卡点击走 MouseArea (exclusive grab) 而非 TapHandler (passive grab): 作为背景被
    // modal dialog 覆盖时, passive grabber 会被 dialog 内点击穿透命中 (详见 SongRow 同款注释).
    // 浮层播放键 (z 更高) 也用 MouseArea, exclusive 竞争中胜出, 点播放键只播放不进详情.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onClicked: root.activated()
    }
    Keys.onReturnPressed: root.activated()
    Keys.onSpacePressed: root.activated()

    ColumnLayout {
        id: column

        width: root.width
        spacing: ThemeTokens.Spacing.s3

        Item {
            id: coverWrap

            Layout.fillWidth: true
            Layout.preferredHeight: width

            AlbumArt {
                anchors.fill: parent
                circular: root.circular
                coverUrl: root.coverUrl
                coverController: root.coverController
                iconText: root.circular ? "♬" : "♪"
            }

            // 圆形遮罩（艺人）——用一个边框圈近似，封面本身仍方形圆角
            Rectangle {
                anchors.fill: parent
                visible: root.activeFocus
                radius: root.circular ? width / 2 : ThemeTokens.Spacing.radiusLg
                color: "transparent"
                border.color: ThemeTokens.Palette.focusRing
                border.width: 2
                z: 3
            }

            // 播放量角标（hover 时让位给播放浮层）
            Rectangle {
                visible: root.meta.length > 0 && !hover.hovered && !root.circular
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: ThemeTokens.Spacing.s2
                height: 20
                width: metaLabel.implicitWidth + ThemeTokens.Spacing.s3
                radius: ThemeTokens.Spacing.radiusSm
                color: ThemeTokens.Palette.imageOverlay
                z: 2

                Label {
                    id: metaLabel

                    anchors.centerIn: parent
                    text: "▶ " + root.meta
                    color: ThemeTokens.Palette.imageOverlayText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                }
            }

            // hover：暗化 + 居中绿色播放键
            Rectangle {
                anchors.fill: parent
                visible: hover.hovered
                radius: root.circular ? Math.round(coverWrap.width / 2) : ThemeTokens.Spacing.radiusLg
                color: ThemeTokens.Palette.imageOverlayHover
                z: 2

                Rectangle {
                    anchors.centerIn: parent
                    width: 44
                    height: 44
                    radius: width / 2
                    color: playHover.hovered ? ThemeTokens.Palette.primaryHover : ThemeTokens.Palette.primary

                    HoverHandler { id: playHover }
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton
                        onClicked: root.playRequested()
                    }

                    AppIcon {
                        anchors.centerIn: parent
                        anchors.horizontalCenterOffset: 1
                        size: 18
                        source: "../icons/play.svg"
                        color: ThemeTokens.Palette.primaryText
                    }
                }
            }
        }

        Label {
            Layout.fillWidth: true
            text: root.title
            color: ThemeTokens.Palette.surfaceText
            font.pixelSize: ThemeTokens.TypeScale.bodySm
            font.weight: ThemeTokens.TypeScale.medium
            elide: Text.ElideRight
        }

        Label {
            Layout.fillWidth: true
            visible: root.subtitle.length > 0
            text: root.subtitle
            color: ThemeTokens.Palette.surfaceVariantText
            font.pixelSize: ThemeTokens.TypeScale.caption
            elide: Text.ElideRight
        }
    }
}
