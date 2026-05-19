# 工作流模板与契约设计

## 模块定位

工作流模块负责管理工作流模板和契约校验。工作流模板由开发者维护的 YAML/JSON 文件定义。

工作流契约是 XiAgent 自己的稳定格式，不依赖 LangGraph、PydanticAI 或前端画布结构。

## 第一版能力

- 从项目目录加载 YAML/JSON 工作流模板。
- 支持全局和项目作用域。
- 使用 JSON Schema 描述工作流输入、节点输入和节点输出。
- 支持 DAG。
- 支持条件分支。
- 使用长路径引用节点输入。
- 校验节点引用是否存在。
- 校验输入引用是否可解析。
- 校验 DAG 是否可执行。

不支持通用循环。

## 工作流模板实体

```text
workflow_template_id
workflow_id
version
scope: global | project
project_id
name
description
contract
status
created_at
updated_at
```

规则：

- `scope = global` 时 `project_id` 必须为空。
- `scope = project` 时 `project_id` 必须存在。
- `workflow_id + version + scope + project_id` 应唯一。

## 契约示例

```yaml
workflow:
  id: comic_script_generate
  version: "1.0.0"
  scope: project
  name: 漫画脚本生成
  input_schema:
    type: object
    required: ["topic"]
    properties:
      topic:
        type: string

nodes:
  - id: planner
    ref: ai.planner.v1
    inputs:
      topic:
        from: "$workflow.input.topic"
    config:
      style: "comic"
    outputs:
      type: object
      required: ["plan"]
      properties:
        plan:
          type: object

  - id: human_review
    ref: system.human_approval.v1
    inputs:
      plan:
        from: "$nodes.planner.output.plan"
    config:
      prompt: "确认是否继续生成脚本"
      options: ["approve", "reject"]
    outputs:
      type: object
      required: ["decision"]
      properties:
        decision:
          type: string

  - id: writer
    ref: ai.writer.v1
    inputs:
      plan:
        from: "$nodes.planner.output.plan"
      decision:
        from: "$nodes.human_review.output.decision"
    outputs:
      type: object
      required: ["script"]
      properties:
        script:
          type: string

edges:
  - from: START
    to: planner
  - from: planner
    to: human_review
  - from: human_review
    to: writer
    when:
      path: "$nodes.human_review.output.decision"
      equals: "approve"
  - from: writer
    to: END
```

## 引用格式

第一版只使用长路径引用：

```text
$workflow.input.<field>
$nodes.<node_id>.output.<field>
```

不使用短别名，避免调试和前端展示时含义不清。

未来可以扩展执行版本引用：

```text
$nodes.<node_id>.executions.<attempt>.output.<field>
```

第一版不实现版本引用，但数据模型为 attempt 保留空间。

## 校验规则

加载工作流模板时必须校验：

- `workflow.id`、`workflow.version`、`workflow.scope` 必填。
- `workflow.input_schema` 是合法 JSON Schema。
- 每个节点 `id` 在模板内唯一。
- 每个节点 `ref` 能在 `NodeRegistry` 找到。
- 每个节点的 `outputs` 是合法 JSON Schema。
- 所有输入引用使用长路径格式。
- 输入引用指向的 workflow input 或上游节点存在。
- 边中的节点存在。
- 图是 DAG。
- 条件分支引用的路径存在于条件节点输出中。

运行任务前必须校验：

- 用户有项目访问权限。
- 模板作用域允许在当前项目使用。
- 任务输入满足 `workflow.input_schema`。

## LangGraph 边界

工作流契约不包含 LangGraph 类型。

LangGraph 适配器负责：

- 把平台 DAG 转换为 LangGraph 图。
- 包装每个节点执行前后的输入解析和执行记录保存。
- 把等待、失败、完成状态交回 `RuntimeService`。

如果未来替换执行引擎，工作流契约不需要变化。

