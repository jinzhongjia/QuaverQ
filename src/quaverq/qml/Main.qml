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

    width: ThemeTokens.Spacing.windowWidth
    height: ThemeTokens.Spacing.windowHeight
    minimumWidth: ThemeTokens.Spacing.minWindowWidth
    minimumHeight: ThemeTokens.Spacing.minWindowHeight
    visible: true
    title: qsTr("QuaverQ")
    color: ThemeTokens.Palette.background
    readonly property var appController: AppController
    readonly property var serviceController: ServiceController
    readonly property var playerController: PlayerController
    property bool queuePanelOpen: false
    property string currentRoute: "search"
    property string currentTopRoute: "search"
    property string currentDetailTitle: ""
    property int pendingSeekMs: -1
    property int pendingSeekAttempts: 0
    property bool muteForPendingSeek: false
    readonly property int pendingSeekToleranceMs: 1000
    readonly property int pendingSeekMaxAttempts: 60

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

    function pushDetail(kind, title, subtitle) {
        root.queuePanelOpen = false
        root.releaseTextFocus()
        contentStack.push(detailPageComponent, {
            detailKind: kind,
            detailTitle: title,
            detailSubtitle: subtitle
        }, StackView.Immediate)
        root.currentDetailTitle = title
        root.currentRoute = "detail"
    }

    function goBack() {
        if (contentStack.depth <= 1)
            return
        contentStack.pop(StackView.Immediate)
        root.currentDetailTitle = ""
        root.currentRoute = root.currentTopRoute.length > 0 ? root.currentTopRoute : "search"
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

    Item {
        id: shortcutFocusSink

        focus: true
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
        height: ThemeTokens.Spacing.headerHeight
        color: ThemeTokens.Palette.surface

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: ThemeTokens.Spacing.s5
            anchors.rightMargin: ThemeTokens.Spacing.s5
            spacing: ThemeTokens.Spacing.s4

            Button {
                id: backButton

                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                visible: contentStack.depth > 1
                text: "‹"
                Accessible.name: qsTr("返回")
                onClicked: root.goBack()

                contentItem: Label {
                    text: backButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.h2
                }

                background: Rectangle {
                    radius: width / 2
                    color: backButton.down
                        ? ThemeTokens.Palette.statePressed
                        : backButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                }
            }

            Label {
                text: qsTr("QuaverQ")
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.medium
            }

            Label {
                Layout.preferredWidth: root.width < 920 ? 0 : 120
                visible: root.width >= 920
                text: root.routeTitle(root.currentRoute)
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                elide: Text.ElideRight
            }

            Components.SearchField {
                id: searchField

                Layout.fillWidth: true
                Layout.maximumWidth: 520
                placeholderText: qsTr("搜索歌曲、歌手、专辑")
                loading: root.serviceController ? root.serviceController.loading : false
                onSearchRequested: function(keyword) {
                    root.searchAndOpen(keyword)
                }
                onEditingCancelled: root.releaseTextFocus()
            }
        }
    }

    RowLayout {
        anchors.top: headerBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: playerBar.top
        spacing: 0

        Components.Sidebar {
            Layout.preferredWidth: root.width < 920 ? 64 : 240
            Layout.fillHeight: true
            appController: root.appController
            compact: root.width < 920
            selectedRoute: root.currentTopRoute
            onLoginRequested: loginDialog.open()
            onRouteRequested: function(route) {
                root.navigate(route)
            }
        }

        StackView {
            id: contentStack

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            initialItem: searchPageComponent
        }
    }

    Components.PlayerBar {
        id: playerBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        currentSong: root.playerController ? root.playerController.currentSong : ({})
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
            playerController: root.playerController
            onSearchRequested: function(keyword) {
                root.searchAndOpen(keyword)
            }
            onDetailRequested: function(kind, title, subtitle) {
                root.pushDetail(kind, title, subtitle)
            }
            onNowPlayingRequested: root.navigate("now-playing")
        }
    }

    Component {
        id: searchPageComponent

        Views.SearchView {
            serviceController: root.serviceController
            playerController: root.playerController
        }
    }

    Component {
        id: libraryPageComponent

        Views.LibraryView {
            appController: root.appController
            onLoginRequested: loginDialog.open()
            onDetailRequested: function(kind, title, subtitle) {
                root.pushDetail(kind, title, subtitle)
            }
        }
    }

    Component {
        id: detailPageComponent

        Views.DetailView {
            onBackRequested: root.goBack()
            onSearchRequested: function(keyword) {
                root.searchAndOpen(keyword)
            }
        }
    }

    Component {
        id: nowPlayingPageComponent

        Views.NowPlayingView {
            playerController: root.playerController
            onQueueRequested: root.queuePanelOpen = true
        }
    }

    Component {
        id: settingsPageComponent

        Views.SettingsView {
            appController: root.appController
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
        width: Math.min(360, root.width - 96)
        z: 10

        sourceComponent: Component {
            Panels.QueuePanel {
                anchors.fill: parent
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
}
