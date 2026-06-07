#!/usr/bin/env python3
"""QuaverQ 统一 lint 入口.

用法:
    uv run python scripts/lint.py           # 检查 Python + QML, 不修改文件
    uv run python scripts/lint.py --fix     # ruff 自动修复 + ruff format
    uv run python scripts/lint.py --py      # 仅跑 Python lint (ruff check + format --check)
    uv run python scripts/lint.py --qml     # 仅跑 QML lint (pyside6-qmllint)

退出码: 0 = 全部通过; 非 0 = 至少一项有未通过的检查.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QML_ROOT = ROOT / "src" / "quaverq" / "qml"


def _resolve_tool(name: str) -> str:
    """在当前 PATH 上把工具名解析成绝对路径.

    Windows 的 ``CreateProcess`` 不会按 ``PATHEXT`` 自动补 ``.exe`` / ``.cmd``,
    所以 ``subprocess.run(["ruff", ...])`` 在 Windows 上会 FileNotFoundError.
    ``shutil.which`` 会按 PATHEXT 搜, 跨平台返回带扩展名的真实路径.

    本脚本预期经 ``uv run python scripts/lint.py`` 拉起, 此时 venv 已激活,
    ``ruff`` / ``pyside6-qmllint`` 都在 PATH 上. 找不到则抛 FileNotFoundError,
    提示用户用 ``uv run`` 启动.
    """
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(
            f"未能在 PATH 上找到可执行 {name!r}; "
            f"请改用 `uv run python scripts/lint.py` 启动 (venv 自动激活)."
        )
    return path


def _run(cmd: list[str], *, label: str) -> int:
    print(f"\n[lint] >> {label}: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    print(f"[lint] << {label}: exit={result.returncode}", flush=True)
    return result.returncode


def _ruff(fix: bool) -> int:
    ruff = _resolve_tool("ruff")
    targets = ["src", "tests", "scripts", "build.py"]
    check = [ruff, "check", *targets]
    fmt = [ruff, "format"]
    if fix:
        return _run([*check, "--fix"], label="ruff check --fix") | _run(
            [*fmt, *targets], label="ruff format"
        )
    return _run(check, label="ruff check") | _run(
        [*fmt, *targets, "--check"], label="ruff format --check"
    )


def _qmllint() -> int:
    qml_files = sorted(str(p) for p in QML_ROOT.rglob("*.qml"))
    if not qml_files:
        print("[lint] 未找到 .qml 文件, 跳过 QML lint")
        return 0
    qmllint = _resolve_tool("pyside6-qmllint")
    # --max-warnings=0: 任何 warning 都让退出码非 0; 项目里合法的特殊用法 (如 ContextProperty)
    # 已用 inline `// qmllint disable <rule>` 注释精确抑制, 不应放水整条规则.
    cmd = [
        qmllint,
        "--max-warnings=0",
        "-I",
        str(QML_ROOT),
        *qml_files,
    ]
    return _run(cmd, label="pyside6-qmllint")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--fix", action="store_true", help="ruff 自动修复 + ruff format")
    parser.add_argument("--py", action="store_true", help="仅跑 Python lint")
    parser.add_argument("--qml", action="store_true", help="仅跑 QML lint")
    args = parser.parse_args()

    if args.fix and args.qml and not args.py:
        print("[lint] --fix 对 QML 不适用 (pyside6-qmllint 不支持自动修复)", file=sys.stderr)

    run_py = args.py or not args.qml
    run_qml = args.qml or not args.py

    rc = 0
    if run_py:
        rc |= _ruff(fix=args.fix)
    if run_qml:
        rc |= _qmllint()

    if rc == 0:
        print("\n[lint] OK 全部通过")
    else:
        print(f"\n[lint] FAIL 退出码 = {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
