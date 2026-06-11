pragma Singleton

import QtQuick

QtObject {
    readonly property int display: 32
    readonly property int h1: 23
    readonly property int h2: 19
    readonly property int body: 16
    readonly property int bodySm: 14
    // 12 而非 13: 与 bodySm(14) 只差 1px 时层级全靠颜色撑, 拉开到 2px 才有字阶感 (W12)
    readonly property int caption: 12

    readonly property int regular: Font.Normal
    readonly property int medium: Font.Medium
    readonly property int bold: Font.DemiBold
}
