# Windows 11 任务栏歌词渲染 Python 技术实现文档

本文档详细介绍了如何使用 Python 在 Windows 11 的任务栏中嵌入并渲染歌词窗口。本方案基于最新的开源研究成果，针对 Windows 11 任务栏的特殊结构和渲染机制（如 Acrylic 模糊效果）提供了经过验证的解决方案。

## 一、 Windows 11 任务栏架构解析

在 Windows 10 时代，开发者通常使用 `FindWindowEx` 遍历寻找 `ReBarWindow32` 或 `MSTaskSwWClass` 来嵌入窗口。然而，Windows 11 使用 XAML 彻底重写了任务栏，传统的类名层级结构已经失效。

根据开源项目 Taskbar-Lyrics 的源码分析，Windows 11 任务栏的正确操作方式如下：

1.  **主窗口句柄**：依然是 `Shell_TrayWnd`，这是唯一可以直接通过 `FindWindow` 获取的传统 Win32 句柄。
2.  **子元素定位**：内部结构不再是标准的 Win32 子窗口，而是 UI Automation 元素。必须使用 Microsoft UI Automation (UIA) 接口来查找任务栏框架、系统托盘、开始按钮等元素的精确屏幕坐标。
3.  **Acrylic 模糊限制**：Windows 11 强制对任务栏应用材质效果。如果直接嵌入普通窗口，内容会被模糊处理。**核心突破点**是：在创建嵌入窗口时，必须使用 `WS_EX_NOREDIRECTIONBITMAP` 扩展样式。

## 二、 核心技术栈选择

为了在 Python 中实现这一目标，我们需要以下技术栈组合：

*   **窗口创建与嵌入**：使用 `ctypes` 调用底层的 Win32 API (`CreateWindowEx`, `SetParent`)。
*   **UI 自动化定位**：使用 `uiautomation` 库（封装了 COM 接口）来获取 Windows 11 任务栏内部各个 XAML 元素的边界矩形（Bounding Rectangle），以计算歌词窗口应该放置的位置。
*   **透明渲染**：由于使用了 `WS_EX_NOREDIRECTIONBITMAP`，传统的 GDI/GDI+ 绘图将失效。必须使用基于 DirectX 的现代渲染管线。在 Python 中，可以使用 `pywin32` 配合 `win32gui` 和 Direct2D/DirectComposition 接口，或者使用 PyQt/PySide 的现代渲染后端。

## 三、 详细实现步骤与代码示例

以下是使用纯 Python (依赖 `ctypes` 和 `uiautomation`) 实现核心嵌入逻辑的完整指南。

### 1. 环境准备

首先需要安装用于 UI 自动化的 Python 库：

```bash
pip install uiautomation
```

### 2. 获取任务栏及内部元素位置

由于 Windows 11 任务栏图标可能居中或居左，我们需要动态计算可用空间。

```python
import ctypes
from ctypes import wintypes
import uiautomation as auto

user32 = ctypes.windll.user32

def get_taskbar_info():
    # 1. 获取任务栏主窗口句柄
    taskbar_hwnd = user32.FindWindowW("Shell_TrayWnd", None)
    if not taskbar_hwnd:
        raise Exception("无法找到 Windows 任务栏 (Shell_TrayWnd)")

    # 2. 使用 UIAutomation 查找任务栏内部元素
    # 获取任务栏主控元素
    taskbar_control = auto.ControlFromHandle(taskbar_hwnd)
    
    # 查找任务栏框架
    taskbar_frame = taskbar_control.Control(ClassName="Taskbar.TaskbarFrameAutomationPeer")
    
    # 查找任务列表（应用图标区域）
    task_list = taskbar_control.Control(ClassName="Taskbar.TaskListButtonAutomationPeer")
    
    # 查找系统托盘区域
    system_tray = taskbar_control.Control(AutomationId="SystemTrayIcon")

    # 获取各自的屏幕坐标矩形 (BoundingRectangle)
    frame_rect = taskbar_frame.BoundingRectangle if taskbar_frame.Exists(0) else None
    list_rect = task_list.BoundingRectangle if task_list.Exists(0) else None
    tray_rect = system_tray.BoundingRectangle if system_tray.Exists(0) else None

    return {
        "hwnd": taskbar_hwnd,
        "frame": frame_rect,
        "list": list_rect,
        "tray": tray_rect
    }
```

