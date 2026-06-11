import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

// 统一工具按钮：≥44px 命中区、焦点环、Enter/Space 触发、无障碍名。
// text 作为无障碍名，iconText 作为显示字形（图标按钮 tooltip 不能替代 Accessible.name）。
AbstractButton {
    id: control

    property string iconText: ""
    // SVG 图标 (优先于 iconText): 经 AppIcon 按 iconColor 染色
    property url iconSource: ""
    property int iconSize: ThemeTokens.TypeScale.h2
    property color iconColor: ThemeTokens.Palette.surfaceVariantText
    property int hitSize: ThemeTokens.Spacing.toolHitSize
    property real cornerRadius: ThemeTokens.Spacing.radiusMd
    property color hoverColor: ThemeTokens.Palette.stateHover
    property color pressedColor: ThemeTokens.Palette.statePressed

    implicitWidth: control.hitSize
    implicitHeight: control.hitSize
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true

    Accessible.role: Accessible.Button
    Accessible.name: control.text

    Keys.onReturnPressed: control.clicked()
    Keys.onEnterPressed: control.clicked()
    Keys.onSpacePressed: control.clicked()

    // 字形图标含义不自明 (⇄ / ☰ / 词 等), hover 出无障碍名作提示
    AppToolTip {
        visible: control.hovered && control.text.length > 0
        text: control.text
    }

    background: Rectangle {
        radius: control.cornerRadius
        color: control.down
            ? control.pressedColor
            : control.hovered ? control.hoverColor : "transparent"

        Rectangle {
            anchors.fill: parent
            // visualFocus: 仅键盘聚焦时画环, 鼠标点击不残留
            visible: control.visualFocus
            radius: parent.radius
            color: "transparent"
            border.color: ThemeTokens.Palette.focusRing
            border.width: 2
        }
    }

    contentItem: Item {
        AppIcon {
            anchors.centerIn: parent
            visible: control.iconSource.toString().length > 0
            size: control.iconSize
            source: control.iconSource
            color: control.iconColor
        }

        Label {
            anchors.centerIn: parent
            visible: control.iconSource.toString().length === 0
            text: control.iconText
            color: control.iconColor
            font.pixelSize: control.iconSize
        }
    }
}
