# UI 任务交互与控件库设计

## 背景

XiAgent 第一版已经形成契约驱动的工作流后端：工作流由开发者维护 YAML/JSON 契约，运行时保存任务、节点执行、事件、输入快照和输出快照。接下来前端不应做低代码或拖拽式工作流编辑器，而应围绕用户创建任务、逐节点交互、查看输入输出和重跑节点来设计。

本设计确认第一版 UI 采用 `React + Vite + TypeScript`，前端代码统一放在项目根目录的 `ui/V1/` 下。`ui/` 目录用于承载未来多套前端实现，`V1/` 是第一版前端的独立工程根目录。后续如果出现新的产品形态或重构版本，应新增独立目录，例如 `ui/V2/`，不得把第一版代码直接散放到 `ui/` 根目录。

## 目标

- 以项目和任务为主线，提供普通用户可理解的工作流运行体验。
- 将任务详情页设计为逐节点交互运行界面，而不是单纯日志页。
- 每个工作流节点对应一个 UI 节点块，节点块内直接展示输入参数、输出参数、详情、错误、重跑和 attempt 历史。
- 工作流节点运行完成后，前端立即更新对应节点块状态和参数信息。
- 需要用户交互的节点在当前节点块内等待用户输入、选择或确认；不需要用户交互的节点继续自动执行。
- UI 控件采用契约化控件库，工作流通过 `ui` 字段显式绑定控件，避免依赖 schema 全自动猜测展示方式。
- 支持完成节点重跑：重跑创建新 attempt，清空下游当前结果，并从重跑节点继续执行。

## 非目标

- 第一版不做拖拽式工作流编排器。
- 第一版不做工作流定义的实时推送、轮询或多人协作编辑。
- 第一版不把 UI 控件做成散装 React 组件。
- 第一版不把所有 UI 都抽象成完整 DSL。
- 第一版不要求普通用户直接查看节点注册表。

## 信息架构

第一版 UI 的主线是：

```text
项目 / 全局
  -> 任务
     -> 创建任务
        -> 选择当前项目可用工作流
        -> 创建任务实例
     -> 任务详情
        -> 纵向节点块
        -> 节点输入 / 输出 / 详情 / 错误 / 重跑 / attempt 历史
```

规则：

- `项目` 是工作流和任务的上级空间。
- 工作流必须属于某个项目或全局。
- `全局` 可以理解为默认项目；没有项目时默认显示全局。
- 当前项目下创建任务时，可用工作流包括当前项目工作流和全局工作流。
- `任务` 是主入口，不只是历史记录。
- `任务列表` 第一行是 `创建任务`。
- `资产库` 保留独立入口。
- `UI 控件库` 保留独立入口。
- `节点注册表` 放入开发者工具，主要用于查看后端可执行节点 `ref`、输入 schema、输出 schema 和配置 schema。
- 原先讨论中的“工作流运行台”不作为主导航概念，合并为 `任务详情 / 运行详情` 页面形态。

## 前端目录边界

前端第一版工程目录：

```text
ui/
  V1/
    package.json
    index.html
    src/
      app/
      api/
      routes/
      task/
      workflow/
      assets/
      ui-blocks/
      developer-tools/
      styles/
      tests/
```

边界规则：

- `ui/V1/` 是完整独立前端工程，可独立安装依赖、启动开发服务器和构建产物。
- 后端 Python 包不得 import 前端代码。
- 前端通过 HTTP API 和 SSE 与后端通信，不直接读取 SQLite、后端文件路径或 Python 内部类。
- 未来新增前端版本时，新建 `ui/V2/` 等目录，不直接覆盖 `ui/V1/`。
- `ui/` 根目录只放跨版本说明或索引，不放具体业务代码。

## 任务运行交互模型

任务创建时必须保存工作流快照。作者修改 YAML/JSON 后，不影响已创建任务；新建任务才读取最新工作流。

任务详情页按节点级事件实时更新，使用 SSE：

```text
GET /api/tasks/{task_id}/stream
```

运行规则：

- 节点开始时，后端发 `node_started`，页面把对应节点块显示为 `running`，并展示输入快照。
- 节点成功时，后端发 `node_succeeded`，页面立即展示输出快照、图片、资产引用、usage 和 metadata。
- 节点失败时，后端发 `node_failed`，页面在节点块内展示错误码、错误信息和 details。
- 节点不需要用户交互时，后端继续执行下一个节点。
- 节点需要用户交互时，后端发 `node_waiting` 和 `task_waiting`，页面在当前节点块内展示交互控件。
- 用户提交交互后，前端调用恢复或交互提交接口，后端继续执行，SSE 继续推送后续节点事件。

## 用户交互节点

底层保留一个通用交互能力：

```text
system.user_interaction.v1
```

第一版提供三个预制节点模板：

