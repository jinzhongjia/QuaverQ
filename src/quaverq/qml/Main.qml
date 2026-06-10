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
    readonly property var systemTheme: SystemTheme
    // qmllint enable unqualified
    // 托盘可用时由 Python 置 true: 关闭改为隐藏到托盘而非退出
    property bool closeToTray: false
    property bool queuePanelOpen: false
    property string currentRoute: "home"
    property string currentTopRoute: "home"
    property string currentDetailTitle: ""
    property int pendingSeekMs: -1
    property int pendingSeekAttempts: 0
    property bool muteForPendingSeek: false
    readonly property int pendingSeekToleranceMs: 1000
    readonly property int pendingSeekMaxAttempts: 60

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

    function routeTitle(route) {
        switch (route) {
        case "home":
            return qsTr("发现")
        case "library":
            return qsTr("资料库")
        case "settings":
            return qsTr("设置")
        case "now-playing":
            return qsTr("正在播放")
        case "detail":
            return root.currentDetailTitle.length > 0 ? root.currentDetailTitle : qsTr("详情")
        default:
            return qsTr("搜索")
        }
    }

    function resetContent(component, route) {
        root.queuePanelOpen = false
        root.currentDetailTitle = ""
        contentStack.clear(StackView.Immediate)
        contentStack.push(component, {}, StackView.Immediate)
        root.currentRoute = route
        root.currentTopRoute = route
    }

    function navigate(route) {
        root.releaseTextFocus()
        if (route === root.currentRoute && contentStack.depth === 1)
            return
        if (route === "home") {
            root.resetContent(homePageComponent, "home")
        } else if (route === "library") {
            root.resetContent(libraryPageComponent, "library")
        } else if (route === "settings") {
            root.resetContent(settingsPageComponent, "settings")
        } else if (route === "now-playing") {
            root.resetContent(nowPlayingPageComponent, "now-playing")
            root.currentTopRoute = ""
        } else {
            root.resetContent(searchPageComponent, "search")
        }
    }

    function pushDetail(kind, detailId, title, subtitle, coverUrl) {
        root.queuePanelOpen = false
        root.releaseTextFocus()
        contentStack.push(detailPageComponent, {
            detailKind: kind,
            detailId: detailId,
            detailTitle: title,
            detailSubtitle: subtitle,
            // 入口卡片封面透传: 头图即刻显示, 详情接口的封面到了再升级 (B1)
            detailCoverUrl: coverUrl || ""
        }, StackView.Immediate)
        root.currentDetailTitle = title
        root.currentRoute = "detail"
    }

    function goBack() {
        if (contentStack.depth <= 1)
            return
        contentStack.pop(StackView.Immediate)
        root.currentDetailTitle = ""
        root.currentRoute = root.currentTopRoute.length > 0 ? root.currentTopRoute : "home"
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

    AudioOutput {
        id: audioOutput

        volume: root.muteForPendingSeek ? 0 : (root.playerController ? root.playerController.volume : 0.8)
    }

    MediaPlayer {
        id: mediaPlayer

        audioOutput: audioOutput
        source: root.playerController ? root.playerController.sourceUrl : ""

        onPositionChanged: {
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
            if (root.pendingSeekMs >= 0) {
                root.muteForPendingSeek = true
                mediaPlayer.play()
                root.applyPendingSeek()
                return
            }
            mediaPlayer.play()
        }

        function onPauseRequested() {
            mediaPlayer.pause()
        }

        function onStopRequested() {
            root.clearPendingSeek()
            mediaPlayer.stop()
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

        function onCredExpired() {
            globalBanner.kind = "warning"
            globalBanner.actionText = qsTr("重新登录")
            globalBanner.message = qsTr("登录已过期，请重新登录")
        }
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
        sequence: "Ctrl+Left"
        enabled: !searchField.activeFocus && !loginDialog.visible
        onActivated: {
            if (root.playerController)
                root.playerController.prev()
        }
    }

    Shortcut {
        sequence: "Esc"
        enabled: searchField.activeFocus || root.queuePanelOpen || contentStack.depth > 1
        onActivated: {
            if (searchField.activeFocus) {
                root.releaseTextFocus()
            } else if (root.queuePanelOpen) {
                root.queuePanelOpen = false
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
                enabled: contentStack.depth > 1
                text: qsTr("返回")
                iconText: "←"
                iconColor: enabled ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText
                cornerRadius: width / 2
                onClicked: root.goBack()
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
                Layout.maximumWidth: 500
                // 宽窗口下搜索框到达 500px 上限后在剩余空间内居中,
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
            compact: root.width < 920
            selectedRoute: root.currentTopRoute
            onLoginRequested: loginDialog.open()
            onRouteRequested: function(route) {
                root.navigate(route)
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
        playbackState: root.playerController ? root.playerController.playbackState : "stopped"
        positionMs: root.playerController ? root.playerController.positionMs : 0
        durationMs: root.playerController ? root.playerController.durationMs : 0
        volume: root.playerController ? root.playerController.volume : 0.8
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
        onModeRequested: function(value) {
            if (root.playerController)
                root.playerController.setMode(value)
        }
        onQueueRequested: root.queuePanelOpen = !root.queuePanelOpen
        onNowPlayingRequested: root.navigate("now-playing")
    }

    Component {
        id: homePageComponent

        Views.HomeView {
            appController: root.appController
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
            onNowPlayingRequested: root.navigate("now-playing")
        }
    }

    Component {
        id: searchPageComponent

        Views.SearchView {
            serviceController: root.serviceController
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
            coverController: root.coverController
            libraryController: root.libraryController
            playerController: root.playerController
            songDetailController: root.songDetailController
            onLoginRequested: loginDialog.open()
            onDetailRequested: function(kind, detailId, title, subtitle, coverUrl) {
                root.pushDetail(kind, detailId, title, subtitle, coverUrl)
            }
        }
    }

    Component {
        id: detailPageComponent

        Views.DetailView {
            coverController: root.coverController
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
        id: nowPlayingPageComponent

        Views.NowPlayingView {
            coverController: root.coverController
            playerController: root.playerController
            libraryController: root.libraryController
            lyricController: root.lyricController
            settingsController: root.settingsController
            onQueueRequested: root.queuePanelOpen = true
        }
    }

    Component {
        id: settingsPageComponent

        Views.SettingsView {
            appController: root.appController
            settingsController: root.settingsController
            onLoginRequested: loginDialog.open()
        }
    }

    Loader {
        id: queuePanelLoader

        active: root.queuePanelOpen
        asynchronous: true
        visible: active
        anchors.top: headerBar.bottom
        anchors.right: parent.right
        anchors.bottom: playerBar.top
        anchors.rightMargin: root.windowShadowMargin
        width: Math.min(360, root.width - 96 - root.windowShadowMargin * 2)
        z: 10

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
            }
        }
    }

    Dialogs.LoginDialog {
        id: loginDialog

        appController: root.appController
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
