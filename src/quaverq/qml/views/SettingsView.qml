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

    function weightLabel(value) {
        switch (value) {
        case "regular":
            return qsTr("常规")
        case "bold":
            return qsTr("加粗")
        default:
            return qsTr("中等")
        }
    }

    function fontFamilyLabel(value) {
        return (value && value.length > 0) ? value : qsTr("系统默认")
    }

    function orientationLabel(value) {
        return value === "vertical" ? qsTr("竖向") : qsTr("横向")
    }

    function onOffLabel(value) {
        return value ? qsTr("开") : qsTr("关")
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
            title: qsTr("歌词")

            FontPickerRow {
                Layout.fillWidth: true
                title: qsTr("字体")
                families: root.settingsController ? root.settingsController.availableLyricFonts : []
                currentValue: root.settingsController ? root.settingsController.lyricFontFamily : ""
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setLyricFontFamily(value)
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("字号")
                value: root.settingsController ? (root.settingsController.lyricFontSize + " px") : "22 px"
                model: ["14 px", "16 px", "18 px", "20 px", "22 px", "24 px", "26 px", "28 px", "32 px", "36 px", "40 px"]
                values: ["14", "16", "18", "20", "22", "24", "26", "28", "32", "36", "40"]
                currentValue: root.settingsController ? String(root.settingsController.lyricFontSize) : "22"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setLyricFontSize(parseInt(value))
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("字重")
                value: root.weightLabel(root.settingsController ? root.settingsController.lyricFontWeight : "medium")
                model: [qsTr("常规"), qsTr("中等"), qsTr("加粗")]
                values: ["regular", "medium", "bold"]
                currentValue: root.settingsController ? root.settingsController.lyricFontWeight : "medium"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setLyricFontWeight(value)
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("斜体")
                value: (root.settingsController && root.settingsController.lyricFontItalic) ? qsTr("开") : qsTr("关")
                model: [qsTr("关"), qsTr("开")]
                values: ["off", "on"]
                currentValue: (root.settingsController && root.settingsController.lyricFontItalic) ? "on" : "off"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setLyricFontItalic(value === "on")
                }
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("重置歌词字体")
                value: qsTr("恢复字体 / 字号 / 字重 / 斜体到默认值")
                actionText: qsTr("重置")
                onActionRequested: {
                    if (root.settingsController)
                        root.settingsController.resetLyricFont()
                }
            }
        }

        // 桌面悬浮歌词: 仅 Windows 暴露 (Linux / macOS 故意不实现, 见 platform/base.py)
        SettingsSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            visible: Qt.platform.os === "windows"
            title: qsTr("桌面悬浮歌词")

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("锁定 (鼠标穿透)")
                value: root.settingsController
                    ? root.onOffLabel(root.settingsController.desktopLyricsLocked)
                    : root.onOffLabel(true)
                model: [qsTr("开"), qsTr("关")]
                values: ["on", "off"]
                currentValue: (root.settingsController && root.settingsController.desktopLyricsLocked) ? "on" : "off"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsLocked(value === "on")
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("方向")
                value: root.settingsController
                    ? root.orientationLabel(root.settingsController.desktopLyricsOrientation)
                    : root.orientationLabel("horizontal")
                model: [qsTr("横向"), qsTr("竖向")]
                values: ["horizontal", "vertical"]
                currentValue: root.settingsController ? root.settingsController.desktopLyricsOrientation : "horizontal"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsOrientation(value)
                }
            }

            FontPickerRow {
                Layout.fillWidth: true
                title: qsTr("字体")
                families: root.settingsController ? root.settingsController.availableLyricFonts : []
                currentValue: root.settingsController ? root.settingsController.desktopLyricsFontFamily : ""
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsFontFamily(value)
                }
            }

            SpinRow {
                Layout.fillWidth: true
                title: qsTr("字号")
                fromValue: 14
                toValue: 72
                suffix: qsTr(" px")
                currentValue: root.settingsController ? root.settingsController.desktopLyricsFontSize : 32
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsFontSize(value)
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("粗体")
                value: root.settingsController
                    ? root.onOffLabel(root.settingsController.desktopLyricsBold)
                    : root.onOffLabel(true)
                model: [qsTr("关"), qsTr("开")]
                values: ["off", "on"]
                currentValue: (root.settingsController && root.settingsController.desktopLyricsBold) ? "on" : "off"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsBold(value === "on")
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("斜体")
                value: root.settingsController
                    ? root.onOffLabel(root.settingsController.desktopLyricsItalic)
                    : root.onOffLabel(false)
                model: [qsTr("关"), qsTr("开")]
                values: ["off", "on"]
                currentValue: (root.settingsController && root.settingsController.desktopLyricsItalic) ? "on" : "off"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsItalic(value === "on")
                }
            }

            ColorRow {
                Layout.fillWidth: true
                title: qsTr("未唱字色")
                colorValue: root.settingsController ? root.settingsController.desktopLyricsColorBase : "#FFFFFF"
                onPickRequested: {
                    if (root.settingsController)
                        root.settingsController.pickDesktopLyricsColor("base")
                }
            }

            ColorRow {
                Layout.fillWidth: true
                title: qsTr("已唱字色")
                colorValue: root.settingsController ? root.settingsController.desktopLyricsColorHighlight : "#FFA200"
                onPickRequested: {
                    if (root.settingsController)
                        root.settingsController.pickDesktopLyricsColor("highlight")
                }
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("重置桌面歌词")
                value: qsTr("字体 / 字号 / 颜色 / 方向 恢复默认 (不动锁定状态)")
                actionText: qsTr("重置")
                onActionRequested: {
                    if (root.settingsController)
                        root.settingsController.resetDesktopLyrics()
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
            // 行间 0 间距让 SettingsRow 的 1px 底分隔线直接相邻成连续列表;
            // 章节标题与首行的间距由标题 bottomMargin 单独给.
            spacing: 0

            Label {
                Layout.fillWidth: true
                Layout.bottomMargin: ThemeTokens.Spacing.s3
                text: section.title
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.bold
                elide: Text.ElideRight
            }
        }
    }

    // 行容器: 不再加边框 / 圆角背景 (section 卡已带), 改用 1px 底分隔线让多行连成一列.
    // section 内最后一行 / 单行的多余分隔线被 section 下边距 / 圆角自然吸收, 视觉无歧义.
    component SettingsRow: Item {
        id: row

        property string title: ""
        property string value: ""
        property string actionText: ""
        property int rightReservedWidth: row.actionText.length > 0 ? 96 : 0
        property bool showSeparator: true

        signal actionRequested()

        implicitHeight: 56

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s3
            anchors.rightMargin: ThemeTokens.Spacing.s3 + row.rightReservedWidth
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

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
                    visible: text.length > 0
                }
            }

            Button {
                id: actionButton

                Layout.preferredWidth: 86
                Layout.preferredHeight: 32
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
                    border.color: ThemeTokens.Palette.outlineMuted
                }
            }
        }

        // 1px 底分隔线: 把列表纵向连成一气 (vs. 每行独立 card)
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: ThemeTokens.Palette.outlineMuted
            opacity: 0.6
            visible: row.showSeparator
        }
    }

    component ChoiceRow: SettingsRow {
        id: row

        property var model: []
        property var values: []
        property string currentValue: ""
        property int popupMaxHeight: 0  // >0 时给下拉列表设上限, 避免长列表撑出窗口
        property int comboWidth: 142

        signal valueRequested(string value)

        actionText: ""
        rightReservedWidth: row.comboWidth + 12

        ComboBox {
            id: combo

            anchors.right: parent.right
            anchors.rightMargin: ThemeTokens.Spacing.s3
            anchors.verticalCenter: parent.verticalCenter
            width: row.comboWidth
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
                implicitHeight: row.popupMaxHeight > 0
                    ? Math.min(listView.contentHeight, row.popupMaxHeight) + ThemeTokens.Spacing.s2
                    : listView.contentHeight + ThemeTokens.Spacing.s2
                padding: ThemeTokens.Spacing.s2

                contentItem: ListView {
                    id: listView

                    clip: true
                    implicitHeight: contentHeight
                    model: combo.popup.visible ? combo.delegateModel : null
                    currentIndex: combo.highlightedIndex
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
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

    // 数字输入行: 纯 TextField + 后缀, 不带 +/- 按钮 (用户偏好直接键盘输入).
    component SpinRow: SettingsRow {
        id: spinRow

        property int fromValue: 0
        property int toValue: 100
        property int currentValue: 0
        property string suffix: ""

        signal valueRequested(int value)

        actionText: ""
        rightReservedWidth: 110

        TextField {
            id: numField

            anchors.right: parent.right
            anchors.rightMargin: ThemeTokens.Spacing.s3
            anchors.verticalCenter: parent.verticalCenter
            width: 96
            height: 32
            horizontalAlignment: TextInput.AlignHCenter
            verticalAlignment: TextInput.AlignVCenter
            font.pixelSize: ThemeTokens.TypeScale.bodySm
            color: ThemeTokens.Palette.surfaceText
            selectByMouse: true
            inputMethodHints: Qt.ImhDigitsOnly
            validator: IntValidator { bottom: spinRow.fromValue; top: spinRow.toValue }
            text: spinRow.currentValue + spinRow.suffix
            Accessible.name: spinRow.title

            // currentValue 外部变化 (重置 / 其他入口) 时同步显示
            property int _externalValue: spinRow.currentValue
            onTextEdited: {} // 防止 binding loop, 实际同步走 _externalValue
            Connections {
                target: spinRow
                function onCurrentValueChanged() {
                    if (!numField.activeFocus)
                        numField.text = spinRow.currentValue + spinRow.suffix
                }
            }

            function commit() {
                var raw = text.replace(spinRow.suffix, "").trim()
                var num = parseInt(raw)
                if (isNaN(num))
                    num = spinRow.currentValue
                if (num < spinRow.fromValue) num = spinRow.fromValue
                if (num > spinRow.toValue) num = spinRow.toValue
                text = num + spinRow.suffix
                if (num !== spinRow.currentValue)
                    spinRow.valueRequested(num)
            }

            onEditingFinished: commit()
            Keys.onReturnPressed: numField.focus = false  // 触发 editingFinished
            Keys.onEnterPressed: numField.focus = false

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: numField.activeFocus
                    ? ThemeTokens.Palette.surface
                    : numField.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surface
                border.color: numField.activeFocus
                    ? ThemeTokens.Palette.focusRing
                    : ThemeTokens.Palette.outlineMuted
            }
        }
    }

    // 颜色选择行: 点击触发 QColorDialog (经 SettingsController.pickDesktopLyricsColor).
    component ColorRow: SettingsRow {
        id: colorRow

        property string colorValue: "#FFFFFF"

        signal pickRequested()

        actionText: ""
        rightReservedWidth: 96
        value: colorRow.colorValue.toUpperCase()

        Rectangle {
            id: swatch

            anchors.right: parent.right
            anchors.rightMargin: ThemeTokens.Spacing.s3
            anchors.verticalCenter: parent.verticalCenter
            width: 72
            height: 32
            radius: ThemeTokens.Spacing.radiusSm
            color: colorRow.colorValue
            border.color: swatchMouse.containsMouse
                ? ThemeTokens.Palette.focusRing
                : ThemeTokens.Palette.outlineMuted
            border.width: 1

            MouseArea {
                id: swatchMouse

                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: colorRow.pickRequested()
            }
        }
    }

    // 带搜索框的字体选择器: families 长达 80+ 项, 普通 ComboBox 不便定位.
    component FontPickerRow: SettingsRow {
        id: pickerRow

        property var families: []
        property string currentValue: ""
        readonly property int triggerWidth: 200
        readonly property int popupHeight: 360

        signal valueRequested(string value)

        actionText: ""
        rightReservedWidth: pickerRow.triggerWidth + 12
        value: pickerRow.currentValue.length > 0 ? pickerRow.currentValue : qsTr("系统默认")

        function refilter(query) {
            filteredModel.clear()
            filteredModel.append({ label: qsTr("系统默认"), value: "" })
            var q = String(query || "").toLowerCase().trim()
            var fams = pickerRow.families || []
            for (var i = 0; i < fams.length; ++i) {
                var name = fams[i]
                if (q.length === 0 || name.toLowerCase().indexOf(q) >= 0)
                    filteredModel.append({ label: name, value: name })
            }
        }

        ListModel {
            id: filteredModel
        }

        Button {
            id: trigger

            anchors.right: parent.right
            anchors.rightMargin: ThemeTokens.Spacing.s3
            anchors.verticalCenter: parent.verticalCenter
            width: pickerRow.triggerWidth
            height: 36
            text: pickerRow.currentValue.length > 0 ? pickerRow.currentValue : qsTr("系统默认")
            Accessible.name: pickerRow.title
            onClicked: {
                searchField.text = ""
                pickerRow.refilter("")
                fontPopup.open()
                searchField.forceActiveFocus()
            }

            contentItem: RowLayout {
                spacing: 0

                Label {
                    Layout.fillWidth: true
                    Layout.leftMargin: ThemeTokens.Spacing.s3
                    text: trigger.text
                    color: ThemeTokens.Palette.surfaceText
                    horizontalAlignment: Text.AlignLeft
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }

                Label {
                    Layout.rightMargin: ThemeTokens.Spacing.s3
                    text: fontPopup.visible ? "⌃" : "⌄"
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.body
                }
            }

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: trigger.down || fontPopup.visible
                    ? ThemeTokens.Palette.statePressed
                    : trigger.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surface
                border.color: trigger.activeFocus ? ThemeTokens.Palette.focusRing : ThemeTokens.Palette.outlineMuted
            }
        }

        Popup {
            id: fontPopup

            x: trigger.x + trigger.width - width
            y: trigger.y + trigger.height + 4
            width: trigger.width
            implicitHeight: pickerRow.popupHeight
            padding: ThemeTokens.Spacing.s2

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: ThemeTokens.Palette.surfaceElevated
                border.color: ThemeTokens.Palette.outlineMuted
            }

            contentItem: ColumnLayout {
                spacing: ThemeTokens.Spacing.s2

                TextField {
                    id: searchField

                    Layout.fillWidth: true
                    placeholderText: qsTr("搜索字体…")
                    color: ThemeTokens.Palette.surfaceText
                    placeholderTextColor: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    selectByMouse: true
                    onTextChanged: pickerRow.refilter(text)
                    Keys.onEscapePressed: fontPopup.close()

                    background: Rectangle {
                        radius: ThemeTokens.Spacing.radiusSm
                        color: ThemeTokens.Palette.surface
                        border.color: searchField.activeFocus
                            ? ThemeTokens.Palette.focusRing
                            : ThemeTokens.Palette.outlineMuted
                    }
                }

                ListView {
                    id: pickerList

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: filteredModel
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    delegate: ItemDelegate {
                        id: pickerDelegate

                        required property int index
                        required property string label
                        required property string value

                        width: ListView.view ? ListView.view.width : pickerRow.triggerWidth
                        height: 32
                        text: pickerDelegate.label
                        highlighted: pickerDelegate.value === pickerRow.currentValue
                        onClicked: {
                            pickerRow.valueRequested(pickerDelegate.value)
                            fontPopup.close()
                        }

                        contentItem: Label {
                            text: pickerDelegate.label
                            color: ThemeTokens.Palette.surfaceText
                            verticalAlignment: Text.AlignVCenter
                            font.pixelSize: ThemeTokens.TypeScale.bodySm
                            font.family: pickerDelegate.value.length > 0
                                ? pickerDelegate.value
                                : pickerDelegate.font.family
                            elide: Text.ElideRight
                        }

                        background: Rectangle {
                            radius: ThemeTokens.Spacing.radiusSm
                            color: pickerDelegate.highlighted
                                ? ThemeTokens.Palette.primaryContainer
                                : pickerDelegate.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        visible: filteredModel.count === 0
                        text: qsTr("无匹配字体")
                        color: ThemeTokens.Palette.surfaceVariantText
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                    }
                }
            }
        }
    }
}
