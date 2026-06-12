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
    property bool muted: false
    property string mode: "sequence"
    property bool loading: false
    property string errorMessage: ""
    property int queueCount: 0
    property int downloadActiveCount: 0
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
    signal muteToggleRequested()
    signal modeRequested(string mode)
    signal queueRequested()
    signal nowPlayingRequested()
    signal downloadRequested()

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

    function modeIcon(value) {
        switch (value) {
        case "repeat_all":
            return "../icons/repeat.svg"
        case "repeat_one":
            return "../icons/repeat-one.svg"
        case "shuffle":
            return "../icons/shuffle.svg"
        default:
            return "../icons/sequence.svg"
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

        // 歌曲信息 + 喜欢. 固定宽度防止布局随标题/歌手长度跳变;
        // 超长文字走 MarqueeLabel 自动横向滚动, hover 弹 ToolTip 看完整信息.
        Item {
            id: songInfo

            Layout.preferredWidth: 200
            Layout.maximumWidth: 200
            Layout.preferredHeight: 56
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("打开正在播放")
            activeFocusOnTab: root.hasSong

            TapHandler {
                enabled: root.hasSong
                onTapped: root.nowPlayingRequested()
            }

            HoverHandler {
                id: songInfoHover
                enabled: root.hasSong
            }

            AppToolTip {
                parent: songInfo
                visible: songInfoHover.hovered && root.hasSong
                text: root.songTitle + qsTr(" — ") + root.songMeta
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
                id: infoColumn
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                spacing: ThemeTokens.Spacing.s2

                MarqueeLabel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 20
                    text: root.songTitle
                    color: ThemeTokens.Palette.surfaceText
                    pixelSize: ThemeTokens.TypeScale.bodySm
                    fontWeight: ThemeTokens.TypeScale.medium
                }

                MarqueeLabel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 16
                    text: root.loading ? qsTr("正在准备播放链接") : root.songMeta
                    color: root.errorMessage.length > 0 ? ThemeTokens.Palette.error : ThemeTokens.Palette.surfaceVariantText
                    pixelSize: ThemeTokens.TypeScale.caption
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
                        iconSource: root.modeIcon(root.mode)
                        iconSize: 18
                        iconColor: root.mode !== "sequence"
                            ? ThemeTokens.Palette.primaryFg
                            : ThemeTokens.Palette.surfaceVariantText
                        enabled: root.canControl
                        onClicked: root.modeRequested(root.nextModeName(root.mode))
                    }

                    IconButton {
                        text: qsTr("上一首")
                        iconSource: "../icons/skip-back.svg"
                        iconSize: 20
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

                        contentItem: Item {
                            AppIcon {
                                anchors.centerIn: parent
                                // optical centering for the play triangle
                                anchors.horizontalCenterOffset: root.playbackState === "playing" ? 0 : 1
                                size: 22
                                source: root.playbackState === "playing"
                                    ? "../icons/pause.svg"
                                    : "../icons/play.svg"
                                color: ThemeTokens.Palette.primaryText
                            }
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
                                visible: playButton.visualFocus
                                radius: width / 2
                                color: "transparent"
                                border.color: ThemeTokens.Palette.focusRing
                                border.width: 2
                            }
                        }
                    }

                    IconButton {
                        text: qsTr("下一首")
                        iconSource: "../icons/skip-forward.svg"
                        iconSize: 20
                        iconColor: enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                        enabled: root.canControl
                        onClicked: root.nextRequested()
                    }

                    // 第 5 槽: 与左端模式键对称, 让播放键正压进度条中轴;
                    // 宽窗口纯占位, 窄窗口 (<920, 右区隐藏) 变成 "⋯" 溢出按钮收纳 词/队列/音量
                    Item {
                        Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                        Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize

                        IconButton {
                            id: overflowButton

                            anchors.fill: parent
                            visible: root.width < 920
                            text: qsTr("更多控制")
                            iconSource: "../icons/more-horizontal.svg"
                            iconSize: 20
                            iconColor: ThemeTokens.Palette.surfaceVariantText
                            onClicked: overflowPopup.open()
                            onVisibleChanged: {
                                if (!visible)
                                    overflowPopup.close()
                            }
                        }

                        // 队列非空提示点 (窄窗口下队列入口收进了溢出菜单)
                        Rectangle {
                            visible: overflowButton.visible && root.queueCount > 0
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.rightMargin: 6
                            anchors.topMargin: 8
                            width: 8
                            height: 8
                            radius: 4
                            color: ThemeTokens.Palette.primary
                        }

                        Popup {
                            id: overflowPopup

                            parent: overflowButton
                            x: parent.width - width
                            y: -height - ThemeTokens.Spacing.s2
                            width: 224
                            margins: ThemeTokens.Spacing.s2
                            padding: ThemeTokens.Spacing.s2

                            background: Rectangle {
                                radius: ThemeTokens.Spacing.radiusMd
                                color: ThemeTokens.Palette.surfaceElevated
                                border.color: ThemeTokens.Palette.outline
                            }

                            // 与歌曲行右键菜单同一套语言: 纯文字行 + 分隔线, 不带图标列
                            contentItem: ColumnLayout {
                                spacing: ThemeTokens.Spacing.s2

                                OverflowRow {
                                    Layout.fillWidth: true
                                    label: root.downloadActiveCount > 0
                                        ? qsTr("下载管理 (%1)").arg(root.downloadActiveCount > 99 ? "99+" : root.downloadActiveCount)
                                        : qsTr("下载管理")
                                    onActivated: {
                                        overflowPopup.close()
                                        root.downloadRequested()
                                    }
                                }

                                OverflowRow {
                                    Layout.fillWidth: true
                                    label: qsTr("歌词")
                                    enabled: root.hasSong
                                    onActivated: {
                                        overflowPopup.close()
                                        root.nowPlayingRequested()
                                    }
                                }

                                OverflowRow {
                                    Layout.fillWidth: true
                                    label: root.queueCount > 0
                                        ? qsTr("待播列表 (%1)").arg(root.queueCount > 99 ? "99+" : root.queueCount)
                                        : qsTr("待播列表")
                                    onActivated: {
                                        overflowPopup.close()
                                        root.queueRequested()
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 1
                                    color: ThemeTokens.Palette.outlineMuted
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ThemeTokens.Spacing.s4
                                    Layout.rightMargin: ThemeTokens.Spacing.s4
                                    spacing: ThemeTokens.Spacing.s3

                                    IconButton {
                                        text: root.muted ? qsTr("恢复音量") : qsTr("静音")
                                        iconSource: root.muted ? "../icons/volume-mute.svg" : "../icons/volume.svg"
                                        iconSize: 18
                                        iconColor: ThemeTokens.Palette.surfaceVariantText
                                        onClicked: root.muteToggleRequested()
                                    }

                                    Slider {
                                        id: overflowVolumeSlider

                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 24
                                        from: 0
                                        to: 1
                                        value: root.volume
                                        Accessible.name: qsTr("音量")
                                        onMoved: root.volumeRequested(value)

                                        background: Rectangle {
                                            x: overflowVolumeSlider.leftPadding
                                            y: overflowVolumeSlider.topPadding + overflowVolumeSlider.availableHeight / 2 - height / 2
                                            width: overflowVolumeSlider.availableWidth
                                            height: 4
                                            radius: height / 2
                                            color: ThemeTokens.Palette.outline

                                            Rectangle {
                                                width: overflowVolumeSlider.visualPosition * parent.width
                                                height: parent.height
                                                radius: parent.radius
                                                color: ThemeTokens.Palette.primary
                                                opacity: root.muted ? 0.35 : 1
                                            }
                                        }

                                        handle: Rectangle {
                                            x: overflowVolumeSlider.leftPadding + overflowVolumeSlider.visualPosition * (overflowVolumeSlider.availableWidth - width)
                                            y: overflowVolumeSlider.topPadding + overflowVolumeSlider.availableHeight / 2 - height / 2
                                            width: 12
                                            height: 12
                                            radius: width / 2
                                            color: ThemeTokens.Palette.primary
                                            opacity: root.muted ? 0.35 : 1
                                        }
                                    }
                                }
                            }
                        }
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
            Layout.preferredWidth: root.width >= 920 ? 276 : 0
            Layout.maximumWidth: root.width >= 920 ? 276 : 0
            Layout.fillHeight: true
            visible: root.width >= 920
            spacing: ThemeTokens.Spacing.s2

            Item {
                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize

                IconButton {
                    anchors.fill: parent
                    text: qsTr("下载管理")
                    iconSource: "../icons/download.svg"
                    iconSize: 18
                    iconColor: ThemeTokens.Palette.surfaceVariantText
                    onClicked: root.downloadRequested()
                }

                // 进行中任务数角标 (与待播列表角标同款)
                Rectangle {
                    visible: root.downloadActiveCount > 0
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.rightMargin: 2
                    anchors.topMargin: 4
                    width: Math.max(16, downloadBadgeLabel.implicitWidth + 8)
                    height: 16
                    radius: 8
                    color: ThemeTokens.Palette.primary

                    Label {
                        id: downloadBadgeLabel
                        anchors.centerIn: parent
                        text: root.downloadActiveCount > 99 ? "99+" : root.downloadActiveCount
                        color: ThemeTokens.Palette.primaryText
                        font.pixelSize: 10
                        font.weight: ThemeTokens.TypeScale.medium
                    }
                }
            }

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
                    iconSource: "../icons/queue.svg"
                    iconSize: 18
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

            IconButton {
                text: root.muted ? qsTr("恢复音量") : qsTr("静音")
                iconSource: root.muted ? "../icons/volume-mute.svg" : "../icons/volume.svg"
                iconSize: 18
                iconColor: ThemeTokens.Palette.surfaceVariantText
                onClicked: root.muteToggleRequested()
            }

            Slider {
                id: volumeSlider

                Layout.fillWidth: true
                Layout.preferredHeight: 18
                from: 0
                to: 1
                value: root.volume
                Accessible.name: qsTr("音量")
                // 静音时填充/手柄降权提示无声; 拖动即解除静音 (controller 侧处理)
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
                        opacity: root.muted ? 0.35 : 1
                    }
                }

                handle: Rectangle {
                    x: volumeSlider.leftPadding + volumeSlider.visualPosition * (volumeSlider.availableWidth - width)
                    y: volumeSlider.topPadding + volumeSlider.availableHeight / 2 - height / 2
                    width: 12
                    height: 12
                    radius: width / 2
                    color: ThemeTokens.Palette.primary
                    opacity: root.muted ? 0.35 : 1
                }
            }
        }
    }

    // 溢出菜单行: 纯文字 + hover 高亮, 样式对齐 SongRow 右键菜单 (窄窗口收纳 词/队列 用)
    component OverflowRow: Rectangle {
        id: overflowRow

        property string label: ""

        signal activated()

        implicitHeight: 36
        radius: ThemeTokens.Spacing.radiusSm
        color: overflowRowHover.hovered && overflowRow.enabled
            ? ThemeTokens.Palette.stateHover
            : "transparent"
        opacity: overflowRow.enabled ? 1 : 0.45

        Accessible.role: Accessible.Button
        Accessible.name: overflowRow.label
        activeFocusOnTab: true

        HoverHandler {
            id: overflowRowHover
        }

        TapHandler {
            enabled: overflowRow.enabled
            onTapped: overflowRow.activated()
        }

        Keys.onReturnPressed: {
            if (overflowRow.enabled)
                overflowRow.activated()
        }
        Keys.onSpacePressed: {
            if (overflowRow.enabled)
                overflowRow.activated()
        }

        Rectangle {
            anchors.fill: parent
            visible: overflowRow.activeFocus
            radius: parent.radius
            color: "transparent"
            border.color: ThemeTokens.Palette.focusRing
            border.width: 2
        }

        Label {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s4
            anchors.rightMargin: ThemeTokens.Spacing.s4
            verticalAlignment: Text.AlignVCenter
            text: overflowRow.label
            color: ThemeTokens.Palette.surfaceText
            font.pixelSize: ThemeTokens.TypeScale.bodySm
            elide: Text.ElideRight
        }
    }
}
