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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QML_ROOT = ROOT / "src" / "quaverq" / "qml"


def _run(cmd: list[str], *, label: str) -> int:
    print(f"\n[lint] >> {label}: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    print(f"[lint] << {label}: exit={result.returncode}", flush=True)
    return result.returncode


def _ruff(fix: bool) -> int:
    check = ["uv", "run", "ruff", "check", "src", "tests", "scripts", "build.py"]
    fmt = ["uv", "run", "ruff", "format"]
    fmt_targets = ["src", "tests", "scripts", "build.py"]
    if fix:
        return _run([*check, "--fix"], label="ruff check --fix") | _run(
            [*fmt, *fmt_targets], label="ruff format"
        )
    return _run(check, label="ruff check") | _run(
        [*fmt, *fmt_targets, "--check"], label="ruff format --check"
    )


def _qmllint() -> int:
    qml_files = sorted(str(p) for p in QML_ROOT.rglob("*.qml"))
    if not qml_files:
        print("[lint] 未找到 .qml 文件, 跳过 QML lint")
        return 0
    # --max-warnings=0: 任何 warning 都让退出码非 0; 项目里合法的特殊用法 (如 ContextProperty)
    # 已用 inline `// qmllint disable <rule>` 注释精确抑制, 不应放水整条规则.
    cmd = [
        "uv",
        "run",
        "pyside6-qmllint",
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
