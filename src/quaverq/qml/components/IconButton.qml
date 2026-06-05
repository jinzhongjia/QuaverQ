import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

// 统一工具按钮：≥44px 命中区、焦点环、Enter/Space 触发、无障碍名（见 design §7/§10）。
// text 作为无障碍名，iconText 作为显示字形（图标按钮 tooltip 不能替代 Accessible.name）。
AbstractButton {
    id: control

    property string iconText: ""
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

    background: Rectangle {
        radius: control.cornerRadius
        color: control.down
            ? control.pressedColor
            : control.hovered ? control.hoverColor : "transparent"

        Rectangle {
            anchors.fill: parent
            visible: control.activeFocus
            radius: parent.radius
            color: "transparent"
            border.color: ThemeTokens.Palette.focusRing
            border.width: 2
        }
    }

    contentItem: Label {
        text: control.iconText
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: control.iconColor
        font.pixelSize: control.iconSize
    }
}
