# XiAgent 工作流目录规则

## 适用范围

本文件适用于 `workflows/` 下所有工作流契约，尤其是 `workflows/global/*.workflow.yaml`。

## 基础契约

- 工作流由开发者维护的 YAML/JSON 契约定义，不做低代码或拖拽式编辑器。
- 第一版只支持 DAG 和条件分支，不支持通用循环。
- 节点 `ref` 必须来自已注册节点；不得凭空写不存在的节点。
- 节点输入必须使用长路径引用，例如 `$workflow.input.topic`、`$nodes.planner.output.plan`。
- `workflow.input_schema` 只描述最终 `$workflow.input` 的数据契约，不代表任务创建页可以渲染业务参数表单。
- 带业务入参的工作流必须在任务创建后通过首个输入节点收集参数，并显式声明 `collect_workflow_input`，节点 `ref` 使用平台起始输入节点，例如 `system.workflow_input.v1`。
- 工作流业务节点不得承担“顺手收集初始参数”的职责；创建页也不得提交业务 `input_data`。标准流程是 `START -> collect_workflow_input -> first_business_node`。
- 节点输出必须用 `outputs` JSON Schema 声明；下游只能引用 schema 中可校验的字段。
- 工作流验证和调试优先使用 `WorkflowTestBuilder` 或 `python -m xiagent.workflows.testing_cli`。

## UI 控件配置

- UI 控件规则以 `docs/design/2026-05-27-01-ui-control-manifest-design.md` 为准。
- 控件选择遵循工作流优先、节点默认保底：`nodes[].ui` 高于 `workflow.ui.defaults`，`workflow.ui.defaults` 高于 `NodeDescriptor.ui_defaults`，最后才使用系统 fallback。
- 工作流需要定制展示时，优先在 `nodes[].ui` 指定 `controls.input`、`controls.output`、`controls.interaction` 或 `controls.detail`。
- 起始输入节点使用通用 schema 表单控件承载字段控件，例如文本输入、选择器和资产图片选择；字段控件必须能复用于普通等待节点，不得只服务任务创建页。
- 工作流级通用展示默认放在 `workflow.ui.defaults`，可按节点 ref、节点类型、字段类型或标签匹配。
- 节点级 `ui_defaults` 只作为保底建议，不得依赖它表达具体工作流体验。
- `control_id`、`variant`、`mode` 和 `bindings` 必须来自 UI 控件 manifest 或已注册控件库。
- 绑定路径必须能从工作流输入、当前节点输入、当前节点输出、当前节点等待 metadata 或上游节点输出 schema 中解析。
- 图片三选一、首图大列表、hover 放大等展示方式属于控件变体；后端只校验数据契约和控件兼容性，前端负责具体交互。
- 默认推荐把“模型生成候选图”和“用户三选一”拆成两个节点。生成节点输出候选图数组，选择节点负责等待用户选择并输出选择结果。
- 保留高级单节点模式：复合节点可以生成候选图并等待选择，但仍必须走标准 waiting/resume、输出 schema 校验和 UI 控件绑定规则。

## 修改工作流前检查

- 先确认现有节点输出是否满足目标 UI 控件的绑定要求。
- 如果控件要求三张候选图，节点输出 schema 必须能表达三项候选图数组及图片地址字段。
- 如果用户交互会提交选择结果，节点 `outputs` schema 必须声明对应字段。
- 如果三选一能力会被多个工作流复用，优先使用独立用户选择节点，不要把选择逻辑绑进某个生成节点。
- 如果控件或变体不存在，先补 UI 控件 manifest 和 V2 控件库，不能在工作流里临时发明名称。
