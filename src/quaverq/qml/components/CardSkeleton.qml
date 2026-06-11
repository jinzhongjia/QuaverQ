import QtQuick
import QtQuick.Layouts
import "../Theme" as ThemeTokens

// Card 的加载骨架: 方形封面块 + 标题/副标题条 (几何对齐真实卡片)
Item {
    id: root

    implicitWidth: 160
    implicitHeight: column.implicitHeight

    ColumnLayout {
        id: column

        width: root.width
        spacing: ThemeTokens.Spacing.s3

        SkeletonRect {
            Layout.fillWidth: true
            Layout.preferredHeight: root.width
            radius: ThemeTokens.Spacing.radiusLg
        }

        SkeletonRect {
            Layout.preferredWidth: Math.round(root.width * 0.7)
            Layout.preferredHeight: 14
        }

        SkeletonRect {
            Layout.preferredWidth: Math.round(root.width * 0.45)
            Layout.preferredHeight: 12
        }
    }
}
