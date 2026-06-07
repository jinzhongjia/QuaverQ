# Architecture Contracts

本文件登记**架构级别**的硬约束。任何新增功能、controller、view 都必须遵守，否则会在某种 corner case 下崩坏（通常是 back-nav、多实例并存、生命周期错配）。

跟 [`CLAUDE.md`](CLAUDE.md) 的区别：`CLAUDE.md` 是日常协作规范（commit / lint / TDD 等流程），本文件是**模式与契约**。

---

## 1. 栈式视图必须自持状态

任何会被 `push` 到导航栈（`StackView`、navigation history 等）的 view，**必须**自己持有它依赖的可变 controller。多个相同类型的 view 实例**禁止**共享同一个 controller singleton。

### Why

视图栈生命周期 ≠ 单例 controller 生命周期：
- View 是 push / pop 多实例的，同一时刻多个实例可能共存于栈中
- Singleton controller 的 state 只有一份，后 push 的会覆写前 push 的

后果：用户 pop 回上一层时，视图渲染的还是被覆写后的 state，表面上像"返回键没反应"。

### How to apply

1. **新增可栈页面时**：给它配套写一个 `XxxController(QObject)` + `XxxControllerFactory(QObject)`。Factory 自己是单例（持有 `ServiceController` 引用），通过 `setContextProperty("XxxControllerFactory", factory)` 注入 QML。
2. **View 端持有**：View 的 `Component.onCompleted` 里调 `factory.create(root)` 拿到新 controller，存到自己的 property 上。**必须** `parent=root` 让 Qt parent-child 接管销毁——StackView pop 时 view 销毁，controller 自动 GC，所有 signal slot 自动断开。
3. **不要在 `Main.qml` 顶层做 `readonly property var xxxController: XxxController`**——这是单例模式的入口，跟"per-view 实例"原则冲突。
4. **不可栈的单例 controller 不受影响**：`AppController` / `HomeController` / `LibraryController` / `PlayerController` / `LyricController` / `MprisController` / `SongDetailController` / `ServiceController` / `SettingsController` / `CoverController` 都是全局唯一（同时只有一个实例显示），继续走 `setContextProperty` 单例注入即可。

### 反例（修复前）

- `DetailController` 曾是 singleton，push 到 detail stack 时只有一份。复现：搜歌手 → 进艺人页 → 切"全部专辑" tab → 点专辑卡片 → 按返回 → 看到仍是专辑内容（因为底层 artist View 共享同一个 controller，状态被覆写）。**2026-06-08 修复**：改成 `DetailControllerFactory` 模式（PR feat/qqmusic-api-integration-2）。

### 自检 checklist

新增 detail-like 视图前先问：
- [ ] 这个 view 是放到 `contentStack.push(...)` 进栈的吗？
- [ ] 它的 controller 有可变 state 吗（model / loading flag / current entity ID）？

如果两个都是 yes → **必须**走 factory 模式，不能 singleton。
