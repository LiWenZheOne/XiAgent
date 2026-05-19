# XiAgent 架构总览

## 项目定位

XiAgent 是一个契约驱动的 Agent 工作流后端平台。系统面向开发者维护工作流模板，面向用户执行已发布的工作流任务。

XiAgent 不做低代码或拖拽式工作流平台。用户端不负责编排工作流，只选择已有工作流模板并提交输入。开发者通过 YAML/JSON 契约编排工作流，通过节点接口封装 AI 模型、工具脚本、人工确认和未来的子工作流。

## 核心目标

- 用约定契约描述工作流模板，保证模板可校验、可版本化、可由前端读取。
- 用强约束节点接口隔离模型、工具、脚本和执行引擎。
- 用任务、节点执行记录和事件持久化完整执行状态，支持未来中断、恢复、回溯和重跑。
- 用资产库模块统一管理本地文件资产和文字资产，供节点和工作流使用。
- 用用户与项目模块建立任务、资产、模板和检索结构的归属边界。
- 保持模块化单体架构，模块内部可迭代，模块外部接口稳定。

## 总体架构

```text
api
  ↓
application services
  ├─ users
  ├─ assets
  ├─ workflows
  ├─ nodes
  └─ runtime
        ↓
  adapters/langgraph
        ↓
  concrete node implementations

infrastructure
  ├─ sqlite
  ├─ local file storage
  ├─ json schema validation
  └─ logging
```

## 一级模块

### users

用户与项目模块。负责账号、登录、项目、项目归属和基础访问校验。

对外提供 `UserService`。其他模块不得直接读取用户表或项目表。

### assets

资产模块。负责本地文件资产、文字资产、资产元数据、全局和项目级目录树、标签、搜索索引、项目资产绑定。

对外提供 `AssetService`。节点、运行时和 API 不得直接读取资产文件路径或检索表。

### workflows

工作流模板模块。负责加载 YAML/JSON 契约、校验模板结构、校验节点引用、校验 DAG 和条件分支。

对外提供 `WorkflowService`。LangGraph 不是契约中心，只是执行适配器。

### nodes

节点模块。负责 `BaseNode`、`NodeDescriptor`、`NodeResult`、`NodeRegistry` 和具体节点实现。

正式节点必须继承 `BaseNode`。节点注册第一版采用显式注册，不做自动扫描。

### runtime

任务运行模块。负责创建任务、执行节点、保存节点执行记录、保存任务事件、处理等待与恢复、派生任务视图。

对外提供 `RuntimeService`。运行时可以调用 `UserService`、`AssetService`、`WorkflowService`、`NodeRegistry` 和 LangGraph 适配器。

### adapters/langgraph

LangGraph 适配器。只负责把平台工作流契约翻译成 LangGraph 可执行图，并把 LangGraph 执行过程接回平台运行时。

核心领域对象不得依赖 LangGraph 类型。

### api

REST API 层。第一版使用 FastAPI。API 层只调用 application service，不直接读写数据库、文件系统或节点实现。

### infrastructure

基础设施模块。第一版包含 SQLite、FTS5、本地文件存储、JSON Schema 校验器、密码哈希、日志等实现。

## 跨模块依赖规则

允许依赖：

```text
api -> application services
runtime -> users/assets/workflows/nodes/adapters
workflows -> nodes registry
users -> infrastructure
assets -> infrastructure
nodes -> core interfaces
adapters -> core interfaces + third-party runtime
```

禁止依赖：

```text
api -> sqlite tables
nodes -> sqlite tables
nodes -> local file paths
workflows -> langgraph types
assets -> runtime internals
users -> assets internals
users -> workflow internals
```

## 作用域模型

系统支持全局和项目两个作用域。

```text
Global
  ├─ Global Assets
  ├─ Global Asset Taxonomy
  └─ Global Workflow Templates

User
  └─ Project
       ├─ Tasks
       ├─ Project Assets
       ├─ Project Asset Taxonomy
       └─ Project Workflow Templates
```

全局资产和全局工作流模板可被项目使用。项目可以建立自己的目录树、标签、用途说明和项目模板，不污染全局。

## 第一版技术选择

- 后端形态：模块化单体。
- API：FastAPI。
- 工作流执行：LangGraph 适配器。
- AI 节点实现：可使用 PydanticAI，但不进入核心接口。
- 存储：SQLite。
- 文件资产：本地文件存储，按内容 hash 分片。
- 检索：SQLite FTS5 + 关系表目录树和标签。
- 接口约束：抽象基类 `ABC`。
- 契约校验：JSON Schema。

## 明确非目标

- 不做低代码工作流编排器。
- 不做拖拽式节点画布。
- 不做完整 RBAC 和团队协作。
- 不做微服务拆分。
- 不支持外部 URL 资产。
- 不做向量检索。
- 不支持通用循环工作流。
- 不实现完整回溯重跑 UI。
- 不把 LangGraph、PydanticAI、FastAPI、SQLite 类型暴露到核心接口。
- 不在正式代码中使用 `Protocol` 作为平台接口。

