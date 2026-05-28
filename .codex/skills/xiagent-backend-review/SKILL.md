---
name: xiagent-backend-review
description: Use when reviewing XiAgent backend code changes involving api, users, assets, workflows, nodes, runtime, infrastructure, model providers, service interfaces, data ownership, module boundaries, contract stability, coupling, or extensibility.
---

# XiAgent 后端代码审查

## Overview

审查 XiAgent 后端改动时，先判断数据口径、模块职责和公共契约是否稳定，再看局部实现质量。目标不是只挑代码风格，而是阻止跨模块偷取数据、重复定义口径、绕开服务接口、把扩展点堆成临时分支。

## Review Workflow

1. 先进入代码审查姿态：输出时 findings 在前，按严重级别排序；没有问题时明确说没有发现阻塞问题。
2. 读取根 `AGENTS.md`，再按改动目录读取对应目录 `AGENTS.md`。涉及节点读 `xiagent/nodes/AGENTS.md`，涉及工作流读 `workflows/AGENTS.md`。
3. 查看改动面：`git status --short`、`git diff --stat`、目标 diff。审查当前未提交代码时运行 `gitnexus_detect_changes({repo: "XiAgent"})`，用它核对影响的符号和执行流。
4. 对不熟悉的符号或流程，用 GitNexus `context`、`impact`、`api_impact` 或 `route_map` 补足调用方、下游消费者和 API 形状影响。不要只靠文本搜索判断边界。
5. 先按“架构与契约”审，再按“实现与测试”审。架构问题即使代码能跑，也应优先指出。
6. 给出修复方向时，说明应该归属到哪个模块、哪个服务接口或哪个契约，而不是只说“重构一下”。

## Severity

| Level | Use For |
| --- | --- |
| P0 | 数据越权、凭据泄漏、破坏任务/节点历史记录、公共契约大面积不兼容。 |
| P1 | 跨模块绕过服务接口、核心接口泄漏第三方实现、数据口径出现多个来源、扩展点走向硬编码分支。 |
| P2 | 错误语义不稳定、测试缺失、DTO/schema 与实际输出不一致、文档未随接口变更同步。 |
| P3 | 命名、局部重复、可读性、非阻塞的测试覆盖或维护性问题。 |

## Architecture Gates

### 1. 数据口径唯一

- 同一个业务概念只能有一个权威来源：用户/项目归属归 `UserService`，资产本体和分类归 `AssetService`，工作流模板契约归 `WorkflowService`，任务和节点执行记录归 `RuntimeService` 或 `ExecutionStore`。
- 审查是否存在同一字段在 API、workflow、node、UI config、repository 中重复定义且语义不一致。
- 工作流节点输出以 `outputs` JSON Schema 为唯一数据契约来源。不要在 `inputs`、`config`、UI `layout` 或前端控件配置里再复制一份业务 schema。
- 全局和项目作用域必须隔离。任何项目资产、项目模板、项目检索结构、任务记录都必须能追溯明确的 `user_id` 和 `project_id`。
- 节点执行记录必须保留独立 input/output 快照，不得用“最新状态”覆盖历史。

### 2. 功能归属正确

- API 层只做请求解析、权限入口和 application service 调用，不直接读写数据库、文件系统、节点实现或 provider SDK。
- 用户、项目、资产、工作流、节点、运行时各自维护自己的内部实现；跨模块调用只能走稳定服务接口或注册表。
- 节点只负责把工作流输入适配为节点结果。资产访问走 `AssetService` 或 `NodeContext` 暴露的正式能力；模型访问走 `ChatModelRouter` 和 provider。
- 工作流模块负责契约加载、节点引用、DAG 和条件分支校验；LangGraph 只是适配器，不是工作流契约中心。
- UI 展示规则归 UI manifest、workflow UI config 或节点 `ui_defaults` 保底建议；不要把具体页面布局、React 组件路径或某个工作流体验写进后端节点。

### 3. 模块解耦

允许依赖方向：

```text
api -> application services
runtime -> users/assets/workflows/nodes/adapters
workflows -> nodes registry
users -> infrastructure
assets -> infrastructure
nodes -> core interfaces
adapters -> core interfaces + third-party runtime
```

必须指出的违规依赖：

```text
api -> sqlite tables
nodes -> sqlite tables
nodes -> local file paths
workflows -> langgraph types
assets -> runtime internals
users -> assets internals
users -> workflow internals
```

其他红线：

