pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

ScrollView {
    id: root

    property string routeName: "detail"
    property string detailKind: "playlist"
    property string detailId: ""
    property string detailTitle: qsTr("详情")
    property string detailSubtitle: ""

    signal backRequested()
    signal searchRequested(string keyword)

    contentWidth: availableWidth

    function kindLabel(kind) {
        switch (kind) {
        case "album":
            return qsTr("专辑")
        case "artist":
            return qsTr("艺人")
        default:
            return qsTr("歌单")
        }
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

            Rectangle {
                Layout.preferredWidth: 128
                Layout.preferredHeight: 128
                radius: ThemeTokens.Spacing.radiusLg
                color: ThemeTokens.Palette.surfaceVariant

                Label {
                    anchors.centerIn: parent
                    text: root.detailKind === "artist" ? "◎" : "♪"
                    color: ThemeTokens.Palette.primary
                    font.pixelSize: ThemeTokens.TypeScale.display
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s3

                Label {
                    Layout.fillWidth: true
                    text: root.kindLabel(root.detailKind)
                    color: ThemeTokens.Palette.primary
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.detailTitle
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.medium
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text: root.detailSubtitle.length > 0 ? root.detailSubtitle : qsTr("暂无简介")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    wrapMode: Text.WordWrap
                }

                Button {
                    id: searchButton

                    Layout.preferredWidth: 112
                    Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                    text: qsTr("搜索相关")
                    Accessible.name: text
                    onClicked: root.searchRequested(root.detailTitle)

                    contentItem: Label {
                        text: searchButton.text
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: ThemeTokens.Palette.onPrimary
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        font.weight: ThemeTokens.TypeScale.medium
                    }

                    background: Rectangle {
                        radius: ThemeTokens.Spacing.radiusMd
                        color: ThemeTokens.Palette.primary
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            Layout.bottomMargin: ThemeTokens.Spacing.s6
            spacing: ThemeTokens.Spacing.s3

            Label {
                Layout.fillWidth: true
                text: root.detailKind === "artist" ? qsTr("热门歌曲") : qsTr("曲目")
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.medium
                elide: Text.ElideRight
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 72
                radius: ThemeTokens.Spacing.radiusMd
                color: ThemeTokens.Palette.surface
                border.color: ThemeTokens.Palette.outline

                Label {
                    anchors.centerIn: parent
                    text: qsTr("暂无曲目")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                }
            }
        }
    }
}
