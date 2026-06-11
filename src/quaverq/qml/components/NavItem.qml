import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property string text: ""
    property string iconText: ""
    // SVG 图标 (优先): Unicode 字形会落到不同回退字体, 视觉大小不可控
    property url iconSource: ""
    property bool selected: false
    property bool compact: false
    readonly property color iconColor: root.selected
        ? ThemeTokens.Palette.primaryFg
        : ThemeTokens.Palette.surfaceVariantText

    signal activated()

    implicitHeight: 42
    radius: ThemeTokens.Spacing.radiusMd
    color: root.selected
        ? ThemeTokens.Palette.stateSelected
        : (hoverHandler.hovered ? ThemeTokens.Palette.stateHover : "transparent")

    Accessible.role: Accessible.Button
    Accessible.name: text
    activeFocusOnTab: true

    HoverHandler {
        id: hoverHandler
    }

    TapHandler {
        onTapped: root.activated()
    }

    Keys.onReturnPressed: root.activated()
    Keys.onSpacePressed: root.activated()

    Rectangle {
        anchors.fill: parent
        visible: root.activeFocus
        radius: parent.radius
        color: "transparent"
        border.color: ThemeTokens.Palette.focusRing
        border.width: 2
        z: 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: root.compact ? 0 : ThemeTokens.Spacing.s4
        anchors.rightMargin: root.compact ? 0 : ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s3

        Item {
            id: iconBox

            readonly property int iconPx: root.compact ? 20 : 17

            Layout.alignment: Qt.AlignVCenter
            Layout.preferredWidth: root.compact ? parent.width : ThemeTokens.Spacing.s5
            Layout.preferredHeight: 22

            AppIcon {
                anchors.centerIn: parent
                visible: root.iconSource.toString().length > 0
                size: iconBox.iconPx
                source: root.iconSource
                color: root.iconColor
            }

            // 后备: 没给 iconSource 时仍走字形
            Label {
                anchors.centerIn: parent
                visible: root.iconSource.toString().length === 0
                text: root.iconText || root.text.slice(0, 1)
                color: root.iconColor
                font.pixelSize: root.compact ? ThemeTokens.TypeScale.h2 : ThemeTokens.TypeScale.body
                font.weight: ThemeTokens.TypeScale.medium
            }
        }

        Label {
            Layout.fillWidth: true
            visible: !root.compact
            text: root.text
            color: root.selected ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
            font.pixelSize: ThemeTokens.TypeScale.bodySm
            font.weight: root.selected ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.regular
            elide: Text.ElideRight
        }
    }
}
