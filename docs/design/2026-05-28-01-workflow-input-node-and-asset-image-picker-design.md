# 工作流起始输入节点与资产图片选择控件设计

## 背景

当前 V2 创建任务页会根据 `workflow.input_schema` 在任务创建前渲染业务参数表单。这样会造成两套输入体验：

- 创建任务前的 workflow 入参由页面表单特判渲染。
- 任务详情中的节点输入、输出和交互由 `node-ui` 控件库渲染。

对于图片输入字段，例如 `runninghub_image_to_image_test.workflow.yaml` 中的 `$workflow.input.image_urls`，这种拆分会导致资产选择、上传、预览、单选/多选、错误态和控件配置无法复用。后续如果继续扩展资产库选择控件，创建任务页和节点详情页会出现重复实现和语义漂移。

## 目标

1. 彻底取消任务创建前的业务参数输入。
2. 任务创建页只展示工作流介绍、输入准备说明、节点流程摘要和创建入口。
3. 所有 workflow 入参统一在任务创建后的第一个输入节点中填写。
4. 起始输入节点复用 `node-ui` 控件库，不再为创建任务页维护独立业务表单。
5. 新增通用资产图片选择控件，支持资产库选择、本地上传后选择、单选、多选、缩略图折叠预览和大图预览。
6. 保持 `$workflow.input.<field>` 引用语义稳定，避免要求业务节点直接依赖输入节点输出路径。

## 非目标

- 不引入低代码或拖拽式工作流编辑器。
- 不把资产选择逻辑写进具体业务节点。
- 不让前端控件直接读取 SQLite、资产文件路径或资产模块内部实现。
- 不改变 `image_urls` 的数据形态；单选图片仍提交为长度为 1 的 URL 数组。

## 强约束

- `workflow.input_schema` 是最终 `$workflow.input` 的数据契约，不是创建任务页表单定义。
- 任务创建页不得收集业务入参，也不得维护独立 schema 表单、资产选择或上传逻辑。
- 所有初始业务入参必须在任务创建后由首个输入节点收集、校验并固化为 `$workflow.input`。
- 起始输入节点和运行中等待输入节点必须复用同一套 `node-ui` 控件与字段控件；新增控件时优先保证可复用性。
- 通用 schema 表单控件应使用 `ui.input.schema_form.v1` 一类中性命名，不使用只服务 workflow 起始输入的 `workflow_form` 分支。

## 运行模型

任务创建分为两个阶段：

1. 创建任务。
2. 在任务详情中提交起始输入节点。

创建任务时，前端只提交 `project_id` 和工作流契约，不提交业务 `input_data`。运行时检测工作流存在 `input_schema` 后，先创建一个等待状态的系统输入节点，例如 `system.workflow_input.v1`。该节点展示在任务详情的第一步，负责收集、校验并提交 workflow 输入。

用户提交起始输入节点后，运行时按 `workflow.input_schema` 校验 payload。校验通过后，系统将该 payload 固化为任务的 workflow input，使后续节点继续通过 `$workflow.input.prompt`、`$workflow.input.image_urls` 等路径读取数据。

该设计让用户体验上所有输入都发生在节点详情中，同时保留现有工作流路径引用语义。

## 工作流契约

带业务入参的工作流必须显式增加首个输入节点：

```yaml
nodes:
  - id: collect_workflow_input
    ref: system.workflow_input.v1
    outputs:
      $ref: "#/workflow/input_schema"
    ui:
      controls:
        interaction:
          control_id: ui.input.schema_form.v1
          variant: default
          mode: input

edges:
  - from: START
    to: collect_workflow_input
  - from: collect_workflow_input
    to: transform_image
```

工作流作者不得依赖运行时隐式插入起始输入节点。验证器应要求带业务入参的工作流显式声明起始输入节点，使任务详情、执行轨迹、输入快照和 UI 控件配置都能在工作流契约中被追踪和评审。

## 创建任务页

创建任务页不再渲染业务参数表单。页面只展示：

- 工作流名称和描述。
- 适用场景。
- 运行前需要准备的输入。
- 节点流程摘要。
- 可能产生的输出。

这些内容来自工作流配置，建议增加 `workflow.ui.launch`：

```yaml
workflow:
  ui:
    launch:
      summary: 使用 RunningHub 图生图模型转换输入图片。
      input_hint: 需要准备提示词、参考图片、画面比例和分辨率。
      output_hint: 运行完成后会输出生成图片 URL。
```

如果没有 `workflow.ui.launch`，V2 使用 `workflow.description`、`input_schema` 字段标签和节点列表生成简短摘要，但不展示原始 schema、binding 或 JSON。

## 起始输入节点控件

