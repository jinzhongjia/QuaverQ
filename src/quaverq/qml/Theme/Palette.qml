pragma Singleton

import QtQuick

// QQ 音乐 PC 风格配色 (见 .claude/skills/qq-music-design)。
// 亮色为主：品牌绿 #31C27C + 白底 #FFF + 浅灰侧栏 #F5F5F7 + 文本 #333/#999。
// 深色为打磨过的对应版（同品牌绿，中性深灰层级）。所有 token 名保持稳定，
// 组件只绑定名字、不写裸 hex；换肤只动本文件。
QtObject {
    // ---- 背景层 ----
    readonly property color background: Theme.dark ? "#1b1c1f" : "#ffffff"
    readonly property color surface: Theme.dark ? "#232428" : "#ffffff"
    readonly property color surfaceElevated: Theme.dark ? "#2a2b30" : "#ffffff"
    readonly property color surfaceVariant: Theme.dark ? "#2e3036" : "#f5f5f7"
    readonly property color surfaceContainerHigh: Theme.dark ? "#34363d" : "#ebebeb"
    readonly property color sidebar: Theme.dark ? "#1f2024" : "#f5f5f7"

    // ---- 文本 ----
    readonly property color surfaceText: Theme.dark ? "#f0f1f3" : "#333333"
    readonly property color surfaceVariantText: Theme.dark ? "#9a9ca2" : "#767676"

    // ---- 描边 / 窗口边框 ----
    readonly property color outline: Theme.dark ? "#3a3c42" : "#e0e0e0"
    readonly property color outlineMuted: Theme.dark ? "#2c2e33" : "#f0f0f0"
    readonly property color windowBorder: Theme.dark ? "#4a4c52" : "#d0d4da"
    readonly property color windowBorderInactive: Theme.dark ? "#34363b" : "#e0e0e0"

    // ---- 品牌强调色 (QQ 音乐绿) ----
    readonly property color primary: "#31c27c"
    readonly property color primaryHover: Theme.dark ? "#3ace8a" : "#2caf6f"
    readonly property color primaryActive: Theme.dark ? "#2cb074" : "#28a065"
    // 品牌绿直接作前景 (文字 / 字形图标 / 下划线 / 选中指示条) 时用这个:
    // #31c27c 在白底只有 ~2.3:1, 亮色压暗到 ~3.6:1; 深色底品牌绿 >7:1 直接复用.
    // 大色块填充 (播放键 / 登录按钮 / 进度条) 仍用 primary 保持品牌观感.
    readonly property color primaryFg: Theme.dark ? "#31c27c" : "#1d9a60"
    readonly property color primaryText: "#ffffff"
    readonly property color primaryContainer: Theme.dark ? "#173c2c" : "#e7f7ef"

    // ---- 次级强调 (徽章 / 空间音频蓝等) ----
    readonly property color accent: Theme.dark ? "#5b9bff" : "#3b82f6"
    readonly property color accentContainer: Theme.dark ? "#1e2a40" : "#e8f0fe"
    readonly property color accentText: "#ffffff"

    // ---- 封面占位 ----
    readonly property color albumSurface: Theme.dark ? "#2a2c32" : "#f0f0f2"
    readonly property color albumAccent: "#31c27c"

    // ---- 状态色 ----
    readonly property color error: Theme.dark ? "#f87171" : "#dc2626"
    readonly property color warning: Theme.dark ? "#fbbf24" : "#e08600"

    // ---- 交互状态 ----
    readonly property color stateHover: Theme.dark ? "#2a2c31" : "#f4f4f5"
    readonly property color statePressed: Theme.dark ? "#34363d" : "#ebebeb"
    readonly property color stateSelected: primaryContainer
    readonly property color stateDisabled: Theme.dark ? "#34363b" : "#e0e0e0"
    readonly property color focusRing: primaryFg
    readonly property color scrim: Theme.dark ? "#99000000" : "#66000000"
}
