pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property var lyricController
    property var settingsController
    property bool compact: true
    property bool hasSong: false

    // 用户可配置歌词字体: 没有 settingsController 时回退到默认值, 保证 LyricPanel 可独立预览.
    readonly property string lyricFontFamily: root.settingsController ? root.settingsController.lyricFontFamily : ""
    readonly property int lyricFontBaseSize: root.settingsController ? root.settingsController.lyricFontSize : 22
    readonly property string lyricFontWeightKey: root.settingsController ? root.settingsController.lyricFontWeight : "medium"
    readonly property bool lyricFontItalic: root.settingsController ? root.settingsController.lyricFontItalic : false

    // 基准为 active 行像素值, 其余行按视觉层次比例缩放, 对齐原 h1/body/bodySm/caption 关系.
    readonly property int lyricActiveSize: root.lyricFontBaseSize
    readonly property int lyricCompactActiveSize: Math.max(12, Math.round(root.lyricFontBaseSize * 0.73))
    readonly property int lyricInactiveSize: Math.max(12, Math.round(root.lyricFontBaseSize * 0.70))
    readonly property int lyricCompactInactiveSize: Math.max(11, Math.round(root.lyricFontBaseSize * 0.64))
    readonly property int lyricCreditSize: Math.max(11, Math.round(root.lyricFontBaseSize * 0.64))
    readonly property int lyricCompactCreditSize: Math.max(10, Math.round(root.lyricFontBaseSize * 0.59))
    readonly property int lyricTranslationSize: Math.max(11, Math.round(root.lyricFontBaseSize * 0.64))
    readonly property int lyricCompactTranslationSize: Math.max(10, Math.round(root.lyricFontBaseSize * 0.59))

    readonly property int lyricStrongWeight: root.lyricFontWeightKey === "bold"
        ? ThemeTokens.TypeScale.bold
        : (root.lyricFontWeightKey === "regular" ? ThemeTokens.TypeScale.medium : ThemeTokens.TypeScale.bold)
    readonly property int lyricNormalWeight: root.lyricFontWeightKey === "bold"
        ? ThemeTokens.TypeScale.medium
        : (root.lyricFontWeightKey === "regular" ? ThemeTokens.TypeScale.regular : ThemeTokens.TypeScale.medium)
    readonly property int lyricMutedWeight: root.lyricFontWeightKey === "bold"
        ? ThemeTokens.TypeScale.regular
        : ThemeTokens.TypeScale.regular
    readonly property int lineCount: root.lyricController ? root.lyricController.lineCount : 0
    readonly property int activeIndex: root.lyricController ? root.lyricController.activeIndex : -1
    readonly property bool loading: root.lyricController ? root.lyricController.loading : false
    readonly property string errorMessage: root.lyricController ? root.lyricController.errorMessage : ""
    readonly property color mutedLineColor: ThemeTokens.Theme.dark ? "#798292" : "#9aa3af"
    readonly property color creditLineColor: ThemeTokens.Theme.dark ? "#5b6472" : "#b4bcc8"
    readonly property color creditActiveColor: ThemeTokens.Theme.dark ? "#87909f" : "#7d8794"
    property int lastRevealedIndex: -1
    // 逐字高亮: 当前播放位置 + 已唱/未唱字色 (hex, 供 RichText <font>)
    readonly property int positionMs: root.lyricController ? root.lyricController.positionMs : 0
    readonly property string sungHex: String(ThemeTokens.Palette.primaryFg)
    readonly property string mutedHex: String(root.mutedLineColor)

    function escapeHtml(value) {
        return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    // words[0..sungCount-1] 用已唱色, 其余未唱色; sungCount 只在跨字时变 -> 不每帧重排
    function karaokeHtml(words, sungCount) {
        let html = ""
        for (let i = 0; i < words.length; ++i) {
            const color = i < sungCount ? root.sungHex : root.mutedHex
            html += '<font color="' + color + '">' + root.escapeHtml(words[i].text) + '</font>'
        }
        return html
    }

    radius: root.compact ? ThemeTokens.Spacing.radiusMd : 0
    color: root.compact ? ThemeTokens.Palette.surfaceElevated : "transparent"
    border.color: root.compact ? ThemeTokens.Palette.outlineMuted : "transparent"
    clip: true

    function isCreditLine(text) {
        const value = String(text || "").trim()
        if (value.length <= 0)
            return false
        const prefixes = [
            "词：", "词:", "作词：", "作词:",
            "曲：", "曲:", "作曲：", "作曲:",
            "编曲：", "编曲:", "制作人：", "制作人:",
            "监制：", "监制:", "录音：", "录音:",
            "混音：", "混音:", "母带：", "母带:",
            "OP：", "OP:", "SP：", "SP:",
            "发行：", "发行:", "出品：", "出品:",
            "Lyrics by", "Lyricist", "Composed by",
            "Composer", "Producer", "Written by", "Arranged by"
        ]
        for (let i = 0; i < prefixes.length; ++i) {
            if (value.indexOf(prefixes[i]) === 0)
                return true
        }
        return false
    }

    function clampedContentY(value) {
        const maxY = Math.max(0, lyricList.contentHeight - lyricList.height)
        return Math.max(0, Math.min(maxY, value))
    }

    function revealActiveLine(animated) {
        if (root.activeIndex < 0 || lyricList.count <= 0)
            return

        const activeItem = lyricList.itemAtIndex(root.activeIndex)
        if (!activeItem) {
            lyricScrollAnimation.stop()
            lyricList.positionViewAtIndex(root.activeIndex, ListView.Center)
            Qt.callLater(function() { root.revealActiveLine(false) })
            return
        }

        const targetY = root.clampedContentY(activeItem.y + activeItem.height / 2 - lyricList.height * 0.45)
        const distance = Math.abs(targetY - lyricList.contentY)
        if (!animated || distance > lyricList.height * 0.65) {
            lyricScrollAnimation.stop()
            lyricList.contentY = targetY
            return
        }

        lyricScrollAnimation.stop()
        lyricScrollAnimation.to = targetY
        lyricScrollAnimation.duration = Math.max(160, Math.min(320, distance * 1.6))
        lyricScrollAnimation.start()
    }

    function revealForActiveChange() {
        const delta = root.lastRevealedIndex < 0 ? 999 : Math.abs(root.activeIndex - root.lastRevealedIndex)
        root.lastRevealedIndex = root.activeIndex
        Qt.callLater(function() { root.revealActiveLine(delta <= 2) })
    }

    Component.onCompleted: Qt.callLater(function() { root.revealActiveLine(false) })

    onVisibleChanged: {
        if (visible)
            Qt.callLater(function() { root.revealActiveLine(false) })
    }

    NumberAnimation {
        id: lyricScrollAnimation

        target: lyricList
        property: "contentY"
        duration: 240
        easing.type: Easing.OutCubic
    }

    Connections {
        target: root.lyricController

        function onActiveIndexChanged() {
            root.revealForActiveChange()
        }

        function onLyricChanged() {
            root.lastRevealedIndex = root.activeIndex
            Qt.callLater(function() { root.revealActiveLine(false) })
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.compact ? ThemeTokens.Spacing.s4 : ThemeTokens.Spacing.s6
        spacing: root.compact ? ThemeTokens.Spacing.s3 : ThemeTokens.Spacing.s5

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: root.compact ? 32 : 40
            spacing: ThemeTokens.Spacing.s3

            Label {
                Layout.fillWidth: true
                text: qsTr("歌词")
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: root.compact ? ThemeTokens.TypeScale.body : ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.medium
                elide: Text.ElideRight
            }

            Label {
                visible: root.lyricController && root.lyricController.hasTranslation
                text: qsTr("翻译")
                color: ThemeTokens.Palette.primaryFg
                font.pixelSize: ThemeTokens.TypeScale.caption
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: lyricList

                anchors.fill: parent
                visible: root.lineCount > 0
                model: root.lyricController ? root.lyricController.lyricModel : null
                currentIndex: root.activeIndex
                clip: true
                spacing: root.compact ? 0 : ThemeTokens.Spacing.s2
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true

                delegate: Item {
                    id: lyricDelegate

                    required property int index
                    required property string lineText
                    required property string translation
                    required property var words

                    readonly property bool activeLine: lyricDelegate.index === root.activeIndex
                    readonly property bool creditLine: root.isCreditLine(lyricDelegate.lineText)
                    readonly property bool strongActive: lyricDelegate.activeLine && !lyricDelegate.creditLine
                    // 逐字仅在 full 播放页的当前行 (有逐字数据、非 credit 行) 启用
                    readonly property bool karaoke: !root.compact
                        && lyricDelegate.activeLine
                        && lyricDelegate.words.length > 0
                        && !lyricDelegate.creditLine
                    readonly property int sungCount: {
                        if (!lyricDelegate.karaoke)
                            return 0
                        let count = 0
                        const pos = root.positionMs
                        for (let i = 0; i < lyricDelegate.words.length; ++i) {
                            if (pos >= lyricDelegate.words[i].startMs)
                                count += 1
                        }
                        return count
                    }
                    readonly property int minimumRowHeight: root.compact
                        ? (lyricDelegate.strongActive ? 44 : 32)
                        : (lyricDelegate.strongActive ? 58 : 38)
                    readonly property int verticalPadding: lyricDelegate.strongActive
                        ? ThemeTokens.Spacing.s4
                        : ThemeTokens.Spacing.s3

                    width: ListView.view.width
                    height: Math.max(
                        lyricDelegate.minimumRowHeight,
                        lyricColumn.implicitHeight + lyricDelegate.verticalPadding
                    )

                    ColumnLayout {
                        id: lyricColumn

                        anchors.fill: parent
                        anchors.leftMargin: root.compact ? ThemeTokens.Spacing.s2 : ThemeTokens.Spacing.s5
                        anchors.rightMargin: root.compact ? ThemeTokens.Spacing.s2 : ThemeTokens.Spacing.s5
                        anchors.topMargin: Math.floor(lyricDelegate.verticalPadding / 2)
                        anchors.bottomMargin: Math.floor(lyricDelegate.verticalPadding / 2)
                        spacing: lyricDelegate.strongActive ? ThemeTokens.Spacing.s2 : 0

                        Label {
                            id: lyricText

                            Layout.fillWidth: true
                            visible: !lyricDelegate.karaoke
                            text: lyricDelegate.lineText
                            color: lyricDelegate.creditLine
                                ? (lyricDelegate.activeLine ? root.creditActiveColor : root.creditLineColor)
                                : (lyricDelegate.activeLine
                                    ? (root.compact ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.primaryFg)
                                    : root.mutedLineColor)
                            horizontalAlignment: root.compact ? Text.AlignLeft : Text.AlignHCenter
                            font.family: root.lyricFontFamily.length > 0 ? root.lyricFontFamily : lyricText.font.family
                            font.italic: root.lyricFontItalic
                            font.pixelSize: lyricDelegate.activeLine
                                ? (lyricDelegate.creditLine
                                    ? (root.compact ? root.lyricCompactCreditSize : root.lyricCreditSize)
                                    : (root.compact ? root.lyricCompactActiveSize : root.lyricActiveSize))
                                : (root.compact ? root.lyricCompactInactiveSize : root.lyricInactiveSize)
                            font.weight: lyricDelegate.strongActive
                                ? (root.compact ? root.lyricNormalWeight : root.lyricStrongWeight)
                                : root.lyricMutedWeight
                            wrapMode: Text.WordWrap
                            maximumLineCount: root.compact ? 2 : (lyricDelegate.strongActive ? 3 : 2)
                            elide: Text.ElideRight
                        }

                        // 逐字高亮: 当前行用 RichText 按字着色 (已唱绿/未唱灰)
                        Label {
                            id: karaokeText

                            Layout.fillWidth: true
                            visible: lyricDelegate.karaoke
                            text: lyricDelegate.karaoke
                                ? root.karaokeHtml(lyricDelegate.words, lyricDelegate.sungCount)
                                : ""
                            textFormat: Text.RichText
                            horizontalAlignment: Text.AlignHCenter
                            font.family: root.lyricFontFamily.length > 0 ? root.lyricFontFamily : karaokeText.font.family
                            font.italic: root.lyricFontItalic
                            font.pixelSize: root.compact ? root.lyricCompactActiveSize : root.lyricActiveSize
                            font.weight: root.lyricStrongWeight
                            wrapMode: Text.WordWrap
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }

                        Label {
                            id: translationText

                            Layout.fillWidth: true
                            visible: lyricDelegate.translation.length > 0
                            text: lyricDelegate.translation
                            color: lyricDelegate.strongActive ? ThemeTokens.Palette.primaryFg : root.mutedLineColor
                            horizontalAlignment: root.compact ? Text.AlignLeft : Text.AlignHCenter
                            font.family: root.lyricFontFamily.length > 0 ? root.lyricFontFamily : translationText.font.family
                            font.italic: root.lyricFontItalic
                            font.pixelSize: root.compact ? root.lyricCompactTranslationSize : root.lyricTranslationSize
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                    }
                }

                ScrollBar.vertical: ScrollBar {}
            }

            Label {
                anchors.centerIn: parent
                visible: root.lineCount === 0
                width: Math.min(parent.width, 320)
                text: root.errorMessage.length > 0
                    ? root.errorMessage
                    : root.loading
                        ? qsTr("正在同步歌词")
                        : root.hasSong ? qsTr("暂无歌词") : qsTr("播放后显示歌词")
                color: root.errorMessage.length > 0 ? ThemeTokens.Palette.error : ThemeTokens.Palette.surfaceVariantText
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                wrapMode: Text.WordWrap
            }
        }
    }
}
