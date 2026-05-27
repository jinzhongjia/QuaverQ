import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property var currentSong: ({})
    property string playbackState: "stopped"
    property int positionMs: 0
    property int durationMs: 0
    property real volume: 0.8
    property string mode: "sequence"
    property bool loading: false
    property string errorMessage: ""
    property int queueCount: 0

    readonly property bool hasSong: currentSong
        && typeof currentSong.name === "string"
        && currentSong.name.length > 0
    readonly property string songTitle: hasSong ? currentSong.name : qsTr("尚未播放")
    readonly property string songMeta: errorMessage.length > 0
        ? errorMessage
        : hasSong ? singerText(currentSong) : qsTr("选择一首歌曲后开始")
    readonly property bool canControl: hasSong || loading

    signal playPauseRequested()
    signal nextRequested()
    signal prevRequested()
    signal seekRequested(int positionMs)
    signal volumeRequested(real volume)
    signal modeRequested(string mode)
    signal queueRequested()

    height: ThemeTokens.Spacing.playerBarHeight
    color: ThemeTokens.Palette.surface
    border.color: ThemeTokens.Palette.outline

    function formatMs(ms) {
        if (ms <= 0)
            return "0:00"
        const totalSeconds = Math.floor(ms / 1000)
        const minutes = Math.floor(totalSeconds / 60)
        const seconds = totalSeconds % 60
        return "%1:%2".arg(minutes).arg(seconds < 10 ? "0" + seconds : seconds)
    }

    function singerText(songData) {
        if (!songData)
            return ""
        if (songData.singerNames && songData.singerNames.length > 0)
            return songData.singerNames.join(" / ")
        if (songData.singers && songData.singers.length > 0)
            return songData.singers.map(function(singer) { return singer.name }).join(" / ")
        return songData.albumName || ""
    }

    function nextModeName(value) {
        switch (value) {
        case "sequence":
            return "repeat_all"
        case "repeat_all":
            return "repeat_one"
        case "repeat_one":
            return "shuffle"
        default:
            return "sequence"
        }
    }

    function modeLabel(value) {
        switch (value) {
        case "repeat_all":
            return qsTr("列表循环")
        case "repeat_one":
            return qsTr("单曲")
        case "shuffle":
            return qsTr("随机")
        default:
            return qsTr("顺序")
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s5
        anchors.rightMargin: ThemeTokens.Spacing.s5
        spacing: ThemeTokens.Spacing.s4

        Rectangle {
            Layout.preferredWidth: 52
            Layout.preferredHeight: 52
            radius: ThemeTokens.Spacing.radiusLg
            color: root.hasSong ? ThemeTokens.Palette.primaryContainer : ThemeTokens.Palette.surfaceVariant
            border.color: root.loading ? ThemeTokens.Palette.primary : "transparent"

            Label {
                anchors.centerIn: parent
                text: "♪"
                color: ThemeTokens.Palette.primary
                font.pixelSize: ThemeTokens.TypeScale.h2
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 240
            Layout.maximumWidth: 300
            spacing: ThemeTokens.Spacing.s2

            Label {
                Layout.fillWidth: true
                text: root.songTitle
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.body
                font.weight: ThemeTokens.TypeScale.medium
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: root.loading ? qsTr("正在准备播放链接") : root.songMeta
                color: root.errorMessage.length > 0 ? ThemeTokens.Palette.error : ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width, 520)
                spacing: ThemeTokens.Spacing.s2

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: ThemeTokens.Spacing.s3

                    Button {
                        id: prevButton

                        Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                        Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                        text: "‹"
                        enabled: root.canControl
                        Accessible.name: qsTr("上一首")
                        onClicked: root.prevRequested()

                        contentItem: Label {
                            text: prevButton.text
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: prevButton.enabled ? ThemeTokens.Palette.onSurface : ThemeTokens.Palette.onSurfaceVariant
                            font.pixelSize: ThemeTokens.TypeScale.h2
                        }

                        background: Rectangle {
                            radius: width / 2
                            color: prevButton.down ? ThemeTokens.Palette.statePressed : prevButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                            border.color: "transparent"
                        }
                    }

                    Button {
                        id: playButton

                        Layout.preferredWidth: 48
                        Layout.preferredHeight: 48
                        text: root.playbackState === "playing" ? "Ⅱ" : "▶"
                        enabled: root.canControl
                        Accessible.name: root.playbackState === "playing" ? qsTr("暂停") : qsTr("播放")
                        onClicked: root.playPauseRequested()

                        contentItem: Label {
                            text: playButton.text
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: playButton.enabled ? ThemeTokens.Palette.onPrimary : ThemeTokens.Palette.onSurfaceVariant
                            font.pixelSize: ThemeTokens.TypeScale.body
                        }

                        background: Rectangle {
                            radius: width / 2
                            color: playButton.enabled
                                ? (playButton.down ? ThemeTokens.Palette.primary : ThemeTokens.Palette.primary)
                                : ThemeTokens.Palette.stateDisabled
                        }
                    }

                    Button {
                        id: nextButton

                        Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                        Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                        text: "›"
                        enabled: root.canControl
                        Accessible.name: qsTr("下一首")
                        onClicked: root.nextRequested()

                        contentItem: Label {
                            text: nextButton.text
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: nextButton.enabled ? ThemeTokens.Palette.onSurface : ThemeTokens.Palette.onSurfaceVariant
                            font.pixelSize: ThemeTokens.TypeScale.h2
                        }

                        background: Rectangle {
                            radius: width / 2
                            color: nextButton.down ? ThemeTokens.Palette.statePressed : nextButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                            border.color: "transparent"
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: ThemeTokens.Spacing.s3

                    Label {
                        Layout.preferredWidth: 40
                        text: root.formatMs(root.positionMs)
                        color: ThemeTokens.Palette.onSurfaceVariant
                        horizontalAlignment: Text.AlignRight
                        font.pixelSize: ThemeTokens.TypeScale.caption
                    }

                    Slider {
                        id: progressSlider

                        Layout.fillWidth: true
                        Layout.preferredHeight: 20
                        from: 0
                        to: Math.max(1, root.durationMs)
                        enabled: root.hasSong && root.durationMs > 0
                        live: false
                        onPressedChanged: {
                            if (!pressed && enabled)
                                root.seekRequested(Math.round(value))
                        }

                        Binding on value {
                            when: !progressSlider.pressed
                            value: Math.min(root.positionMs, progressSlider.to)
                        }

                        background: Rectangle {
                            x: progressSlider.leftPadding
                            y: progressSlider.topPadding + progressSlider.availableHeight / 2 - height / 2
                            width: progressSlider.availableWidth
                            height: 4
                            radius: 2
                            color: ThemeTokens.Palette.surfaceVariant

                            Rectangle {
                                width: progressSlider.visualPosition * parent.width
                                height: parent.height
                                radius: parent.radius
                                color: progressSlider.enabled ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
                            }
                        }

                        handle: Rectangle {
                            x: progressSlider.leftPadding + progressSlider.visualPosition * (progressSlider.availableWidth - width)
                            y: progressSlider.topPadding + progressSlider.availableHeight / 2 - height / 2
                            width: 12
                            height: 12
                            radius: width / 2
                            color: progressSlider.enabled ? ThemeTokens.Palette.primary : ThemeTokens.Palette.onSurfaceVariant
                        }
                    }

                    Label {
                        Layout.preferredWidth: 40
                        text: root.durationMs > 0 ? root.formatMs(root.durationMs) : "--:--"
                        color: ThemeTokens.Palette.onSurfaceVariant
                        font.pixelSize: ThemeTokens.TypeScale.caption
                    }
                }
            }
        }

        Button {
            id: queueButton

            Layout.preferredWidth: root.queueCount > 99 ? 92 : 74
            Layout.preferredHeight: 34
            text: root.queueCount > 0 ? qsTr("待播 %1").arg(root.queueCount) : qsTr("待播")
            Accessible.name: qsTr("待播列表")
            onClicked: root.queueRequested()

            contentItem: Label {
                text: queueButton.text
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.caption
                elide: Text.ElideRight
            }

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: queueButton.down ? ThemeTokens.Palette.statePressed : queueButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                border.color: ThemeTokens.Palette.outline
            }
        }

        RowLayout {
            Layout.preferredWidth: root.width >= 920 ? 230 : 0
            Layout.maximumWidth: root.width >= 920 ? 230 : 0
            Layout.fillHeight: true
            visible: root.width >= 920
            spacing: ThemeTokens.Spacing.s3

            Button {
                id: modeButton

                Layout.preferredWidth: 88
                Layout.preferredHeight: 34
                text: root.modeLabel(root.mode)
                enabled: root.canControl
                Accessible.name: qsTr("播放模式")
                onClicked: root.modeRequested(root.nextModeName(root.mode))

                contentItem: Label {
                    text: modeButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: modeButton.enabled ? ThemeTokens.Palette.onSurface : ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: modeButton.down ? ThemeTokens.Palette.statePressed : modeButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: ThemeTokens.Palette.outline
                }
            }

            Label {
                text: qsTr("音量")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.caption
            }

            Slider {
                id: volumeSlider

                Layout.fillWidth: true
                Layout.preferredHeight: 20
                from: 0
                to: 1
                value: root.volume
                onMoved: root.volumeRequested(value)

                background: Rectangle {
                    x: volumeSlider.leftPadding
                    y: volumeSlider.topPadding + volumeSlider.availableHeight / 2 - height / 2
                    width: volumeSlider.availableWidth
                    height: 4
                    radius: 2
                    color: ThemeTokens.Palette.surfaceVariant

                    Rectangle {
                        width: volumeSlider.visualPosition * parent.width
                        height: parent.height
                        radius: parent.radius
                        color: ThemeTokens.Palette.primary
                    }
                }

                handle: Rectangle {
                    x: volumeSlider.leftPadding + volumeSlider.visualPosition * (volumeSlider.availableWidth - width)
                    y: volumeSlider.topPadding + volumeSlider.availableHeight / 2 - height / 2
                    width: 12
                    height: 12
                    radius: width / 2
                    color: ThemeTokens.Palette.primary
                }
            }
        }
    }
}
