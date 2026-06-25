import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

// 药丸状可点搜索词 chip (相关搜索词 / 热门搜索共用): 显示 text, 点击发 clicked()
Rectangle {
    id: root

    property string text: ""

    signal clicked()

    radius: ThemeTokens.Spacing.radiusPill
    height: 30
    width: chipLabel.implicitWidth + ThemeTokens.Spacing.s5 * 2
    color: chipArea.containsMouse ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant

    Accessible.role: Accessible.Button
    Accessible.name: root.text

    Label {
        id: chipLabel

        anchors.centerIn: parent
        text: root.text
        color: ThemeTokens.Palette.surfaceText
        font.pixelSize: ThemeTokens.TypeScale.bodySm
    }

    MouseArea {
        id: chipArea

        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
