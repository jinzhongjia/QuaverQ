import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "Theme" as ThemeTokens

ApplicationWindow {
    id: root

    width: ThemeTokens.Spacing.windowWidth
    height: ThemeTokens.Spacing.windowHeight
    minimumWidth: ThemeTokens.Spacing.minWindowWidth
    minimumHeight: ThemeTokens.Spacing.minWindowHeight
    visible: true
    title: qsTr("QuaverQ")
    color: ThemeTokens.Palette.background

    Rectangle {
        anchors.fill: parent
        color: ThemeTokens.Palette.background

        ColumnLayout {
            anchors.centerIn: parent
            spacing: ThemeTokens.Spacing.s5

            Label {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("QuaverQ")
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.display
                font.weight: ThemeTokens.TypeScale.medium
            }

            Label {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Qt Quick shell is ready")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.body
            }

            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: ThemeTokens.Spacing.s3
                implicitWidth: Math.min(root.width - ThemeTokens.Spacing.s8, ThemeTokens.Spacing.s8 * 8)
                implicitHeight: ThemeTokens.Spacing.s8 * 2
                radius: ThemeTokens.Spacing.radiusLg
                color: ThemeTokens.Palette.surface
                border.color: ThemeTokens.Palette.outline

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: ThemeTokens.Spacing.s5
                    spacing: ThemeTokens.Spacing.s4

                    Rectangle {
                        Layout.preferredWidth: ThemeTokens.Spacing.s8
                        Layout.preferredHeight: ThemeTokens.Spacing.s8
                        radius: ThemeTokens.Spacing.radiusMd
                        color: ThemeTokens.Palette.primaryContainer

                        Label {
                            anchors.centerIn: parent
                            text: "Q"
                            color: ThemeTokens.Palette.primary
                            font.pixelSize: ThemeTokens.TypeScale.h1
                            font.weight: ThemeTokens.TypeScale.medium
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: ThemeTokens.Spacing.s2

                        Label {
                            text: ThemeTokens.Theme.dark ? qsTr("Dark tokens active") : qsTr("Light tokens active")
                            color: ThemeTokens.Palette.onSurface
                            font.pixelSize: ThemeTokens.TypeScale.body
                            font.weight: ThemeTokens.TypeScale.medium
                        }

                        Label {
                            text: qsTr("Palette / TypeScale / Spacing / Motion")
                            color: ThemeTokens.Palette.onSurfaceVariant
                            font.pixelSize: ThemeTokens.TypeScale.caption
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }
    }
}
