pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property var downloadModel
    property int activeCount: 0
    readonly property int taskCount: root.downloadModel ? root.downloadModel.count : 0

    signal closeRequested()
    signal cancelRequested(int row)
    signal retryRequested(int row)
    signal openDirRequested()

    color: ThemeTokens.Palette.surfaceElevated
    border.color: ThemeTokens.Palette.outlineMuted
    focus: visible

    // 抽屉事件屏障: 与 QueuePanel 同款, 吞掉无处理器区域的点击 / 滚轮 / 悬停防穿透
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
        onWheel: function(wheel) {
            wheel.accepted = true
        }
    }

    Keys.onEscapePressed: root.closeRequested()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s3

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            spacing: ThemeTokens.Spacing.s3

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                Label {
                    Layout.fillWidth: true
                    text: qsTr("下载管理")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.activeCount > 0
                        ? qsTr("%1 个任务进行中").arg(root.activeCount)
                        : root.taskCount > 0 ? qsTr("全部完成") : qsTr("暂无下载任务")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }

            Button {
                id: closeButton

                Layout.preferredWidth: 34
                Layout.preferredHeight: 34
                text: "×"
                Accessible.name: qsTr("关闭下载管理")
                onClicked: root.closeRequested()

                contentItem: Label {
                    text: closeButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.body
                }

                background: Rectangle {
                    radius: width / 2
                    color: closeButton.down ? ThemeTokens.Palette.statePressed : closeButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                    border.color: "transparent"
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            WheelHandler {
                target: null
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: function(event) {
                    const rawDelta = event.pixelDelta.y !== 0
                        ? event.pixelDelta.y
                        : event.angleDelta.y / 120 * ThemeTokens.Spacing.s8
                    const maxContentY = Math.max(0, downloadList.contentHeight - downloadList.height)
                    downloadList.contentY = Math.max(0, Math.min(maxContentY, downloadList.contentY - rawDelta))
                    event.accepted = true
                }
            }

            ListView {
                id: downloadList

                anchors.fill: parent
                clip: true
                spacing: ThemeTokens.Spacing.s2
                model: root.downloadModel
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true

                delegate: Rectangle {
                    id: taskRow

                    required property int index
                    required property string title
                    required property string singers
                    required property string status
                    required property string statusText
                    required property real progress
                    required property string qualityText
                    required property string errorText

                    readonly property bool active: taskRow.status === "pending" || taskRow.status === "running"
                    readonly property bool retryable: taskRow.status === "failed" || taskRow.status === "canceled"

                    width: ListView.view.width
                    implicitHeight: 60
                    radius: ThemeTokens.Spacing.radiusMd
                    color: rowHover.hovered ? ThemeTokens.Palette.stateHover : "transparent"

                    Accessible.role: Accessible.ListItem
                    Accessible.name: qsTr("%1, %2").arg(taskRow.title).arg(taskRow.statusText)

                    HoverHandler {
                        id: rowHover
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: ThemeTokens.Spacing.s3
                        anchors.rightMargin: ThemeTokens.Spacing.s3
                        spacing: ThemeTokens.Spacing.s3

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

                        Button {
                            id: taskActionButton

                            Layout.preferredWidth: 56
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            visible: taskRow.active || taskRow.retryable
                            text: taskRow.retryable ? qsTr("重试") : qsTr("取消")
                            Accessible.name: qsTr("%1 %2").arg(text).arg(taskRow.title)
                            onClicked: {
                                if (taskRow.retryable)
                                    root.retryRequested(taskRow.index)
                                else
                                    root.cancelRequested(taskRow.index)
                            }

                            contentItem: Label {
                                text: taskActionButton.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                color: ThemeTokens.Palette.surfaceVariantText
                                font.pixelSize: ThemeTokens.TypeScale.caption
                            }

                            background: Rectangle {
                                radius: ThemeTokens.Spacing.radiusMd
                                color: taskActionButton.down
                                    ? ThemeTokens.Palette.statePressed
                                    : taskActionButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                                border.color: ThemeTokens.Palette.outlineMuted
                            }
                        }
                    }
                }

                ScrollBar.vertical: ScrollBar {}
            }

            Label {
                anchors.centerIn: parent
                visible: root.taskCount === 0
                text: qsTr("从歌曲菜单选择「下载」开始")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
            }
        }

        Button {
            id: openDirButton

            Layout.fillWidth: true
            Layout.preferredHeight: 36
            text: qsTr("打开下载目录")
            Accessible.name: text
            onClicked: root.openDirRequested()

            contentItem: Label {
                text: openDirButton.text
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                color: ThemeTokens.Palette.surfaceText
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                font.weight: ThemeTokens.TypeScale.medium
            }

            background: Rectangle {
                radius: ThemeTokens.Spacing.radiusMd
                color: openDirButton.down
                    ? ThemeTokens.Palette.statePressed
                    : openDirButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                border.color: ThemeTokens.Palette.outlineMuted
            }
        }
    }
}
