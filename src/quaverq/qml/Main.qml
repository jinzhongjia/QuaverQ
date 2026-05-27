import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "components" as Components
import "dialogs" as Dialogs
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

    AudioOutput {
        id: audioOutput

        volume: root.playerController ? root.playerController.volume : 0.8
    }

    MediaPlayer {
        id: mediaPlayer

        audioOutput: audioOutput
        source: root.playerController ? root.playerController.sourceUrl : ""

        onPositionChanged: {
            if (root.playerController)
                root.playerController.updatePosition(mediaPlayer.position)
        }
        onDurationChanged: {
            if (root.playerController)
                root.playerController.updateDuration(mediaPlayer.duration)
        }
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
            if (root.playerController && mediaStatus === MediaPlayer.EndOfMedia)
                root.playerController.handleEndOfMedia()
        }
    }

    Connections {
        target: root.playerController

        function onPlayRequested() {
            if (root.playerController && root.playerController.sourceUrl.length > 0)
                mediaPlayer.play()
        }

        function onPauseRequested() {
            mediaPlayer.pause()
        }

        function onStopRequested() {
            mediaPlayer.stop()
        }

        function onSeekRequested(positionMs) {
            mediaPlayer.setPosition(positionMs)
        }
    }

    Shortcut {
        sequence: "Ctrl+F"
        onActivated: searchField.focusInput()
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
            spacing: ThemeTokens.Spacing.s5

            Label {
                text: qsTr("QuaverQ")
                color: ThemeTokens.Palette.onSurface
                font.pixelSize: ThemeTokens.TypeScale.h2
                font.weight: ThemeTokens.TypeScale.medium
            }

            Components.SearchField {
                id: searchField

                Layout.fillWidth: true
                Layout.maximumWidth: 520
                placeholderText: qsTr("搜索歌曲、歌手、专辑")
                text: "周杰伦"
                loading: root.serviceController ? root.serviceController.loading : false
                onSearchRequested: function(keyword) {
                    if (root.serviceController)
                        root.serviceController.search(keyword)
                }
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
            selectedRoute: "search"
            onLoginRequested: loginDialog.open()
        }

        Views.SearchView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            serviceController: root.serviceController
            playerController: root.playerController
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
    }

    Dialogs.LoginDialog {
        id: loginDialog

        appController: root.appController
    }
}
