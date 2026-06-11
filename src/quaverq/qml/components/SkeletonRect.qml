import QtQuick
import "../Theme" as ThemeTokens

// 骨架屏基件: 轻脉动灰块, 全应用加载占位的统一形态
Rectangle {
    id: root

    radius: ThemeTokens.Spacing.radiusSm
    color: ThemeTokens.Palette.surfaceVariant

    // 减少动效时停脉动 (持续性运动), 静态灰块仍是有效的加载占位
    SequentialAnimation on opacity {
        running: root.visible && !ThemeTokens.Motion.reduceMotion
        loops: Animation.Infinite
        onRunningChanged: {
            if (!running)
                root.opacity = 1
        }

        NumberAnimation {
            from: 1
            to: 0.45
            duration: 700
            easing.type: Easing.InOutQuad
        }

        NumberAnimation {
            from: 0.45
            to: 1
            duration: 700
            easing.type: Easing.InOutQuad
        }
    }
}
