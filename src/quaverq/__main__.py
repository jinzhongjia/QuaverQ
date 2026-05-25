"""QuaverQ 入口 (占位).

旧的 PyWebView + Svelte 入口已按 docs/design.md §12 清理. PySide6 + Qt Quick
启动在 design §14 的 Q0 阶段落地; 在此之前直接运行 `quaverq` 只会打印提示.

Q0 落地后, 这里将:
  1. 创建 QApplication + qasync EventLoop (见 design §8.4)
  2. 实例化 AppController / ServiceController / PlayerController / LibraryController
  3. QQmlApplicationEngine.load("qml/Main.qml")
  4. state.restore() → 注入 PlayerController.queue (不自动播放)
"""

from __future__ import annotations

import logging
import sys

from .config import load as load_config

logger = logging.getLogger("quaverq")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_config()
    logger.error(
        "PySide6 + Qt Quick 入口尚未实现. 请先按 docs/design.md §14 执行 Q0."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
