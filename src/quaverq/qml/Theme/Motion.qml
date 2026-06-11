pragma Singleton

import QtQuick

QtObject {
    // 减少动效 (无障碍): 由 SettingsController.reduceMotion 经 Main.qml Binding 注入.
    // Qt 6.x 没有系统级 prefers-reduced-motion 接口, 走应用级设置.
    // 开启后时长 token 归零 = 各处过渡瞬时完成 (替换为 instant, 不是放慢);
    // 持续性运动 (Marquee 横滚 / 骨架脉动) 由消费方自行绑定 reduceMotion 停用.
    // 加载指示 (Spinner) 刻意不受控 —— 旋转是"正在工作"的必要反馈.
    property bool reduceMotion: false

    readonly property int durFast: reduceMotion ? 0 : 120
    readonly property int durMed: reduceMotion ? 0 : 220
    readonly property int durSlow: reduceMotion ? 0 : 320

    readonly property int easeOut: Easing.OutCubic
    readonly property int easeIn: Easing.InCubic
    readonly property int easeStd: Easing.InOutCubic
}
