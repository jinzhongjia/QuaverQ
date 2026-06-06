# src/quaverq/qml/dialogs

模态弹窗。每个文件导出一个 `Dialog`（Qt Quick Controls Basic），由 [`Main.qml`](../README.md) 拥有并按需 `open()`。

| 组件 | 作用 |
| --- | --- |
| `LoginDialog.qml` | **二维码登录对话框**。`open()` 后自动调用 `appController.loginByQrCode()` 启动扫码流程，显示二维码图像 + 状态文案；`onAuthChanged(authed)` 命中 `authed=true` 自动关闭。`closePolicy: CloseOnEscape \| CloseOnPressOutside`，凭据过期态 (`loginState === "expired"`) 时不会重复触发登录。 |

## 约定

- **`property var appController` 注入**：由 `Main.qml` 在挂载时传，不直接访问 `AppController` context property，方便复用。
- **`modal: true`**：登录是阻塞流程，不让用户在期间操作背景。
- **居中布局**：`x` / `y` 跟随 `parent`，宽度取 `min(parent.width - s8, 420)` 在小窗时不会溢出。
