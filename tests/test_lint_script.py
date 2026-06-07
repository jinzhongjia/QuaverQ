"""scripts/lint.py 的跨平台可执行解析测试.

背景: 原版直接 ``subprocess.run(["uv", "run", "ruff", ...])`` 在 Windows 上
找不到 ``uv`` —— Windows 的 CreateProcess 不会按 PATHEXT 自动补 ``.exe``.
脚本本身就是经 ``uv run python scripts/lint.py`` 拉起的, venv 已激活,
直接调 venv 里的 ``ruff`` / ``pyside6-qmllint`` 即可. 这里测试 ``_resolve_tool``
能在当前平台上找到这俩工具.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_LINT_PY = Path(__file__).resolve().parent.parent / "scripts" / "lint.py"


def _load_lint_module():
    spec = importlib.util.spec_from_file_location("quaverq_lint", _LINT_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_tool_finds_ruff():
    lint = _load_lint_module()
    path = lint._resolve_tool("ruff")
    assert Path(path).is_file()
    # Windows 上必须解析到 .exe / .cmd 等带扩展名的可执行
    if sys.platform == "win32":
        assert Path(path).suffix.lower() in {".exe", ".cmd", ".bat", ".com"}


def test_resolve_tool_finds_qmllint():
    lint = _load_lint_module()
    path = lint._resolve_tool("pyside6-qmllint")
    assert Path(path).is_file()


def test_resolve_tool_raises_on_missing():
    lint = _load_lint_module()
    with pytest.raises(FileNotFoundError, match="not-a-real-tool"):
        lint._resolve_tool("not-a-real-tool")
