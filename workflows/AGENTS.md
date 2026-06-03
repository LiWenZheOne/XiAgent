# XiAgent 工作流目录规则

## 适用范围

本文件适用于 `workflows/` 下所有工作流契约，尤其是 `workflows/global/*.workflow.yaml`。

## 基础契约

- 工作流由开发者维护的 YAML/JSON 契约定义，不做低代码或拖拽式编辑器。
- 第一版只支持 DAG 和条件分支，不支持通用循环。
- 节点 `ref` 必须来自已注册节点；不得凭空写不存在的节点。
- 节点业务输入必须使用长路径引用上游节点输出，例如 `$nodes.collect_input.output.topic`、`$nodes.planner.output.plan`。
- runtime 不再支持 `system.workflow_input.v1`，工作流业务数据不得使用 `$workflow.input.*` 引用。
- 新工作流不得把 `workflow.input_schema` 作为业务入参契约；需要用户填写的字段必须放在具体节点 input spec 中。
- 任务创建页只创建任务，不提交业务 `input_data`，也不渲染业务表单。
- 初始参数和运行中补充参数都是普通节点输入。节点 input spec 使用 `from_user: true` 声明等待用户填写；运行时校验 payload 后写入该节点 `input_snapshot`，再执行节点并产生 `output_snapshot`。
- 泛用输入节点使用 `system.user_input.v1`；专用业务节点也可以直接声明 `from_user: true` 输入并等待填写后继续运行。
- 节点输出必须用 `outputs` JSON Schema 声明；下游只能引用 schema 中可校验的字段。
- LLM 不负责输出或修订身份字段。`index`、`segment_index`、标题、原文、分段参数、资产归属等用于排序、回接和下游引用的字段，必须通过 `passthrough_fields` 或节点内部合并逻辑从输入 item 程序化继承。提示词只要求 LLM 返回本步骤生成或修订的业务字段，不得要求 LLM 返回完整对象来补齐身份字段。
- 工作流验证和调试优先使用 `WorkflowTestBuilder` 或 `python -m xiagent.workflows.testing_cli`，并通过真实等待/提交交互路径提供业务参数，不得把业务参数塞到创建任务 `input_data`。

## UI 控件配置

- UI 控件规则以 `docs/design/2026-05-27-01-ui-control-manifest-design.md` 为准。
- 控件选择遵循工作流优先、节点默认保底：`nodes[].ui` 高于 `workflow.ui.defaults`，`workflow.ui.defaults` 高于 `NodeDescriptor.ui_defaults`，最后才使用系统 fallback。
- 工作流需要定制展示时，优先在 `nodes[].ui` 指定 `controls.input`、`controls.output`、`controls.interaction` 或 `controls.detail`。
- 用户输入节点使用通用 schema 表单控件承载字段控件，例如文本输入、选择器和资产图片选择；字段控件必须能复用于普通等待节点，不得只服务任务创建页。
- 工作流级通用展示默认放在 `workflow.ui.defaults`，可按节点 ref、节点类型、字段类型或标签匹配。
- 节点级 `ui_defaults` 只作为保底建议，不得依赖它表达具体工作流体验。
- `control_id`、`variant`、`mode` 和 `bindings` 必须来自 UI 控件 manifest 或已注册控件库。
- 绑定路径必须能从当前节点输入、当前节点输出、当前节点等待 metadata 或上游节点输出 schema 中解析；不得绑定 `workflow.input`。
- 图片三选一、首图大列表、hover 放大等展示方式属于控件变体；后端只校验数据契约和控件兼容性，前端负责具体交互。
- 默认推荐把“模型生成候选图”和“用户三选一”拆成两个节点。生成节点输出候选图数组，选择节点负责等待用户选择并输出选择结果。
- 保留高级单节点模式：复合节点可以生成候选图并等待选择，但仍必须走标准 waiting/resume、输出 schema 校验和 UI 控件绑定规则。

## 修改工作流前检查

- 先确认现有节点输出是否满足目标 UI 控件的绑定要求。
- 如果控件要求三张候选图，节点输出 schema 必须能表达三项候选图数组及图片地址字段。
- 如果用户交互会提交选择结果，节点 `outputs` schema 必须声明对应字段。
- 如果三选一能力会被多个工作流复用，优先使用独立用户选择节点，不要把选择逻辑绑进某个生成节点。
- 如果控件或变体不存在，先补 UI 控件 manifest 和 V2 控件库，不能在工作流里临时发明名称。