- 不得从其他模块导入 repository、database model、内部 helper 来绕过服务接口。
- 业务服务接口不得返回 ORM/数据库对象；对外返回领域 record 或 DTO。
- 核心领域接口不得暴露 FastAPI、SQLite、LangGraph、PydanticAI、OpenAI SDK 等具体实现类型。
- 正式平台接口使用 `ABC` 抽象基类，不使用 `Protocol` 作为公开接口。测试替身可以临时使用 `Protocol`。

### 4. 强契约和扩展点

- 经常扩展的能力必须有稳定入口：service interface、ABC、registry、router、provider、manifest、DTO、JSON Schema 或版本化 `ref`。
- 新增 provider、节点、工作流能力时，优先扩展已有 router/registry/schema；不要复制一套平行接口。
- 公共契约必须写清输入、输出、错误语义、权限检查点和兼容性。错误不能只靠字符串或日志表达，应有稳定 code/status/details，details 不得包含敏感信息。
- 节点 `NodeDescriptor.ref` 使用稳定版本化 ref，例如 `tool.echo.v1`。输入输出 schema 要能被工作流下游通过长路径稳定引用。
- 需要改 `BaseNode`、`NodeContext`、`ChatRequest`、`ChatResponse`、`RuntimeService`、workflow validator 等公共框架时，按框架变更处理：先说明影响面、迁移策略和回归测试，不要伪装成局部实现。

## Review Checklist

| Question | Problem Signal |
| --- | --- |
| 数据口径是否唯一？ | 同一字段多个 owner、schema 重复、API/节点/UI 各算一遍。 |
| 功能是否在正确模块？ | API 写业务细节、节点读 DB、workflow 依赖 LangGraph 类型。 |
| 跨模块是否只走服务接口？ | 导入其他模块 repository、表模型、内部 helper。 |
| 扩展点是否有强契约？ | 新能力靠 if/else、复制 provider、硬编码 workflow 专属字段。 |
| 错误语义是否稳定？ | 只打印日志、吞异常、返回随意字符串、泄漏 key/header。 |
| 权限和作用域是否完整？ | 缺少 user/project 校验，全局和项目分类互相污染。 |
| 历史记录是否可追溯？ | 节点 input/output 被覆盖，任务事件缺失。 |
| 测试是否覆盖契约？ | 只测 happy path，未测 schema、注册表、权限、错误、替身。 |
| 文档是否同步？ | 跨模块接口变更但未更新 `AGENTS.md`、`docs/design/` 或 `docs/development/`。 |

## Anti-Mess Signals

发现以下情况时，优先按架构风险审查：

- “临时字段”进入公共 schema、DTO、节点输出或 API 响应。
- 某个工作流需要展示变化，就新增后端字段或节点，而不是扩展 UI manifest/control。
- provider 或外部服务接入绕过 `ChatModelRouter`，在节点里直接拼 HTTP、读 key、轮询状态。
- 资产路径、SQLite 表名、FTS 查询细节出现在节点、API 或运行时外层。
- 用工具函数跨模块共享业务规则，导致 owner 不清。
- 为每个业务场景复制一份相似节点、相似 provider、相似 service 方法。
- 测试依赖真实外部 API、真实密钥或本机私有配置。
- 为了让当前页面跑通，牺牲工作流契约、节点 schema 或历史快照稳定性。

## Expected Output

审查结果使用中文，优先列问题：

```text
**Findings**
- [P1] 标题：说明具体风险。文件:行
  说明违反的数据口径、模块边界或契约规则，以及建议修复归属。

**Open Questions**
- 仅列影响判断的问题。

**Tests / Verification**
- 说明已运行或缺失的验证，例如 GitNexus detect_changes、pytest、workflow testing_cli。
```

如果没有发现问题：

```text
未发现阻塞性问题。剩余风险：说明未覆盖的测试、未验证的执行流或依赖的假设。
```

## Common Fix Directions

- 口径重复：选定 owner，把派生逻辑收回 owner service，其它模块只消费 DTO/schema。
- 模块串线：把直接导入的 repository/model/helper 替换为正式 service 或 registry 调用。
- 扩展失控：新增或扩展 ABC/provider/registry/manifest，而不是继续加场景分支。
- 契约不稳：先定义 DTO、JSON Schema、错误 code/status，再改实现。
- 节点过重：拆成稳定生成节点、用户选择节点、资产访问服务或 provider 适配器。
- 测试薄弱：补权限、scope 隔离、schema 一致性、错误语义、外部服务 fake、WorkflowTestBuilder/CLI 回归。
