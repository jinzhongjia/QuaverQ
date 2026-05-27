import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

FocusScope {
    id: root

    property alias text: input.text
    property alias placeholderText: input.placeholderText
    property bool loading: false

    signal searchRequested(string text)

    implicitWidth: 560
    implicitHeight: ThemeTokens.Spacing.toolHitSize

    function focusInput() {
        input.forceActiveFocus()
        input.selectAll()
    }

    Rectangle {
        anchors.fill: parent
        radius: ThemeTokens.Spacing.radiusMd
        color: ThemeTokens.Palette.surfaceVariant
        border.color: input.activeFocus ? ThemeTokens.Palette.focusRing : ThemeTokens.Palette.outline
        border.width: input.activeFocus ? 2 : 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s4
        anchors.rightMargin: ThemeTokens.Spacing.s2
        spacing: ThemeTokens.Spacing.s3

        Label {
            text: "⌕"
            color: ThemeTokens.Palette.onSurfaceVariant
            font.pixelSize: ThemeTokens.TypeScale.h2
        }

        TextField {
            id: input

            Layout.fillWidth: true
            selectByMouse: true
            font.pixelSize: ThemeTokens.TypeScale.body
            color: ThemeTokens.Palette.onSurface
            placeholderTextColor: ThemeTokens.Palette.onSurfaceVariant
            Accessible.name: qsTr("搜索")
            onAccepted: root.searchRequested(text)

            background: Item {}
        }

        Button {
            Layout.preferredWidth: 88
            Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize - ThemeTokens.Spacing.s2
            text: root.loading ? qsTr("搜索中") : qsTr("搜索")
            enabled: !root.loading
            Accessible.name: qsTr("执行搜索")
            onClicked: root.searchRequested(input.text)

            contentItem: Label {
                text: parent.text
                color: parent.enabled ? ThemeTokens.Palette.onPrimary : ThemeTokens.Palette.onSurfaceVariant
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                font.weight: ThemeTokens.TypeScale.medium
            }

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: parent.enabled ? ThemeTokens.Palette.primary : ThemeTokens.Palette.stateDisabled
            }
        }
    }
}
