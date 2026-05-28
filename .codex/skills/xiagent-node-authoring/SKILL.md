---
name: xiagent-node-authoring
description: Use when creating or modifying XiAgent BaseNode implementations, node refs, NodeDescriptor schemas, node registry entries, or tests for workflow node capabilities.
---

# XiAgent 节点编写

## Overview

新增或修改节点时，先按需求检查现有节点和对应 UI 节点控件是否已经满足；存在候选节点时暂停并让用户确认复用还是继续新建。确需开发时，必须先用 TDD 固化行为，再实现 `BaseNode` 节点并注册到节点注册表。

## Core Workflow

1. 明确节点规格：`ref`、职责、输入 schema、输出 schema、错误语义、资产访问、外部服务或凭据、是否需要人工交互、是否需要通用 `ui_defaults`、目标 UI 节点控件是否已存在。
2. 检查现有节点是否满足需求：读取 `build_node_registry(settings)`、现有节点 `NodeDescriptor`、相近节点实现和测试，按职责、输入输出 schema、错误语义和依赖能力判断可复用性。
3. 如果找到一个或多个候选节点，暂停开发新节点，向用户列出候选 `ref`、匹配点、差距和复用影响，并等待用户确认“复用现有节点”还是“继续开发新节点”。用户未确认前不要写新节点代码或测试。
4. 第一轮需求方案确认时，同步核对目标节点体验需要的 UI 节点控件。如果缺少对应控件，把控件新增或修改列入同一计划：建议 `control_id`、variant、mode、bindings、依赖的输出 schema、manifest、V2 控件实现、预览/校验测试和目标工作流接入点。然后建议使用 `$xiagent-ui-control-library-authoring` 补控件。
5. 只有确认需要新建或修改节点后，先读现有模式：`AGENTS.md`、`xiagent/nodes/AGENTS.md`、`xiagent/nodes/base.py`、`xiagent/nodes/registry.py`、`xiagent/nodes/__init__.py`、相近节点实现和测试。
6. RED：先写失败测试。节点行为测试通常放在 `tests/test_node_registry.py`、现有节点测试文件，或新建聚焦测试文件。测试应直接执行节点或验证注册表行为。
7. 运行目标测试，确认失败原因是节点能力缺失，而不是测试拼写、导入错误或夹具错误。
8. GREEN：实现最小节点代码。正式节点必须继承 `BaseNode`，实现 `describe()` 和 `execute()`，返回 `NodeResult`。
9. 注册节点：按现有模式更新 `xiagent/nodes/__init__.py` 的 `build_node_registry(settings)`，必要时更新包导出。
10. REFACTOR：只在测试为绿后整理命名、抽取小函数或压缩重复。
11. 回接工作流：如果节点是为某个工作流缺口创建的，返回节点 `ref`、输入输出 schema、示例工作流片段、UI 控件配置或控件缺口处理结果，并用 `WorkflowTestBuilder` 或 CLI 验证目标工作流。

## Project Constraints

- 正式代码不使用 `Protocol` 作为平台接口；核心接口统一使用 `ABC` 抽象基类。
- 可注册节点必须继承平台 `BaseNode`，不要绕过 `NodeRegistry` 的类型检查。
- 节点不得直接读取 SQLite、拼接资产文件路径或依赖资产模块内部实现；访问资产必须通过 `AssetService` 或 `NodeContext` 暴露的正式能力。
- 核心领域接口不得依赖 LangGraph、PydanticAI、FastAPI、SQLite 等具体实现；第三方库只能出现在适配器、基础设施或具体节点实现中。
- 模型类第三方能力可以注册为工作流节点，但节点不得直接依赖模型 SDK、HTTP/API 实现、请求地址、轮询细节或密钥配置；RunningHub、DeepSeek 等能力必须通过 `ChatModelRouter` 调用 `xiagent.models.providers.*`，节点只负责把工作流输入输出适配为模型请求和节点结果。
- 节点输入输出 schema 要能被工作流契约和下游节点稳定引用；不要把临时内部字段暴露为公共契约。
- 普通业务节点不得通过任务创建页或创建任务 `input_data` 获取业务参数。需要用户填写的节点 input spec 必须显式声明 `from_user: true`；运行时校验 payload 后写入该节点 `input_snapshot`，再执行节点并产生 `output_snapshot`。
- runtime 不再支持 `system.workflow_input.v1`；节点输出不得要求下游通过 `$workflow.input.*` 读取业务数据。
- 外部 API 节点必须明确凭据来源、超时、失败状态和测试替身；不要在测试里真实调用外部服务。

## Structured Output Boundary

- LLM 结构化输出节点的业务数据契约必须由工作流节点的 `outputs` JSON Schema 声明；节点代码只实现通用结构化生成、JSON 解析、schema 校验、失败重试和错误语义。
- 通用结构化节点应读取 `NodeContext.output_schema` 作为目标 schema，不要把角色表、分镜表、镜头表等业务字段硬编码进节点实现。只有明确创建专用领域节点时，才允许在节点描述中固定领域输出结构。
- 不要为了让节点拿到结构而在 `inputs` 或 `config` 里重复一份输出 schema；除非是兼容旧工作流的过渡方案，否则以工作流 `outputs` 为唯一数据契约来源。
- UI `layout`、表格列名、审批展示文案只负责展示，不得替代 `outputs` 数据契约；下游节点必须依赖 `$nodes.<id>.output...` 中由 schema 声明的字段。

## UI Defaults Boundary

