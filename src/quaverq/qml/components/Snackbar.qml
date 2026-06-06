import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

// 轻量状态提示：调用 show() 显示，autoHideMs 后自动收起。
Rectangle {
    id: root

    property string message: ""
    property string kind: "info"   // info / error / warning / success
    property int autoHideMs: 4000

    readonly property color accent: root.kind === "error"
        ? ThemeTokens.Palette.error
        : root.kind === "warning"
        ? ThemeTokens.Palette.warning
        : root.kind === "success"
        ? ThemeTokens.Palette.primary
        : ThemeTokens.Palette.surfaceVariantText

    function show(text, kind) {
        root.message = text || ""
        if (root.message.length === 0)
            return
        root.kind = kind || "info"
        root.opacity = 1
        hideTimer.restart()
    }

    function dismiss() {
        hideTimer.stop()
        root.opacity = 0
    }

    visible: opacity > 0
    opacity: 0
    radius: ThemeTokens.Spacing.radiusMd
    color: ThemeTokens.Palette.surfaceContainerHigh
    border.color: root.accent
    implicitWidth: Math.min(560, contentRow.implicitWidth + ThemeTokens.Spacing.s5 * 2)
    implicitHeight: Math.max(48, contentRow.implicitHeight + ThemeTokens.Spacing.s4 * 2)

    Behavior on opacity {
        NumberAnimation {
            duration: ThemeTokens.Motion.durMed
            easing.type: ThemeTokens.Motion.easeStd
        }
    }

    Timer {
        id: hideTimer
        interval: root.autoHideMs
        onTriggered: root.dismiss()
    }

    RowLayout {
        id: contentRow
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s5
        anchors.rightMargin: ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s4

        Rectangle {
            Layout.preferredWidth: 4
            Layout.preferredHeight: 18
            radius: 2
            color: root.accent
        }

        Label {
            Layout.fillWidth: true
            text: root.message
            color: ThemeTokens.Palette.surfaceText
            wrapMode: Text.WordWrap
            font.pixelSize: ThemeTokens.TypeScale.bodySm
        }

        Button {
            id: closeButton

            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            text: "×"
            Accessible.name: qsTr("关闭提示")
            onClicked: root.dismiss()

            contentItem: Label {
                text: closeButton.text
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }

            background: Rectangle {
                radius: width / 2
                color: closeButton.down
                    ? ThemeTokens.Palette.statePressed
                    : closeButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
            }
        }
    }
}
