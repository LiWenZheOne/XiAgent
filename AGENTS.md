# XiAgent 项目规则

## 文档语言

所有需要用户评审、git commit备注、交付或长期维护的项目文档使用中文编写。代码标识符、类名、函数名、文件名按 Python 工程习惯使用英文。

## 文档分层

项目文档分为三个一级层级：

- `docs/project-architecture/`：项目级架构、模块关系、跨模块依赖规则。
- `docs/design/`：模块级设计文档。每个核心模块单独成文，避免单个大文档难以维护。
- `docs/development/`：开发约束、编码规范、测试策略、后续实现计划。

## 目录级规则

部分目录包含更细的 `AGENTS.md`，修改对应目录内容前必须同时遵守：

- `workflows/AGENTS.md`：工作流契约、UI 控件配置、工作流验证规则。
- `xiagent/nodes/AGENTS.md`：节点接口、节点实现、`NodeDescriptor.ui_defaults` 和节点 UI 默认规则。

根目录规则优先描述全局边界；目录级规则用于补充该目录的具体落地约束。

文档命名规则：

```text
YYYY-MM-DD-NN-topic-document-kind.md
```

示例：

```text
2026-05-19-01-xiagent-architecture-overview.md
2026-05-19-03-asset-module-design.md
2026-05-19-01-development-guidelines.md
```

命名要求：

- 使用日期前缀，便于追踪文档产生时间。
- 使用两位序号，便于同一天多文档排序。
- topic 使用英文短语，保持路径兼容性。
- document-kind 使用 `overview`、`design`、`guidelines`、`plan` 等有意义后缀。

## 架构约束

XiAgent 第一版采用模块化单体架构。模块内部可以迭代，模块外部调用必须依赖稳定服务接口。

禁止跨模块直接访问其他模块的数据库表、文件路径、内部实现类或第三方库适配细节。

核心领域接口不得依赖 LangGraph、PydanticAI、FastAPI、SQLite 等具体实现。第三方库只能出现在适配器、基础设施或具体节点实现中。

## 节点接口约束

正式代码不使用 `Protocol` 作为平台接口设计。核心接口统一使用 `ABC` 抽象基类进行强约束。

可注册节点必须继承平台提供的 `BaseNode`。测试中可以临时使用 `Protocol` 辅助替身类型，但不得进入正式模块和公开 API。

节点不能直接读取 SQLite、拼接资产文件路径或依赖资产模块内部实现。节点访问资产必须通过 `AssetService`。

## 工作流约束

工作流模板由开发者维护的 YAML/JSON 契约定义，不做低代码或拖拽式工作流编辑器。

工作流第一版支持 DAG 和条件分支，不支持通用循环。节点输入使用长路径引用，例如：

```text
$workflow.input.topic
$nodes.planner.output.plan
```

节点输出不覆盖全局状态。每次节点执行都必须保留独立的输入快照、输出快照、状态、错误和事件。

任务创建前不得收集工作流业务入参。创建任务页只允许展示工作流说明、输入准备提示、节点流程摘要和创建入口；不得根据 `workflow.input_schema` 渲染业务表单，也不得提交业务 `input_data` 作为创建任务的必要条件。

需要用户提供初始参数的工作流，必须在任务创建后通过首个输入节点收集参数。该节点负责等待用户输入、校验 payload，并将结果固化为任务的 `$workflow.input`，后续业务节点继续使用 `$workflow.input.<field>` 长路径引用，不直接依赖输入节点输出路径。

起始输入节点和运行中等待输入节点必须复用同一套节点 UI 控件库和字段控件。不得为任务创建页、起始输入节点和普通等待节点分别维护三套表单或资产选择逻辑。

## 工作流测试约束

调试和验证工作流时，默认优先使用 `xiagent.workflows.testing.WorkflowTestBuilder` 或 `python -m xiagent.workflows.testing_cli`，把它作为无 UI 工作流测试的标准入口。

工作流测试构建器面向开发者与 Codex 共同调试使用，应尽量提供接近 UI 工作流执行的体验：默认创建可用的高权限测试用户和项目，装配运行时、节点注册表、资产服务和工作流目录，并输出任务事件、节点输入快照、节点输出快照、状态、错误以及可识别的图片资产预览信息。

