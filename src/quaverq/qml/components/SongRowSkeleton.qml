import QtQuick
import QtQuick.Layouts
import "../Theme" as ThemeTokens

// SongRow 的加载骨架: 序号位 + 封面块 + 标题/副标题条 + 时长条 (几何对齐真实行)
Item {
    id: root

    // 标题条宽度比例: 调用方按 index 错开, 避免整齐划一的"假"感
    property real titleRatio: 0.42

    implicitHeight: 64

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s4
        anchors.rightMargin: ThemeTokens.Spacing.s4
        spacing: ThemeTokens.Spacing.s4

        Item {
            Layout.preferredWidth: 28
        }

        SkeletonRect {
            Layout.preferredWidth: 46
            Layout.preferredHeight: 46
        }

        ColumnLayout {
            id: textColumn

            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s3

            SkeletonRect {
                Layout.preferredWidth: Math.round(textColumn.width * root.titleRatio)
                Layout.preferredHeight: 14
            }

            SkeletonRect {
                Layout.preferredWidth: Math.round(textColumn.width * 0.26)
                Layout.preferredHeight: 12
            }
        }

        SkeletonRect {
            Layout.preferredWidth: 36
            Layout.preferredHeight: 12
        }
    }
}
