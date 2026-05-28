# XiAgent UI V2 开发子规则

## 适用范围

本文件记录 `ui/V2` 的版本特有 UI 规则。通用规则以 `.codex/skills/xiagent-ui-development/SKILL.md` 为准；本文件只记录 V2 的风格、结构、数据接入、节点控件和验证命令。

## 技术栈

- React 19、TypeScript、Vite、Vitest、Testing Library、Playwright。
- 入口：`ui/V2/src/app/App.tsx`。
- 样式：`ui/V2/src/styles/app.css`。
- API 层：`ui/V2/src/api/`。
- 展示转换工具：`ui/V2/src/utils/display.ts`。

## 产品定位

- V2 是面向最终用户的工作流任务平台，不是静态 demo。
- 核心首屏是任务工作台：项目选择、任务列表、创建任务、任务详情、等待交互、运行上下文。
- 资产库和项目页是同一工作台的支撑能力，必须和当前项目上下文一致。
- 默认项目来自后端 `/api/projects` 返回的真实 `project_id=global` 全局项目。

## 视觉规则

- V2 采用克制的后台工作台风格：浅灰背景、白色面板、紧凑网格、明确边线、少装饰。
- CSS token 位于 `:root`：
  - 背景：`--bg: #eef2f6`
  - 面板：`--surface: #ffffff`
  - 文字：`--text: #1f2933`
  - 次级文字：`--muted: #65758b`
  - 主色：`--accent: #2563eb`
  - 圆角：`--radius: 8px`
- 主导航为顶部条，任务工作台为三栏布局：左侧项目/任务，中间工作区，右侧运行上下文；窄屏通过媒体查询降为单列。
- 卡片只用于任务、工作流、项目、资产、节点等独立对象；不要把页面大区块层层套卡片。
- 文本必须在按钮、卡片、表单和状态条内完整可读，移动宽度不得互相遮挡。

## 数据接入规则

- 登录后调用 `/api/projects`，选择真实项目；默认应为 `global`。
- 任务列表、任务详情、事件流、交互提交、资产查询、工作流查询都必须带当前 `project_id`。
- 创建任务调用 `/api/tasks` 时，body 必须包含当前项目 `project_id` 和选中的工作流契约；业务 `input_data` 不得作为创建任务前置表单要求。
- 工作流必填入参在任务创建后的起始输入节点中填写，提交后由后端固化为 `$workflow.input`。
- 工作流列表调用 `/api/workflows?project_id=<current>`；不能用无项目上下文的全部工作流列表驱动用户创建任务。
- 资产查询使用当前项目与 scope，例如 `scope=combined&project_id=<current>`。

## 节点与控件规则

- V2 页面不得直接显示 `input_schema`、`output_snapshot`、`public_url`、节点 ref 或原始 JSON。
- 工作流输入 schema 只能在任务详情的起始输入节点中渲染成可读表单：字符串输入、长文本、选择项、图片资产选择、公开图片地址等。
- 创建任务页不得为 workflow 入参维护独立表单，也不得复制起始输入节点的资产选择、上传或校验逻辑。
- 节点执行输入/输出应渲染为用户卡片：字段列表、文本段落、图片预览、状态、错误和等待操作。
- 节点控件选择遵循工作流优先、节点默认保底：`nodes[].ui` 高于 `workflow.ui.defaults`，`workflow.ui.defaults` 高于 `NodeDescriptor.ui_defaults`，最后才使用系统 fallback。
- 工作流可以分别指定节点的输入、输出、交互和详情控件；工作流只覆盖某一区域时，不应清空其他区域的默认控件。
- 后端 UI 控件 manifest 是控件兼容性的硬性检查来源，V2 React 控件实现必须使用相同 `control_id`、`variant`、`mode` 和 `bindings` 语义。
- 可复用节点 UI 已建立在 `ui/V2/src/node-ui/`：
  - `registry.ts` 负责把后端 `control_id` 映射到 V2 React 控件。
  - `resolve.ts` 负责解析任务节点的交互控件配置和 binding。
  - `ControlLibraryPage.tsx` 负责顶部“控件库”页签。
  - `controls/ImageChoiceThreeControl.tsx` 支持图片三选一的 `equal_grid`、`hero_list`、`hover_focus` 变体。
  - `controls/SchemaFormControl.tsx` 支持 `ui.input.schema_form.v1`，用于任务详情里的起始输入节点和普通等待输入节点。
  - `ui.input.asset_image_picker.v1` 是 schema 表单内的字段级资产图片控件，负责资产库选择、本地上传到资产库后取 URL，并按字段 schema 写入字符串或 URL 数组。
  - 每个控件有稳定 `control_id`。
  - 工作流或节点配置只引用控件 ID、variant、mode、bindings。
  - 控件输入输出必须匹配工作流 schema、节点 descriptor 和运行时交互 payload。
  - 新控件必须补测试，并在本文件记录用途和 payload 约束。
- 任务详情页的节点输入、输出通过 `ui/V2/src/node-ui/` 控件注册表解析；等待交互优先使用控件注册表，未声明交互控件时按节点输出 schema 使用页面级 fallback。
- 节点输入和输出采用上下堆叠布局，不使用左右双栏；默认折叠输入和节点事件，只展开输出或错误区域，避免大输入、大输出节点横向溢出。
- 顶部导航已有“控件库”页签，用于浏览可用控件、变体、能力标签、绑定要求和预览 fixture。
- `system.user_choice.v1` 在没有工作流显式配置时使用 V2 默认三选一控件；工作流仍可通过 `nodes[].ui.controls.interaction` 改为首图大列表或 hover 放大变体。

## 交互状态

- 必须覆盖 loading、empty、error、disabled、saving、waiting、running、succeeded、failed。
- 等待人工输入时，页面显示问题、输入控件和提交动作；提交内容必须满足人工节点 output schema。
- 创建任务后应自动进入任务详情并选中该任务；切换项目时清理旧项目任务详情，避免跨项目残留。
- 项目页必须显示全局项目，但创建项目表单只创建普通用户项目。

## 验证命令

在 `ui/V2` 下运行：

```powershell
npm run test
npm run build
npm run test:e2e
```

涉及后端契约时，至少运行相关后端测试，例如：

```powershell
python -m pytest tests/test_api_smoke.py tests/test_users_service.py tests/test_runtime_service.py -q
```

最终验收必须用真实浏览器和真实后端完成一条主流程：注册/登录、确认当前项目为全局项目、创建任务、进入任务详情、确认页面没有用户不需要理解的 JSON。

## 维护要求

- 修改 V2 配色、布局、项目选择、工作流匹配、节点展示、资产展示或测试策略时，同步更新本文件。
- 如果新增通用规则，更新 `.codex/skills/xiagent-ui-development/SKILL.md`；如果只是 V2 特例，只更新本文件。
