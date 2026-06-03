pragma Singleton

import QtQuick

QtObject {
    readonly property int durFast: 120
    readonly property int durMed: 220
    readonly property int durSlow: 320

    readonly property int easeOut: Easing.OutCubic
    readonly property int easeIn: Easing.InCubic
    readonly property int easeStd: Easing.InOutCubic
}