测试工作流依赖前置参数时，优先通过构建器的显式配置方法和 CLI 参数提供，例如数据库路径、资产目录、工作流目录、用户、项目、工作流输入和交互输入。不得为了测试方便直接绕过正式服务接口、权限检查或运行时持久化。

如果现有构建器不能覆盖某类工作流调试场景，应优先评估是否把能力补充到构建器、运行器或 CLI 中，使其成为双方可复用的调试能力；只有一次性、局部且无复用价值的场景才使用临时测试夹具。

## 资产约束

资产模块负责管理本地文件资产和文字资产。资产本体、项目内使用关系、检索分类系统必须解耦。

检索系统独立于文件管理系统。全局检索结构和项目检索结构必须隔离，项目级目录和标签不得污染全局。

资产删除第一版使用软删除，避免历史任务和节点执行记录丢失引用。

## 用户与项目约束

第一版用户模块实现账号密码登录、项目创建、项目归属和基础访问校验。

任务、项目资产、项目工作流模板和项目检索结构必须挂到明确的 `user_id` 与 `project_id` 关系下。

## 开发约束

所有跨模块服务接口在实现前先写清输入、输出、错误语义和权限检查点。

优先保持接口稳定，模块内部实现可以逐步替换。未来从 SQLite 换到 PostgreSQL、从 FTS5 换到向量检索、从 LangGraph 换到其他执行引擎时，不应影响核心接口和上层调用方。

<!-- gitnexus:start -->
# GitNexus 代码智能索引

本项目已通过 GitNexus 建立索引，仓库别名为 **XiAgent**（4517 个符号、9232 条关系、228 条执行流）。理解代码结构、评估改动影响和定位执行流程时，优先使用 GitNexus MCP 工具。

> 如果 GitNexus 工具提示索引过期，先在终端执行 `gitnexus analyze --name XiAgent .` 更新索引。
> 当前本机 GitNexus FTS 扩展不可用，索引未生成 embeddings；自然语言 `query` 可能命中较少。需要稳定结果时，优先使用 `context`、`impact`、`cypher` 和 `gitnexus://repo/XiAgent/...` 资源。

## 必须执行

- **修改任何符号前必须做影响分析。** 修改函数、类或方法前，运行 `gitnexus_impact({target: "symbolName", direction: "upstream", repo: "XiAgent"})`，并向用户说明影响范围，包括直接调用方、受影响执行流和风险等级。
- **提交前必须运行 `gitnexus_detect_changes({repo: "XiAgent"})`**，确认改动只影响预期符号和执行流。
- 如果影响分析返回 HIGH 或 CRITICAL 风险，继续编辑前必须先告知用户。
- 探索不熟悉代码时，优先使用 `gitnexus_query({query: "concept", repo: "XiAgent"})` 查找按执行流分组的结果，再补充文本搜索。
- 需要查看某个符号的完整上下文时，使用 `gitnexus_context({name: "symbolName", repo: "XiAgent"})` 查看调用方、被调用方和参与的执行流。

## 禁止事项

- 禁止在未运行 `gitnexus_impact` 的情况下直接修改函数、类或方法。
- 禁止忽略影响分析中的 HIGH 或 CRITICAL 风险。
- 禁止用普通查找替换重命名符号；应使用理解调用图的 `gitnexus_rename`。
- 禁止在未运行 `gitnexus_detect_changes()` 检查影响范围的情况下提交。

## 资源

| 资源 | 用途 |
|----------|---------|
| `gitnexus://repo/XiAgent/context` | 查看代码库概览与索引新鲜度 |
| `gitnexus://repo/XiAgent/clusters` | 查看全部功能区域 |
| `gitnexus://repo/XiAgent/processes` | 查看全部执行流 |
| `gitnexus://repo/XiAgent/process/{name}` | 查看单个执行流的逐步调用轨迹 |

## CLI

| 任务 | 阅读此技能文件 |
|------|---------------------|
| 理解架构或“X 如何工作” | `.codex/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| 评估“修改 X 会影响什么” | `.codex/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| 追踪“为什么 X 失败” | `.codex/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| 重命名、抽取、拆分或重构 | `.codex/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| 工具、资源和图谱 schema 参考 | `.codex/skills/gitnexus/gitnexus-guide/SKILL.md` |
| 索引、状态、清理、wiki 等 CLI 命令 | `.codex/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
