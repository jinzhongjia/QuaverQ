pragma Singleton

import QtQuick

QtObject {
    readonly property int s2: 4
    readonly property int s3: 8
    readonly property int s4: 12
    readonly property int s5: 16
    readonly property int s6: 24
    readonly property int s7: 32
    readonly property int s8: 48

    readonly property int radiusSm: 4
    readonly property int radiusMd: 8
    readonly property int radiusLg: 12
    readonly property int radiusXl: 16

    readonly property int windowWidth: 1080
    readonly property int windowHeight: 720
    readonly property int minWindowWidth: 760
    readonly property int minWindowHeight: 640
    readonly property int headerHeight: 56
    readonly property int playerBarHeight: 104
    readonly property int toolHitSize: 44
}