```text
system.user_input.v1
system.user_choice.v1
system.user_approval.v1
```

职责：

- `system.user_input.v1`：用户填写文本、图片、文档或资产。
- `system.user_choice.v1`：用户从候选输出中选择一个或多个。
- `system.user_approval.v1`：用户确认、拒绝或补充意见。

推荐把“生成”和“用户选择”拆成两个节点。例如生图工作流使用：

```text
generate_images
  输出 3 张候选图

choose_image
  输入 3 张候选图
  用户选择 1 张
  输出 selected_image
```

这样 AI 节点只负责生成，用户交互节点只负责等待和收集选择。后续如果某些特殊节点需要自己生成候选并等待用户选择，也可以作为高级能力支持，但第一版不作为推荐模式。

## 重跑语义

所有已完成节点都可以显示 `重新运行` 动作，是否显示由节点 `ui.actions.rerun` 控制。

重跑规则：

- 重跑某个节点时，创建该节点新的 `attempt`。
- 旧 attempt 不删除，可在历史中查看。
- 重跑节点的下游所有当前结果立即失效，并从 `current_view.active_node_outputs` 移除。
- 下游旧执行记录保留为历史，但不再作为当前有效结果。
- 后端从重跑节点继续执行，直到任务完成、失败或遇到下一个用户交互节点。
- 前端显示下游节点为 `cleared` 或 `pending`，并通过 SSE 重新填充最新状态。

## 工作流 `ui` 契约

第一版把 UI 绑定写进工作流 YAML/JSON 的节点级 `ui` 字段。执行语义仍由 `ref`、`inputs`、`outputs`、`edges` 决定；`ui` 只负责前端如何呈现、如何收集用户交互、如何绑定输出选择和动作。

展示类节点示例：

```yaml
nodes:
  - id: generate_images
    ref: ai.runninghub_text_to_image.v1
    inputs:
      prompt:
        from: "$nodes.prepare_prompt.output.prompt"
    outputs:
      type: object
      required: ["results"]
      properties:
        results:
          type: array
    ui:
      block_ref: ui.image_grid.v1
      variant: gallery_three
      sections:
        input:
          collapsed: false
          fields: ["prompt", "aspect_ratio"]
        output:
          collapsed: false
          fields: ["results"]
        detail:
          collapsed: true
        error:
          collapsed: true
      actions:
        rerun: true
        save_asset: true
```

选择类节点示例：

```yaml
nodes:
  - id: choose_image
    ref: system.user_choice.v1
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
      block_ref: ui.image_choice.v1
      variant: select_one_gallery
      mode: select_one
      bindings:
        items_path: "$node.input.candidates"
        selected_output_key: "selected_image"
      actions:
        rerun: false
        confirm: true
```

契约规则：

- `ui.block_ref` 必须指向前端 UI 控件库中已注册的控件。
- `ui.variant` 必须是该控件声明支持的变体。
- `ui.mode` 用于选择和确认类控件，例如 `select_one`、`select_many`、`approve_reject`。
- `ui.bindings` 只描述 UI 如何从节点 input/output 中取展示数据，以及如何生成用户提交输出。
- `ui.sections` 控制节点块中的输入、输出、详情、错误区域是否显示和默认折叠状态。
- `ui.actions` 控制是否显示重跑、确认、保存资产等动作。
- 后端第一版校验 `ui` 基本结构，前端控件库负责更细的兼容性校验。
- 创建任务时保存完整 workflow contract snapshot，包括 `ui`。

## UI 控件库接口约束

UI 控件库采用强契约注册表。每个控件必须同时提供：

- `descriptor`：控件元信息、分类、标签、支持的 schema、支持的变体和动作。
- `component`：React 组件实现。
- `previewFixtures`：控件库浏览页使用的预览数据。
- `compatibility check`：判断当前工作流节点是否能使用该控件。
- `action handler contract`：控件能向任务运行层提交哪些动作。

主分类按交互阶段：

```ts
type UiBlockKind =
  | "input"
  | "output"
  | "choice"
  | "approval"
  | "detail";
```

控件描述：

```ts
interface UiBlockDescriptor {
  ref: string;
  version: string;
  name: string;
  kind: UiBlockKind;
  tags: string[];
  variants: UiBlockVariant[];
  supportedInputSchema?: JsonSchema;
  supportedOutputSchema?: JsonSchema;
  actionSchema?: JsonSchema;
}
```

控件组件接口：

```ts
interface UiBlockProps {
  nodeSpec: WorkflowNodeSpec;
  execution: NodeExecutionView | null;
  attempts: NodeAttemptView[];
  uiConfig: NodeUiConfig;
  readonly: boolean;
  onSubmitAction(action: UiBlockAction): Promise<void>;
  onRerun(): Promise<void>;
}
```

动作结构：

