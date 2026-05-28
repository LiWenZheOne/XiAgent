# UI 控件 Manifest 与后端对接规则设计

## 背景

V2 任务界面需要把工作流节点展示从页面硬编码中抽离出来。节点本身应保留可执行能力、输入输出 schema 和通用默认展示建议；不同工作流可以按业务场景指定不同输入控件、输出控件、交互控件和展示变体。

典型场景包括：

- 三张候选图片三选一。
- 三张候选图等宽展示。
- 首图放大、其余图片列表展示。
- 鼠标悬停当前图片时放大当前图并缩小其他候选图。
- 同一个图片生成节点在不同工作流里使用不同展示方式。

因此 UI 配置不能只绑在节点实现上，也不能完全由前端根据 schema 猜测。后端需要有一套泛化 UI 对接规则，能够在加载工作流时检查工作流指定的控件、变体、绑定路径和节点输入输出是否匹配；前端 V2 则负责实现真实 React 控件库和控件库浏览页。

## 目标

- 建立后端可识别的 UI 控件 manifest，描述控件 ID、版本、分类、能力标签、变体、绑定要求、输入输出约束和动作约束。
- 支持工作流优先指定节点输入、输出、交互和详情展示控件。
- 支持节点通过 `NodeDescriptor` 提供默认 UI 建议，但只作为保底，不绑定具体工作流体验。
- 工作流加载时，后端根据控件 manifest、节点 schema 和工作流 UI 配置做硬性兼容检查。
- 创建任务时保存完整 workflow snapshot，包括最终有效 UI 配置所需的原始配置，保证历史任务不受后续工作流变更影响。
- V2 顶部导航增加“控件库”页签，用于浏览当前可用控件、变体、能力标签、绑定要求和预览示例。

## 非目标

- 不做拖拽式工作流编辑器。
- 不把整个前端做成完整低代码 UI DSL。
- 后端不实现 hover 放大、图片布局、动画等具体前端交互。
- 后端不 import V2 React 代码，也不依赖某一个 UI 项目的组件实现。
- 普通用户不直接编辑控件 manifest；manifest 由开发者维护。

## 总体架构

```text
UI Control Manifest
  -> 后端加载控件元数据
  -> workflow validator 校验 workflow.ui / nodes[].ui
  -> /api/ui/node-controls 暴露可用控件元数据

Workflow Contract
  -> workflow.ui 定义当前工作流的展示默认规则
  -> nodes[].ui 定义当前工作流中某个节点的显式控件选择

NodeDescriptor
  -> input_schema / output_schema / config_schema
  -> ui_defaults 提供节点级默认 UI 建议

V2 UI
  -> ui/V2/src/node-ui/ 注册 React 控件实现
  -> 任务详情页解析最终有效 UI 配置
  -> 控件库浏览页展示控件、变体、标签和 fixture
```

## UI 配置归属

UI 配置分三层：

1. 工作流级 `workflow.ui`。
2. 工作流节点级 `nodes[].ui`。
3. 节点描述符级 `NodeDescriptor.ui_defaults`。

工作流配置优先，节点默认保底。节点实现不应为了某个工作流写死 UI 展示方式。

## Workflow 起始输入边界

`workflow.input_schema` 只描述最终 `$workflow.input` 的数据契约，不是任务创建页表单定义。创建任务页不得根据 `input_schema` 渲染业务参数表单，也不得维护专用资产选择、上传或字段校验逻辑。

带业务入参的工作流必须显式声明首个输入节点，例如 `collect_workflow_input` / `system.workflow_input.v1`。该节点在任务创建后等待用户输入，提交后由运行时校验 payload 并固化为 `$workflow.input`，后续业务节点继续使用 `$workflow.input.<field>` 引用。

起始输入节点、运行中等待输入节点和字段级控件必须复用同一套节点 UI 控件库。通用 schema 表单控件应使用 `ui.input.schema_form.v1` 一类中性命名，字段控件如资产图片选择应能在起始输入和普通输入场景中复用。交互节点提交成功后，任务详情应继续使用原交互控件的 `readonly` 模式展示已提交参数，不退回通用值展示或原始表单。

## 控件解析优先级

最终有效 UI 配置按以下顺序解析：

```text
system fallback
  < NodeDescriptor.ui_defaults
  < workflow.ui.defaults
  < nodes[].ui
```

