pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../dialogs" as Dialogs
import "../Theme" as ThemeTokens

// 下载管理整页: 侧边栏「下载」入口进入. 行 = 封面 + 歌名 + 状态/音质/进度 + 操作;
// 整行点击 → 在本应用内播放该歌 (本地优先, 文件失效回退在线).
Item {
    id: root

    property string routeName: "downloads"
    property var downloadController
    property var coverController
    property var playerController

    // 删除确认: 记下待删行与歌名, 确认后删本地文件
    property int pendingDeleteRow: -1
    property string pendingDeleteTitle: ""

    readonly property var downloadModel: root.downloadController ? root.downloadController.downloadModel : null
    readonly property int taskCount: root.downloadModel ? root.downloadModel.count : 0
    readonly property int activeCount: root.downloadController ? root.downloadController.activeCount : 0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s6
        spacing: ThemeTokens.Spacing.s5

        // ===== header =====
        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: qsTr("下载管理")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.h1
                    font.weight: ThemeTokens.TypeScale.bold
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.activeCount > 0
                        ? qsTr("%1 个任务进行中").arg(root.activeCount)
                        : root.taskCount > 0 ? qsTr("共 %1 首").arg(root.taskCount) : qsTr("暂无下载")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    elide: Text.ElideRight
                }
            }

            Button {
                id: openDirButton

                Layout.preferredHeight: 40
                Layout.preferredWidth: 120
                text: qsTr("打开下载目录")
                Accessible.name: text
                onClicked: {
                    if (root.downloadController)
                        root.downloadController.openDownloadDirectory()
                }

                contentItem: Label {
                    text: openDirButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusPill
                    color: openDirButton.down
                        ? ThemeTokens.Palette.statePressed
                        : openDirButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: ThemeTokens.Palette.outline
                }
            }
        }

        // ===== list =====
        ListView {
            id: downloadList

            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.taskCount > 0
            clip: true
            spacing: ThemeTokens.Spacing.s2
            model: root.downloadModel
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            ScrollBar.vertical: ScrollBar {}

            delegate: Rectangle {
                id: taskRow

                required property int index
                required property var song
                required property string title
                required property string singers
                required property string status
                required property string statusText
                required property real progress
                required property string qualityText
                required property string errorText
                required property string coverUrl

                readonly property bool active: taskRow.status === "pending" || taskRow.status === "running"
                readonly property bool retryable: taskRow.status === "failed" || taskRow.status === "canceled" || taskRow.status === "missing"
                readonly property bool playable: !!(taskRow.song && taskRow.song.mid)

                width: ListView.view.width
                implicitHeight: 64
                radius: ThemeTokens.Spacing.radiusMd
                color: rowHover.hovered ? ThemeTokens.Palette.stateHover : "transparent"

                Accessible.role: Accessible.ListItem
                Accessible.name: qsTr("%1, %2").arg(taskRow.title).arg(taskRow.statusText)

                HoverHandler {
                    id: rowHover
                }

                // 整行点击 → 应用内播放 (本地优先; 文件失效时播放核心自动回退在线)
                TapHandler {
                    enabled: taskRow.playable
                    onTapped: {
                        if (root.playerController)
                            root.playerController.pushAndPlay(taskRow.song)
                    }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: ThemeTokens.Spacing.s3
                    anchors.rightMargin: ThemeTokens.Spacing.s3
                    spacing: ThemeTokens.Spacing.s3

                    Components.AlbumArt {
                        Layout.preferredWidth: 46
                        Layout.preferredHeight: 46
                        compact: true
                        coverUrl: taskRow.coverUrl
                        coverController: root.coverController
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 3

                        Label {
                            Layout.fillWidth: true
                            text: taskRow.title
                            color: ThemeTokens.Palette.surfaceText
                            font.pixelSize: ThemeTokens.TypeScale.bodySm
                            font.weight: ThemeTokens.TypeScale.medium
                            elide: Text.ElideRight
                        }

                        // 失败时整行副标题让位给错误原因 (红色); 正常显示 歌手 · 状态 · 音质
                        Label {
                            Layout.fillWidth: true
                            text: taskRow.status === "failed" && taskRow.errorText
                                ? taskRow.errorText
                                : [taskRow.singers, taskRow.statusText, taskRow.qualityText]
                                    .filter(function(part) { return part && part.length > 0 })
                                    .join(" · ")
                            color: taskRow.status === "failed"
                                ? ThemeTokens.Palette.error
                                : taskRow.status === "missing"
                                    ? ThemeTokens.Palette.warning
                                    : ThemeTokens.Palette.surfaceVariantText
                            font.pixelSize: ThemeTokens.TypeScale.caption
                            elide: Text.ElideRight
                        }

                        ProgressBar {
                            id: taskProgress

                            Layout.fillWidth: true
                            Layout.preferredHeight: 3
                            visible: taskRow.status === "running"
                            indeterminate: taskRow.progress < 0
                            value: Math.max(0, taskRow.progress)

                            background: Rectangle {
                                radius: 1.5
                                color: ThemeTokens.Palette.surfaceVariant
                            }

                            contentItem: Item {
                                Rectangle {
                                    width: taskProgress.indeterminate ? parent.width : taskProgress.visualPosition * parent.width
                                    height: parent.height
                                    radius: 1.5
                                    color: ThemeTokens.Palette.primary
                                    opacity: taskProgress.indeterminate ? 0.4 : 1
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignVCenter
                        spacing: ThemeTokens.Spacing.s2

                        RowActionButton {
                            visible: taskRow.active
                            text: qsTr("取消")
                            Accessible.name: qsTr("取消 %1").arg(taskRow.title)
                            onClicked: {
                                if (root.downloadController)
                                    root.downloadController.cancelTask(taskRow.index)
                            }
                        }

                        RowActionButton {
                            visible: taskRow.retryable
                            text: taskRow.status === "missing" ? qsTr("重新下载") : qsTr("重试")
                            Accessible.name: qsTr("%1 %2").arg(text).arg(taskRow.title)
                            onClicked: {
                                if (root.downloadController)
                                    root.downloadController.retryTask(taskRow.index)
                            }
                        }

                        RowActionButton {
                            visible: taskRow.retryable
                            text: qsTr("移除")
                            Accessible.name: qsTr("移除 %1").arg(taskRow.title)
                            onClicked: {
                                if (root.downloadController)
                                    root.downloadController.removeTask(taskRow.index)
                            }
                        }

                        // 删除已下载的音乐 (删本地文件, 破坏性 → 二次确认)
                        RowActionButton {
                            visible: taskRow.status === "done"
                            text: qsTr("删除")
                            Accessible.name: qsTr("删除 %1").arg(taskRow.title)
                            onClicked: {
                                root.pendingDeleteRow = taskRow.index
                                root.pendingDeleteTitle = taskRow.title
                                deleteConfirmDialog.open()
                            }
                        }
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.taskCount === 0

            ColumnLayout {
                anchors.centerIn: parent
                spacing: ThemeTokens.Spacing.s3

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("暂无下载")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                }

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("在歌曲菜单或播放栏选择「下载」开始")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                }
            }
        }
    }

    // 行尾操作按钮 (取消 / 重试 / 重新下载 / 移除) 共用样式
    component RowActionButton: Button {
        id: actionBtn

        Layout.preferredWidth: 64
        Layout.preferredHeight: 30

        contentItem: Label {
            text: actionBtn.text
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: ThemeTokens.Palette.surfaceVariantText
            font.pixelSize: ThemeTokens.TypeScale.caption
        }

        background: Rectangle {
            radius: ThemeTokens.Spacing.radiusMd
            color: actionBtn.down
                ? ThemeTokens.Palette.statePressed
                : actionBtn.hovered ? ThemeTokens.Palette.stateHover : "transparent"
            border.color: ThemeTokens.Palette.outlineMuted
        }
    }

    // 删除本地文件不可逆 → 二次确认, 确认键用 error 红
    Dialogs.ConfirmDialog {
        id: deleteConfirmDialog

        title: qsTr("删除已下载的音乐")
        message: qsTr("将删除《%1》的本地音频、歌词与封面文件，此操作不可恢复。").arg(root.pendingDeleteTitle)
        confirmText: qsTr("删除")
        destructive: true
        onAccepted: {
            if (root.downloadController && root.pendingDeleteRow >= 0)
                root.downloadController.deleteTask(root.pendingDeleteRow)
            root.pendingDeleteRow = -1
        }
    }
}
