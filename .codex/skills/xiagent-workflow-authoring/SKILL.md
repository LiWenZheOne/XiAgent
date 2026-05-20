---
name: xiagent-workflow-authoring
description: Use when creating or modifying XiAgent workflow YAML/JSON contracts, adding workflow files under workflows/global, or translating user requirements into executable XiAgent workflow DAGs.
---

# XiAgent 工作流编写

## Overview

把用户需求转成 XiAgent 工作流契约时，先匹配现有节点，再创建或修改 `workflows/global/*.workflow.yaml`。默认用 `WorkflowTestBuilder` 或 `python -m xiagent.workflows.testing_cli` 验证无 UI 执行体验。

## Core Workflow

1. 先读项目约束：`AGENTS.md`、现有 `workflows/global/*.workflow.yaml`、`xiagent/nodes/**`、`tests/test_workflow_validator.py`、`tests/test_workflow_testing_*.py`。
2. 从用户描述提炼工作流输入、目标输出、节点顺序、条件分支、人工交互、资产或图片输入输出。
3. 查找可用节点：优先看 `xiagent.nodes.build_node_registry()` 注册了什么，再读各节点的 `NodeDescriptor`、输入输出 schema 和测试。不要凭空写不存在的 `ref`。
4. 如果现有节点不足，立即暂停工作流落盘，列出缺失节点规格：建议 `ref`、职责、输入 schema、输出 schema、错误语义、是否访问资产、是否需要外部凭据、建议测试。然后建议使用 `$xiagent-node-authoring` 先补节点。
5. 节点能力满足后再创建或修改工作流。默认路径是 `workflows/global/<workflow-id>.workflow.yaml`，默认 `scope: global`，除非用户明确要求其他位置或 scope。
6. 用现有加载与校验逻辑验证契约，不绕过运行时或注册表。至少覆盖 schema、节点 ref、边、条件分支、输入路径引用。
7. 用工作流测试构建器验证执行：优先 `WorkflowTestBuilder`；CLI 场景用 `python -m xiagent.workflows.testing_cli <workflow>`。需要交互输入时使用 CLI 交互能力；有图片输出时使用 preview 或图片路径输出。
8. 汇报时给出工作流文件、用到的节点、测试命令和结果；如果暂停在节点缺口，汇报缺口而不是提交半成品工作流。

## Project Constraints

- 工作流模板由开发者维护的 YAML/JSON 契约定义，不做拖拽式或低代码编辑器。
- 第一版只支持 DAG 和条件分支，不支持通用循环。
- 节点输入使用长路径引用，例如 `$workflow.input.topic`、`$nodes.planner.output.plan`。
- 节点输出不覆盖全局状态；运行时必须保留每个节点的输入快照、输出快照、状态、错误和事件。
- 不直接访问 SQLite、资产文件路径或其他模块内部实现；测试也要通过正式服务、运行时和构建器。
- 任务、项目、资产、工作流必须挂到明确的 `user_id` 和 `project_id` 关系下；默认测试用户和项目由构建器创建。

## Structured Output Boundary

- LLM 结构化输出的目标结构写在工作流节点的 `outputs` JSON Schema 中；`prompt` 只描述任务语义，不能作为唯一数据契约。
- 下游节点引用结构化结果前，先确认对应字段已经在上游节点 `outputs` 中声明，例如 `$nodes.character_analysis.output.characters` 必须能被 schema 校验器识别。
- UI `layout` 只描述展示形态，例如 table、tabs、grid、confirm；不要把展示列、页签或文案当作数据结构来源。
- 通用结构化抽取、结构化生成、JSON 解析、schema 校验和失败重试属于节点能力；工作流只选择节点、提供输入、声明输出契约和连接 DAG。
- 需要角色表、分镜表、镜头表等不同结构时，优先复用同一个通用结构化节点并在各自工作流 `outputs` 中声明不同 schema；只有领域逻辑稳定且值得复用时才新增专用节点。

## Framework Change Gate

- 编写或修改工作流时，如果发现必须调整 `BaseNode`、`NodeContext`、运行时服务、工作流校验器、输入解析器、节点注册表等基础框架，先停止落工作流文件，向用户列出修改方案、影响范围、兼容性和测试计划，等待确认后再继续。
- 工作流 skill 只应直接修改工作流契约、工作流测试或与契约验证直接相关的文档；基础框架改造应切换到节点或运行时实现任务，并遵守用户确认门。

## Node Matching Checklist

| Question | Action |
| --- | --- |
| 现有节点能完成需求吗？ | 读取 `NodeDescriptor` 和节点测试，确认输入输出形状。 |
| 节点 ref 是否已注册？ | 查 `build_node_registry()` 或 `NodeRegistry.list()`。 |
| 输出能接到下游吗？ | 对照 schema 和 `$nodes.<id>.output...` 路径。 |
| 需要人工确认吗？ | 优先使用已有 human approval 节点和 CLI 交互。 |
| 需要图片或文件吗？ | 通过资产服务和测试构建器的图片预览能力处理。 |
| 缺节点吗？ | 停止创建工作流，给出节点规格，转 `$xiagent-node-authoring`。 |

## Validation

常用命令：

```powershell
python -m pytest tests/test_workflow_validator.py -q
python -m pytest tests/test_workflow_testing_builder.py tests/test_workflow_testing_runner.py tests/test_workflow_testing_cli.py -q
python -m xiagent.workflows.testing_cli workflows/global/<workflow-id>.workflow.yaml --input '{"topic":"测试"}'
```

涉及新增节点、运行时、资产或人工交互时，增加对应节点测试和全量 `python -m pytest -q`。

## Common Mistakes

- 直接写一个不存在的节点 `ref`：先暂停并补节点规格。
- 为了测试直接查 SQLite 或拼资产路径：使用 `WorkflowTestBuilder`、`RuntimeService` 和 `AssetService`。
- 忘记工作流是 DAG：不要引入通用循环；需要循环能力时先提出引擎能力缺口。
- 只校验 YAML 能读：还要跑构建器或 CLI，确认事件、快照和交互路径可用。
