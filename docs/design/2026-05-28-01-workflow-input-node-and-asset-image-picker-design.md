# 运行时节点输入与资产图片选择控件设计

## 背景

XiAgent runtime 输入语义统一收敛到节点输入。旧方案把初始业务参数先固化为 workflow 级输入，再由后续节点通过 `$workflow.input.*` 引用；这会让创建任务、起始输入节点、运行中等待节点和 UI 控件绑定形成多套路径。

新方案彻底移除 runtime 的 `system.workflow_input.v1`，停止使用 `$workflow.input.*`。所有用户业务数据都通过节点 input spec、节点 `input_snapshot` 和节点 `output_snapshot` 流转。

## 目标

1. 创建任务页只创建任务，不提交业务 `input_data`。
2. 初始参数和运行中补充参数都是普通节点输入。
3. 节点 input spec 使用 `from_user: true` 声明等待用户填写。
4. 运行时校验用户提交 payload 后写入该节点 `input_snapshot`，再执行节点并产生 `output_snapshot`。
5. 后续节点只引用上游节点输出，例如 `$nodes.collect_prompt.output.prompt`。
6. 泛用输入节点使用 `system.user_input.v1`。
7. 专用业务节点也可以直接声明 `from_user: true` 输入并等待填写后继续运行。
8. UI 控件统一绑定节点 `input`、`metadata`、`output` 或上游节点输出，不再绑定 workflow input。

## 非目标

- 不引入低代码或拖拽式工作流编辑器。
- 不把资产选择逻辑写进具体业务节点。
- 不让前端控件直接读取 SQLite、资产文件路径或资产模块内部实现。
- 不保留 `system.workflow_input.v1` 的 runtime 兼容路径。

## 强约束

- `system.workflow_input.v1` 不再是可用节点 ref。
- workflow 业务数据不得通过 `$workflow.input.*` 引用。
- 新工作流不得把 `workflow.input_schema` 作为业务入参契约。
- 创建任务页不得根据 workflow schema 渲染业务参数表单。
- 创建任务 API 不得要求业务 `input_data`。
- 工作流测试不得把业务参数塞到 create_task input_data 绕过等待/提交路径。

## 运行模型

任务创建和业务输入分为两个阶段：

1. 创建任务：前端提交项目和工作流选择信息，不提交业务数据。
2. 节点输入：运行时执行到带 `from_user: true` 的节点输入时进入等待状态。用户提交 payload 后，运行时按节点 input spec 校验数据，写入该节点 `input_snapshot`，执行节点，并保存 `output_snapshot`。

初始参数只是 DAG 中较早出现的用户输入节点；运行中补充参数只是 DAG 中较晚出现的用户输入节点。runtime 不区分“workflow 起始输入”和“普通等待输入”两套机制。

## 工作流契约示例

```yaml
nodes:
  - id: collect_prompt
    ref: system.user_input.v1
    inputs:
      prompt:
        from_user: true
        schema:
          type: string
      image_urls:
        from_user: true
        schema:
          type: array
          items:
            type: string
    outputs:
      type: object
      required: ["prompt", "image_urls"]
      properties:
        prompt:
          type: string
        image_urls:
          type: array
          items:
            type: string
    ui:
      controls:
        input:
          control_id: ui.input.schema_form.v1
          variant: default
          mode: input

  - id: transform_image
    ref: ai.runninghub_image_to_image.v1
    inputs:
      prompt:
        from: "$nodes.collect_prompt.output.prompt"
      image_urls:
        from: "$nodes.collect_prompt.output.image_urls"

edges:
  - from: START
    to: collect_prompt
  - from: collect_prompt
    to: transform_image
```

专用业务节点也可以直接声明用户输入：

```yaml
nodes:
  - id: choose_cover
    ref: business.cover_choice.v1
    inputs:
      candidates:
        from: "$nodes.generate_images.output.results"
      selected_id:
        from_user: true
        schema:
          type: string
```

该节点等待用户填写 `selected_id` 后继续运行，输出仍由节点 `outputs` schema 声明。

## UI 控件绑定

支持的稳定 binding 来源：

```text
$node.input.<field>
$node.output.<field>
$node.metadata.<field>
$nodes.<node_id>.output.<field>
```

字段级资产图片选择控件仍使用通用控件库，例如：

```text
control_id: ui.input.asset_image_picker.v1
kind: input
variant: thumbnails
mode: input
```

资产图片选择控件通过资产 API 查询目录、标签、资产和上传文件。提交值写入等待节点的用户输入 payload，经运行时校验后进入该节点 `input_snapshot`，再由节点执行逻辑产出 `output_snapshot`。

## 创建任务页

创建任务页只展示：

- 工作流名称和描述。
- 适用场景。
- 运行前需要准备的输入说明。
- 节点流程摘要。
- 可能产生的输出。

这些内容可以来自 `workflow.ui.launch`。页面不得展示业务表单、原始 schema、binding 或 JSON。

## 校验与兼容

- 工作流 validator 应拒绝引用 `system.workflow_input.v1`。
- 工作流 validator 应拒绝业务输入路径中的 `$workflow.input.*`。
- UI binding validator 应拒绝 `workflow.input` 来源。
- 带 `from_user: true` 的 input spec 必须有可校验 schema。
- 用户提交 payload 必须满足目标节点 input spec。
- 下游引用必须指向上游节点 `outputs` schema 中存在的字段。
- 历史任务快照按原数据只读展示；新任务和新工作流不再走旧 workflow input 路径。

## 测试策略

后端测试：

- 创建任务时不提交业务 `input_data` 也能进入执行。
- 执行到 `from_user: true` 输入时任务进入等待。
- 提交等待节点 payload 后写入该节点 `input_snapshot`。
- 节点执行后产生 `output_snapshot`，下游节点从 `$nodes.<id>.output.<field>` 读取数据。
- `system.workflow_input.v1` 和 `$workflow.input.*` 被 validator 拒绝。
- 业务参数塞到 create_task `input_data` 的测试路径被拒绝或不会影响节点输入。

前端测试：

- 创建任务页不展示业务输入表单，不暴露 schema 或 binding。
- 任务详情页用同一套节点 UI 控件渲染初始输入和运行中等待输入。
- 资产图片选择控件覆盖加载、空态、错误、禁用、上传中、单选、多选、折叠展开和大图预览。
- 提交节点输入后，任务详情展示已提交参数的 readonly 状态，并继续后续节点。

浏览器验收：

- 注册或登录。
- 选择项目。
- 创建需要用户输入的工作流任务。
- 在任务详情的等待节点填写文本或选择资产图片。
- 提交后确认后续节点开始运行，页面不出现普通用户不应理解的 JSON、schema 或 binding。
