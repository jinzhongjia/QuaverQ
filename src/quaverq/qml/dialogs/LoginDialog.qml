import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../Theme" as ThemeTokens

Dialog {
    id: root

    property var appController
    objectName: "loginDialog"

    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: Math.min(parent ? parent.width - ThemeTokens.Spacing.s8 : 420, 420)
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? Math.round((parent.height - implicitHeight) / 2) : 0
    padding: ThemeTokens.Spacing.s6

    function startLogin(force) {
        if (!force && root.appController && root.appController.loginState === "expired")
            return
        if (root.appController && !root.appController.authed && !root.appController.loggingIn)
            root.appController.loginByQrCode()
    }

    onOpened: startLogin(false)

    Connections {
        target: root.appController

        function onAuthChanged(authed, reason) {
            if (authed)
                root.close()
        }
    }

    background: Rectangle {
        radius: ThemeTokens.Spacing.radiusLg
        color: ThemeTokens.Palette.surface
        border.color: ThemeTokens.Palette.outline
    }

    contentItem: ColumnLayout {
        spacing: ThemeTokens.Spacing.s5

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s4

            ColumnLayout {
                Layout.fillWidth: true
                spacing: ThemeTokens.Spacing.s2

                Label {
                    Layout.fillWidth: true
                    text: qsTr("登录 QQ 音乐")
                    color: ThemeTokens.Palette.onSurface
                    font.pixelSize: ThemeTokens.TypeScale.h2
                    font.weight: ThemeTokens.TypeScale.medium
                    elide: Text.ElideRight
                }

                Label {
                    Layout.fillWidth: true
                    text: qsTr("扫码后会保存登录态用于播放和资料库同步")
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.caption
                    wrapMode: Text.WordWrap
                }
            }

            Button {
                id: closeButton

                Layout.preferredWidth: ThemeTokens.Spacing.toolHitSize
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                text: "×"
                Accessible.name: qsTr("关闭")
                onClicked: root.close()

                contentItem: Label {
                    text: closeButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.h2
                }

                background: Rectangle {
                    radius: width / 2
                    color: closeButton.down
                        ? ThemeTokens.Palette.statePressed
                        : closeButton.hovered ? ThemeTokens.Palette.stateHover : "transparent"
                }
            }
        }

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 236
            Layout.preferredHeight: 236
            radius: ThemeTokens.Spacing.radiusMd
            color: ThemeTokens.Palette.background
            border.color: ThemeTokens.Palette.outline

            Image {
                anchors.centerIn: parent
                width: 212
                height: 212
                visible: root.appController && root.appController.qrcodeDataUrl.length > 0
                source: visible ? root.appController.qrcodeDataUrl : ""
                sourceSize.width: 212
                sourceSize.height: 212
                fillMode: Image.PreserveAspectFit
            }

            BusyIndicator {
                anchors.centerIn: parent
                running: visible
                visible: root.appController
                    && root.appController.loggingIn
                    && root.appController.qrcodeDataUrl.length === 0
            }

            Label {
                anchors.centerIn: parent
                width: parent.width - ThemeTokens.Spacing.s6
                visible: !root.appController
                    || (!root.appController.loggingIn
                        && root.appController.qrcodeDataUrl.length === 0)
                text: qsTr("点击重试获取二维码")
                color: ThemeTokens.Palette.onSurfaceVariant
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                font.pixelSize: ThemeTokens.TypeScale.bodySm
            }
        }

        Label {
            Layout.fillWidth: true
            text: root.appController && root.appController.loginMessage.length > 0
                ? root.appController.loginMessage
                : qsTr("准备登录")
            color: root.appController
                && (root.appController.loginState === "error"
                    || root.appController.loginState === "expired")
                ? ThemeTokens.Palette.error
                : ThemeTokens.Palette.onSurfaceVariant
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            font.pixelSize: ThemeTokens.TypeScale.bodySm
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: ThemeTokens.Spacing.s3

            Button {
                id: retryButton

                Layout.fillWidth: true
                Layout.preferredHeight: ThemeTokens.Spacing.toolHitSize
                text: root.appController && root.appController.loggingIn ? qsTr("等待确认") : qsTr("重新获取")
                enabled: root.appController && !root.appController.loggingIn && !root.appController.authed
                Accessible.name: text
                onClicked: root.startLogin(true)

                contentItem: Label {
                    text: retryButton.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: retryButton.enabled ? ThemeTokens.Palette.onPrimary : ThemeTokens.Palette.onSurfaceVariant
                    font.pixelSize: ThemeTokens.TypeScale.bodySm
                    font.weight: ThemeTokens.TypeScale.medium
                }

                background: Rectangle {
                    radius: ThemeTokens.Spacing.radiusMd
                    color: retryButton.enabled
                        ? ThemeTokens.Palette.primary
                        : ThemeTokens.Palette.stateDisabled
                }
            }
        }
    }
}
