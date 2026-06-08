"""debug 脚本跨平台基线测试.

之前: scripts/debug_*.py 全都硬编码 ``~/.config/quaverq/...`` + ``open()`` 无 encoding,
在 Windows (路径不对 + cp936 默认编码) 上跑必崩.

本组测试守护:
1. 不再有硬编码 POSIX 路径 (走 ``quaverq.config.CONFIG_DIR``).
2. 不再有无 encoding 的 ``open()`` (隐式 locale 编码会 GBK 崩).
3. 脚本模块本身可 import (路径解析延迟到 ``main()`` 内, import 期不触发 expanduser 之类).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_DEBUG_SCRIPTS = sorted(_SCRIPTS_DIR.glob("debug_*.py"))


@pytest.mark.parametrize("script", _DEBUG_SCRIPTS, ids=lambda p: p.name)
def test_no_hardcoded_posix_config_path(script: Path):
    """debug 脚本不应硬编码 ``~/.config/quaverq/...`` (Windows 上路径错)."""
    text = script.read_text(encoding="utf-8")
    assert "~/.config/quaverq" not in text, (
        f"{script.name} 仍硬编码 POSIX 路径; 应改用 `quaverq.config.CONFIG_DIR`"
    )
    assert "~/.cache/quaverq" not in text, (
        f"{script.name} 仍硬编码 POSIX 路径; 应改用 `quaverq.config.CACHE_DIR`"
    )


@pytest.mark.parametrize("script", _DEBUG_SCRIPTS, ids=lambda p: p.name)
def test_text_open_has_explicit_utf8(script: Path):
    """debug 脚本里所有文本模式 ``open(...)`` 必须显式 ``encoding="utf-8"``,
    否则 Windows cp936 locale 下读 Unicode 文件会 GBK 崩 (与 state.py / service.py 同病).

    简单启发: 任何 ``open(<path>)`` 形式 (单参) 都拒. 二进制 ``open(p, "rb")`` 可以放过.
    """
    text = script.read_text(encoding="utf-8")
    # 简易: 查 "open(" 行, 如果缺少 'encoding=' 且不是二进制模式 ('b'), 报错
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "open(" not in line or line.strip().startswith("#"):
            continue
        # 只关心 builtin open; 跳过 .open(), socket.socket.open 等 (这里没用到)
        if ".open(" in line and "open(" not in line.replace(".open(", ""):
            continue
        # 二进制 (含 "rb" / "wb") OK
        if '"rb"' in line or "'rb'" in line or '"wb"' in line or "'wb'" in line:
            continue
        # 显式 encoding 写法
        if "encoding=" in line:
            continue
        # QML / Dialog open() 不是文件 IO (无 path 参), 排除
        # 简易: 含 "Path" 或 "_path" 的行视为文件 open
        if "path" in line.lower():
            pytest.fail(
                f"{script.name}:{lineno} `open()` 无 encoding=, "
                f"Windows 上会 GBK 崩: {line.strip()!r}"
            )


@pytest.mark.parametrize("script", _DEBUG_SCRIPTS, ids=lambda p: p.name)
def test_module_importable(script: Path):
    """脚本应当能被 importlib 加载 (不触发 main / 不解析路径). 防回归: 引入未来出问题的 import-time 副作用."""
    spec = importlib.util.spec_from_file_location(f"_debug_{script.stem}", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 此处 exec_module 会跑顶层代码 (import / 函数定义), 不跑 if __name__ == "__main__": main()
    spec.loader.exec_module(module)
