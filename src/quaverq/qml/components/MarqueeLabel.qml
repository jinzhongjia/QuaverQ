pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

// 当文字超出容器宽度时, 自动横向滚动 (seamless tile); 否则显示省略号兜底.
// 用于底部播放栏歌曲名 / 歌手名这类长度可变又不希望撑大父布局的位置.
Item {
    id: root

    property string text: ""
    property color color: "black"
    property int pixelSize: 14
    property int fontWeight: Font.Normal
    property int marqueeGap: 40
    property int pixelsPerSecond: 30
    property int startDelay: 1500

    readonly property bool overflows: textMetrics.boundingRect.width > width && width > 0
    // 减少动效 = 持续性横滚停用, 回退到静态省略号
    readonly property bool marqueeActive: root.overflows && !ThemeTokens.Motion.reduceMotion

    clip: true
    implicitHeight: textMetrics.boundingRect.height
    // 切换回滚动态时从头开始, 避免残留上次的滚动偏移在 startDelay 期间静止展示
    onMarqueeActiveChanged: marqueeRow.x = 0

    // 悬停暂停: 无限横滚属于余光区持续运动, 用户凑近想读时应停下;
    // 移开后从当前位置继续 (paused 而非 stop, 不回跳)
    HoverHandler {
        id: marqueeHover

        enabled: root.marqueeActive
    }

    TextMetrics {
        id: textMetrics
        text: root.text
        font.pixelSize: root.pixelSize
        font.weight: root.fontWeight
    }

    Label {
        id: elidedLabel
        visible: !root.marqueeActive
        anchors.fill: parent
        text: root.text
        color: root.color
        font.pixelSize: root.pixelSize
        font.weight: root.fontWeight
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
    }

    Row {
        id: marqueeRow
        visible: root.marqueeActive
        anchors.verticalCenter: parent.verticalCenter
        spacing: root.marqueeGap

        Repeater {
            model: 2
            Label {
                text: root.text
                color: root.color
                font.pixelSize: root.pixelSize
                font.weight: root.fontWeight
            }
        }

        // 滑动 W+gap 距离, 第二个拷贝刚好对齐到第一个的起始位置, 循环回到 0 时画面连续.
        SequentialAnimation on x {
            running: root.marqueeActive && root.visible
            // paused 只在 running 时有意义, 条件里带上 running 防"未运行时设置 paused"告警
            paused: running && marqueeHover.hovered
            loops: Animation.Infinite
            PauseAnimation { duration: root.startDelay }
            NumberAnimation {
                from: 0
                to: -(textMetrics.boundingRect.width + root.marqueeGap)
                duration: Math.max(1, (textMetrics.boundingRect.width + root.marqueeGap) * 1000 / root.pixelsPerSecond)
            }
        }
    }
}
