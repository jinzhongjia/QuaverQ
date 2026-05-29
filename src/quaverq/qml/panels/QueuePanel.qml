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

    color: ThemeTokens.Palette.surfaceElevated
    border.color: ThemeTokens.Palette.outlineMuted
    focus: visible

    function revealCurrentItem() {
        forceActiveFocus()
        if (root.currentIndex >= 0)
            queueList.positionViewAtIndex(root.currentIndex, ListView.Contain)
    }

    Component.onCompleted: {
        if (visible)
            revealCurrentItem()
    }

    onVisibleChanged: {
        if (visible) {
            revealCurrentItem()
        }
    }

    onCurrentIndexChanged: {
        if (visible && root.currentIndex >= 0)
            revealCurrentItem()
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
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.body
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: root.queueCount > 0 ? qsTr("%1 首歌曲").arg(root.queueCount) : qsTr("没有待播歌曲")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    elide: Text.ElideRight
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
                    color: ThemeTokens.Palette.onSurface
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
                currentIndex: root.currentIndex
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
                }

                ScrollBar.vertical: ScrollBar {}
            }

            Label {
                anchors.centerIn: parent
                visible: root.queueCount === 0
                text: qsTr("暂无待播歌曲")
                color: ThemeTokens.Palette.onSurfaceVariant
                font.pixelSize: ThemeTokens.TypeScale.body
            }
        }
    }
}
