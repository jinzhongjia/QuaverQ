import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    height: ThemeTokens.Spacing.playerBarHeight
    color: ThemeTokens.Palette.surface
    border.color: ThemeTokens.Palette.outline

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s5
        anchors.rightMargin: ThemeTokens.Spacing.s5
        spacing: ThemeTokens.Spacing.s5

        Rectangle {
            Layout.preferredWidth: 56
            Layout.preferredHeight: 56
            radius: ThemeTokens.Spacing.radiusLg
            color: ThemeTokens.Palette.surfaceVariant

            Label {
                anchors.centerIn: parent
                text: "♪"
                color: ThemeTokens.Palette.primary
                font.pixelSize: ThemeTokens.TypeScale.h1
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 220
            spacing: ThemeTokens.Spacing.s2

            Label {
                Layout.fillWidth: true
                text: qsTr("尚未播放")
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.body
                font.weight: ThemeTokens.TypeScale.medium
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: qsTr("选择一首歌曲后开始")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width, 520)
                spacing: ThemeTokens.Spacing.s3

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: ThemeTokens.Spacing.s3

                    Repeater {
                        model: ["⏮", "▶", "⏭"]

                        delegate: Button {
                            Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                            Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                            text: modelData
                            enabled: false

                            contentItem: Label {
                                text: parent.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                color: parent.enabled ? ThemeTokens.Palette.onSurface : ThemeTokens.Palette.onSurfaceVariant
                                font.pixelSize: ThemeTokens.TypeScale.body
                            }

                            background: Rectangle {
                                radius: width / 2
                                color: modelData === "▶"
                                    ? ThemeTokens.Palette.primaryContainer
                                    : "transparent"
                                border.color: modelData === "▶"
                                    ? ThemeTokens.Palette.primary
                                    : "transparent"
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: ThemeTokens.Spacing.s3

                    Label {
                        text: "0:00"
                        color: ThemeTokens.Palette.onSurfaceVariant
                        font.pixelSize: ThemeTokens.TypeScale.caption
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 4
                        radius: 2
                        color: ThemeTokens.Palette.surfaceVariant

                        Rectangle {
                            width: 0
                            height: parent.height
                            radius: parent.radius
                            color: ThemeTokens.Palette.primary
                        }
                    }

                    Label {
                        text: "--:--"
                        color: ThemeTokens.Palette.onSurfaceVariant
                        font.pixelSize: ThemeTokens.TypeScale.caption
                    }
                }
            }
        }

        Label {
            Layout.preferredWidth: 120
            text: qsTr("balanced")
            color: ThemeTokens.Palette.onSurfaceVariant
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
        }
    }
}
