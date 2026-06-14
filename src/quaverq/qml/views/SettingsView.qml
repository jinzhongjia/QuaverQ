pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import "../dialogs" as Dialogs
import "../Theme" as ThemeTokens

ScrollView {
    id: root

    property string routeName: "settings"
    property var appController
    property var settingsController
    property var downloadController
    property var audioDeviceController

    signal loginRequested()
    signal logoutRequested()

    // 设置内容最大宽度: 宽窗口下行控件不随窗口无限拉开
    readonly property int contentMaxWidth: 840
    // 右侧值控件 (下拉框 / 字体选择器) 统一宽度, 右缘对齐成一列
    readonly property int controlWidth: 200

    contentWidth: availableWidth

    Component.onCompleted: {
        if (root.settingsController)
            root.settingsController.refreshCoverCacheSize()
    }

    ColumnLayout {
        width: root.availableWidth
        spacing: ThemeTokens.Spacing.s6

        ColumnLayout {
            Layout.fillWidth: true
            Layout.maximumWidth: root.contentMaxWidth
            Layout.margins: ThemeTokens.Spacing.s6
            Layout.bottomMargin: 0
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
                destructive: root.appController && root.appController.authed
                showSeparator: false
                onActionRequested: {
                    if (root.appController && root.appController.authed) {
                        root.logoutRequested()
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
                model: [qsTr("标准"), qsTr("均衡"), qsTr("高品质")]
                values: ["standard", "balanced", "high"]
                currentValue: root.settingsController ? root.settingsController.qualityPreference : "balanced"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setQualityPreference(value)
                }
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("淡入淡出")
                value: qsTr("切歌与暂停时音量渐弱渐起")
                checked: root.settingsController ? root.settingsController.fadeEnabled : true
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setFadeEnabled(newValue)
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("淡入淡出时长")
                enabled: root.settingsController ? root.settingsController.fadeEnabled : true
                opacity: enabled ? 1 : 0.45
                model: ["0.2 s", "0.3 s", "0.5 s", "0.8 s", "1.0 s", "1.5 s", "2.0 s"]
                values: ["200", "300", "500", "800", "1000", "1500", "2000"]
                currentValue: root.settingsController ? String(root.settingsController.fadeDurationMs) : "500"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setFadeDurationMs(parseInt(value))
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("输出设备")
                model: root.audioDeviceController ? root.audioDeviceController.deviceLabels : [qsTr("跟随系统默认")]
                values: root.audioDeviceController ? root.audioDeviceController.deviceValues : [""]
                currentValue: root.settingsController ? root.settingsController.audioOutputDeviceId : ""
                showSeparator: false
                onValueRequested: function(value) {
                    if (root.audioDeviceController)
                        root.audioDeviceController.selectDevice(value)
                }
            }
        }

        SettingsSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            title: qsTr("下载")

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("下载音质")
                model: [qsTr("标准（128K）"), qsTr("高品质（320K）"), qsTr("无损（FLAC 优先）"), qsTr("臻品母带（优先）")]
                values: ["standard", "balanced", "high", "master"]
                currentValue: root.settingsController ? root.settingsController.downloadQuality : "balanced"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setDownloadQuality(value)
                }
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("下载目录")
                value: root.settingsController ? root.settingsController.downloadDirectory : ""
                actionText: qsTr("更改")
                onActionRequested: downloadDirDialog.open()
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("同时下载歌词（.lrc）")
                checked: root.settingsController ? root.settingsController.downloadWithLyric : true
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setDownloadWithLyric(newValue)
                }
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("同时下载封面（.jpg）")
                checked: root.settingsController ? root.settingsController.downloadWithCover : true
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setDownloadWithCover(newValue)
                }
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("嵌入歌曲标签")
                value: qsTr("把标题、歌手、专辑与封面写进音频文件")
                checked: root.settingsController ? root.settingsController.downloadEmbedTags : true
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setDownloadEmbedTags(newValue)
                }
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("已下载文件")
                value: qsTr("在文件管理器中查看下载目录")
                actionText: qsTr("打开")
                showSeparator: false
                onActionRequested: {
                    if (root.downloadController)
                        root.downloadController.openDownloadDirectory()
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
                model: [qsTr("跟随系统"), qsTr("浅色"), qsTr("深色")]
                values: ["system", "light", "dark"]
                currentValue: root.settingsController ? root.settingsController.themeMode : "system"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setThemeMode(value)
                }
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("减少动效")
                checked: root.settingsController ? root.settingsController.reduceMotion : false
                showSeparator: false
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setReduceMotion(newValue)
                }
            }
        }

        SettingsSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            title: qsTr("歌词")

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("显示歌词翻译")
                value: qsTr("关闭后应用内歌词、桌面悬浮歌词和 D-Bus 歌词输出都会隐藏翻译")
                checked: root.settingsController ? root.settingsController.lyricTranslationVisible : true
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setLyricTranslationVisible(newValue)
                }
            }

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
                model: [qsTr("常规"), qsTr("中等"), qsTr("加粗")]
                values: ["regular", "medium", "bold"]
                currentValue: root.settingsController ? root.settingsController.lyricFontWeight : "medium"
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setLyricFontWeight(value)
                }
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("斜体")
                checked: root.settingsController ? root.settingsController.lyricFontItalic : false
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setLyricFontItalic(newValue)
                }
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("重置歌词字体")
                value: qsTr("恢复字体 / 字号 / 字重 / 斜体到默认值")
                actionText: qsTr("重置")
                showSeparator: false
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

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("启用")
                checked: root.settingsController ? root.settingsController.desktopLyricsEnabled : true
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsEnabled(newValue)
                }
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("锁定 (鼠标穿透)")
                checked: root.settingsController ? root.settingsController.desktopLyricsLocked : true
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsLocked(newValue)
                }
            }

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("方向")
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
                suffix: qsTr("px")
                currentValue: root.settingsController ? root.settingsController.desktopLyricsFontSize : 32
                onValueRequested: function(value) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsFontSize(value)
                }
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("粗体")
                checked: root.settingsController ? root.settingsController.desktopLyricsBold : true
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsBold(newValue)
                }
            }

            SwitchRow {
                Layout.fillWidth: true
                title: qsTr("斜体")
                checked: root.settingsController ? root.settingsController.desktopLyricsItalic : false
                onToggleRequested: function(newValue) {
                    if (root.settingsController)
                        root.settingsController.setDesktopLyricsItalic(newValue)
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
                showSeparator: false
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
            title: qsTr("缓存")

            ChoiceRow {
                Layout.fillWidth: true
                title: qsTr("封面缓存上限")
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
                showSeparator: false
                onActionRequested: clearCacheDialog.open()
            }
        }

        // O5: 给 MSI/Portable 装出去的用户一个"这是什么软件"的落点
        SettingsSection {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s6
            Layout.rightMargin: ThemeTokens.Spacing.s6
            Layout.bottomMargin: ThemeTokens.Spacing.s6
            title: qsTr("关于")

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("版本")
                value: root.appController ? root.appController.appVersion : ""
            }

            SettingsRow {
                Layout.fillWidth: true
                title: qsTr("开源仓库")
                value: "github.com/jinzhongjia/QuaverQ"
                actionText: qsTr("打开")
                showSeparator: false
                onActionRequested: Qt.openUrlExternally("https://github.com/jinzhongjia/QuaverQ")
            }
        }
    }

    // 系统目录选择器: 返回 file:// URL, SettingsController.setDownloadDirectory 内归一为本地路径
    FolderDialog {
        id: downloadDirDialog

        title: qsTr("选择下载目录")
        onAccepted: {
            if (root.settingsController)
                root.settingsController.setDownloadDirectory(selectedFolder.toString())
        }
    }

    // 清缓存可逆 (封面会按需重下), 确认键用品牌绿而非 error 红
    Dialogs.ConfirmDialog {
        id: clearCacheDialog

        title: qsTr("清理封面缓存")
        message: qsTr("已缓存的封面会被删除，之后会按需重新下载。")
        confirmText: qsTr("清理")
        onAccepted: {
            if (root.settingsController)
                root.settingsController.clearCoverCache()
        }
    }

    // 分区: 小号灰标题在卡片外, 卡片只装行 (压缩单行分区的视觉体量)
    component SettingsSection: ColumnLayout {
        id: section

        property string title: ""
        default property alias content: sectionColumn.data

        Layout.maximumWidth: root.contentMaxWidth
        spacing: ThemeTokens.Spacing.s3

        Label {
            Layout.fillWidth: true
            Layout.leftMargin: ThemeTokens.Spacing.s3
            text: section.title
            color: ThemeTokens.Palette.surfaceVariantText
            font.pixelSize: ThemeTokens.TypeScale.bodySm
            font.weight: ThemeTokens.TypeScale.medium
            elide: Text.ElideRight
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: sectionColumn.implicitHeight + ThemeTokens.Spacing.s2 * 2
            radius: ThemeTokens.Spacing.radiusLg
            color: ThemeTokens.Palette.surfaceElevated
            border.color: ThemeTokens.Palette.outlineMuted

            ColumnLayout {
                id: sectionColumn

                anchors.fill: parent
                anchors.leftMargin: ThemeTokens.Spacing.s3
                anchors.rightMargin: ThemeTokens.Spacing.s3
                anchors.topMargin: ThemeTokens.Spacing.s2
                anchors.bottomMargin: ThemeTokens.Spacing.s2
                // 行间 0 间距让 SettingsRow 的 1px 底分隔线直接相邻成连续列表
                spacing: 0
            }
        }
    }

    // 行容器: 左标题(+可选说明) + 右控件区, 行间 1px 内缩分隔线
    component SettingsRow: Item {
        id: row

        property string title: ""
        property string value: ""
        property string actionText: ""
        // 危险动作 (如退出登录) 文字用 error 色
        property bool destructive: false
        // 仅供浮层控件 (下拉 / 开关 / 色板) 占位; 行内动作按钮在布局流里, 不需要预留,
        // 这样按钮右缘与其他值控件收在同一条线上
        property int rightReservedWidth: 0
        property bool showSeparator: true

        signal actionRequested()

        implicitHeight: 52

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
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
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
                Layout.preferredHeight: 36
                visible: row.actionText.length > 0
                text: row.actionText
                Accessible.name: text
                onClicked: row.actionRequested()

                contentItem: Label {
                    text: actionButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: row.destructive ? ThemeTokens.Palette.error : ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: actionButton.down
                        ? ThemeTokens.Palette.statePressed
                        : actionButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: ThemeTokens.Palette.outlineMuted

                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        visible: actionButton.visualFocus
                        color: "transparent"
                        border.color: ThemeTokens.Palette.focusRing
                        border.width: 2
                    }
                }
            }
        }

        // 1px 内缩底分隔线 (最后一行 showSeparator: false)
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: ThemeTokens.Spacing.s3
            anchors.rightMargin: ThemeTokens.Spacing.s3
            height: 1
            color: ThemeTokens.Palette.outlineMuted
            opacity: 0.6
            visible: row.showSeparator
        }
    }

    // 开关行: 二元设置用 Switch, 不用下拉框
    component SwitchRow: SettingsRow {
        id: switchRow

        property bool checked: false

        signal toggleRequested(bool newValue)

        actionText: ""
        rightReservedWidth: 56

        Switch {
            id: toggle

            anchors.right: parent.right
            anchors.rightMargin: ThemeTokens.Spacing.s3
            anchors.verticalCenter: parent.verticalCenter
            width: 40
            height: 22
            text: ""
            Accessible.name: switchRow.title
            onToggled: switchRow.toggleRequested(toggle.checked)

            // 显式 Binding: 用户拨动后外部值变化 (如重置按钮) 仍能同步回来
            Binding on checked {
                value: switchRow.checked
            }

            indicator: Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: toggle.checked ? ThemeTokens.Palette.primary : ThemeTokens.Palette.surfaceContainerHigh
                border.color: toggle.checked ? ThemeTokens.Palette.primary : ThemeTokens.Palette.outline

                Behavior on color {
                    ColorAnimation {
                        duration: ThemeTokens.Motion.durFast
                    }
                }

                Rectangle {
                    x: toggle.checked ? parent.width - width - 3 : 3
                    anchors.verticalCenter: parent.verticalCenter
                    width: 16
                    height: 16
                    radius: width / 2
                    color: ThemeTokens.Palette.primaryText

                    Behavior on x {
                        NumberAnimation {
                            duration: ThemeTokens.Motion.durFast
                            easing.type: ThemeTokens.Motion.easeOut
                        }
                    }
                }

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -3
                    radius: height / 2
                    visible: toggle.visualFocus
                    color: "transparent"
                    border.color: ThemeTokens.Palette.focusRing
                    border.width: 2
                }
            }

            contentItem: Item {}
        }
    }

    component ChoiceRow: SettingsRow {
        id: row

        property var model: []
        property var values: []
        property string currentValue: ""
        property int popupMaxHeight: 0  // >0 时给下拉列表设上限, 避免长列表撑出窗口
        property int comboWidth: root.controlWidth

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
            Accessible.name: row.title
            onActivated: function(index) {
                if (index >= 0 && index < row.values.length)
                    row.valueRequested(row.values[index])
            }

            // 显式 Binding: 用户选过一次后外部值变化 (如重置按钮) 仍能同步回来
            Binding on currentIndex {
                value: Math.max(0, row.values.indexOf(row.currentValue))
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
                    : combo.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant
                border.color: combo.visualFocus ? ThemeTokens.Palette.focusRing : ThemeTokens.Palette.outlineMuted
            }

            popup: Popup {
                y: combo.height + 4
                width: combo.width
                // 设正边距让 Popup 在窗口内自动收高 / 上移, 而不是被窗口边缘裁掉
                topMargin: ThemeTokens.Spacing.s3
                bottomMargin: ThemeTokens.Spacing.s3
                // 高度 = 内容 + 上下 padding 两边; 只加一边会让列表永远差 8px
                // 形成隐形可滚动区, ComboBox 悬停自动滚入视野时菜单就会"动一下"
                implicitHeight: (row.popupMaxHeight > 0
                    ? Math.min(listView.contentHeight, row.popupMaxHeight)
                    : listView.contentHeight) + ThemeTokens.Spacing.s2 * 2
                padding: ThemeTokens.Spacing.s2
                // 打开时把当前选中项滚入视野 (列表可滚动时)
                onOpened: Qt.callLater(function() {
                    if (combo.currentIndex >= 0)
                        listView.positionViewAtIndex(combo.currentIndex, ListView.Center)
                })

                contentItem: ListView {
                    id: listView

                    clip: true
                    implicitHeight: contentHeight
                    model: combo.popup.visible ? combo.delegateModel : null
                    // 故意不绑 currentIndex / 不让 ListView 跟随高亮滚动:
                    // hover 改变 highlightedIndex 时 ensure-visible 会和鼠标位置互相打架,
                    // 表现为菜单来回滚动. 高亮视觉由 delegate 按 combo.highlightedIndex 自绘.
                    // 已知取舍: 鼠标悬停在列表上时键盘上下键不触发滚动 —— 当前所有下拉都
                    // 不设 popupMaxHeight (列表全高展开, 无滚动区), 该组合不可达; 若未来
                    // 启用 popupMaxHeight 出现可滚动下拉, 需区分键盘/悬停来源再放开.
                    highlightFollowsCurrentItem: false
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    HoverHandler {
                        id: listHover
                    }

                    Connections {
                        target: combo
                        // 键盘上下导航时仍跟随滚动; 鼠标悬停 (listHover.hovered) 来源的高亮变化不滚
                        function onHighlightedIndexChanged() {
                            if (!listHover.hovered && combo.highlightedIndex >= 0)
                                listView.positionViewAtIndex(combo.highlightedIndex, ListView.Contain)
                        }
                    }
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

    // 数字输入行: TextField + 框外后缀, 不带 +/- 按钮 (用户偏好直接键盘输入)
    component SpinRow: SettingsRow {
        id: spinRow

        property int fromValue: 0
        property int toValue: 100
        property int currentValue: 0
        property string suffix: ""

        signal valueRequested(int value)

        actionText: ""
        rightReservedWidth: 110

        RowLayout {
            anchors.right: parent.right
            anchors.rightMargin: ThemeTokens.Spacing.s3
            anchors.verticalCenter: parent.verticalCenter
            spacing: ThemeTokens.Spacing.s2

            TextField {
                id: numField

                Layout.preferredWidth: 64
                Layout.preferredHeight: 32
                horizontalAlignment: TextInput.AlignHCenter
                verticalAlignment: TextInput.AlignVCenter
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                color: ThemeTokens.Palette.surfaceText
                selectByMouse: true
                inputMethodHints: Qt.ImhDigitsOnly
                validator: IntValidator { bottom: spinRow.fromValue; top: spinRow.toValue }
                text: String(spinRow.currentValue)
                Accessible.name: spinRow.title

                // currentValue 外部变化 (重置 / 其他入口) 时同步显示
                Connections {
                    target: spinRow
                    function onCurrentValueChanged() {
                        if (!numField.activeFocus)
                            numField.text = String(spinRow.currentValue)
                    }
                }

                function commit() {
                    var num = parseInt(text.trim())
                    if (isNaN(num))
                        num = spinRow.currentValue
                    if (num < spinRow.fromValue) num = spinRow.fromValue
                    if (num > spinRow.toValue) num = spinRow.toValue
                    text = String(num)
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
                        : numField.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant
                    border.color: numField.activeFocus
                        ? ThemeTokens.Palette.focusRing
                        : ThemeTokens.Palette.outlineMuted
                }
            }

            Label {
                text: spinRow.suffix
                visible: text.length > 0
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
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
        readonly property int triggerWidth: root.controlWidth
        readonly property int popupHeight: 360

        signal valueRequested(string value)

        actionText: ""
        rightReservedWidth: pickerRow.triggerWidth + 12

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
                    : trigger.hovered ? ThemeTokens.Palette.stateHover : ThemeTokens.Palette.surfaceVariant
                border.color: trigger.visualFocus ? ThemeTokens.Palette.focusRing : ThemeTokens.Palette.outlineMuted
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