解析规则不是简单对象覆盖，而是按区域合并：

- `controls.input`
- `controls.output`
- `controls.interaction`
- `controls.detail`
- `actions`
- `sections`
- `bindings`

例如工作流只覆盖 `controls.output` 时，不应清空节点默认的 `controls.input`。

## 工作流 UI 契约

`workflow.ui` 负责当前工作流的全局展示策略和默认控件规则。

```yaml
workflow:
  id: image_choice_demo
  version: "1.0.0"
  scope: global
  name: 图片三选一示例
  input_schema:
    type: object
    required: ["prompt"]
    properties:
      prompt:
        type: string
  ui:
    layout:
      task_detail: vertical_timeline
    defaults:
      by_node_ref:
        ai.runninghub_text_to_image.v1:
          controls:
            output:
              control_id: ui.display.image_candidates.v1
              variant: compact_grid
      by_tags:
        - tags: ["image", "choice", "select_one"]
          controls:
            interaction:
              control_id: ui.choice.image_three.v1
              variant: grid_equal
```

`nodes[].ui` 负责当前工作流中某个节点的显式展示配置。

```yaml
nodes:
  - id: choose_cover
    ref: system.human_approval.v1
    inputs:
      candidates:
        from: "$nodes.generate_images.output.results"
    outputs:
      type: object
      required: ["selected_image"]
      properties:
        selected_image:
          type: object
    ui:
      controls:
        input:
          control_id: ui.display.image_candidates.v1
          variant: compact_grid
          bindings:
            items_path: "$node.input.candidates"
        interaction:
          control_id: ui.choice.image_three.v1
          variant: hover_focus
          mode: select_one
          bindings:
            items_path: "$node.input.candidates"
            selected_output_key: "selected_image"
      actions:
        confirm: true
        rerun: false
```

## 节点默认 UI 建议

`NodeDescriptor` 可以扩展 `ui_defaults` 字段，表达节点通用默认展示建议。

```python
NodeDescriptor(
    ref="ai.runninghub_text_to_image.v1",
    name="RunningHub 文生图",
    version="1.0.0",
    kind="ai.image_generation",
    input_schema={...},
    output_schema={...},
    config_schema={...},
    ui_defaults={
        "tags": ["image", "generation"],
        "controls": {
            "output": {
                "control_id": "ui.display.image_result.v1",
                "variant": "single_or_grid",
                "bindings": {
                    "items_path": "$node.output.results"
                },
            }
        },
    },
)
```

节点默认只表达“这个节点一般适合怎样展示”，不表达具体工作流体验。工作流可以完全覆盖它。

## 节点拆分与高级单节点模式

默认推荐把“模型生成候选”和“用户三选一”拆成两个节点：

```text
generate_images
  ref: ai.runninghub_text_to_image.v1
  输出 3 张候选图

choose_image
  ref: system.user_choice.v1
  输入候选图数组
  等待用户三选一
  输出 selected_image
```

这样三选一节点可以复用于多个工作流。不同工作流只需要通过 `nodes[].ui` 给 `choose_image` 绑定不同控件变体，例如等宽三图、首图大列表或 hover 放大三选一。

保留高级单节点模式：某些复合节点可以在一个节点内完成“生成候选图并等待用户选择”。这种节点仍必须通过标准节点结果表达等待状态，输入输出 schema 必须同时声明候选图和选择结果，UI 配置仍通过 `workflow.ui` 或 `nodes[].ui` 指定。该模式适合强绑定的领域能力，但不作为普通工作流的默认建模方式。

单节点高级模式的约束：

- 节点 `output_schema` 必须声明用户恢复后写入的选择结果字段。
- 节点等待时的 metadata 或快照必须能让 UI 控件通过 binding 读取候选图。
- 恢复接口提交的 payload 必须继续按节点 `output_schema` 校验。
- 如果三选一交互可被多个工作流复用，应优先拆成独立 `system.user_choice.v1` 或同类交互节点。

## UI 控件 Manifest

控件 manifest 是后端与前端共同遵守的稳定元数据，不包含 React 代码。

