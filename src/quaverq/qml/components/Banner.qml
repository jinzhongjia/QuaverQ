import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

// 持久提示：带恢复动作、不自动关闭（见 design §11）。message 非空即显示。
Rectangle {
    id: root

    property string message: ""
    property string kind: "warning"   // warning / error / info
    property string actionText: ""

    signal actionTriggered()
    signal dismissed()

    readonly property color accent: root.kind === "error"
        ? ThemeTokens.Palette.error
        : root.kind === "warning"
        ? ThemeTokens.Palette.warning
        : ThemeTokens.Palette.primary

    function dismiss() {
        root.message = ""
        root.dismissed()
    }

    visible: root.message.length > 0
    implicitHeight: visible ? Math.max(48, bannerRow.implicitHeight + ThemeTokens.Spacing.s3 * 2) : 0
    color: ThemeTokens.Palette.surfaceContainerHigh
    border.color: root.accent

    RowLayout {
        id: bannerRow
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s5
        anchors.rightMargin: ThemeTokens.Spacing.s4
        anchors.topMargin: ThemeTokens.Spacing.s3
        anchors.bottomMargin: ThemeTokens.Spacing.s3
        spacing: ThemeTokens.Spacing.s4

        Rectangle {
            Layout.preferredWidth: 4
            Layout.fillHeight: true
            radius: 2
            color: root.accent
        }

        Label {
            Layout.fillWidth: true
            text: root.message
            color: ThemeTokens.Palette.surfaceText
            wrapMode: Text.WordWrap
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: ThemeTokens.TypeScale.bodySm
        }

        Button {
            id: actionButton

            visible: root.actionText.length > 0
            Layout.preferredHeight: 32
            text: root.actionText
            Accessible.name: root.actionText
            onClicked: root.actionTriggered()

            contentItem: Label {
                text: actionButton.text
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                leftPadding: ThemeTokens.Spacing.s4
                rightPadding: ThemeTokens.Spacing.s4
                color: ThemeTokens.Palette.primaryText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                font.weight: ThemeTokens.TypeScale.medium
            }

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: actionButton.down
                    ? ThemeTokens.Palette.statePressed
                    : root.accent
            }
        }

        Button {
            id: closeButton

            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            text: "×"
            Accessible.name: qsTr("关闭")
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
