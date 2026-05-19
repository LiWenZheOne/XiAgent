# 工作流测试运行器设计

## 背景

当前 `tests/test_manual_workflow_logging.py` 通过 FastAPI TestClient 模拟一次完整工作流执行，并把步骤打印到测试日志里。这能验证 API 闭环，但作为日常调试工具不够方便：

- 每次调试都需要写或修改 pytest 用例。
- 不容易直接执行 `workflows/` 目录下已有工作流文件。
- 遇到人工等待节点时，缺少接近 UI 的交互恢复体验。
- 节点输入、输出、事件和执行快照分散在断言和日志中，不适合临时观察。
- 如果节点输入或输出包含图片，普通 JSON 日志只能显示原始字段，不能提供有效预览。

第一版需要提供一个不依赖 UI 的工作流测试入口，让开发者可以用命令行执行指定工作流，同时保留正式运行时的权限、事件、快照和恢复语义。

## 目标

- 在工作流模块下提供测试专用构建器，快速准备工作流执行所需依赖。
- 提供 CLI 入口执行指定工作流文件或已加载工作流模板。
- 默认创建或复用一个测试管理员用户和测试项目，避免每次手动注册登录。
- 支持通过命令行参数、JSON 文件或交互式提示提供工作流输入。
- 执行过程中逐步展示任务事件、节点输入快照、输出快照、等待状态和错误。
- 遇到 `waiting` 任务时，在 CLI 中收集恢复输出，并调用正式 `RuntimeService.resume_task` 继续执行。
- 对图片输入和输出提供稳定的展示方式：路径打印、系统查看器打开、HTML 预览报告。
- 复用正式 `RuntimeService`、`UserService`、`WorkflowCatalog` 和 `NodeRegistry`，不新增第二套工作流执行引擎。

## 非目标

- 不实现新的 UI 页面或拖拽式工作流编辑器。
- 不改变工作流契约格式。
- 不绕过项目权限校验，也不直接写任务、节点执行或事件表。
- 不把终端内图片渲染作为第一版能力，因为 PowerShell、Windows Terminal、IDE 终端和 CI 环境支持不一致。
- 不为测试工具引入复杂 TUI 框架。第一版使用标准输入输出和 HTML 报告即可。

## 模块边界

新增测试工具放在工作流模块下：

```text
xiagent/workflows/testing/
  __init__.py
  builder.py
  runner.py
  console.py
  artifacts.py
```

新增命令行入口：

```text
xiagent/workflows/testing_cli.py
```

职责划分：

- `builder.py`：构建测试会话，负责数据库迁移、服务装配、测试用户、测试项目和工作流目录加载。
- `runner.py`：执行一个工作流，处理任务创建、等待恢复、事件读取和运行结果聚合。
- `console.py`：负责命令行交互展示，包括输入采集、事件输出、等待节点提示和恢复输出采集。
- `artifacts.py`：识别并保存图片等运行产物，生成 HTML 预览报告，按需调用系统默认查看器。
- `testing_cli.py`：解析命令行参数，调用 builder、runner 和 console，不包含业务执行逻辑。

该工具属于开发与测试辅助能力。正式 API 和运行时不依赖 `xiagent.workflows.testing`。

## 测试会话构建器

`WorkflowTestBuilder` 使用链式配置，默认值适合本地开发：

```python
session = await (
    WorkflowTestBuilder()
    .with_database_path(Path(".data/workflow-test.sqlite3"))
    .with_asset_storage_dir(Path(".data/workflow-test-assets"))
    .with_workflow_dir(Path("workflows"))
    .with_default_admin(username="workflow-test-admin")
    .with_default_project(name="Workflow Test Project")
    .build()
)
```

`build()` 返回 `WorkflowTestSession`，包含：

```text
settings
users
assets
node_registry
runtime
workflows
user
project
run_output_dir
```

默认测试管理员不是超级用户表字段，也不绕过权限。构建器通过正式 `SqliteUserService` 创建或复用用户，再通过正式项目接口创建或复用项目。后续任务仍然带明确的 `user_id` 和 `project_id`。