- 节点 UI 规则以 `docs/design/2026-05-27-01-ui-control-manifest-design.md` 为准。
- 第一轮需求方案确认必须核对目标体验需要的 UI 节点控件是否已经存在；缺控件时，把控件 manifest、后端暴露、V2 控件实现、绑定校验和测试纳入同一轮新增/修改计划。
- 节点可以在 `NodeDescriptor.ui_defaults` 中提供通用默认展示建议，但不得把某个工作流的具体体验写死到节点里。
- 控件选择优先级是 `nodes[].ui` > `workflow.ui.defaults` > `NodeDescriptor.ui_defaults` > 系统 fallback；节点默认只负责保底。
- `ui_defaults` 只能引用后端 UI 控件 manifest 中存在的 `control_id`、`variant`、`mode` 和 `bindings`。不要引用 V2 React 组件路径或前端内部实现。
- 用户输入节点的 `ui_defaults` 应使用通用 schema 表单控件承载字段控件；不要创建任务创建页专用表单或 workflow-only 控件分支。
- UI 控件统一绑定节点 `input`、`metadata`、`output` 或上游节点输出，不再绑定 `workflow.input`。
- 节点输出 schema 必须先稳定描述业务数据，再让 UI 控件绑定它；不要为了某个控件临时暴露内部字段。
- 图片、资产、候选列表、三选一等 UI 需求应通过稳定字段表达，例如图片候选数组、图片 URL 字段、选择结果字段。字段是否足够应由工作流 validator 和 UI manifest 校验。
- 默认推荐把生成候选图和用户三选一拆成不同节点；如果三选一可复用于多个工作流，优先新增或复用用户选择节点。
- 保留高级单节点模式：复合节点可以生成候选图并等待用户选择，但必须使用标准 waiting/resume 语义，候选图和选择结果都要能由 schema 或快照稳定表达。
- 如果需要新的展示方式，优先新增或扩展 UI 控件 manifest 和 V2 控件库；不要在节点实现中加入前端布局逻辑。
- 当节点提供 `ui_defaults` 时，节点测试至少覆盖 `NodeDescriptor` 中 schema 与默认 bindings 指向字段的一致性。

## Framework Change Gate

- 如果节点开发需要修改 `BaseNode`、`NodeContext`、`NodeRegistry`、运行时服务、工作流校验器、输入解析器或其它基础框架代码，先暂停实现，向用户说明修改原因、影响范围、兼容性和测试计划，等待用户确认后再改。
- 只在新增或修改节点自己所属文件、节点测试、注册表接入时可以直接按本 skill 的 TDD 流程推进；不要把基础框架改造伪装成节点内部改动。

## TDD Checklist

| Phase | Required Evidence |
| --- | --- |
| Reuse Check | 已检查现有节点，并在存在候选节点时取得用户确认。 |
| UI Control Plan | 已检查目标 UI 节点控件是否存在；缺控件时已列入控件库新增/修改计划。 |
| RED | 新测试已运行并按预期失败。 |
| GREEN | 最小节点实现后目标测试通过。 |
| Registry | 注册表能列出并获取新节点 ref。 |
| Contract | 工作流校验能识别节点 schema。 |
| UI Defaults | 如果提供 `ui_defaults`，默认控件和 bindings 与节点 schema 一致。 |
| Runtime | 目标工作流可用构建器或 CLI 走通。 |

不能展示 RED 失败证据时，不要声称完成 TDD。

## Implementation Notes

- `NodeDescriptor.ref` 使用稳定版本化 ref，例如 `tool.echo.v1`、`ai.deepseek_chat.v1`。
- `describe()` 描述节点名称、输入 schema、输出 schema 和必要元数据；schema 要和工作流输入路径匹配。
- `execute()` 从 `inputs`、`NodeContext` 和正式服务接口取数据；保持输出结构稳定。
- 成功返回 `NodeResult(status="succeeded", output=...)`；需要等待人工输入时通过 input spec 的 `from_user: true` 进入等待/提交路径，或按现有 human approval 节点模式返回等待状态。
- 错误要进入节点结果或运行时错误语义，不要吞掉异常或只打印日志。

## Validation

常用命令：

```powershell
python -m pytest tests/test_node_registry.py -q
python -m pytest tests/test_workflow_validator.py -q
python -m pytest tests/test_workflow_testing_runner.py -q
python -m pytest -q
```

如果节点是为某个工作流新增的，再运行：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/<workflow-id>.workflow.yaml --interactive
```

## Common Mistakes

- 先写节点再补测试：违反 TDD，回到 RED 阶段。
- 第一轮方案只列节点代码、不列 UI 控件缺口：必须同步检查控件库，缺控件时纳入同一计划。
- 没查现有节点就新建：先列出现有候选节点，等待用户确认复用或继续开发。
- 让任务创建页提交业务参数，或让节点把初始参数写回 `$workflow.input`：应使用 `system.user_input.v1` 或声明 `from_user: true` 的业务节点，并让下游引用该节点输出。
- 注册了节点但没测试注册表：工作流可能仍找不到 `ref`。
- 节点直接访问数据库或资产路径：改为通过正式服务接口。
- RunningHub 或 DeepSeek 节点直接导入 SDK、拼接 HTTP 请求或读取模型密钥：改为通过 `ChatModelRouter` 和 `xiagent.models.providers.*`，节点只保留输入输出适配逻辑。
- 输出 schema 和实际输出不一致：工作流验证可能通过，但运行时下游会断。
- 为了满足一个工作流写死字段：把稳定能力抽象到节点输入输出契约里。
