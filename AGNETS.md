# Project Memory

**除非明确要求使用英文交流，否则所有的交流和文档均使用中文**。

LLM 约定：

<AGNET-TODO> 表示需要 AGNET 进行补充的内容，AGNET 需要根据上下文进行合理的补充，确保内容完整且符合项目需求。

## 项目使用的库

<AGNET-TODO>

## 开发可用命令

<AGNET-TODO>

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
