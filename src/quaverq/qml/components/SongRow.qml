import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property string name: ""
    property string singers: ""
    property string albumName: ""
    property string durationText: ""
    property int rowNumber: 0

    signal activated()

    implicitHeight: 58
    radius: ThemeTokens.Spacing.radiusMd
    color: hoverHandler.hovered ? ThemeTokens.Palette.stateHover : "transparent"

    Accessible.role: Accessible.ListItem
    Accessible.name: albumName
        ? qsTr("%1, %2, %3").arg(name).arg(singers).arg(albumName)
        : qsTr("%1, %2").arg(name).arg(singers)

    HoverHandler {
        id: hoverHandler
    }

    TapHandler {
        onTapped: root.activated()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s4
        anchors.rightMargin: ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s4

        Label {
            Layout.preferredWidth: 28
            text: rowNumber > 0 ? String(rowNumber) : ""
            color: ThemeTokens.Palette.onSurfaceVariant
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
        }

        Rectangle {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            radius: ThemeTokens.Spacing.radiusMd
            color: ThemeTokens.Palette.surfaceVariant

            Label {
                anchors.centerIn: parent
                text: "♪"
                color: ThemeTokens.Palette.primary
                font.pixelSize: ThemeTokens.TypeScale.h2
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s2

            Label {
                Layout.fillWidth: true
                text: root.name
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.body
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: albumName ? qsTr("%1 · %2").arg(singers).arg(albumName) : singers
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }
        }

        Label {
            Layout.preferredWidth: 52
            text: durationText
            color: ThemeTokens.Palette.onSurfaceVariant
            horizontalAlignment: Text.AlignRight
            font.pixelSize: ThemeTokens.TypeScale.caption
        }
    }
}
