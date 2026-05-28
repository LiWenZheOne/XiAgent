# 工作流输入节点与资产图片选择实施计划（已废弃）

> **状态：已废弃。** 本计划原本基于 `system.workflow_input.v1`、`$workflow.input.*`、`workflow.input_schema` 业务入参和创建任务 `input_data` 设计。该方案已经被当前 runtime 节点输入规则取代，旧代码片段不再保留，避免被后续实现误用。

当前有效规则见：

- `AGENTS.md`
- `workflows/AGENTS.md`
- `xiagent/nodes/AGENTS.md`
- `docs/design/2026-05-28-01-workflow-input-node-and-asset-image-picker-design.md`
- `docs/development/2026-05-28-02-runtime-node-input-cleanup-guidelines.md`

## 当前结论

- runtime 不再支持 `system.workflow_input.v1`。
- 工作流业务数据不得使用 `$workflow.input.*` 引用。
- 创建任务阶段不得提交业务 `input_data`。
- 用户业务输入统一通过节点 input spec 声明 `from_user: true`，由任务运行时暂停、校验、恢复。
- 泛用输入节点使用 `system.user_input.v1`；专用业务节点也可以直接声明 `from_user: true` 输入并在恢复后执行。
- 后续节点必须引用上游节点输出，例如 `$nodes.collect_prompt.output.prompt`。

## 历史处置

如需追溯旧方案，请查看 Git 历史。本仓库维护文档只保留当前规则和废弃边界，不再保留旧实施步骤。
