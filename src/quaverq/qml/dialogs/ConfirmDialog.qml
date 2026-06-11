pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

// 二次确认弹窗 (退出登录 / 清理缓存等): 统一自绘样式, 替代 Basic 默认
// standardButtons 的灰块直角观感. 调用方设 title / message / confirmText,
// destructive: true 时确认键用 error 红 (不可逆或代价高的动作), 否则品牌绿.
// 确认按钮文字应直述动作 (如「退出登录」「清理」), 不要泛泛的「确定」.
Dialog {
    id: root

    property string message: ""
    property string confirmText: qsTr("确定")
    property string cancelText: qsTr("取消")
    property bool destructive: false

    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    // 模态遮罩走 scrim token (W13)
    Overlay.modal: Rectangle { color: ThemeTokens.Palette.scrim }
    anchors.centerIn: Overlay.overlay
    width: Math.min(420, Math.max(280, (root.parent ? root.parent.width : 420) - ThemeTokens.Spacing.s6 * 2))
    padding: ThemeTokens.Spacing.s6
    topPadding: ThemeTokens.Spacing.s3

    // 打开时焦点落在「取消」(安全默认): 误按 Enter/Space 不触发破坏性动作
    onOpened: cancelButton.forceActiveFocus()

    background: Rectangle {
        radius: ThemeTokens.Spacing.radiusLg
        color: ThemeTokens.Palette.surface
        border.color: ThemeTokens.Palette.outline
    }

    header: Label {
        text: root.title
        visible: root.title.length > 0
        color: ThemeTokens.Palette.surfaceText
        font.pixelSize: ThemeTokens.TypeScale.body
        font.weight: ThemeTokens.TypeScale.bold
        elide: Text.ElideRight
        leftPadding: ThemeTokens.Spacing.s6
        rightPadding: ThemeTokens.Spacing.s6
        topPadding: ThemeTokens.Spacing.s6
    }

    contentItem: Label {
        text: root.message
        color: ThemeTokens.Palette.surfaceVariantText
        font.pixelSize: ThemeTokens.TypeScale.bodySm
        wrapMode: Text.WordWrap
        lineHeight: 1.4
    }

    footer: Item {
        implicitHeight: footerRow.implicitHeight + ThemeTokens.Spacing.s3 + ThemeTokens.Spacing.s6

        RowLayout {
            id: footerRow

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: ThemeTokens.Spacing.s6
            anchors.rightMargin: ThemeTokens.Spacing.s6
            anchors.bottomMargin: ThemeTokens.Spacing.s6
            spacing: ThemeTokens.Spacing.s3

            Item { Layout.fillWidth: true }

            Button {
                id: cancelButton

                Layout.preferredHeight: 36
                text: root.cancelText
                Accessible.name: text
                Keys.onReturnPressed: cancelButton.clicked()
                onClicked: root.reject()

                contentItem: Label {
                    text: cancelButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: ThemeTokens.Spacing.s5
                    rightPadding: ThemeTokens.Spacing.s5
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: cancelButton.down
                        ? ThemeTokens.Palette.statePressed
                        : cancelButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: cancelButton.visualFocus
                        ? ThemeTokens.Palette.focusRing
                        : ThemeTokens.Palette.outline
                    border.width: cancelButton.visualFocus ? 2 : 1
                }
            }

            Button {
                id: confirmButton

                Layout.preferredHeight: 36
                text: root.confirmText
                Accessible.name: text
                Keys.onReturnPressed: confirmButton.clicked()
                onClicked: root.accept()

                contentItem: Label {
                    text: confirmButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: ThemeTokens.Spacing.s5
                    rightPadding: ThemeTokens.Spacing.s5
                    color: ThemeTokens.Palette.primaryText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: {
                        if (root.destructive) {
                            return confirmButton.down
                                ? ThemeTokens.Palette.errorActive
                                : confirmButton.hovered ? ThemeTokens.Palette.errorHover : ThemeTokens.Palette.error
                        }
                        return confirmButton.down
                            ? ThemeTokens.Palette.primaryActive
                            : confirmButton.hovered ? ThemeTokens.Palette.primaryHover : ThemeTokens.Palette.primary
                    }
                    border.color: confirmButton.visualFocus ? ThemeTokens.Palette.focusRing : "transparent"
                    border.width: confirmButton.visualFocus ? 2 : 0
                }
            }
        }
    }
}
