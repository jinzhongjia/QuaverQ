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
    signal editingCancelled()

    implicitWidth: 500
    implicitHeight: ThemeTokens.Spacing.toolHitSize

    function focusInput() {
        input.forceActiveFocus()
        input.selectAll()
    }

    function releaseInputFocus() {
        input.focus = false
        root.focus = false
    }

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: ThemeTokens.Palette.surfaceVariant
        border.color: input.activeFocus ? ThemeTokens.Palette.focusRing : "transparent"
        border.width: input.activeFocus ? 2 : 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s4
        anchors.rightMargin: ThemeTokens.Spacing.s2
        spacing: ThemeTokens.Spacing.s3

        AppIcon {
            size: 18
            source: "../icons/search.svg"
            color: ThemeTokens.Palette.surfaceVariantText
        }

        TextField {
            id: input

            Layout.fillWidth: true
            selectByMouse: true
            font.pixelSize: ThemeTokens.TypeScale.body
            color: ThemeTokens.Palette.surfaceText
            placeholderTextColor: ThemeTokens.Palette.surfaceVariantText
            Accessible.name: qsTr("搜索")
            onAccepted: root.searchRequested(text)
            Keys.onEscapePressed: root.editingCancelled()

            background: Item {}
        }

        Button {
            id: searchButton

            Layout.preferredWidth: 76
            Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize - ThemeTokens.Spacing.s2
            text: root.loading ? qsTr("搜索中") : qsTr("搜索")
            enabled: !root.loading
            Accessible.name: qsTr("执行搜索")
            onClicked: root.searchRequested(input.text)

            contentItem: Label {
                text: searchButton.text
                color: searchButton.enabled ? ThemeTokens.Palette.primaryText : ThemeTokens.Palette.surfaceVariantText
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                font.weight: ThemeTokens.TypeScale.medium
            }

            background: Rectangle {
                radius: height / 2
                color: searchButton.enabled ? ThemeTokens.Palette.primary : ThemeTokens.Palette.stateDisabled
            }
        }
    }
}
