import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: root

    width: 1080
    height: 720
    minimumWidth: 760
    minimumHeight: 640
    visible: true
    title: qsTr("QuaverQ")
    color: "#0d0d10"

    Rectangle {
        anchors.fill: parent
        color: "#0d0d10"

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 12

            Label {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("QuaverQ")
                color: "#ececf1"
                font.pixelSize: 32
                font.weight: Font.Medium
            }

            Label {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Qt Quick shell is ready")
                color: "#a3a3ad"
                font.pixelSize: 16
            }
        }
    }
}
