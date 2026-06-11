pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

// 文字 + 2px 品牌绿下划线的水平 tab 行 (QQ 音乐样式).
// 统一收编 SearchView / LibraryView / DetailView 三处各自复制且已漂移的实现
// (36 vs 38px 基线、有无焦点环不一致、命中区只有文字宽).
RowLayout {
    id: root

    // 元素是字符串或 {label: ...} 对象 (对象形式方便调用方携带 key 等附加字段)
    property var tabs: []
    property int currentIndex: 0

    signal activated(int index)

    spacing: ThemeTokens.Spacing.s6

    Repeater {
        model: root.tabs

        delegate: Item {
            id: tabItem

            required property int index
            required property var modelData

            readonly property string label: typeof tabItem.modelData === "string"
                ? tabItem.modelData
                : (tabItem.modelData && tabItem.modelData.label ? tabItem.modelData.label : "")
            readonly property bool current: root.currentIndex === tabItem.index

            Layout.preferredHeight: 38
            implicitWidth: tabText.implicitWidth

            Accessible.role: Accessible.Button
            Accessible.name: tabItem.label
            activeFocusOnTab: true

            // margin 向四周扩出命中区, 不影响布局对齐 (首个 tab 仍与页面内容左缘平齐)
            HoverHandler {
                id: tabHover

                margin: ThemeTokens.Spacing.s3
            }

            TapHandler {
                margin: ThemeTokens.Spacing.s3
                onTapped: root.activated(tabItem.index)
            }

            Keys.onReturnPressed: root.activated(tabItem.index)
            Keys.onSpacePressed: root.activated(tabItem.index)

            Label {
                id: tabText

                anchors.top: parent.top
                anchors.topMargin: ThemeTokens.Spacing.s2
                anchors.horizontalCenter: parent.horizontalCenter
                text: tabItem.label
                color: tabItem.current
                    ? ThemeTokens.Palette.primaryFg
                    : (tabHover.hovered ? ThemeTokens.Palette.surfaceText : ThemeTokens.Palette.surfaceVariantText)
                font.pixelSize: ThemeTokens.TypeScale.body
                font.weight: tabItem.current ? ThemeTokens.TypeScale.bold : ThemeTokens.TypeScale.regular
            }

            Rectangle {
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter
                width: tabText.implicitWidth
                height: 2
                radius: 1
                visible: tabItem.current
                color: ThemeTokens.Palette.primaryFg
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: -ThemeTokens.Spacing.s2
                visible: tabItem.activeFocus
                radius: ThemeTokens.Spacing.radiusSm
                color: "transparent"
                border.color: ThemeTokens.Palette.focusRing
                border.width: 2
            }
        }
    }

    Item {
        Layout.fillWidth: true
    }
}