```yaml
controls:
  - control_id: ui.choice.image_three.v1
    version: "1.0.0"
    name: 三图选择
    kind: interaction
    modes: ["select_one"]
    tags: ["image", "choice", "select_one", "candidates_3"]
    variants:
      - id: grid_equal
        name: 等宽三图
        tags: ["grid", "candidates_3"]
      - id: hero_first
        name: 首图大列表
        tags: ["hero_first", "candidates_3"]
      - id: hover_focus
        name: 悬停放大
        tags: ["hover_focus", "candidates_3"]
    required_bindings:
      items_path:
        source: ["node.input", "node.output"]
        schema:
          type: array
          minItems: 3
          maxItems: 3
          items:
            type: object
            anyRequired: ["url", "public_url", "image_url"]
      selected_output_key:
        source: ["node.output_schema.properties"]
        schema:
          type: string
    output_payload:
      type: object
      requiredFromBinding: ["selected_output_key"]
```

Manifest 字段规则：

- `control_id` 必须全局唯一，使用 `ui.<category>.<name>.vN`。
- `kind` 表示控件用途，建议值为 `input`、`output`、`interaction`、`detail`。
- `tags` 用于智能检查和浏览筛选，例如 `image`、`text`、`asset`、`choice`、`select_one`、`candidates_3`。
- `variants` 声明同一控件的可选展示变体。
- `required_bindings` 声明工作流必须提供哪些绑定，以及绑定路径应满足的 schema 约束。
- `output_payload` 声明控件提交给任务运行层的 payload 形状。

## 后端校验规则

工作流加载或创建任务前，后端必须执行以下检查：

1. `workflow.ui` 和 `nodes[].ui` 必须是对象。
2. `control_id` 必须存在于 UI 控件 manifest。
3. `variant` 必须属于该控件。
4. `mode` 必须属于该控件支持的模式。
5. `bindings` 必须包含控件 manifest 声明的必需绑定。
6. 绑定路径必须使用受支持路径格式：

```text
$workflow.input.<field>
$node.input.<field>
$node.output.<field>
$node.metadata.<field>
$nodes.<node_id>.output.<field>
```

7. 绑定路径必须能从工作流 input schema、当前节点 input schema、当前节点 output schema、当前节点等待 metadata schema 或上游节点 output schema 中解析。
8. 绑定目标 schema 必须满足控件 manifest 的约束，例如数组长度、元素类型、图片地址字段要求。
9. 控件能力标签必须满足用途要求，例如 `interaction + image + select_one + candidates_3`。
10. 用户交互提交的 payload 必须满足节点 `outputs` schema。
11. 工作流显式配置优先于节点默认配置；节点默认配置只在工作流未指定时参与有效 UI 解析。

校验失败时使用稳定错误码，例如：

```text
unknown_ui_control
unknown_ui_control_variant
invalid_ui_binding_path
ui_binding_schema_mismatch
missing_ui_binding
unsupported_ui_control_mode
ui_control_payload_mismatch
```

## API 对接

后端新增或扩展 UI 元数据接口：

```text
GET /api/ui/node-controls
GET /api/ui/node-controls/{control_id}
```

返回内容是控件 manifest 的只读视图，用于 V2 控件库浏览页展示和前端运行时校验提示。

工作流接口继续返回工作流契约：

```text
GET /api/workflows?project_id=<current>
```

任务详情继续返回任务自己的 workflow snapshot：

```text
GET /api/tasks/{task_id}?project_id=<current>
```

任务详情页应使用任务 snapshot 中的 UI 配置，而不是重新读取最新工作流配置。

## V2 控件库结构

V2 建议新增目录：

```text
ui/V2/src/node-ui/
  registry.ts
  types.ts
  controls/
    imageChoiceThree.tsx
    imageDisplay.tsx
    textDisplay.tsx
    schemaInput.tsx
    approval.tsx
    fallback.tsx
  fixtures/
    imageChoiceThree.ts
  ControlLibraryPage.tsx
```

每个前端控件提供：

- `control_id`
- `component`
- `supportedVariants`
- `previewFixtures`
- `runtime adapter`
- `compatibility hint`

任务详情页只通过注册表解析控件，不直接 import 某个具体控件。

## 控件库浏览页

V2 顶部导航增加“控件库”页签。

页面能力：

- 按 `kind` 浏览：输入、输出、交互、详情。
- 按标签筛选：图片、文本、资产、三选一、审批、列表、首图大、悬停放大。
- 查看每个控件的 `control_id`、版本、变体、绑定要求、payload 要求。
- 查看 fixture 预览，例如三图等宽、首图大列表、悬停放大三选一。
- 显示该控件适配的 schema 条件，不显示后端原始任务 JSON。

