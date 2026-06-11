pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components" as Components
import "../Theme" as ThemeTokens

Rectangle {
    id: root

    property var queueModel
    property var coverController
    property int currentIndex: -1
    readonly property int queueCount: root.queueModel ? root.queueModel.count : 0

    signal closeRequested()
    signal playIndexRequested(int row)
    signal removeIndexRequested(int row)
    signal clearRequested()

    color: ThemeTokens.Palette.surfaceElevated
    border.color: ThemeTokens.Palette.outlineMuted
    focus: visible

    // 抽屉事件屏障: 面板盖在内容区上方, 标题栏等无处理器区域的点击 / 滚轮 / 悬停
    // 会穿透到底下的页面, 整层吞掉 (列表等子项声明在后, 不受影响)
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
        onWheel: function(wheel) {
            wheel.accepted = true
        }
    }

    // 仅在面板打开时滚到当前曲, **不** hook currentIndex 变化 —— 否则播放器内部任何
    // _emit_current_changed (next/prev/playQueueIndex/setQueue ...) 都会把用户滚开的
    // 视图强行拉回当前曲. 面板现由常驻 Loader 承载 (滑入/出动画需要 item 存活,
    // 不再每次打开重新挂载), 故"每次打开定位到当前曲"由 visible 变化触发.
    function revealCurrentItem() {
        if (root.currentIndex >= 0)
            queueList.positionViewAtIndex(root.currentIndex, ListView.Contain)
    }

    Component.onCompleted: {
        // 等 ListView 完成首次 layout 再定位, 避免 positionViewAtIndex 在 height==0 时无效
        Qt.callLater(revealCurrentItem)
    }

    onVisibleChanged: {
        if (visible)
            Qt.callLater(revealCurrentItem)
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
                    text: qsTr("待播列表")
                    color: ThemeTokens.Palette.surfaceText
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.queueCount > 0 ? qsTr("%1 首歌曲").arg(root.queueCount) : qsTr("没有待播歌曲")
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
                }
            }

            Button {
                id: clearButton

                Layout.preferredHeight: 28
                visible: root.queueCount > 0
                text: qsTr("清空")
                Accessible.name: qsTr("清空待播列表")
                onClicked: root.clearRequested()

                contentItem: Label {
                    text: clearButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: ThemeTokens.Spacing.s3
                    rightPadding: ThemeTokens.Spacing.s3
                    color: ThemeTokens.Palette.surfaceVariantText
                    font.pixelSize: ThemeTokens.TypeScale.caption
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: clearButton.down
                        ? ThemeTokens.Palette.statePressed
                        : clearButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                }
            }

            Button {
                id: closeButton

                Layout.preferredWidth: 34
                Layout.preferredHeight: 34
                text: "×"
                Accessible.name: qsTr("关闭待播列表")
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
                id: queueWheelHandler

                target: null
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: function(event) {
                    const rawDelta = event.pixelDelta.y !== 0
                        ? event.pixelDelta.y
                        : event.angleDelta.y / 120 * ThemeTokens.Spacing.s8
                    const maxContentY = Math.max(0, queueList.contentHeight - queueList.height)
                    queueList.contentY = Math.max(0, Math.min(maxContentY, queueList.contentY - rawDelta))
                    event.accepted = true
                }
            }

            ListView {
                id: queueList

                anchors.fill: parent
                clip: true
                spacing: ThemeTokens.Spacing.s2
                model: root.queueModel
                // 不绑 currentIndex 给 ListView 自己: 用户向上滚动时 Qt 会把当前 item 锁回可见区
                // (highlight follow 策略). 高亮由 delegate 的 current 自己判断, ListView 不需要知道.
                // 显式滚动到当前用 positionViewAtIndex (revealCurrentItem).
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true

                delegate: Components.QueueRow {
                    id: queueRow

                    width: ListView.view.width
                    current: queueRow.index === root.currentIndex
                    coverController: root.coverController
                    onActivated: function(songData, row) {
                        root.playIndexRequested(row)
                    }
                    onRemoveRequested: function(row) {
                        root.removeIndexRequested(row)
                    }
                }

                ScrollBar.vertical: ScrollBar {}
            }

            Label {
                anchors.centerIn: parent
                visible: root.queueCount === 0
                text: qsTr("暂无待播歌曲")
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }
    }
}
