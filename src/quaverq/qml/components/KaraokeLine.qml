pragma ComponentBehavior: Bound

import QtQuick

// 逐字渐进高亮 (karaoke wipe) 歌词行: 每个词双层 Text —— 底层未唱色,
// 顶层 clip 容器内已唱色, clip 宽度 = fraction * 词宽, 从左到右扫亮.
// fraction = (positionMs - startMs) / durationMs, 与桌面歌词
// DesktopLyricsWindow._word_fractions 同构; position tick (~100ms) 之间
// 由 Behavior 线性追赶, 视觉连续推进, 暂停时 tick 停则动画自然静止.
Item {
    id: root

    // [{text, startMs, durationMs}] — 与 LyricLineListModel 的 words 角色同构
    property var words: []
    property int positionMs: 0
    property color sungColor: "#1d9a60"
    property color unsungColor: "#9aa3af"
    property string fontFamily: ""
    property int fontPixelSize: 22
    property int fontWeight: Font.DemiBold
    property bool fontItalic: false
    // tick 之间的线性追赶时长; 0 = 瞬时 (reduceMotion), 调用方传 Motion.durFast
    property int wipeDurationMs: 120

    // 贪心分行: 词为原子不拆, 行宽超出可用宽度才折行; 每词附带测量宽 w + 全局 index
    readonly property var lineGroups: {
        const source = root.words
        const maxW = root.width
        if (!source || source.length === 0 || maxW <= 0)
            return []
        // advanceWidth 是方法调用, 不会自动建立字体依赖; 读 metrics.font 全部子属性
        // 挂上依赖 —— 字体任一属性变化时 metrics 先更新, 本绑定随后用新字体重排
        const _fontDep = [metrics.font.family, metrics.font.pixelSize, metrics.font.weight, metrics.font.italic]
        const lines = []
        let line = []
        let lineW = 0
        for (let i = 0; i < source.length; ++i) {
            const text = String(source[i].text ?? "")
            const w = Math.ceil(metrics.advanceWidth(text))
            if (line.length > 0 && lineW + w > maxW) {
                lines.push(line)
                line = []
                lineW = 0
            }
            line.push({
                index: i,
                text: text,
                startMs: Number(source[i].startMs ?? 0),
                durationMs: Number(source[i].durationMs ?? 0),
                w: w
            })
            lineW += w
        }
        if (line.length > 0)
            lines.push(line)
        return lines
    }

    implicitHeight: lineColumn.implicitHeight

    FontMetrics {
        id: metrics

        font.family: root.fontFamily
        font.pixelSize: root.fontPixelSize
        font.weight: root.fontWeight
        font.italic: root.fontItalic
    }

    Column {
        id: lineColumn

        anchors.horizontalCenter: parent.horizontalCenter

        Repeater {
            model: root.lineGroups

            delegate: Row {
                id: lineRow

                required property var modelData

                anchors.horizontalCenter: parent.horizontalCenter

                Repeater {
                    model: lineRow.modelData

                    delegate: Item {
                        id: wordItem

                        required property var modelData

                        objectName: "karaokeWord-" + wordItem.modelData.index
                        // 0..1: 词前 0 / 词中 elapsed/duration / 词后 1;
                        // duration<=0 视为瞬时词, pos 到点即满格 (兼防除零)
                        readonly property real sungFraction: {
                            const pos = root.positionMs
                            const start = wordItem.modelData.startMs
                            if (pos < start)
                                return 0
                            const dur = wordItem.modelData.durationMs
                            if (dur <= 0)
                                return 1
                            return Math.min(1, (pos - start) / dur)
                        }
                        readonly property alias wipeWidth: wipeClip.width

                        width: wordItem.modelData.w
                        height: baseText.implicitHeight

                        Text {
                            id: baseText

                            text: wordItem.modelData.text
                            color: root.unsungColor
                            font.family: root.fontFamily
                            font.pixelSize: root.fontPixelSize
                            font.weight: root.fontWeight
                            font.italic: root.fontItalic
                        }

                        Item {
                            id: wipeClip

                            clip: true
                            width: wordItem.width * wordItem.sungFraction
                            height: wordItem.height
                            visible: width > 0

                            Behavior on width {
                                enabled: root.wipeDurationMs > 0
                                NumberAnimation {
                                    duration: root.wipeDurationMs
                                    easing.type: Easing.Linear
                                }
                            }

                            Text {
                                text: wordItem.modelData.text
                                color: root.sungColor
                                font.family: root.fontFamily
                                font.pixelSize: root.fontPixelSize
                                font.weight: root.fontWeight
                                font.italic: root.fontItalic
                            }
                        }
                    }
                }
            }
        }
    }
}