该页面面向开发者和工作流作者，用于确认当前有哪些可用 UI 控件。

## 与现有 V1/V2 的关系

V1 已有 `ui.block_ref` 和控件库方向设计，但偏节点块级绑定。V2 方案需要细化为输入、输出、交互、详情控件的分区配置，并引入后端 manifest 校验。

V2 当前实现主要通过 `display.ts` 推断字段展示，任务详情页内部直接渲染输入、输出和等待交互。后续实现应将这部分迁移到 `node-ui` 注册表，由任务详情页解析有效 UI 配置并渲染控件。

## 示例：三选一图片交互

同一个交互能力可以有多个变体：

```text
ui.choice.image_three.v1 / grid_equal
ui.choice.image_three.v1 / hero_first
ui.choice.image_three.v1 / hover_focus
```

工作流作者根据当前场景选择：

- `grid_equal`：三张候选图同等重要。
- `hero_first`：第一张是默认推荐，另外两张是备选。
- `hover_focus`：需要对比大图细节，悬停当前图自动放大。

后端只校验它们都属于同一个控件、都满足三图选择的数据要求；具体 hover 交互由 V2 控件实现。

## 实施顺序建议

1. 定义 UI 控件 manifest 数据结构和后端加载入口。
2. 扩展 workflow validator，校验 `workflow.ui`、`nodes[].ui` 和有效 UI 配置。
3. 扩展 `NodeDescriptor`，增加 `ui_defaults`。
4. 增加通用用户选择节点，例如 `system.user_choice.v1`，优先支撑生成候选图后独立三选一的工作流建模方式。
5. 保留并测试高级单节点模式，确保生成并等待选择的复合节点仍走标准 waiting/resume 和 output schema 校验。
6. 增加 `/api/ui/node-controls` 只读接口。
7. V2 新建 `node-ui` 注册表和 fallback 控件。
8. 把任务详情页的输入/输出/等待交互渲染迁移到控件库。
9. 增加“控件库”顶部导航页签。
10. 给现有图片工作流补充 `workflow.ui` 和 `nodes[].ui` 示例。
11. 增加后端校验测试、V2 控件渲染测试和浏览器主流程测试。

## 测试策略

后端测试：

- 合法控件 manifest 能被加载。
- 工作流指定未知控件时失败。
- 工作流指定未知变体时失败。
- `items_path` 指向不存在字段时失败。
- 三选一控件绑定非数组字段时失败。
- 三选一控件绑定数组但没有图片 URL 字段时失败。
- 独立三选一节点能接收上游候选图并在恢复后输出选择结果。
- 高级单节点模式能在同一节点内生成候选图、进入 waiting，并在恢复后输出选择结果。
- 交互提交 payload 不满足节点 output schema 时失败。
- 节点 `ui_defaults` 能作为保底生效，工作流显式配置能覆盖默认值。

前端测试：

- 控件注册表能查找控件和变体。
- 任务详情页优先使用工作流节点级控件配置。
- 工作流只覆盖 output 控件时，input 默认控件仍然保留。
- 三图等宽、首图大列表、悬停放大三种变体能渲染同一份候选图数据。
- 控件库浏览页能按 kind 和 tag 筛选控件。
- 缺失控件时降级到 fallback 控件，并给出开发者可读提示。

集成测试：

- 使用真实后端加载带 UI 配置的工作流。
- 创建任务后任务 snapshot 保留 UI 配置。
- 打开 V2 任务详情，按 snapshot 渲染节点控件。
- 在三选一图片控件里选择一张图并提交，后端校验 payload 后继续任务。

## 自检

- 方案不引入拖拽式工作流编辑器，符合 XiAgent 工作流约束。
- 后端只依赖控件 manifest，不依赖 V2 React 实现，保持泛化能力。
- 工作流显式配置优先，节点默认配置保底，节点保持可复用。
- 控件 manifest 支持标签、变体和 schema 约束，能覆盖三图、列表、首图大列表、悬停放大等图片选择场景。
- 默认推荐生成节点与三选一交互节点拆分，保留高级单节点模式，兼顾复用和特殊场景能力。
- V2 控件库浏览页提供可发现性，避免工作流作者不知道当前有哪些控件可用。
