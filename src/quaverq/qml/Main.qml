pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "components" as Components
import "dialogs" as Dialogs
import "panels" as Panels
import "Theme" as ThemeTokens
import "views" as Views

ApplicationWindow {
    id: root

    readonly property int windowShadowMarginBase: 2
    readonly property bool maximizedWindow: root.visibility === Window.Maximized || root.visibility === Window.FullScreen
    readonly property int windowShadowMargin: root.maximizedWindow ? 0 : root.windowShadowMarginBase
    readonly property int windowCornerRadius: root.maximizedWindow ? 0 : ThemeTokens.Spacing.radiusSm
    readonly property int resizeHandleSize: 8

    width: ThemeTokens.Spacing.windowWidth + root.windowShadowMarginBase * 2
    height: ThemeTokens.Spacing.windowHeight + root.windowShadowMarginBase * 2
    minimumWidth: ThemeTokens.Spacing.minWindowWidth + root.windowShadowMarginBase * 2
    minimumHeight: ThemeTokens.Spacing.minWindowHeight + root.windowShadowMarginBase * 2
    visible: true
    title: qsTr("QuaverQ")
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"
    // ContextProperty 由 Python (__main__.py setContextProperty) 注入, qmllint 视角下不可见;
    // 此处收拢为 root 的 readonly property var, 子组件经 root.<name> 走 qualified 访问.
    // qmllint disable unqualified
    readonly property var appController: AppController
    readonly property var coverController: CoverController
    readonly property var homeController: HomeController
    readonly property var detailControllerFactory: DetailControllerFactory
    readonly property var songDetailController: SongDetailController
    readonly property var serviceController: ServiceController
    readonly property var libraryController: LibraryController
    readonly property var lyricController: LyricController
    readonly property var playerController: PlayerController
    readonly property var settingsController: SettingsController
    readonly property var downloadController: DownloadController
    readonly property var audioDeviceController: AudioDeviceController
    readonly property var systemTheme: SystemTheme
    // qmllint enable unqualified
    // 托盘可用时由 Python 置 true: 关闭改为隐藏到托盘而非退出
    property bool closeToTray: false
    property bool queuePanelOpen: false
    // 正在播放沉浸浮层 (盖侧栏 + 内容区, 不进导航栈): 开/关语义, 收起后精确还原打开前的位置
    property bool nowPlayingOpen: false
    property string currentRoute: "home"
    property string currentTopRoute: "home"
    property string currentDetailTitle: ""
    property int pendingSeekMs: -1
    property int pendingSeekAttempts: 0
    property bool muteForPendingSeek: false
    readonly property int pendingSeekToleranceMs: 1000
    readonly property int pendingSeekMaxAttempts: 60
    // 切歌淡入淡出 (issue #11): fadeFactor 乘进 AudioOutput.volume, 0↔1 由两个
    // NumberAnimation 驱动. 音频包络不是视觉动效, 刻意不接 Motion.reduceMotion.
    property real fadeFactor: 1
    // Python 协调的切歌淡出进行中 (fadeOutRequested → 新源挂载): 尾部淡出的
    // 自愈淡入在此窗口内不得抢跑
    property bool fadeSwitchActive: false
    // 暂停渐变: 淡出动画播完后才真正 pause; 恢复播放时清标志防"刚恢复又被按下"
    property bool pauseFadePending: false

    function fadeMs() {
        return root.settingsController && root.settingsController.fadeEnabled
            ? root.settingsController.fadeDurationMs : 0
    }

    function startFadeOut(ms) {
        fadeInAnim.stop()
        fadeOutAnim.duration = ms
        fadeOutAnim.restart()
    }

    function startFadeIn(ms) {
        // 先清暂停渐变标志再 stop(): stop 会同步触发 fadeOutAnim.onStopped,
        // 不清会把刚恢复的播放又 pause 下去
        root.pauseFadePending = false
        fadeOutAnim.stop()
        root.fadeSwitchActive = false
        fadeInAnim.duration = ms
        fadeInAnim.restart()
    }

    // EOS 尾部淡出: 自然播完前 fadeMs 内渐弱 (切歌淡出由 Python fadeOutRequested
    // 协调, 不在此处); seek 离开尾部窗口时自愈淡回.
    function applyTailFade() {
        const ms = root.fadeMs()
        if (ms <= 0 || root.fadeSwitchActive)
            return
        if (mediaPlayer.playbackState !== MediaPlayer.PlayingState || mediaPlayer.duration <= 0)
            return
        const remaining = mediaPlayer.duration - mediaPlayer.position
        if (remaining <= ms) {
            if (!fadeOutAnim.running && root.fadeFactor > 0)
                root.startFadeOut(Math.max(50, Math.min(ms, remaining)))
        } else if (root.fadeFactor < 1 && !fadeInAnim.running && !root.pauseFadePending) {
            // 不要求 !fadeOutAnim.running: 尾部淡出途中用户向前 seek 离开末尾窗口时,
            // startFadeIn 会停掉正在跑的淡出并立即淡回, 避免"先继续静音再恢复" (review 发现)
            root.startFadeIn(ms)
        }
    }

    onClosing: function(close) {
        if (root.closeToTray) {
            close.accepted = false
            root.hide()
        }
    }

    Binding {
        target: ThemeTokens.Theme
        property: "mode"
        value: root.settingsController ? root.settingsController.themeMode : ThemeTokens.Theme.systemMode
    }

    Binding {
        target: ThemeTokens.Theme
        property: "systemDark"
        value: root.systemTheme ? root.systemTheme.dark : false
        when: root.systemTheme !== null
    }

    Binding {
        target: ThemeTokens.Motion
        property: "reduceMotion"
        value: root.settingsController ? root.settingsController.reduceMotion : false
    }

    function routeTitle(route) {
        switch (route) {
        case "home":
            return qsTr("发现")
        case "library":
            return qsTr("资料库")
        case "settings":
            return qsTr("设置")
        case "downloads":
            return qsTr("下载")
        case "detail":
            return root.currentDetailTitle.length > 0 ? root.currentDetailTitle : qsTr("详情")
        default:
            return qsTr("搜索")
        }
    }

    function resetContent(component, route) {
        root.queuePanelOpen = false
        root.currentDetailTitle = ""
        // replace(null, ...) = 整栈替换: 走 replaceEnter/Exit 的 120ms 交叉淡入 (O2);
        // reduceMotion 时 durFast=0, 行为等价原 StackView.Immediate
        contentStack.replace(null, component, {})
        root.currentRoute = route
        root.currentTopRoute = route
    }

    function navigate(route) {
        // 任何导航动作先收起正在播放浮层, 避免"结果页在浮层底下"的怪态
        root.nowPlayingOpen = false
        root.releaseTextFocus()
        if (route === root.currentRoute && contentStack.depth === 1)
            return
        if (route === "home") {
            root.resetContent(homePageComponent, "home")
        } else if (route === "library") {
            root.resetContent(libraryPageComponent, "library")
        } else if (route === "settings") {
            root.resetContent(settingsPageComponent, "settings")
        } else if (route === "downloads") {
            root.resetContent(downloadsPageComponent, "downloads")
        } else {
            root.resetContent(searchPageComponent, "search")
        }
    }

    // 正在播放 = 沉浸浮层: 不进导航栈, 打开是"展开"、收起是"还原",
    // 底下的路由 / 滚动位置 / 侧栏选中态全程不动. 已打开时再次触发 (再点播放栏封面) 视为收起.
    function openNowPlaying() {
        if (root.nowPlayingOpen) {
            root.closeNowPlaying()
            return
        }
        root.queuePanelOpen = false
        root.releaseTextFocus()
        // 闩锁必须先置位: Behavior 的 enabled 依赖它, 否则首开没有滑入动画
        nowPlayingLoader.everOpened = true
        root.nowPlayingOpen = true
    }

    function closeNowPlaying() {
        if (!root.nowPlayingOpen)
            return
        root.nowPlayingOpen = false
        // 焦点还给全局快捷键宿主, 防止键盘焦点滞留在已隐藏的浮层里 (键盘陷阱)
        shortcutFocusSink.forceActiveFocus()
    }

    function pushDetail(kind, detailId, title, subtitle, coverUrl) {
        root.nowPlayingOpen = false
        root.queuePanelOpen = false
        root.releaseTextFocus()
        contentStack.push(detailPageComponent, {
            detailKind: kind,
            detailId: detailId,
            detailTitle: title,
            detailSubtitle: subtitle,
            // 入口卡片封面透传: 头图即刻显示, 详情接口的封面到了再升级 (B1)
            detailCoverUrl: coverUrl || ""
        })
        root.currentDetailTitle = title
        root.currentRoute = "detail"
    }

    function goBack() {
        if (contentStack.depth <= 1)
            return
        contentStack.pop()
        root.currentDetailTitle = ""
        // pop 后仍在栈上 (>1) 说明落点是 push 进来的详情页; 否则回到顶层路由
        root.currentRoute = contentStack.depth > 1
            ? "detail"
            : (root.currentTopRoute.length > 0 ? root.currentTopRoute : "home")
    }

    function searchAndOpen(keyword) {
        searchField.text = keyword
        root.navigate("search")
        root.releaseTextFocus()
        if (root.serviceController)
            root.serviceController.search(keyword)
    }

    function releaseTextFocus() {
        searchField.releaseInputFocus()
        shortcutFocusSink.forceActiveFocus()
    }

    function toggleMaximized() {
        if (root.visibility === Window.Maximized) {
            root.visibility = Window.Windowed
        } else {
            root.visibility = Window.Maximized
        }
    }

    function clearPendingSeek() {
        root.pendingSeekMs = -1
        root.pendingSeekAttempts = 0
        root.muteForPendingSeek = false
        resumeSeekTimer.stop()
    }

    function pendingSeekReached() {
        return root.pendingSeekMs < 0
            || mediaPlayer.position >= Math.max(0, root.pendingSeekMs - root.pendingSeekToleranceMs)
    }

    function beginPendingSeek(positionMs) {
        const target = Math.max(0, positionMs)
        if (target <= 0) {
            root.clearPendingSeek()
            mediaPlayer.setPosition(0)
            return
        }
        root.pendingSeekMs = target
        root.pendingSeekAttempts = 0
        resumeSeekTimer.restart()
        root.applyPendingSeek()
    }

    function applyPendingSeek() {
        if (root.pendingSeekMs < 0)
            return false
        const target = root.pendingSeekMs
        root.pendingSeekAttempts += 1
        if (mediaPlayer.duration <= 0 && !mediaPlayer.seekable) {
            if (root.pendingSeekAttempts >= root.pendingSeekMaxAttempts) {
                root.clearPendingSeek()
                if (root.playerController)
                    root.playerController.updatePosition(mediaPlayer.position)
                return true
            }
            return false
        }
        mediaPlayer.setPosition(target)
        if (root.pendingSeekReached() || root.pendingSeekAttempts >= root.pendingSeekMaxAttempts) {
            root.clearPendingSeek()
            if (root.playerController)
                root.playerController.updatePosition(mediaPlayer.position)
            return true
        }
        if (!resumeSeekTimer.running)
            resumeSeekTimer.start()
        return false
    }

    Timer {
        id: resumeSeekTimer

        interval: 120
        repeat: true
        onTriggered: root.applyPendingSeek()
    }

    NumberAnimation {
        id: fadeOutAnim

        target: root
        property: "fadeFactor"
        to: 0
        easing.type: Easing.OutQuad
        onStopped: {
            // 暂停渐变: 渐弱播完才真 pause (startFadeIn 接管 / 切歌淡出时已清标志)
            if (root.pauseFadePending) {
                root.pauseFadePending = false
                mediaPlayer.pause()
            }
        }
    }

    NumberAnimation {
        id: fadeInAnim

        target: root
        property: "fadeFactor"
        to: 1
        easing.type: Easing.InQuad
    }

    AudioOutput {
        id: audioOutput

        volume: (root.muteForPendingSeek ? 0 : (root.playerController ? root.playerController.volume : 0.8)) * root.fadeFactor
        muted: root.playerController ? root.playerController.muted : false
        // 设备路由交给 Python 托管 (枚举 / 持久化匹配 / 热插拔软回退), 见 AudioDeviceController
        Component.onCompleted: {
            if (root.audioDeviceController)
                root.audioDeviceController.attachAudioOutput(audioOutput)
        }
    }

    MediaPlayer {
        id: mediaPlayer

        audioOutput: audioOutput
        source: root.playerController ? root.playerController.sourceUrl : ""

        onSourceChanged: {
            if (String(source).length <= 0)
                return
            // 新源挂载: fade 开启时从静音起播 (转入 PlayingState 后淡入),
            // 顺带清掉上一首尾部淡出/暂停渐变的残留状态
            root.pauseFadePending = false
            fadeOutAnim.stop()
            fadeInAnim.stop()
            root.fadeFactor = root.fadeMs() > 0 ? 0 : 1
        }
        onPositionChanged: {
            root.applyTailFade()
            if (root.pendingSeekMs >= 0) {
                if (root.pendingSeekReached()) {
                    root.clearPendingSeek()
                    if (root.playerController)
                        root.playerController.updatePosition(mediaPlayer.position)
                }
                return
            }
            if (root.playerController)
                root.playerController.updatePosition(mediaPlayer.position)
        }
        onDurationChanged: {
            if (root.playerController)
                root.playerController.updateDuration(mediaPlayer.duration)
            root.applyPendingSeek()
        }
        onSeekableChanged: root.applyPendingSeek()
        onPlaybackStateChanged: {
            if (playbackState === MediaPlayer.PlayingState) {
                if (root.fadeMs() > 0 && root.fadeFactor < 1) {
                    root.startFadeIn(root.fadeMs())
                } else if (root.fadeMs() <= 0 && root.fadeFactor < 1) {
                    // fade 设置中途被关掉的自愈: 音量直接回满
                    fadeOutAnim.stop()
                    fadeInAnim.stop()
                    root.fadeFactor = 1
                }
            }
            if (root.playerController) {
                if (playbackState === MediaPlayer.PlayingState) {
                    root.playerController.updatePlaybackState("playing")
                } else if (playbackState === MediaPlayer.PausedState) {
                    root.playerController.updatePlaybackState("paused")
                } else {
                    root.playerController.updatePlaybackState("stopped")
                }
            }
        }
        onMediaStatusChanged: {
            root.applyPendingSeek()
            if (root.playerController && mediaStatus === MediaPlayer.EndOfMedia)
                root.playerController.handleEndOfMedia()
        }
        onErrorOccurred: function(error, errorString) {
            if (root.playerController)
                root.playerController.handleMediaError(error, errorString)
        }
    }

    Connections {
        target: root.playerController

        function onPlayRequested() {
            if (!root.playerController || root.playerController.sourceUrl.length <= 0)
                return
            const resumingFromPauseFade = root.pauseFadePending
            root.pauseFadePending = false
            if (root.pendingSeekMs >= 0) {
                root.muteForPendingSeek = true
                mediaPlayer.play()
                root.applyPendingSeek()
                return
            }
            mediaPlayer.play()
            // 暂停渐变中途恢复: 还没真 pause, play() 不产生状态变化, 主动淡回
            if (resumingFromPauseFade && root.fadeMs() > 0)
                root.startFadeIn(root.fadeMs())
        }

        function onPauseRequested() {
            const ms = root.fadeMs()
            if (ms > 0 && mediaPlayer.playbackState === MediaPlayer.PlayingState) {
                // 暂停渐变: min(fade, 200ms) 渐弱后真 pause (fadeOutAnim.onStopped);
                // 渐变期间再按播放由 onPlayRequested 清标志接管
                root.pauseFadePending = true
                root.startFadeOut(Math.min(ms, 200))
            } else {
                mediaPlayer.pause()
            }
        }

        function onStopRequested() {
            root.pauseFadePending = false
            // 清切歌淡出标志, 否则停止/全跳过后 applyTailFade 永久被抑制 (review 发现)
            root.fadeSwitchActive = false
            // 暂停渐变/淡出途中停止: 停掉动画并复位音量包络, 别让 fadeFactor 残留 0
            fadeOutAnim.stop()
            fadeInAnim.stop()
            root.fadeFactor = 1
            root.clearPendingSeek()
            mediaPlayer.stop()
        }

        function onFadeOutRequested(durationMs) {
            // Python 切歌协调: 取链与淡出并行, 淡出播完才换源 (player_controller._load_current)
            root.pauseFadePending = false
            root.fadeSwitchActive = true
            root.startFadeOut(durationMs)
        }

        function onSeekRequested(positionMs) {
            if (root.playerController && root.playerController.playbackState === "loading") {
                root.beginPendingSeek(positionMs)
            } else {
                root.clearPendingSeek()
                mediaPlayer.setPosition(Math.max(0, positionMs))
            }
        }
    }

    Connections {
        target: root.appController

        function onAuthChanged(authed, reason) {
            if (authed)
                globalBanner.dismiss()
        }
        function onErrorRaised(message) {
            globalSnackbar.show(message, "error")
        }
    }

    Item {
        id: shortcutFocusSink

        focus: true
    }

    Item {
        id: windowBackground

        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            anchors.margins: root.windowShadowMargin
            radius: root.windowCornerRadius
            antialiasing: true
            color: ThemeTokens.Palette.background
            border.width: 0
        }
    }

    Shortcut {
        sequence: "Ctrl+F"
        onActivated: {
            root.navigate("search")
            searchField.focusInput()
        }
    }

    Shortcut {
        sequence: "Space"
        enabled: !searchField.activeFocus && !loginDialog.visible && !root.queuePanelOpen
        onActivated: {
            if (root.playerController)
                root.playerController.togglePlayPause()
        }
    }

    Shortcut {
        sequence: "Ctrl+Right"
        enabled: !searchField.activeFocus && !loginDialog.visible
        onActivated: {
            if (root.playerController)
                root.playerController.next()
        }
    }

    Shortcut {
        sequence: "Ctrl+Up"
        enabled: !searchField.activeFocus && !loginDialog.visible
        onActivated: {
            if (root.playerController)
                root.playerController.nudgeVolume(0.05)
        }
    }

    Shortcut {
        sequence: "Ctrl+Down"
        enabled: !searchField.activeFocus && !loginDialog.visible
        onActivated: {
            if (root.playerController)
                root.playerController.nudgeVolume(-0.05)
        }
    }

    Shortcut {
        sequence: "Ctrl+Left"
        enabled: !searchField.activeFocus && !loginDialog.visible
        onActivated: {
            if (root.playerController)
                root.playerController.prev()
        }
    }

    Shortcut {
        sequence: "Esc"
        enabled: searchField.activeFocus || root.queuePanelOpen || root.nowPlayingOpen || contentStack.depth > 1
        onActivated: {
            if (searchField.activeFocus) {
                root.releaseTextFocus()
            } else if (root.queuePanelOpen) {
                root.queuePanelOpen = false
            } else if (root.nowPlayingOpen) {
                root.closeNowPlaying()
            } else {
                root.goBack()
            }
        }
    }

    Rectangle {
        id: headerBar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: root.windowShadowMargin
        anchors.leftMargin: root.windowShadowMargin
        anchors.rightMargin: root.windowShadowMargin
        height: ThemeTokens.Spacing.headerHeight
        radius: root.windowCornerRadius
        antialiasing: true
        color: ThemeTokens.Palette.background

        DragHandler {
            target: null
            acceptedButtons: Qt.LeftButton
            onActiveChanged: {
                if (active)
                    root.startSystemMove()
            }
        }

        // 桌面惯例: 双击标题栏切换最大化 / 还原 (按钮在上层, 不受影响)
        TapHandler {
            acceptedButtons: Qt.LeftButton
            gesturePolicy: TapHandler.DragThreshold
            onDoubleTapped: root.toggleMaximized()
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: ThemeTokens.Palette.outlineMuted
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s6
            anchors.rightMargin: ThemeTokens.Spacing.s6
            spacing: ThemeTokens.Spacing.s4

            Components.IconButton {
                id: backButton

                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                enabled: contentStack.depth > 1 || root.nowPlayingOpen
                text: qsTr("返回")
                // 相对路径会延迟到 AppIcon (components/) 才解析, 这里必须显式按本文件解析
                iconSource: Qt.resolvedUrl("icons/arrow-left.svg")
                iconSize: 20
                // 禁用态用中灰: stateDisabled(#e0e0e0) 在白底上接近隐形
                iconColor: enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                cornerRadius: width / 2
                onClicked: {
                    if (root.nowPlayingOpen) {
                        root.closeNowPlaying()
                    } else {
                        root.goBack()
                    }
                }
            }

            RowLayout {
                spacing: ThemeTokens.Spacing.s3

                Rectangle {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    radius: ThemeTokens.Spacing.radiusMd
                    color: ThemeTokens.Palette.primary

                    Label {
                        anchors.centerIn: parent
                        text: "♪"
                        color: ThemeTokens.Palette.primaryText
                        font.pixelSize: ThemeTokens.TypeScale.body
                        font.weight: ThemeTokens.TypeScale.bold
                    }
                }

                Label {
                    visible: root.width >= 920
                    text: qsTr("QuaverQ")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h2
                    font.weight: ThemeTokens.TypeScale.bold
                }
            }

            Components.SearchField {
                id: searchField

                Layout.fillWidth: true
                // 随窗宽缩放 (45%, 上限 500): 窄窗口不再霸占大半个顶栏
                Layout.maximumWidth: Math.min(500, Math.round(root.width * 0.45))
                // 宽窗口下搜索框到达上限后在剩余空间内居中,
                // 避免"控件全部左挤 + 中部真空"的失衡构图
                Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
                placeholderText: qsTr("搜索歌曲、歌手、专辑")
                loading: root.serviceController ? root.serviceController.loading : false
                onSearchRequested: function(keyword) {
                    root.searchAndOpen(keyword)
                }
                onEditingCancelled: root.releaseTextFocus()
            }

            Components.IconButton {
                id: minimizeButton

                Layout.preferredWidth: 40
                Layout.preferredHeight: 40
                text: qsTr("最小化")
                onClicked: root.showMinimized()

                contentItem: Item {
                    Rectangle {
                        anchors.centerIn: parent
                        width: 11
                        height: 2
                        radius: 1
                        color: ThemeTokens.Palette.surfaceVariantText
                    }
                }
            }

            Components.IconButton {
                id: maximizeButton

                Layout.preferredWidth: 40
                Layout.preferredHeight: 40
                text: root.maximizedWindow ? qsTr("还原窗口") : qsTr("最大化")
                onClicked: root.toggleMaximized()

                contentItem: Item {
                    Rectangle {
                        anchors.centerIn: parent
                        anchors.horizontalCenterOffset: root.maximizedWindow ? 2 : 0
                        anchors.verticalCenterOffset: root.maximizedWindow ? -2 : 0
                        width: 10
                        height: 10
                        radius: 1
                        color: "transparent"
                        border.color: ThemeTokens.Palette.surfaceVariantText
                        border.width: 2
                    }

                    Rectangle {
                        visible: root.maximizedWindow
                        anchors.centerIn: parent
                        anchors.horizontalCenterOffset: -2
                        anchors.verticalCenterOffset: 2
                        width: 10
                        height: 10
                        radius: 1
                        color: "transparent"
                        border.color: ThemeTokens.Palette.surfaceVariantText
                        border.width: 2
                    }
                }
            }

            Components.IconButton {
                id: closeButton

                Layout.preferredWidth: 40
                Layout.preferredHeight: 40
                text: qsTr("关闭")
                onClicked: root.close()

                contentItem: Item {
                    readonly property color iconColor: closeButton.hovered ? ThemeTokens.Palette.error : ThemeTokens.Palette.surfaceVariantText

                    Rectangle {
                        anchors.centerIn: parent
                        width: 12
                        height: 2
                        radius: 1
                        rotation: 45
                        color: parent.iconColor
                    }

                    Rectangle {
                        anchors.centerIn: parent
                        width: 12
                        height: 2
                        radius: 1
                        rotation: -45
                        color: parent.iconColor
                    }
                }
            }
        }
    }

    RowLayout {
        anchors.top: headerBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: playerBar.top
        anchors.leftMargin: root.windowShadowMargin
        anchors.rightMargin: root.windowShadowMargin
        spacing: 0

        Components.Sidebar {
            Layout.preferredWidth: root.width < 920 ? 64 : 240
            Layout.fillHeight: true
            appController: root.appController
            libraryController: root.libraryController
            coverController: root.coverController
            downloadActiveCount: root.downloadController ? root.downloadController.activeCount : 0
            compact: root.width < 920
            selectedRoute: root.currentTopRoute
            onLoginRequested: loginDialog.open()
            onRouteRequested: function(route) {
                root.navigate(route)
                // 点侧栏「搜索」= 想搜东西, 顺手聚焦输入框
                if (route === "search")
                    searchField.focusInput()
            }
            onOpenPlaylistRequested: function(pid, title, coverUrl) {
                root.pushDetail("playlist", pid, title, "", coverUrl)
            }
        }

        StackView {
            id: contentStack

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            initialItem: homePageComponent

            // O2: 页面切换 120ms 透明度交叉淡入 (只动 opacity, GPU 合成不触布局);
            // reduceMotion 开启时 durFast=0 即瞬时, 等价此前的 StackView.Immediate
            pushEnter: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: ThemeTokens.Motion.durFast }
            }
            pushExit: Transition {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: ThemeTokens.Motion.durFast }
            }
            popEnter: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: ThemeTokens.Motion.durFast }
            }
            popExit: Transition {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: ThemeTokens.Motion.durFast }
            }
            replaceEnter: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: ThemeTokens.Motion.durFast }
            }
            replaceExit: Transition {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: ThemeTokens.Motion.durFast }
            }
        }
    }

    Components.PlayerBar {
        id: playerBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: root.windowShadowMargin
        anchors.rightMargin: root.windowShadowMargin
        anchors.bottomMargin: root.windowShadowMargin
        currentSong: root.playerController ? root.playerController.currentSong : ({})
        libraryController: root.libraryController
        coverController: root.coverController
        songDetailController: root.songDetailController
        settingsController: root.settingsController
        playbackState: root.playerController ? root.playerController.playbackState : "stopped"
        positionMs: root.playerController ? root.playerController.positionMs : 0
        durationMs: root.playerController ? root.playerController.durationMs : 0
        volume: root.playerController ? root.playerController.volume : 0.8
        muted: root.playerController ? root.playerController.muted : false
        mode: root.playerController ? root.playerController.mode : "sequence"
        queueCount: root.playerController && root.playerController.queueModel
            ? root.playerController.queueModel.count
            : 0
        loading: root.playerController ? root.playerController.loading : false
        errorMessage: root.playerController ? root.playerController.errorMessage : ""
        bottomCornerRadius: root.windowCornerRadius
        onPlayPauseRequested: {
            if (root.playerController)
                root.playerController.togglePlayPause()
        }
        onPrevRequested: {
            if (root.playerController)
                root.playerController.prev()
        }
        onNextRequested: {
            if (root.playerController)
                root.playerController.next()
        }
        onSeekRequested: function(positionMs) {
            if (root.playerController)
                root.playerController.seek(positionMs)
        }
        onVolumeRequested: function(value) {
            if (root.playerController)
                root.playerController.setVolume(value)
        }
        onMuteToggleRequested: {
            if (root.playerController)
                root.playerController.toggleMute()
        }
        onModeRequested: function(value) {
            if (root.playerController)
                root.playerController.setMode(value)
        }
        onQueueRequested: root.queuePanelOpen = !root.queuePanelOpen
        onNowPlayingRequested: root.openNowPlaying()
        onDownloadRequested: {
            if (root.downloadController && root.playerController)
                root.downloadController.downloadSong(root.playerController.currentSong)
        }
    }

    Component {
        id: homePageComponent

        Views.HomeView {
            appController: root.appController
            downloadController: root.downloadController
            coverController: root.coverController
            homeController: root.homeController
            libraryController: root.libraryController
            playerController: root.playerController
            songDetailController: root.songDetailController
            onLoginRequested: loginDialog.open()
            onSearchRequested: function(keyword) {
                root.searchAndOpen(keyword)
            }
            onDetailRequested: function(kind, detailId, title, subtitle, coverUrl) {
                root.pushDetail(kind, detailId, title, subtitle, coverUrl)
            }
        }
    }

    Component {
        id: searchPageComponent

        Views.SearchView {
            serviceController: root.serviceController
            downloadController: root.downloadController
            playerController: root.playerController
            libraryController: root.libraryController
            coverController: root.coverController
            songDetailController: root.songDetailController
            onDetailRequested: function(kind, detailId, title, subtitle, coverUrl) {
                root.pushDetail(kind, detailId, title, subtitle, coverUrl)
            }
        }
    }

    Component {
        id: libraryPageComponent

        Views.LibraryView {
            appController: root.appController
            downloadController: root.downloadController
            coverController: root.coverController
            libraryController: root.libraryController
            playerController: root.playerController
            songDetailController: root.songDetailController
            onLoginRequested: loginDialog.open()
            onLogoutRequested: logoutConfirmDialog.open()
            onDetailRequested: function(kind, detailId, title, subtitle, coverUrl) {
                root.pushDetail(kind, detailId, title, subtitle, coverUrl)
            }
        }
    }

    Component {
        id: detailPageComponent

        Views.DetailView {
            coverController: root.coverController
            downloadController: root.downloadController
            detailControllerFactory: root.detailControllerFactory
            playerController: root.playerController
            libraryController: root.libraryController
            songDetailController: root.songDetailController
            onBackRequested: root.goBack()
            onSearchRequested: function(keyword) {
                root.searchAndOpen(keyword)
            }
            onDetailRequested: function(kind, detailId, title, subtitle, coverUrl) {
                root.pushDetail(kind, detailId, title, subtitle, coverUrl)
            }
            onErrorRaised: function(message) {
                globalSnackbar.show(message, "error")
            }
        }
    }

    Component {
        id: settingsPageComponent

        Views.SettingsView {
            appController: root.appController
            settingsController: root.settingsController
            serviceController: root.serviceController
            downloadController: root.downloadController
            audioDeviceController: root.audioDeviceController
            onLoginRequested: loginDialog.open()
            onLogoutRequested: logoutConfirmDialog.open()
        }
    }

    Component {
        id: downloadsPageComponent

        Views.DownloadsView {
            downloadController: root.downloadController
            coverController: root.coverController
            playerController: root.playerController
        }
    }

    // 正在播放沉浸浮层: 盖侧栏 + 内容区 (z=5, 低于 QueuePanel 的 z=10), 顶栏与播放栏保持可见.
    // 首次打开后常驻 (everOpened 闩锁): active 绑 nowPlayingOpen 会在收起瞬间销毁 item,
    // 滑出动画就没有宿主可播; 常驻也保住歌词滚动位置等页内状态.
    Loader {
        id: nowPlayingLoader

        property bool everOpened: false

        active: everOpened
        // 滑动期间保持可见 (实心页面滑出), 动画结束才隐藏
        visible: root.nowPlayingOpen || nowPlayingSlideAnim.running
        clip: true
        anchors.top: headerBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: playerBar.top
        anchors.leftMargin: root.windowShadowMargin
        anchors.rightMargin: root.windowShadowMargin
        z: 5

        // 从播放栏上方滑入/出 (QQ 音乐"展开/收起"隐喻): 入场减速 durSlow, 退场加速 durMed.
        // 刻意**不叠加透明度淡出** —— 滑动+淡出并行会呈现"半透明页面在掉下去"的怪异观感
        // (真机验收反馈); 实心面板滑动才是"收进播放栏"的正确隐喻.
        transform: Translate {
            id: nowPlayingSlide

            y: root.nowPlayingOpen ? 0 : nowPlayingLoader.height

            Behavior on y {
                enabled: nowPlayingLoader.everOpened
                NumberAnimation {
                    id: nowPlayingSlideAnim

                    duration: root.nowPlayingOpen ? ThemeTokens.Motion.durSlow : ThemeTokens.Motion.durMed
                    easing.type: root.nowPlayingOpen ? ThemeTokens.Motion.easeOut : ThemeTokens.Motion.easeIn
                }
            }
        }

        sourceComponent: Component {
            Views.NowPlayingView {
                coverController: root.coverController
                playerController: root.playerController
                libraryController: root.libraryController
                lyricController: root.lyricController
                settingsController: root.settingsController
                onQueueRequested: root.queuePanelOpen = true
                onBackRequested: root.closeNowPlaying()
                onDownloadRequested: {
                    if (root.downloadController && root.playerController)
                        root.downloadController.downloadSong(root.playerController.currentSong)
                }
            }
        }
    }

    // 待播列表抽屉: 自右滑入 durMed (O2). 首开后常驻 (onLoaded 闩锁) —— active 绑 open
    // 会在收起瞬间销毁 item, 滑出动画没有宿主; Translate 挂在 Loader 上 (启动即存在),
    // 首次打开 x: width→0 也有完整滑入. "打开时定位到当前曲"改由 QueuePanel.onVisibleChanged 触发.
    Loader {
        id: queuePanelLoader

        property bool everOpened: false

        active: root.queuePanelOpen || queuePanelLoader.everOpened
        onLoaded: queuePanelLoader.everOpened = true
        // 与正在播放浮层同款: 实心滑动不叠加淡出, 动画结束才隐藏
        visible: root.queuePanelOpen || queuePanelSlideAnim.running
        clip: true
        anchors.top: headerBar.bottom
        anchors.right: parent.right
        anchors.bottom: playerBar.top
        anchors.rightMargin: root.windowShadowMargin
        width: Math.min(360, root.width - 96 - root.windowShadowMargin * 2)
        z: 10

        transform: Translate {
            id: queuePanelSlide

            x: root.queuePanelOpen ? 0 : queuePanelLoader.width

            Behavior on x {
                NumberAnimation {
                    id: queuePanelSlideAnim

                    duration: ThemeTokens.Motion.durMed
                    easing.type: root.queuePanelOpen ? ThemeTokens.Motion.easeOut : ThemeTokens.Motion.easeIn
                }
            }
        }

        sourceComponent: Component {
            Panels.QueuePanel {
                anchors.fill: parent
                coverController: root.coverController
                queueModel: root.playerController ? root.playerController.queueModel : null
                currentIndex: root.playerController ? root.playerController.currentIndex : -1
                onCloseRequested: root.queuePanelOpen = false
                onPlayIndexRequested: function(row) {
                    if (root.playerController)
                        root.playerController.playQueueIndex(row)
                }
                onRemoveIndexRequested: function(row) {
                    if (root.playerController)
                        root.playerController.removeQueueIndex(row)
                }
                onClearRequested: {
                    if (root.playerController)
                        root.playerController.clearQueue()
                }
            }
        }
    }


    Dialogs.LoginDialog {
        id: loginDialog

        appController: root.appController
    }

    // 退出登录需重新扫码, 代价高 → 二次确认; 破坏性动作确认键用 error 红
    Dialogs.ConfirmDialog {
        id: logoutConfirmDialog

        title: qsTr("退出登录")
        message: qsTr("退出后播放与资料库同步会停用，重新使用需要再次扫码登录。")
        confirmText: qsTr("退出登录")
        destructive: true
        onAccepted: {
            if (root.appController)
                root.appController.logout()
        }
    }

    Dialogs.SongDetailDialog {
        id: songDetailDialog

        songDetailController: root.songDetailController
        coverController: root.coverController
        libraryController: root.libraryController
        playerController: root.playerController
        onDetailRequested: function(kind, detailId, title, subtitle) {
            root.pushDetail(kind, detailId, title, subtitle)
        }
    }

    Components.Banner {
        id: globalBanner

        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: root.windowShadowMargin + ThemeTokens.Spacing.headerHeight
        anchors.leftMargin: root.windowShadowMargin
        anchors.rightMargin: root.windowShadowMargin
        z: 970
        onActionTriggered: loginDialog.open()
    }

    Components.Snackbar {
        id: globalSnackbar

        anchors.top: globalBanner.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.topMargin: ThemeTokens.Spacing.s4
        z: 980
    }

    Connections {
        target: root.serviceController
        function onErrorRaised(message) { globalSnackbar.show(message, "error") }
        function onNoticeRaised(message) { globalSnackbar.show(message, "info") }
    }
    Connections {
        target: root.homeController
        function onErrorRaised(message) { globalSnackbar.show(message, "error") }
    }
    Connections {
        target: root.libraryController
        function onErrorRaised(message) { globalSnackbar.show(message, "error") }
    }
    Connections {
        target: root.settingsController
        function onErrorRaised(message) { globalSnackbar.show(message, "error") }
    }
    Connections {
        target: root.playerController
        function onErrorRaised(message) { globalSnackbar.show(message, "error") }
        // 轻提示 (自动跳过无版权曲目等): info 级, 不用错误红
        function onNoticeRaised(message) { globalSnackbar.show(message, "info") }
    }
    Connections {
        target: root.downloadController
        function onErrorRaised(message) { globalSnackbar.show(message, "error") }
        function onNoticeRaised(message) { globalSnackbar.show(message, "info") }
        function onDownloadFinished(message) { globalSnackbar.show(message, "success") }
    }

    Item {
        id: windowBorderLayer

        anchors.fill: parent
        z: 990

        Rectangle {
            anchors.fill: parent
            anchors.margins: root.windowShadowMargin
            radius: root.windowCornerRadius
            antialiasing: true
            color: "transparent"
            border.width: 1
            border.color: root.active ? ThemeTokens.Palette.windowBorder : ThemeTokens.Palette.windowBorderInactive
        }
    }

    Item {
        id: resizeLayer

        anchors.fill: parent
        enabled: !root.maximizedWindow
        z: 1000

        MouseArea {
            anchors.left: parent.left
            anchors.top: parent.top
            width: root.resizeHandleSize
            height: root.resizeHandleSize
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeFDiagCursor
            onPressed: function(mouse) {
                if (!root.startSystemResize(Qt.LeftEdge | Qt.TopEdge))
                    mouse.accepted = false
            }
        }

        MouseArea {
            anchors.right: parent.right
            anchors.top: parent.top
            width: root.resizeHandleSize
            height: root.resizeHandleSize
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeBDiagCursor
            onPressed: function(mouse) {
                if (!root.startSystemResize(Qt.RightEdge | Qt.TopEdge))
                    mouse.accepted = false
            }
        }

        MouseArea {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            width: root.resizeHandleSize
            height: root.resizeHandleSize
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeBDiagCursor
            onPressed: function(mouse) {
                if (!root.startSystemResize(Qt.LeftEdge | Qt.BottomEdge))
                    mouse.accepted = false
            }
        }

        MouseArea {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            width: root.resizeHandleSize
            height: root.resizeHandleSize
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeFDiagCursor
            onPressed: function(mouse) {
                if (!root.startSystemResize(Qt.RightEdge | Qt.BottomEdge))
                    mouse.accepted = false
            }
        }

        MouseArea {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: root.resizeHandleSize
            anchors.bottomMargin: root.resizeHandleSize
            width: root.resizeHandleSize
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeHorCursor
            onPressed: function(mouse) {
                if (!root.startSystemResize(Qt.LeftEdge))
                    mouse.accepted = false
            }
        }

        MouseArea {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: root.resizeHandleSize
            anchors.bottomMargin: root.resizeHandleSize
            width: root.resizeHandleSize
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeHorCursor
            onPressed: function(mouse) {
                if (!root.startSystemResize(Qt.RightEdge))
                    mouse.accepted = false
            }
        }

        MouseArea {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: root.resizeHandleSize
            anchors.rightMargin: root.resizeHandleSize
            height: root.resizeHandleSize
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeVerCursor
            onPressed: function(mouse) {
                if (!root.startSystemResize(Qt.TopEdge))
                    mouse.accepted = false
            }
        }

        MouseArea {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: root.resizeHandleSize
            anchors.rightMargin: root.resizeHandleSize
            height: root.resizeHandleSize
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeVerCursor
            onPressed: function(mouse) {
                if (!root.startSystemResize(Qt.BottomEdge))
                    mouse.accepted = false
            }
        }
    }
}
