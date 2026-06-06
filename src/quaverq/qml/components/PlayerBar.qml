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
    property int bottomCornerRadius: 0
    property var libraryController
    property var coverController

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
    signal nowPlayingRequested()

    height: ThemeTokens.Spacing.playerBarHeight
    radius: root.bottomCornerRadius
    antialiasing: true
    color: ThemeTokens.Palette.surfaceElevated

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 1
        color: ThemeTokens.Palette.outlineMuted
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: root.bottomCornerRadius
        visible: root.bottomCornerRadius > 0
        color: root.color
    }

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
            return qsTr("单曲循环")
        case "shuffle":
            return qsTr("随机播放")
        default:
            return qsTr("顺序播放")
        }
    }

    function modeGlyph(value) {
        switch (value) {
        case "repeat_all":
            return "↻"
        case "repeat_one":
            return "①"
        case "shuffle":
            return "⇋"
        default:
            return "⇄"
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.topMargin: root.bottomCornerRadius
        anchors.leftMargin: ThemeTokens.Spacing.s5
        anchors.rightMargin: ThemeTokens.Spacing.s5
        spacing: ThemeTokens.Spacing.s4

        // ---------------------------------------------------------- LEFT zone
        AlbumArt {
            id: coverArt

            Layout.preferredWidth: 56
            Layout.preferredHeight: 56
            active: root.hasSong
            coverUrl: root.hasSong && root.currentSong.coverUrl ? root.currentSong.coverUrl : ""
            coverController: root.coverController
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("打开正在播放")
            activeFocusOnTab: root.hasSong

            TapHandler {
                enabled: root.hasSong
                onTapped: root.nowPlayingRequested()
            }

            Keys.onReturnPressed: { if (root.hasSong) root.nowPlayingRequested() }
            Keys.onSpacePressed: { if (root.hasSong) root.nowPlayingRequested() }

            Rectangle {
                anchors.fill: parent
                visible: coverArt.activeFocus
                radius: coverArt.hasImage ? coverArt.coverRadius : coverArt.placeholderRadius
                color: "transparent"
                border.color: ThemeTokens.Palette.focusRing
                border.width: 2
            }
        }

        Item {
            Layout.preferredWidth: 200
            Layout.maximumWidth: 280
            Layout.preferredHeight: 56
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("打开正在播放")
            activeFocusOnTab: root.hasSong

            TapHandler {
                enabled: root.hasSong
                onTapped: root.nowPlayingRequested()
            }

            Keys.onReturnPressed: { if (root.hasSong) root.nowPlayingRequested() }
            Keys.onSpacePressed: { if (root.hasSong) root.nowPlayingRequested() }

            Rectangle {
                anchors.fill: parent
                visible: parent.activeFocus
                radius: ThemeTokens.Spacing.radiusMd
                color: "transparent"
                border.color: ThemeTokens.Palette.focusRing
                border.width: 2
                z: 1
            }

            ColumnLayout {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: root.songTitle
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.loading ? qsTr("正在准备播放链接") : root.songMeta
                    color: root.errorMessage.length > 0 ? ThemeTokens.Palette.error : ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }
        }

        LikeButton {
            Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
            Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
            libraryController: root.libraryController
            song: root.currentSong
        }

        // ---------------------------------------------------------- CENTER zone
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width, 560)
                spacing: ThemeTokens.Spacing.s2

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: ThemeTokens.Spacing.s4

                    IconButton {
                        text: root.modeLabel(root.mode)
                        iconText: root.modeGlyph(root.mode)
                        iconSize: ThemeTokens.TypeScale.body
                        iconColor: root.mode !== "sequence"
                            ? ThemeTokens.Palette.primary
                            : ThemeTokens.Palette.surfaceVariantText
                        enabled: root.canControl
                        onClicked: root.modeRequested(root.nextModeName(root.mode))
                    }

                    IconButton {
                        text: qsTr("上一首")
                        iconText: "◂◂"
                        iconSize: ThemeTokens.TypeScale.h2
                        iconColor: enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                        enabled: root.canControl
                        onClicked: root.prevRequested()
                    }

                    Button {
                        id: playButton

                        Layout.preferredWidth: 52
                        Layout.preferredHeight: 52
                        enabled: root.canControl
                        Accessible.name: root.playbackState === "playing" ? qsTr("暂停") : qsTr("播放")
                        onClicked: root.playPauseRequested()

                        contentItem: Label {
                            text: root.playbackState === "playing" ? "❚❚" : "▶"
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: ThemeTokens.Palette.primaryText
                            font.pixelSize: ThemeTokens.TypeScale.h2
                            // optical centering for the play triangle
                            leftPadding: root.playbackState === "playing" ? 0 : 3
                        }

                        background: Rectangle {
                            radius: width / 2
                            color: !playButton.enabled
                                ? ThemeTokens.Palette.stateDisabled
                                : playButton.down ? ThemeTokens.Palette.primaryActive
                                : playButton.hovered ? ThemeTokens.Palette.primaryHover
                                : ThemeTokens.Palette.primary

                            Rectangle {
                                anchors.fill: parent
                                visible: playButton.activeFocus
                                radius: width / 2
                                color: "transparent"
                                border.color: ThemeTokens.Palette.focusRing
                                border.width: 2
                            }
                        }
                    }

                    IconButton {
                        text: qsTr("下一首")
                        iconText: "▸▸"
                        iconSize: ThemeTokens.TypeScale.h2
                        iconColor: enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                        enabled: root.canControl
                        onClicked: root.nextRequested()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: ThemeTokens.Spacing.s3

                    Label {
                        Layout.preferredWidth: 40
                        text: root.formatMs(root.positionMs)
                        color: ThemeTokens.Palette.surfaceVariantText
                        horizontalAlignment: Text.AlignRight
                        font.pixelSize: ThemeTokens.TypeScale.caption
                    }

                    Slider {
                        id: progressSlider

                        Layout.fillWidth: true
                        Layout.preferredHeight: 18
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
                            radius: height / 2
                            color: ThemeTokens.Palette.outline

                            Rectangle {
                                width: progressSlider.visualPosition * parent.width
                                height: parent.height
                                radius: parent.radius
                                color: progressSlider.enabled ? ThemeTokens.Palette.primary : ThemeTokens.Palette.surfaceVariantText
                            }
                        }

                        handle: Rectangle {
                            x: progressSlider.leftPadding + progressSlider.visualPosition * (progressSlider.availableWidth - width)
                            y: progressSlider.topPadding + progressSlider.availableHeight / 2 - height / 2
                            width: 12
                            height: 12
                            radius: width / 2
                            color: progressSlider.enabled ? ThemeTokens.Palette.primary : ThemeTokens.Palette.surfaceVariantText
                            visible: progressSlider.enabled
                        }
                    }

                    Label {
                        Layout.preferredWidth: 40
                        text: root.durationMs > 0 ? root.formatMs(root.durationMs) : "--:--"
                        color: ThemeTokens.Palette.surfaceVariantText
                        font.pixelSize: ThemeTokens.TypeScale.caption
                    }
                }
            }
        }

        // ---------------------------------------------------------- RIGHT zone
        RowLayout {
            Layout.preferredWidth: root.width >= 920 ? 232 : 0
            Layout.maximumWidth: root.width >= 920 ? 232 : 0
            Layout.fillHeight: true
            visible: root.width >= 920
            spacing: ThemeTokens.Spacing.s2

            IconButton {
                text: qsTr("歌词")
                iconText: "词"
                iconSize: ThemeTokens.TypeScale.bodySm
                iconColor: ThemeTokens.Palette.surfaceVariantText
                enabled: root.hasSong
                onClicked: root.nowPlayingRequested()
            }

            Item {
                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize

                IconButton {
                    id: queueButton
                    anchors.fill: parent
                    text: qsTr("待播列表")
                    iconText: "☰"
                    iconSize: ThemeTokens.TypeScale.body
                    iconColor: ThemeTokens.Palette.surfaceVariantText
                    onClicked: root.queueRequested()
                }

                Rectangle {
                    visible: root.queueCount > 0
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.rightMargin: 2
                    anchors.topMargin: 4
                    width: Math.max(16, badgeLabel.implicitWidth + 8)
                    height: 16
                    radius: 8
                    color: ThemeTokens.Palette.primary

                    Label {
                        id: badgeLabel
                        anchors.centerIn: parent
                        text: root.queueCount > 99 ? "99+" : root.queueCount
                        color: ThemeTokens.Palette.primaryText
                        font.pixelSize: 10
                        font.weight: ThemeTokens.TypeScale.medium
                    }
                }
            }

            Label {
                text: "♪"
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
            }

            Slider {
                id: volumeSlider

                Layout.fillWidth: true
                Layout.preferredHeight: 18
                from: 0
                to: 1
                value: root.volume
                onMoved: root.volumeRequested(value)

                background: Rectangle {
                    x: volumeSlider.leftPadding
                    y: volumeSlider.topPadding + volumeSlider.availableHeight / 2 - height / 2
                    width: volumeSlider.availableWidth
                    height: 4
                    radius: height / 2
                    color: ThemeTokens.Palette.outline

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
