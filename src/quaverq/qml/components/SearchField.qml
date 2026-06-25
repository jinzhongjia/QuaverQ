pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

FocusScope {
    id: root

    property alias text: input.text
    property alias placeholderText: input.placeholderText
    property bool loading: false

    // 输入联想: suggestions 由外部 (serviceController.searchSuggestions) 注入
    property var suggestions: []
    property int suggestDebounceMs: 220
    property int highlightedIndex: -1
    property bool suggestDismissed: false
    readonly property bool suggestVisible: !root.suggestDismissed
        && input.activeFocus
        && input.text.length > 0
        && root.suggestions.length > 0

    signal searchRequested(string text)
    signal editingCancelled()
    // debounce 后请求联想 (空串表示清空); 选中某个联想词
    signal suggestRequested(string text)
    signal suggestionChosen(string text)

    implicitWidth: 500
    implicitHeight: ThemeTokens.Spacing.toolHitSize

    function focusInput() {
        input.forceActiveFocus()
        input.selectAll()
    }

    function releaseInputFocus() {
        input.focus = false
        root.focus = false
    }

    function chooseSuggestion(word) {
        suggestTimer.stop()
        root.suggestDismissed = true
        root.suggestionChosen(word)
    }

    Timer {
        id: suggestTimer

        interval: root.suggestDebounceMs
        repeat: false
        onTriggered: root.suggestRequested(input.text)
    }

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: ThemeTokens.Palette.surfaceVariant
        border.color: input.activeFocus ? ThemeTokens.Palette.focusRing : "transparent"
        border.width: input.activeFocus ? 2 : 1
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: ThemeTokens.Spacing.s4
        anchors.rightMargin: ThemeTokens.Spacing.s2
        spacing: ThemeTokens.Spacing.s3

        AppIcon {
            size: 18
            source: "../icons/search.svg"
            color: ThemeTokens.Palette.surfaceVariantText
        }

        TextField {
            id: input

            Layout.fillWidth: true
            selectByMouse: true
            font.pixelSize: ThemeTokens.TypeScale.body
            color: ThemeTokens.Palette.surfaceText
            placeholderTextColor: ThemeTokens.Palette.surfaceVariantText
            Accessible.name: qsTr("搜索")

            onTextChanged: {
                root.highlightedIndex = -1
                root.suggestDismissed = false
                if (input.text.length > 0 && input.activeFocus) {
                    suggestTimer.restart()
                } else {
                    suggestTimer.stop()
                    root.suggestRequested("")  // 清空联想
                }
            }

            onAccepted: {
                if (root.suggestVisible && root.highlightedIndex >= 0)
                    root.chooseSuggestion(root.suggestions[root.highlightedIndex])
                else
                    root.searchRequested(text)
            }

            Keys.onDownPressed: function(event) {
                if (root.suggestVisible) {
                    root.highlightedIndex = Math.min(root.highlightedIndex + 1, root.suggestions.length - 1)
                    event.accepted = true
                } else {
                    event.accepted = false
                }
            }
            Keys.onUpPressed: function(event) {
                if (root.suggestVisible) {
                    root.highlightedIndex = Math.max(root.highlightedIndex - 1, -1)
                    event.accepted = true
                } else {
                    event.accepted = false
                }
            }
            Keys.onEscapePressed: {
                if (root.suggestVisible) {
                    root.suggestDismissed = true  // 先收起联想下拉, 保留输入
                } else {
                    root.editingCancelled()
                }
            }

            background: Item {}
        }

        Button {
            id: clearButton

            visible: input.text.length > 0
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            Accessible.name: qsTr("清空搜索")
            onClicked: {
                input.clear()
                input.forceActiveFocus()
            }

            contentItem: Label {
                text: "×"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                color: ThemeTokens.Palette.surfaceVariantText
                font.pixelSize: ThemeTokens.TypeScale.body
            }

            background: Rectangle {
                radius: width / 2
                color: clearButton.down
                    ? ThemeTokens.Palette.statePressed
                    : clearButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
            }
        }

        Button {
            id: searchButton

            Layout.preferredWidth: 76
            Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize - ThemeTokens.Spacing.s2
            text: root.loading ? qsTr("搜索中") : qsTr("搜索")
            enabled: !root.loading
            Accessible.name: qsTr("执行搜索")
            onClicked: root.searchRequested(input.text)

            contentItem: Label {
                text: searchButton.text
                color: searchButton.enabled ? ThemeTokens.Palette.primaryText : ThemeTokens.Palette.surfaceVariantText
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.pixelSize: ThemeTokens.TypeScale.bodySm
                font.weight: ThemeTokens.TypeScale.medium
            }

            background: Rectangle {
                radius: height / 2
                color: searchButton.enabled ? ThemeTokens.Palette.primary : ThemeTokens.Palette.stateDisabled
            }
        }
    }

    // 输入联想下拉 (悬浮于输入框下方, 不抢焦点以免打断输入)
    Popup {
        id: suggestPopup

        objectName: "suggestPopup"
        y: root.height + ThemeTokens.Spacing.s2
        x: 0
        width: root.width
        padding: ThemeTokens.Spacing.s2
        visible: root.suggestVisible
        focus: false
        closePolicy: Popup.NoAutoClose

        background: Rectangle {
            radius: ThemeTokens.Spacing.radiusMd
            color: ThemeTokens.Palette.surfaceElevated
            border.color: ThemeTokens.Palette.outline
            border.width: 1
        }

        contentItem: ListView {
            implicitHeight: Math.min(contentHeight, 320)
            model: root.suggestions
            clip: true
            interactive: contentHeight > height
            currentIndex: root.highlightedIndex

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: suggestRow

                required property int index
                required property var modelData

                width: ListView.view ? ListView.view.width : 0
                height: 38
                radius: ThemeTokens.Spacing.radiusSm
                color: suggestRow.index === root.highlightedIndex
                    ? ThemeTokens.Palette.stateSelected
                    : suggestRowArea.containsMouse ? ThemeTokens.Palette.stateHover : "transparent"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: ThemeTokens.Spacing.s3
                    anchors.rightMargin: ThemeTokens.Spacing.s3
                    spacing: ThemeTokens.Spacing.s3

                    AppIcon {
                        size: 14
                        source: "../icons/search.svg"
                        color: ThemeTokens.Palette.surfaceVariantText
                    }

                    Label {
                        Layout.fillWidth: true
                        text: suggestRow.modelData
                        color: ThemeTokens.Palette.surfaceText
                        font.pixelSize: ThemeTokens.TypeScale.bodySm
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: suggestRowArea

                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.chooseSuggestion(suggestRow.modelData)
                }
            }
        }
    }
}
