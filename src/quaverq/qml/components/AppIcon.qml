import QtQuick
import QtQuick.Effects

// 单色 SVG 图标: 白色源图 (qml/icons/*.svg) 经 MultiEffect 按 color 染色,
// 亮暗主题 / 选中 / 禁用态由调用方绑 token 色, 一份资产通吃所有状态.
Item {
    id: root

    property url source: ""
    property color color: "#ffffff"
    property int size: 20

    implicitWidth: root.size
    implicitHeight: root.size

    Image {
        id: iconImage

        anchors.centerIn: parent
        width: root.size
        height: root.size
        visible: false
        source: root.source
        // SVG 以 48px 栅格化再缩到目标尺寸, 高 DPI 下保持锐利
        sourceSize.width: 48
        sourceSize.height: 48
    }

    MultiEffect {
        anchors.fill: iconImage
        source: iconImage
        colorization: 1
        colorizationColor: root.color
    }
}
