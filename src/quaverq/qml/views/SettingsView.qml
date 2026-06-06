pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

ScrollView {
    id: root

    property string routeName: "settings"
    property var appController
    property var settingsController

    signal loginRequested()

    contentWidth: availableWidth

    Component.onCompleted: {
        if (root.settingsController)
            root.settingsController.refreshCoverCacheSize()
    }

    function themeLabel(value) {
        switch (value) {
        case "light":
            return qsTr("浅色")
        case "dark":
            return qsTr("深色")
        default:
            return qsTr("跟随系统")
        }
    }

    function qualityLabel(value) {
        switch (value) {
        case "standard":
            return qsTr("标准")
        case "high":
            return qsTr("高品质")
        default:
            return qsTr("均衡")
        }
    }

    function cacheCapLabel(bytes) {
        if (!bytes || bytes <= 0)
            return qsTr("无限制")
        var mb = bytes / (1024 * 1024)
        if (mb >= 1024)
            return (Math.round(mb / 1024 * 10) / 10) + " GB"
        return Math.round(mb) + " MB"
    }

    ColumnLayout {
        width: root.availableWidth
        spacing: ThemeTokens.Spacing.s5

        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: ThemeTokens.Spacing.s6
            spacing: ThemeTokens.Spacing.s2

            Label {
                Layout.fillWidth: true
                text: qsTr("设置")
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.h1
                font.weight: ThemeTokens.TypeScale.bold
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: qsTr("账号、播放和界面偏好")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }
        }

        SettingsSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            title: qsTr("账号")

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("QQ 音乐账号")
                value: root.appController && root.appController.authed ? qsTr("已同步账号") : qsTr("未登录")
                actionText: root.appController && root.appController.authed ? qsTr("退出登录") : qsTr("登录")
                onActionRequested: {
                    if (root.appController && root.appController.authed) {
                        root.appController.logout()
                    } else {
                        root.loginRequested()
                    }
                }
            }
        }

        SettingsSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            title: qsTr("播放")

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("音质偏好")
                value: root.settingsController
                    ? root.qualityLabel(root.settingsController.qualityPreference)
                    : root.qualityLabel("balanced")
                model: [qsTr("标准"), qsTr("均衡"), qsTr("高品质")]
                values: ["standard", "balanced", "high"]
                currentValue: root.settingsController ? root.settingsController.qualityPreference : "balanced"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setQualityPreference(value)
                }
            }
        }

        SettingsSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            title: qsTr("外观")

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("主题")
                value: root.settingsController
                    ? root.themeLabel(root.settingsController.themeMode)
                    : root.themeLabel("system")
                model: [qsTr("跟随系统"), qsTr("浅色"), qsTr("深色")]
                values: ["system", "light", "dark"]
                currentValue: root.settingsController ? root.settingsController.themeMode : "system"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setThemeMode(value)
                }
            }
        }

        SettingsSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            Layout.bottomMargin: ThemeTokens.Spacing.s6
            title: qsTr("缓存")

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("封面缓存上限")
                value: root.settingsController
                    ? root.cacheCapLabel(root.settingsController.coverCacheMaxBytes)
                    : root.cacheCapLabel(256 * 1024 * 1024)
                model: [qsTr("128 MB"), qsTr("256 MB"), qsTr("512 MB"), qsTr("1 GB"), qsTr("2 GB"), qsTr("无限制")]
                values: ["134217728", "268435456", "536870912", "1073741824", "2147483648", "0"]
                currentValue: root.settingsController ? String(root.settingsController.coverCacheMaxBytes) : "268435456"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setCoverCacheMaxBytes(parseInt(value))
                }
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("封面缓存")
                value: root.settingsController
                    ? root.settingsController.coverCacheSizeText
                    : qsTr("0 B")
                actionText: qsTr("清理")
                onActionRequested: clearCacheDialog.open()
            }
        }
    }

    Dialog {
        id: clearCacheDialog

        modal: true
        title: qsTr("清理封面缓存")
        standardButtons: Dialog.Cancel | Dialog.Ok
        anchors.centerIn: Overlay.overlay
        width: Math.min(420, Math.max(280, root.width - ThemeTokens.Spacing.s6 * 2))
        onAccepted: {
            if (root.settingsController)
                root.settingsController.clearCoverCache()
        }

        contentItem: Label {
            text: qsTr("已缓存的封面会被删除，之后会按需重新下载。")
            color: ThemeTokens.Palette.surfaceText
            wrapMode: Text.WordWrap
            font.pixelSize: ThemeTokens.TypeScale.bodySm
        }
    }

    component SettingsSection: Rectangle {
        id: section

        property string title: ""
        default property alias content: sectionColumn.data

        implicitHeight: sectionColumn.implicitHeight + ThemeTokens.Spacing.s5 * 2
        radius: ThemeTokens.Spacing.radiusLg
        color: ThemeTokens.Palette.surfaceElevated
        border.color: ThemeTokens.Palette.outlineMuted

        ColumnLayout {
            id: sectionColumn

            anchors.fill: parent
            anchors.margins: ThemeTokens.Spacing.s5
            spacing: ThemeTokens.Spacing.s3

            Label {
                Layout.fillWidth: true
                text: section.title
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.bold
                elide: Text.ElideRight
            }
        }
    }

    component SettingsRow: Rectangle {
        id: row

        property string title: ""
        property string value: ""
        property string actionText: ""
        property int rightReservedWidth: row.actionText.length > 0 ? 94 : 0

        signal actionRequested()

        implicitHeight: 60
        radius: ThemeTokens.Spacing.radiusMd
        color: ThemeTokens.Palette.surface
        border.color: ThemeTokens.Palette.outlineMuted

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s4
            anchors.rightMargin: ThemeTokens.Spacing.s3 + row.rightReservedWidth
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: row.title
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: row.value
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }

            Button {
                id: actionButton

                Layout.preferredWidth: 86
                Layout.preferredHeight: 34
                visible: row.actionText.length > 0
                text: row.actionText
                Accessible.name: text
                onClicked: row.actionRequested()

                contentItem: Label {
                    text: actionButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: actionButton.down
                        ? ThemeTokens.Palette.statePressed
                        : actionButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: ThemeTokens.Palette.outline
                }
            }
        }
    }

    component ChoiceRow: SettingsRow {
        id: row

        property var model: []
        property var values: []
        property string currentValue: ""

        signal valueRequested(string value)

        actionText: ""
        rightReservedWidth: 154

        ComboBox {
            id: combo

            anchors.right: parent.right
            anchors.rightMargin: ThemeTokens.Spacing.s3
            anchors.verticalCenter: parent.verticalCenter
            width: 142
            height: 36
            model: row.model
            currentIndex: Math.max(0, row.values.indexOf(row.currentValue))
            Accessible.name: row.title
            onActivated: function(index) {
                if (index >= 0 && index < row.values.length)
                    row.valueRequested(row.values[index])
            }

            contentItem: Label {
                leftPadding: ThemeTokens.Spacing.s3
                rightPadding: ThemeTokens.Spacing.s6
                text: combo.displayText
                color: ThemeTokens.Palette.surfaceText
                horizontalAlignment: Text.AlignLeft
                verticalAlignment: Text.AlignVCenter
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }

            indicator: Label {
                anchors.right: parent.right
                anchors.rightMargin: ThemeTokens.Spacing.s3
                anchors.verticalCenter: parent.verticalCenter
                text: combo.popup.visible ? "⌃" : "⌄"
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: combo.down || combo.popup.visible
                    ? ThemeTokens.Palette.statePressed
                    : combo.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surface
                border.color: combo.activeFocus ? ThemeTokens.Palette.focusRing : ThemeTokens.Palette.outlineMuted
            }

            popup: Popup {
                y: combo.height + 4
                width: combo.width
                implicitHeight: listView.contentHeight + ThemeTokens.Spacing.s2
                padding: ThemeTokens.Spacing.s2

                contentItem: ListView {
                    id: listView

                    clip: true
                    implicitHeight: contentHeight
                    model: combo.popup.visible ? combo.delegateModel : null
                    currentIndex: combo.highlightedIndex
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: ThemeTokens.Palette.surfaceElevated
                    border.color: ThemeTokens.Palette.outlineMuted
                }
            }

            delegate: ItemDelegate {
                id: comboDelegate

                required property int index
                required property string modelData

                width: combo.width
                height: 34
                text: modelData
                highlighted: combo.highlightedIndex === index

                contentItem: Label {
                    text: comboDelegate.modelData
                    color: ThemeTokens.Palette.surfaceText
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusSm
                    color: comboDelegate.highlighted
                        ? ThemeTokens.Palette.stateHover
                        : comboDelegate.index === combo.currentIndex ? ThemeTokens.Palette.primaryContainer : "transparent"
                }
            }
        }
    }
}