第一版高权限含义限定为：测试构建器自动准备拥有目标测试项目的用户。它不授予跨项目访问能力。

## 工作流选择

CLI 支持两种选择方式：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml
python -m xiagent.workflows.testing_cli --workflow-id deepseek_echo
```

规则：

- 传入文件路径时，直接调用 `load_workflow_file()` 读取并交给 `RuntimeService.create_task_from_contract()`。
- 传入 `--workflow-id` 时，从 `WorkflowCatalog` 读取已加载模板。
- 项目作用域工作流必须使用当前测试项目；如果契约中已有 `project_id`，必须与测试项目一致。
- 工作流执行前继续使用现有 `validate_workflow_contract()` 和 `validate_json_value()`。

## 输入采集

CLI 支持三种输入来源：

```powershell
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input '{"prompt":"你好"}'
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --input-file .data/input.json
python -m xiagent.workflows.testing_cli workflows/global/deepseek_echo.workflow.yaml --interactive
```

输入优先级：

1. `--input`
2. `--input-file`
3. `--interactive`
4. 如果都没有提供，则根据 `workflow.input_schema.required` 逐项询问。

交互式输入第一版只对常见 JSON Schema 类型做简单提示：

- `string`：读取一行文本。
- `number`、`integer`：读取后转换。
- `boolean`：接受 `true/false`、`yes/no`。
- `object`、`array`：要求输入 JSON。

最终输入必须通过工作流 `input_schema` 校验。

## 执行过程展示

执行输出按事件流和节点快照组织，示例：

```text
[01] 加载工作流 deepseek_echo 1.0.0
[02] 准备测试用户 workflow-test-admin
[03] 准备测试项目 Workflow Test Project
[04] 创建任务 task_xxx
[05] node_started chat ai.deepseek_chat.v1
     input: {"prompt": "你好"}
[06] node_succeeded chat
     output: {"text": "...", "model": "deepseek-v4-flash", "usage": {...}}
[07] task_succeeded
```

展示层读取 `RuntimeService.list_events()` 和 `RuntimeService.list_node_executions()`，不直接查询数据库。对同一事件和节点执行记录，CLI 保持任务内顺序稳定，便于与 UI 的时间线体验对应。

## 人工等待与恢复

当任务状态为 `waiting` 时，runner 读取最近的 waiting 节点执行记录，并展示：

- `node_id`
- `node_ref`
- `input_snapshot`
- `metadata.requested_inputs`
- 节点 `outputs` schema

CLI 提示用户输入恢复输出 JSON：

```text
[等待输入] 节点 review system.human_approval.v1
requested_inputs:
  topic: 测试

