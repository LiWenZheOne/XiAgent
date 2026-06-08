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

工作流第一版支持 DAG 和条件分支，不支持通用循环。节点输入使用长路径引用，业务数据只能引用上游节点输出，例如：

```text
$nodes.collect_input.output.topic
$nodes.planner.output.plan
```

runtime 不再支持 `system.workflow_input.v1`。工作流业务数据不得使用 `$workflow.input.*` 引用；后续节点必须引用上游节点输出，例如 `$nodes.collect_input.output.prompt`。

节点输出不覆盖全局状态。每次节点执行都必须保留独立的输入快照、输出快照、状态、错误和事件。

任务创建前不得收集工作流业务入参。创建任务页只允许展示工作流说明、输入准备提示、节点流程摘要和创建入口；不得根据 `workflow.input_schema` 渲染业务表单，也不得提交业务 `input_data` 作为创建任务的必要条件。

需要用户提供初始参数的工作流，必须在任务创建后通过普通节点输入收集参数。节点 input spec 使用 `from_user: true` 声明等待用户填写；运行时校验用户提交 payload 后写入该节点 `input_snapshot`，再执行节点并产生 `output_snapshot`。后续业务节点必须引用该节点输出，不得引用 workflow 级输入。

泛用输入节点使用 `system.user_input.v1`。专用业务节点也可以直接声明 `from_user: true` 输入，等待用户填写后继续运行。

初始参数节点和运行中等待输入节点必须复用同一套节点 UI 控件库和字段控件。UI 控件统一绑定节点 `input`、`metadata`、`output` 或上游节点输出，不再绑定 `workflow.input`。不得为任务创建页、初始输入节点和普通等待节点分别维护三套表单或资产选择逻辑。

## 工作流测试约束

调试和验证工作流时，默认优先使用 `xiagent.workflows.testing.WorkflowTestBuilder` 或 `python -m xiagent.workflows.testing_cli`，把它作为无 UI 工作流测试的标准入口。

工作流测试构建器面向开发者与 Codex 共同调试使用，应尽量提供接近 UI 工作流执行的体验：默认创建可用的高权限测试用户和项目，装配运行时、节点注册表、资产服务和工作流目录，并输出任务事件、节点输入快照、节点输出快照、状态、错误以及可识别的图片资产预览信息。

测试工作流依赖用户业务参数时，必须通过真实等待/提交交互路径提供，例如构建器或 CLI 的交互输入能力。不得把业务参数塞到创建任务 `input_data` 或旧 workflow input 入口中绕过运行时。

如果现有构建器不能覆盖某类工作流调试场景，应优先评估是否把能力补充到构建器、运行器或 CLI 中，使其成为双方可复用的调试能力；只有一次性、局部且无复用价值的场景才使用临时测试夹具。

## UI 真实交互验收约束

涉及网页 UI、任务详情、节点输入控件、资产选择、项目/任务操作或用户明确要求“真实交互测试”时，最终验收必须优先使用 Codex 内部浏览器（in-app browser / Browser plugin）连接真实后端和真实 UI，按真实用户路径点击、输入、提交、等待、刷新或跳转确认结果。

外部浏览器自动化 CLI、旧 e2e 脚本、组件测试、接口测试、直接数据库/接口造数、伪造 localStorage、截图检查或无 UI CLI/Builder 路径只能作为辅助验证，不能替代最终真实交互验收。若 Codex 内部浏览器不可用，必须列出具体阻塞原因和待人工验证步骤，不得声称真实交互测试已通过。

## 易错点开工检查

涉及 UI、工作流、节点控件、任务运行、部署或验收前，必须先确认目标版本、运行环境和权威数据来源，不得根据习惯推断。尤其要确认当前是 `ui/V1` 还是 `ui/V2`、前端连接的真实后端地址、后端工作流目录是否已加载当前磁盘契约、以及验收对象是新任务还是历史任务。

工作流业务输入只能通过任务创建后的普通节点输入收集。不得把业务参数重新放回任务创建页、创建任务 `input_data`、`workflow.input_schema`、`system.workflow_input.v1` 或 `$workflow.input.*`。起始输入节点和运行中等待输入节点都必须走同一套节点 UI 控件库，运行时写入该节点快照，后续节点引用该节点输出。

修改工作流 YAML、节点 UI 配置、控件 manifest 或控件注册表后，验收前必须确认后端 workflow catalog 已重启或重载；新配置验收必须创建新任务并检查该任务持有的新 workflow snapshot。历史任务按旧 snapshot 展示是正确行为，不能通过修改旧 `control_id`、variant、mode 或 binding 的前端语义来让历史任务看起来像新配置；需要历史任务采用新配置时，必须显式迁移或修正其 snapshot/config。

用户对目标版本、部署范围、分支名称或验收方式做出更正时，以最新明确更正为准并立即停止沿用旧目标。生产 V2 前端是静态构建产物时，“重启前端”应理解为重新构建/刷新静态资产并验证或重载 Web 服务，不得凭空假设存在独立前端守护进程。

发现新的可复用规则或修正旧规则时，必须在同一轮同步更新对应层级：根 `AGENTS.md`、目录级 `AGENTS.md`、`.codex/skills/*`、`ui/<version>/docs/ui-development-rules.md` 或相关设计文档。只修代码不更新规则，视为未完成防复发处理。

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
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **XiAgent** (7916 symbols, 17165 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/XiAgent/context` | Codebase overview, check index freshness |
| `gitnexus://repo/XiAgent/clusters` | All functional areas |
| `gitnexus://repo/XiAgent/processes` | All execution flows |
| `gitnexus://repo/XiAgent/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
