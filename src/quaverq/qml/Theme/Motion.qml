pragma Singleton

import QtQuick

QtObject {
    readonly property int durFast: Theme.reducedMotion ? 0 : 120
    readonly property int durMed: Theme.reducedMotion ? 0 : 220
    readonly property int durSlow: Theme.reducedMotion ? 0 : 320

    readonly property int easeOut: Easing.OutCubic
    readonly property int easeIn: Easing.InCubic
    readonly property int easeStd: Easing.InOutCubic
}