起始输入节点使用控件库渲染。普通字段可以由通用 schema 表单控件处理；图片字段使用专用资产图片选择控件。

控件解析优先级保持既有规则：

```text
nodes[].ui > workflow.ui.defaults > NodeDescriptor.ui_defaults > 系统 fallback
```

对于 workflow input 字段，推荐在起始输入节点的 `ui` 中显式配置字段控件。后续如果要抽象通用字段级配置，应仍然映射到同一套 `node-ui` 控件，而不是恢复创建任务页专用表单。

## 资产图片选择控件

新增控件建议为：

```text
control_id: ui.input.asset_image_picker.v1
kind: input
variant: thumbnails
mode: input
```

核心配置：

```yaml
options:
  selection_mode: multiple
  default_collection_id: ""
  preset_tag_ids: []
  upload_scope: project
  upload_collection_ids: []
  upload_tag_ids: []
  collapsed_rows: 1
```

行为要求：

- `selection_mode=single` 时只能选择一张图，但提交值仍为 `["url"]`。
- `selection_mode=multiple` 时提交 URL 数组。
- 主界面默认显示一行缩略图，超出后折叠，提供展开/收起。
- 点击缩略图以弹窗形式查看大图。
- “选择图片”打开资产选择子页面。
- 子页面顶部页签为“资产库”和“本地上传”，默认停留在“资产库”。
- 资产库页签左侧展示树形目录，上方提供标签过滤和搜索，主体展示图片缩略图。
- 本地上传页签先上传文件到指定资产库位置，取得资产 URL 后加入选择结果。
- 空目录、无标签、无图片、上传目标未配置、上传失败和资产搜索失败都必须显示明确状态，不能空白。

前端只能通过资产 API 查询目录、标签、资产和上传文件。上传接口需要支持传入 `collection_ids` 和 `tag_ids`，V2 `uploadAsset()` 封装应补齐这些参数。

## RunningHub 图生图工作流调整

`workflows/global/runninghub_image_to_image_test.workflow.yaml` 调整为：

- 创建任务前不填写 `prompt`、`image_urls`、`aspect_ratio`、`resolution`。
- 增加首个 `collect_workflow_input` 节点。
- `image_urls` 字段使用 `ui.input.asset_image_picker.v1`。
- 根据当前工作流需要配置 `selection_mode`，默认可使用 `multiple`，单图场景使用 `single`。
- `transform_image` 仍引用 `$workflow.input.prompt`、`$workflow.input.image_urls`、`$workflow.input.aspect_ratio`、`$workflow.input.resolution`。

这样业务节点不需要知道输入来自创建页还是起始输入节点。

## 校验与兼容

后端需要补充以下校验：

- `system.workflow_input.v1` 只能作为显式起始输入节点使用。
- 带必填 `workflow.input_schema` 的工作流必须声明 `collect_workflow_input` 一类起始输入节点，并从 `START` 指向该节点。
- 起始输入节点提交 payload 必须满足 `workflow.input_schema`。
- 控件配置中的 `control_id`、`variant`、`mode`、`bindings` 必须存在于 UI control manifest。
- 资产图片选择控件绑定的字段必须是 `string` 或 `string[]`；当前推荐优先支持 `string[]`。
- 单选模式下如果提交多个 URL，应由控件阻止；后端可选择报错以防绕过。

兼容策略：

- 现有工作流需要随本次改造迁移为显式 `collect_workflow_input` 节点，不能继续把开头参数停留在创建页。
- V2 创建任务页删除业务参数表单后，旧任务详情仍按已有快照显示，不影响历史任务查看。

## 测试策略

后端测试：

- UI control catalog 包含 `ui.input.asset_image_picker.v1`。
- workflow validator 接受显式起始输入节点和图片控件配置，并拒绝带必填入参但缺少起始输入节点的新工作流。
- 创建任务时允许空 `input_data` 进入等待输入状态。
- 提交起始输入节点后按 `workflow.input_schema` 校验并继续执行。
- `image_urls` 单选、多选 payload 均保持数组形态。

前端测试：

- 创建任务页不展示业务输入表单，不暴露 `input_schema` 或原始 JSON。
- 任务创建后自动进入详情页并显示起始输入节点。
- 资产图片选择控件覆盖加载、空态、错误、禁用、上传中、单选、多选、折叠展开、大图预览。
- 本地上传成功后新资产 URL 能加入已选结果。
- `runninghub_image_to_image_test` 可以在任务详情中完成输入并进入后续节点。

浏览器验收：

- 注册或登录。
- 选择项目。
- 创建 RunningHub 图生图测试任务。
- 在任务详情首个输入节点选择资产图片或上传图片。
- 提交输入后确认后续节点开始运行，页面不出现普通用户不应理解的 JSON、schema 或 binding。