请输入恢复输出 JSON:
> {"decision":"approve"}
```

恢复输出先通过等待节点的 `outputs` schema 校验，再调用：

```python
await session.runtime.resume_task(
    user_id=session.user.user_id,
    project_id=session.project.project_id,
    task_id=task.task_id,
    node_id=waiting_node_id,
    output=resume_output,
)
```

如果恢复后再次进入 `waiting`，继续提示。第一版默认允许多次等待恢复，但仍由工作流 DAG 和运行时状态决定能否继续。

## 图片与产物展示

CLI 不要求终端直接渲染图片。第一版支持三种稳定方式：

### 路径打印

默认输出图片引用信息：

```text
[图片输出] node=render field=result.image
path: D:\...\data\workflow-test-runs\task_xxx\images\render_result_image.png
mime: image/png
```

### 系统查看器

使用 `--open-images` 时，CLI 对识别出的图片路径调用系统默认查看器。在 Windows 上使用 Python 标准库能力打开本地文件，不把系统命令写入运行时模块。

```powershell
python -m xiagent.workflows.testing_cli workflows/demo.workflow.yaml --open-images
```

### HTML 预览报告

使用 `--preview html` 时，运行结束后生成：

```text
.data/workflow-test-runs/<task_id>/preview.html
```

报告按节点展示：

- 节点基本信息。
- 输入快照中的图片。
- 输出快照中的图片。
- 文本输入输出的 JSON 摘要。
- 错误信息。
- 图片文件链接和缩略图。

如果同时传入 `--open-preview`，CLI 用默认浏览器打开该 HTML 文件。

## 图片识别规则

`artifacts.py` 负责从输入快照和输出快照中递归识别图片。第一版支持：

- 本地图片路径字符串：后缀为 `.png`、`.jpg`、`.jpeg`、`.webp`、`.gif`。
- 明确对象格式：

```json
{
  "type": "image",
  "path": "D:/path/to/image.png",
  "mime_type": "image/png"
}
```

- data URL：

```text
data:image/png;base64,...
```

对 data URL，测试 runner 将内容落盘到本次运行目录后再展示。第一版不猜测普通 base64 字符串是否为图片，避免误判大文本字段。

未来资产模块支持图片资产后，可扩展识别：

```json
{
  "asset_id": "asset_xxx",
  "asset_type": "file",
  "mime_type": "image/png"
}
```

该扩展必须通过 `AssetService` 读取资产，不能直接拼接资产文件路径。

## 命令行参数

第一版参数：

```text
workflow_path                    可选，工作流 YAML/JSON 文件路径
--workflow-id <id>               从 WorkflowCatalog 读取工作流
--input <json>                   工作流输入 JSON
--input-file <path>              工作流输入 JSON 文件
--interactive                    强制交互输入
--database-path <path>           测试数据库路径
--asset-storage-dir <path>       测试资产目录
--workflow-dir <path>            工作流目录，默认 workflows
--project-id <id>                使用已有项目
--project-name <name>            自动创建或复用测试项目名称
--username <name>                测试用户名称
--show-json                      完整打印最终 task/events/node_executions JSON
--open-images                    用系统默认查看器打开图片
--preview html                   生成 HTML 预览
--open-preview                   生成后打开 HTML 预览
--debug                          非预期异常时打印 traceback
```

`workflow_path` 和 `--workflow-id` 必须二选一。

## 错误处理

CLI 输出标准错误形态：

```text
[错误] json_value_validation_failed
数据不满足 JSON Schema
details: {"path":["prompt"],"error":"..."}
```

规则：

- `XiAgentError` 显示 `code`、`message`、`details`。
- 非预期异常显示异常类型和消息；调试时可通过 `--debug` 打印 traceback。
- 工作流任务已经创建后发生节点失败，CLI 仍读取并展示任务事件、节点错误和当前视图。
- 输入解析或契约校验在任务创建前失败时，不创建任务。

## 测试策略

新增测试覆盖：

- builder 能迁移数据库、创建测试用户、创建测试项目、装配节点注册表和运行时。
- CLI 输入解析支持 `--input`、`--input-file` 和按 schema 交互输入。
- runner 能执行 `tool.echo.v1` 工作流并输出事件摘要。
- runner 遇到 `system.human_approval.v1` 后能通过模拟 console 输入恢复任务。
- 图片识别能识别本地路径、明确 image 对象和 data URL，并能为 data URL 落盘。
- HTML 预览包含节点名称、输入输出摘要和图片引用。

不在单元测试中调用真实系统图片查看器。`--open-images` 使用可替换 opener 进行测试。

## 与现有手动日志测试关系

`tests/test_manual_workflow_logging.py` 可以保留为 API 闭环示例，但后续手动观察推荐使用 CLI。该测试中的日志函数可以被删除或简化，不再承担主要手动调试职责。

## 后续扩展

- 支持从已有 `task_id` 继续观察或恢复任务。
- 支持保存一次运行的完整 JSON 报告。
- 支持筛选只显示某个节点或某类事件。
- 支持资产模块图片引用解析。
- 支持远程 URL 图片下载缓存，但第一版不默认访问外网。

## 自检

- 本设计没有新增第二套工作流执行引擎，执行仍由 `RuntimeService` 负责。
- 测试管理员不绕过权限，任务仍绑定明确的 `user_id` 和 `project_id`。
- 图片展示能力限定在测试工具层，不污染核心工作流契约和运行时接口。
- CLI、runner、console、artifacts 职责清晰，可分别测试。
- 第一版范围可在一次实现计划内完成，不需要拆成多个项目。
