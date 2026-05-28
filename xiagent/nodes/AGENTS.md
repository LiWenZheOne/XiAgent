# XiAgent 节点目录规则

## 适用范围

本文件适用于 `xiagent/nodes/` 下所有节点基础类型、注册表和具体节点实现。

## 基础约束

- 正式节点必须继承平台提供的 `BaseNode`，不得用 `Protocol` 作为正式平台接口。
- 节点必须通过 `NodeDescriptor` 暴露稳定的 `ref`、名称、版本、类型、输入 schema、输出 schema 和配置 schema。
- 节点不得直接读取 SQLite、拼接资产文件路径或依赖资产模块内部实现；访问资产必须通过 `AssetService` 或 `NodeContext` 暴露的正式能力。
- 节点不得直接依赖模型 SDK、外部 HTTP 细节或密钥配置；模型能力应通过 `ChatModelRouter` 和模型 provider 适配器。
- 输出 schema 和实际输出必须一致，保证工作流下游路径引用可校验。

## UI 默认规则

- UI 控件规则以 `docs/design/2026-05-27-01-ui-control-manifest-design.md` 为准。
- 节点可以在 `NodeDescriptor.ui_defaults` 中提供通用默认展示建议，但它只作为保底。
- 控件选择优先级是 `nodes[].ui` > `workflow.ui.defaults` > `NodeDescriptor.ui_defaults` > 系统 fallback。
- 节点实现不得写死某个工作流专属展示方式，例如首图大列表、hover 放大三选一或某个页面布局。
- `ui_defaults` 只能引用 UI 控件 manifest 中存在的 `control_id`、`variant`、`mode` 和 `bindings`，不得引用 V2 React 组件路径。
- 节点业务输出应先保持稳定，再由工作流 UI 配置或节点默认 UI 绑定展示；不要为了某个控件暴露临时内部字段。
- 新增或修改 `ui_defaults` 时，应补测试确认默认 bindings 指向的字段存在于节点 schema。
- 默认推荐把生成候选图和用户三选一拆成不同节点；只有强绑定领域能力才做生成并等待选择的复合节点。
- 复合节点如果直接生成并等待选择，必须使用标准 waiting/resume 语义，候选图和恢复后的选择结果都必须能由 schema 或快照稳定表达。

## 起始输入节点规则

- 工作流初始业务参数必须由任务创建后的首个输入节点收集，不得放在任务创建页。
- 平台起始输入节点只负责等待、展示输入 schema、接收 payload、触发校验和固化 `$workflow.input`；不要把具体业务处理或资产模块实现写进该节点。
- 普通业务节点不得为了绕过起始输入节点而临时承担初始参数采集职责。
- 起始输入节点的 `ui_defaults` 只能引用通用节点 UI 控件，不得引用某个 UI 版本组件路径或创建页专用表单。

## 新增节点前检查

- 先检查现有节点是否可复用；存在候选节点时，向用户列出差距并等待确认。
- 如果只是展示方式不同，优先新增或调整 UI 控件 manifest 和前端控件，不要新增节点。
- 如果只是需要三选一复用，优先新增或复用用户选择节点，不要复制生成节点逻辑。
- 如果需要新的业务数据能力，再新增节点，并同步注册表、节点测试和目标工作流验证。
