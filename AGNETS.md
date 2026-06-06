# Project Memory

**除非明确要求使用英文交流，否则所有的交流和文档均使用中文**。

LLM 约定：

<AGNET-TODO> 表示需要 AGNET 进行补充的内容，AGNET 需要根据上下文进行合理的补充，确保内容完整且符合项目需求。

## 项目使用的库

<AGNET-TODO>

## 开发可用命令

- `uv sync --dev` — 安装运行 + 开发依赖 (含 ruff / pytest / nuitka)
- `uv run pytest` — 跑所有单元测试 (testpaths=tests, asyncio_mode=auto)
- `uv run quaverq` — 启动应用 (等价 `python -m quaverq`)
- `uv run python scripts/lint.py` — 跑 lint (ruff check + ruff format --check + pyside6-qmllint)
- `uv run python scripts/lint.py --fix` — 自动修复可修的 ruff 问题并执行 `ruff format`
- `uv run python scripts/lint.py --py` / `--qml` — 只跑其中一项
- `uv run python build.py --appimage` — 打 AppImage (Nuitka standalone + linuxdeploy)

## 项目使用的 Lint

- **Python**: `ruff check` + `ruff format`, 配置在 `pyproject.toml [tool.ruff]`. 规则集 F/E/W/I/B/UP/C4/SIM/RET/PIE, line-length 100, target-version py310.
- **QML**: `pyside6-qmllint` (随 PySide6 自带), 默认配置在 `.qmllint.ini` (由 `pyside6-qmllint --write-defaults` 生成). `--max-warnings=0` 严格模式: ContextProperty 等已知合法用法用 inline `// qmllint disable <rule>` 注释精确抑制, 不放水整条规则.
- **CI**: 见 `.github/workflows/lint.yml`, push/PR 自动触发.

## commit 消息生成规范

**使用 `git diff` 生成符合 Conventional Commit 格式的提交消息，格式为 `type(scope): 简短描述` + 空行 + 多个带 `-` 的描述点。必须直接输出提交消息内容，不要包含任何 markdown 格式或额外解释。如果提供了提交历史，参考其风格保持一致。**

默认使用中文!
强制要求：commit message 不要带有任何和 LLM 相关的 Co-Authored-By

## 开发必须做的事

<AGNET-TODO>

## 开发禁止做的事

<AGNET-TODO>

## Readme 维护

每个 src 下的目录都需要一个 README.md 文件，内容包括：

- 目录介绍
- 结构说明
- 业务逻辑
- 对外暴露的接口或者方法
- 接口定义说明
- 与其他目录之间依赖的关系

每次更新 src 下目录的代码时，检查 README.md 是否需要更新，保持文档与代码一致。