```ts
interface UiBlockAction {
  type: "submit_interaction" | "select_output" | "approve" | "reject" | "save_asset";
  nodeId: string;
  payload: Record<string, unknown>;
}
```

控件库页面：

- 按 `input`、`output`、`choice`、`approval`、`detail` 分类浏览。
- 支持按标签筛选，例如 `image`、`document`、`asset`、`select_one`。
- 每个控件显示可用变体和预览。
- 每个控件显示适配的 schema 条件。
- 后续创建 UI 控件 skill 时，必须生成 descriptor、组件、预览 fixture 和兼容性测试。

任务详情页不直接 import 任意组件，而是通过注册表解析：

```ts
const block = uiBlockRegistry.get(nodeSpec.ui.block_ref);
```

如果控件不存在或不兼容，显示降级控件 `ui.fallback_json.v1`，保证任务仍可查看和调试。

## 后端 API 支撑

任务创建：

```text
POST /api/tasks
```

任务创建行为：

- 读取当前工作流最新契约。
- 保存完整 workflow contract snapshot，包括 `ui`。
- 返回 task 基础信息。
- 进入任务详情后开始或继续执行。

任务详情：

```text
GET /api/tasks/{task_id}
GET /api/tasks/{task_id}/node-executions
GET /api/tasks/{task_id}/events
```

任务详情需要返回：

- task 基础状态。
- workflow snapshot。
- 当前有效节点输出 `current_view.active_node_outputs`。
- 所有节点最新状态。
- 节点 attempt 历史。
- waiting 节点信息。
- 输入快照、输出快照、错误、metadata、asset_refs。

节点级事件流：

```text
GET /api/tasks/{task_id}/stream
```

事件包括：

```text
task_started
node_started
node_succeeded
node_failed
node_waiting
task_waiting
task_resumed
node_rerun_started
downstream_cleared
task_succeeded
task_failed
```

用户交互提交：

```text
POST /api/tasks/{task_id}/interactions
```

用于提交用户输入、图片选择、审批确认、拒绝或补充意见。

重跑节点：

```text
POST /api/tasks/{task_id}/nodes/{node_id}/rerun
```

重跑接口必须检查项目权限，读取任务 workflow snapshot，创建新 attempt，清空下游当前结果，追加事件，并从该节点继续执行。

## 第一阶段实现顺序

1. 扩展 workflow contract，支持节点级 `ui` 字段，并保存 task workflow snapshot。
2. 增加 `GET /api/tasks/{task_id}/stream`，用 SSE 推送节点级事件。
3. 增加通用用户交互能力，并提供 `system.user_input.v1`、`system.user_choice.v1`、`system.user_approval.v1`。
4. 增加节点重跑接口，重跑后清空下游当前结果并继续执行。
5. 在 `ui/V1/` 创建 React + Vite + TypeScript 前端工程。
6. 实现前端 UI 控件注册表和 `ui.fallback_json.v1`。
7. 实现核心控件：`ui.form_input.v1`、`ui.text_output.v1`、`ui.image_grid.v1`、`ui.image_choice.v1`、`ui.approval.v1`、`ui.run_detail.v1`。
8. 实现任务列表、创建任务、任务详情纵向节点块、SSE 更新、交互提交和节点重跑。
9. 实现 UI 控件库浏览页，支持分类、标签筛选、控件变体和预览。
10. 增加示例工作流，覆盖用户输入、生成候选图、用户选择、后处理、节点重跑和下游清空。

## 测试策略

后端测试：

- workflow contract 接受合法 `ui` 字段并拒绝非法基本结构。
- 创建任务时保存 workflow snapshot。
- SSE 能按节点发送 `node_started`、`node_succeeded`、`node_waiting`、`task_succeeded` 等事件。
- 用户交互提交会校验输出 schema 并恢复任务。
- 节点重跑会创建新 attempt、清空下游当前结果、保留旧历史并追加事件。

前端测试：

- UI 控件注册表能注册、查找和校验控件兼容性。
- 不兼容控件会降级到 `ui.fallback_json.v1`。
- 任务详情页能根据 SSE 更新节点状态。
- 用户选择和审批动作会提交正确 payload。
- 重跑后下游节点显示为 cleared/pending，并随新事件重新更新。

## 自检

- 本设计不引入拖拽式工作流编辑器，符合 XiAgent 第一版工作流约束。
- 前端代码目录限定为 `ui/V1/`，没有污染 `ui/` 根目录，支持未来多套前端并存。
- UI 控件通过显式契约注册和 `ui` 字段绑定，不依赖 schema 全自动猜测展示方式。
- 任务实时更新只针对任务实例事件流，不对工作流定义做轮询或静默推送。
- 节点重跑保留历史 attempt，同时清空下游当前结果，避免旧下游结果与新上游输出混用。
