# Runtime 节点输入清理指南

## 目标

本指南用于 runtime 输入清理后续实现、评审和验证。当前方向是彻底移除 workflow 级业务输入，把用户交互统一放到节点 input 参数。

## 必须遵守

- runtime 不再支持 `system.workflow_input.v1`。
- 工作流业务数据不得使用 `$workflow.input.*` 引用。
- 新工作流不得把 `workflow.input_schema` 作为业务入参契约。
- 创建任务页只创建任务，不提交业务 `input_data`。
- 初始参数和运行中补充参数都是普通节点输入。
- 节点 input spec 使用 `from_user: true` 声明等待用户填写。
- 运行时校验用户提交 payload 后写入目标节点 `input_snapshot`，再执行节点并产生 `output_snapshot`。
- 后续节点必须引用上游节点输出，例如 `$nodes.collect_prompt.output.prompt`。
- UI 控件统一绑定节点 `input`、`metadata`、`output` 或上游节点输出，不再绑定 `workflow.input`。

## 节点建模

泛用输入节点使用 `system.user_input.v1`。它只负责展示 input spec、等待用户提交、触发校验和输出已提交数据，不承载具体业务处理。

专用业务节点可以直接声明 `from_user: true` 输入。适用场景是用户补充的数据和该节点业务动作强绑定，例如“选择封面后立即生成确认结果”。这类节点仍必须让输入、输出和等待 metadata 可被 schema 或快照稳定表达。

## 工作流建模

推荐形态：

```yaml
nodes:
  - id: collect_prompt
    ref: system.user_input.v1
    inputs:
      prompt:
        from_user: true
        schema:
          type: string
    outputs:
      type: object
      required: ["prompt"]
      properties:
        prompt:
          type: string

  - id: generate
    ref: ai.some_generator.v1
    inputs:
      prompt:
        from: "$nodes.collect_prompt.output.prompt"
```

禁止形态：

```yaml
nodes:
  - id: generate
    inputs:
      prompt:
        from: "$workflow.input.prompt"
```

## 测试要求

工作流测试必须覆盖真实等待/提交路径：

- 创建任务时不提交业务 `input_data`。
- 运行到 `from_user: true` 输入后进入等待。
- 通过正式交互提交接口或测试构建器交互能力提交 payload。
- 校验目标节点 `input_snapshot` 保留提交数据。
- 校验节点执行后产生 `output_snapshot`。
- 校验下游节点从 `$nodes.<id>.output.<field>` 读取数据。

不得用 create_task `input_data`、旧 workflow input 入口或直接写数据库来替代交互提交。

## 文档残留处理

历史实施计划中如果保留 `system.workflow_input.v1`、`$workflow.input.*` 或 `workflow.input_schema`，必须在文档顶部明确标注已废弃，并说明旧术语仅作为历史记录。当前规则以根 `AGENTS.md`、`workflows/AGENTS.md`、`xiagent/nodes/AGENTS.md`、本指南和最新设计文档为准。