### 3. 创建抗模糊的嵌入窗口

这是整个方案的**最核心部分**。必须包含特定的窗口样式组合，特别是 `WS_EX_NOREDIRECTIONBITMAP`。

```python
import win32con
import win32gui
import win32api

def create_lyric_window(parent_hwnd):
    # 注册窗口类
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = window_proc # 你需要定义的窗口消息处理函数
    wc.lpszClassName = "PythonTaskbarLyricsClass"
    wc.hInstance = win32api.GetModuleHandle(None)
    
    class_atom = win32gui.RegisterClass(wc)

    # 核心样式定义
    # WS_EX_NOREDIRECTIONBITMAP (0x00200000): 阻止系统为该窗口创建重定向位图，解决 Win11 模糊问题
    # WS_EX_TRANSPARENT: 鼠标事件穿透
    # WS_EX_NOPARENTNOTIFY: 不通知父窗口
    ex_style = win32con.WS_EX_NOPARENTNOTIFY | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_NOACTIVATE | 0x00200000
    
    style = win32con.WS_CHILD | win32con.WS_VISIBLE

    # 创建窗口，直接将 parent_hwnd (任务栏句柄) 作为父窗口
    hwnd = win32gui.CreateWindowEx(
        ex_style,
        class_atom,
        "PythonTaskbarLyrics",
        style,
        0, 0, 0, 0, # 初始位置大小，稍后调整
        parent_hwnd,
        0,
        wc.hInstance,
        None
    )
    
    return hwnd

def window_proc(hwnd, msg, wparam, lparam):
    if msg == win32con.WM_DESTROY:
        win32gui.PostQuitMessage(0)
        return 0
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
```

### 4. 动态计算位置与调整

根据获取到的 UIAutomation 矩形，计算歌词窗口应该放置的具体 X/Y 坐标和宽度。

```python
def update_window_position(lyric_hwnd, taskbar_info):
    frame = taskbar_info["frame"]
    task_list = taskbar_info["list"]
    tray = taskbar_info["tray"]
    
    if not frame:
        return

    # 假设我们要将歌词放在应用图标和系统托盘之间
    # 任务栏是居中的情况
    if task_list and tray:
        # 起始位置在任务列表的右侧
        x_offset = task_list[2] # right
        # 宽度到系统托盘的左侧
        width = tray[0] - x_offset # left - x_offset
    else:
        # 默认回退方案
        x_offset = 100
        width = 400

    height = frame[3] - frame[1] # bottom - top

    # 移动并调整窗口大小
    user32.MoveWindow(lyric_hwnd, x_offset, 0, width, height, False)
    # 强制重绘
    user32.RedrawWindow(lyric_hwnd, None, None, win32con.RDW_INVALIDATE | win32con.RDW_UPDATENOW)
```

### 5. 关于渲染的特别说明

由于我们使用了 `WS_EX_NOREDIRECTIONBITMAP`，标准的 `win32gui.DrawText` 或 PyQt 的普通 `QPainter` 绘制将无法显示在屏幕上。

你必须使用 **DirectComposition** 结合 **Direct2D** 来渲染。在 Python 中，这通常需要借助 `comtypes` 库直接调用 DirectX 接口，或者使用封装好的第三方图形库。

一个简化的替代思路是：如果你发现纯 Python 调用 DirectX 过于复杂，可以考虑用 C++ 编写一个极小的 DLL（参考 go-musicfox-taskbar-lyrics），专门负责 `CreateWindowEx` 和 Direct2D 渲染，然后通过 Python 的 `ctypes` 传递歌词文本给这个 DLL。

## 四、 总结与注意事项

1.  **UIAutomation 性能**：获取 UI 元素树可能会有轻微延迟，建议在后台线程定期或在收到任务栏变化消息时更新坐标，而不是高频轮询。
2.  **高 DPI 适配**：Windows 11 下必须处理 DPI 缩放。在 Python 脚本开头调用 `ctypes.windll.shcore.SetProcessDpiAwareness(2)` 开启 Per-Monitor V2 DPI 感知，否则 UIAutomation 获取的坐标与 Win32 API 需要的坐标会不匹配。
3.  **深浅色主题**：通过读取注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\SystemUsesLightTheme` 来判断系统当前主题，并动态调整歌词文字颜色。
