import QtQuick
import QtQuick.Controls.Basic
import "../Theme" as ThemeTokens

// 统一样式 ToolTip: token 配色 + 600ms 延迟; 贴近窗口顶/底时自动翻到另一侧, 不被窗口边裁掉.
ToolTip {
    id: root

    delay: 600
    margins: ThemeTokens.Spacing.s2
    padding: ThemeTokens.Spacing.s2
    horizontalPadding: ThemeTokens.Spacing.s3

    function chooseSide() {
        if (!parent)
            return
        const windowY = parent.mapToItem(null, 0, 0).y
        const above = -implicitHeight - ThemeTokens.Spacing.s2
        root.y = windowY + above >= 0 ? above : parent.height + ThemeTokens.Spacing.s2
    }

    onAboutToShow: chooseSide()

    contentItem: Label {
        text: root.text
        color: ThemeTokens.Palette.surfaceText
        font.pixelSize: ThemeTokens.TypeScale.caption
        wrapMode: Text.WordWrap
    }

    background: Rectangle {
        radius: ThemeTokens.Spacing.radiusSm
        color: ThemeTokens.Palette.surfaceContainerHigh
        border.color: ThemeTokens.Palette.outline
    }
}
