---
name: xiagent-node-authoring
description: Use when creating or modifying XiAgent BaseNode implementations, node refs, NodeDescriptor schemas, node registry entries, or tests for workflow node capabilities.
---

# XiAgent 节点编写

## Overview

新增或修改节点时，先按需求检查现有节点是否已经满足；存在候选节点时暂停并让用户确认复用还是继续新建。确需开发时，必须先用 TDD 固化行为，再实现 `BaseNode` 节点并注册到节点注册表。

## Core Workflow

1. 明确节点规格：`ref`、职责、输入 schema、输出 schema、错误语义、资产访问、外部服务或凭据、是否需要人工交互。
2. 检查现有节点是否满足需求：读取 `build_node_registry(settings)`、现有节点 `NodeDescriptor`、相近节点实现和测试，按职责、输入输出 schema、错误语义和依赖能力判断可复用性。
3. 如果找到一个或多个候选节点，暂停开发新节点，向用户列出候选 `ref`、匹配点、差距和复用影响，并等待用户确认“复用现有节点”还是“继续开发新节点”。用户未确认前不要写新节点代码或测试。
4. 只有确认需要新建或修改节点后，先读现有模式：`xiagent/nodes/base.py`、`xiagent/nodes/registry.py`、`xiagent/nodes/__init__.py`、相近节点实现和测试。
5. RED：先写失败测试。节点行为测试通常放在 `tests/test_node_registry.py`、现有节点测试文件，或新建聚焦测试文件。测试应直接执行节点或验证注册表行为。
6. 运行目标测试，确认失败原因是节点能力缺失，而不是测试拼写、导入错误或夹具错误。
7. GREEN：实现最小节点代码。正式节点必须继承 `BaseNode`，实现 `describe()` 和 `execute()`，返回 `NodeResult`。
8. 注册节点：按现有模式更新 `xiagent/nodes/__init__.py` 的 `build_node_registry(settings)`，必要时更新包导出。
9. REFACTOR：只在测试为绿后整理命名、抽取小函数或压缩重复。
10. 回接工作流：如果节点是为某个工作流缺口创建的，返回节点 `ref`、输入输出 schema、示例工作流片段，并用 `WorkflowTestBuilder` 或 CLI 验证目标工作流。

## Project Constraints

- 正式代码不使用 `Protocol` 作为平台接口；核心接口统一使用 `ABC` 抽象基类。
- 可注册节点必须继承平台 `BaseNode`，不要绕过 `NodeRegistry` 的类型检查。
- 节点不得直接读取 SQLite、拼接资产文件路径或依赖资产模块内部实现；访问资产必须通过 `AssetService` 或 `NodeContext` 暴露的正式能力。
- 核心领域接口不得依赖 LangGraph、PydanticAI、FastAPI、SQLite 等具体实现；第三方库只能出现在适配器、基础设施或具体节点实现中。
- 节点输入输出 schema 要能被工作流契约和下游节点稳定引用；不要把临时内部字段暴露为公共契约。
- 外部 API 节点必须明确凭据来源、超时、失败状态和测试替身；不要在测试里真实调用外部服务。

## TDD Checklist

| Phase | Required Evidence |
| --- | --- |
| Reuse Check | 已检查现有节点，并在存在候选节点时取得用户确认。 |
| RED | 新测试已运行并按预期失败。 |
| GREEN | 最小节点实现后目标测试通过。 |
| Registry | 注册表能列出并获取新节点 ref。 |
| Contract | 工作流校验能识别节点 schema。 |
| Runtime | 目标工作流可用构建器或 CLI 走通。 |

不能展示 RED 失败证据时，不要声称完成 TDD。

## Implementation Notes

- `NodeDescriptor.ref` 使用稳定版本化 ref，例如 `tool.echo.v1`、`ai.deepseek_chat.v1`。
- `describe()` 描述节点名称、输入 schema、输出 schema 和必要元数据；schema 要和工作流输入路径匹配。
- `execute()` 从 `inputs`、`NodeContext` 和正式服务接口取数据；保持输出结构稳定。
- 成功返回 `NodeResult(status="succeeded", output=...)`；需要等待人工输入时按现有 human approval 节点模式返回等待状态。
- 错误要进入节点结果或运行时错误语义，不要吞掉异常或只打印日志。

## Validation

常用命令：

```powershell
python -m pytest tests/test_node_registry.py -q
python -m pytest tests/test_workflow_validator.py -q
python -m pytest tests/test_workflow_testing_runner.py -q
python -m pytest -q
```

如果节点是为某个工作流新增的，再运行：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/<workflow-id>.workflow.yaml --input '{"topic":"测试"}'
```

## Common Mistakes

- 先写节点再补测试：违反 TDD，回到 RED 阶段。
- 没查现有节点就新建：先列出现有候选节点，等待用户确认复用或继续开发。
- 注册了节点但没测试注册表：工作流可能仍找不到 `ref`。
- 节点直接访问数据库或资产路径：改为通过正式服务接口。
- 输出 schema 和实际输出不一致：工作流验证可能通过，但运行时下游会断。
- 为了满足一个工作流写死字段：把稳定能力抽象到节点输入输出契约里。
