# XiAgent 工作流目录规则

## 适用范围

本文件适用于 `workflows/` 下所有工作流契约，尤其是 `workflows/global/*.workflow.yaml`。

## 基础契约

- 工作流由开发者维护的 YAML/JSON 契约定义，不做低代码或拖拽式编辑器。
- 第一版只支持 DAG 和条件分支，不支持通用循环。
- 节点 `ref` 必须来自已注册节点；不得凭空写不存在的节点。
- 节点输入必须使用长路径引用，例如 `$workflow.input.topic`、`$nodes.planner.output.plan`。
- 节点输出必须用 `outputs` JSON Schema 声明；下游只能引用 schema 中可校验的字段。
- 工作流验证和调试优先使用 `WorkflowTestBuilder` 或 `python -m xiagent.workflows.testing_cli`。

## UI 控件配置

- UI 控件规则以 `docs/design/2026-05-27-01-ui-control-manifest-design.md` 为准。
- 控件选择遵循工作流优先、节点默认保底：`nodes[].ui` 高于 `workflow.ui.defaults`，`workflow.ui.defaults` 高于 `NodeDescriptor.ui_defaults`，最后才使用系统 fallback。
- 工作流需要定制展示时，优先在 `nodes[].ui` 指定 `controls.input`、`controls.output`、`controls.interaction` 或 `controls.detail`。
- 工作流级通用展示默认放在 `workflow.ui.defaults`，可按节点 ref、节点类型、字段类型或标签匹配。
- 节点级 `ui_defaults` 只作为保底建议，不得依赖它表达具体工作流体验。
- `control_id`、`variant`、`mode` 和 `bindings` 必须来自 UI 控件 manifest 或已注册控件库。
- 绑定路径必须能从工作流输入、当前节点输入、当前节点输出或上游节点输出 schema 中解析。
- 图片三选一、首图大列表、hover 放大等展示方式属于控件变体；后端只校验数据契约和控件兼容性，前端负责具体交互。

## 修改工作流前检查

- 先确认现有节点输出是否满足目标 UI 控件的绑定要求。
- 如果控件要求三张候选图，节点输出 schema 必须能表达三项候选图数组及图片地址字段。
- 如果用户交互会提交选择结果，节点 `outputs` schema 必须声明对应字段。
- 如果控件或变体不存在，先补 UI 控件 manifest 和 V2 控件库，不能在工作流里临时发明名称。
