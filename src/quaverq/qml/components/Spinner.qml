import QtQuick
import "../Theme" as ThemeTokens

// 品牌色加载弧: 替代 Basic 默认 BusyIndicator (样式与主题脱节)
Item {
    id: root

    property int size: 32
    property color color: ThemeTokens.Palette.primaryFg

    implicitWidth: root.size
    implicitHeight: root.size

    Canvas {
        id: arc

        anchors.fill: parent
        onPaint: {
            const ctx = arc.getContext("2d")
            ctx.reset()
            const w = arc.width
            const lw = Math.max(2.5, w * 0.09)
            ctx.strokeStyle = String(root.color)
            ctx.lineWidth = lw
            ctx.lineCap = "round"
            ctx.beginPath()
            ctx.arc(w / 2, w / 2, (w - lw) / 2, 0, Math.PI * 1.5)
            ctx.stroke()
        }

        RotationAnimator on rotation {
            running: root.visible
            loops: Animation.Infinite
            from: 0
            to: 360
            duration: 900
        }
    }

    onColorChanged: arc.requestPaint()
}
