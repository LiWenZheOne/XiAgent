# XiAgent UI V2 目录规则

## 适用范围

本文件适用于 `ui/V2/` 下的前端代码、测试、文档和控件库实现。进入本目录工作前，必须同时遵守根目录 `AGENTS.md`、`.codex/skills/xiagent-ui-development/SKILL.md`、`.codex/skills/xiagent-ui-control-library-authoring/SKILL.md` 和 `ui/V2/docs/ui-development-rules.md`。

## 技术栈与入口

- V2 使用 React 19、TypeScript、Vite、Vitest、Testing Library、Playwright。
- 应用入口是 `src/app/App.tsx`，样式入口是 `src/styles/app.css`，API 客户端位于 `src/api/`。
- UI 控件库位于 `src/node-ui/`，不得把可复用节点控件硬编码在页面主流程中。
- 控件库浏览页是 `src/node-ui/ControlLibraryPage.tsx`，顶部导航已有“控件库”页签。

## V2 控件库结构

- `src/node-ui/registry.ts`：把后端 `control_id` 映射到 V2 React 控件，并导出控件解析函数。
- `src/node-ui/resolve.ts`：解析节点 `input`、`output`、`interaction`、`detail` slot 的控件配置和 binding。
- `src/node-ui/types.ts`：定义 V2 控件 props 和公共控件类型。
- `src/node-ui/controls/`：存放具体控件实现。
- `src/node-ui/fixtures/`：存放控件库预览 fixture。
- `src/tests/node-ui.test.tsx`：覆盖控件渲染、默认解析、提交 payload 和 fallback。

当前已注册控件：

| control_id | 用途 | V2 实现 |
| --- | --- | --- |
| `ui.display.value.v1` | 通用值展示 | `ValueDisplayControl` |
| `ui.display.image_candidates.v1` | 图片候选列表展示 | `ImageCandidatesControl` |
| `ui.choice.image_three.v1` | 图片三选一交互 | `ImageChoiceThreeControl` |
| `ui.interaction.approval.v1` | 人工审批交互 | `ApprovalControl` |
| `ui.fallback.schema_form.v1` | schema 表单 fallback | `SchemaFormControl` |

`ui.choice.image_three.v1` 当前支持 `equal_grid`、`hero_list`、`hover_focus` 三个 V2 变体名称；工作流和节点默认配置必须使用后端 manifest 中存在的实际变体名。

## 后端契约边界

- V2 控件实现必须兼容 `xiagent/ui_controls/catalog.py` 中的 `control_id`、variant、mode、binding 和 submit schema。
- 控件库页面通过 `/api/ui/node-controls` 读取 manifest 只读视图；不要在前端复制一份独立 manifest 作为事实来源。
- 工作流或节点配置引用不存在的控件、变体、模式或 binding 时，应先补后端 manifest 和校验测试，不能只在 V2 中临时兜底。
- V2 不 import 后端 Python 模块，不直接读取 SQLite、资产文件路径、节点实现类或 provider 适配细节。

## 任务创建与起始输入

- 创建任务页只展示工作流 launch 信息、输入准备提示、节点摘要和创建按钮，不渲染 `workflow.input_schema` 的业务表单。
- 创建任务 API 调用不得要求用户先填写业务 `input_data`；带必填参数的工作流应创建任务后进入任务详情，由首个输入节点等待用户提交。
- 起始输入节点和普通等待节点都必须通过 `src/node-ui/` 控件注册表渲染，不得在创建任务页维护另一套 schema 表单、资产选择或上传逻辑。
- `workflow.input_schema` 可以用于生成 launch 提示文案，但不得以 schema、binding 或原始 JSON 形式暴露给普通用户。

## 增改控件流程

1. 判断变更是否会被工作流或 `NodeDescriptor.ui_defaults` 引用。会引用时，先按通用 skill 修改后端 manifest、验证规则和后端测试。
2. 在 `src/node-ui/controls/` 新增或修改控件组件，使用 `NodeUiControlProps`，保持 `preview`、`busy`、`onSubmit` 等状态语义清晰。
3. 在 `src/node-ui/registry.ts` 注册控件 ID；未知控件继续走 `FallbackValueControl`。
4. 如果控件需要读取 binding，优先在 `src/node-ui/resolve.ts` 增加小而稳定的解析函数，路径语义必须与后端 validator 一致。
5. 给控件库页面补预览 fixture；预览只使用脱敏、稳定的本地示例数据。
6. 在 `src/tests/node-ui.test.tsx` 或相关测试中覆盖渲染、variant、fallback、提交 payload 和禁用态。
7. 同步更新 `ui/V2/docs/ui-development-rules.md`，记录 V2 专属用途、variant、payload 和验证命令。

## 展示与交互规则

- V2 是面向最终用户的工作流任务平台，不是静态 demo 或 JSON 查看器。
- 任务创建前不得收集工作流业务入参；所有业务入参在任务详情的起始输入节点中提交。
- 任务详情中的节点输入、输出、等待交互优先通过 `src/node-ui/` 控件注册表渲染。
- 页面不得直接显示 `input_schema`、`output_snapshot`、`public_url`、节点 ref、binding 路径或原始 JSON，除非实现明确的开发者调试视图。
- 节点输入和输出采用上下堆叠布局；默认折叠输入和节点事件，只展开输出或错误区域，避免大输入、大输出横向溢出。
- 新增交互控件必须覆盖 loading、empty、error、disabled、busy、waiting、submitted 状态。
- 控件提交 payload 必须满足后端 manifest 的 `submit_schema` 和节点 `outputs`，不能为了前端方便提交 UI-only 字段。

## 视觉规则

- 使用 `src/styles/app.css` 中的 V2 token：浅灰背景、白色面板、克制蓝色主色、8px 圆角、清晰边线。
- 控件应保持后台工作台风格，优先紧凑、可扫描、可比较；不要使用营销页式 hero、过度装饰或层层嵌套卡片。
- 文本必须在按钮、卡片、表单、状态条和移动宽度内完整可读，不得互相遮挡。

## 验证命令

在 `ui/V2` 下运行：

```powershell
npm run test
npm run build
npm run test:e2e
```

涉及后端 manifest、工作流校验或节点默认 UI 时，同时在仓库根目录运行相关后端测试，例如：

```powershell
python -m pytest tests/test_ui_control_catalog.py tests/test_workflow_validator.py tests/test_node_registry.py -q
```

最终验收应使用真实后端和浏览器主流程确认：登录或注册、选择项目、创建任务、进入任务详情、触发或查看目标控件、确认没有普通用户不应理解的 JSON。
