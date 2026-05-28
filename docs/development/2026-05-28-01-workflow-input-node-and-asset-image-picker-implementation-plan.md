# Workflow Input Node and Asset Image Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 取消任务创建前业务参数输入，改为任务详情首个 `system.workflow_input.v1` 节点统一收集 workflow 入参，并新增可复用资产图片选择控件。

**Architecture:** 后端新增系统输入节点与运行时恢复语义，用户提交该节点后把输出固化为 `$workflow.input`。前端创建任务页只展示工作流说明，任务详情用同一套 `node-ui` 控件渲染起始输入节点；资产图片选择作为控件库能力复用在通用 schema 输入表单中。

**Tech Stack:** Python 3.13, FastAPI, SQLite, JSON Schema, Pytest, React 19, TypeScript, Vite, Vitest, Testing Library, Playwright.

---

## 文件结构

- `xiagent/nodes/system/workflow_input.py`：新增 `WorkflowInputNode`，返回 waiting，metadata 携带输入 schema 与显示标题。
- `xiagent/nodes/system/__init__.py`、`xiagent/nodes/__init__.py`：注册 `system.workflow_input.v1`。
- `xiagent/runtime/service.py`：允许空 `input_data` 创建任务；恢复 workflow 输入节点时校验并更新 `tasks.input_json`；继续运行时使用新的 workflow input。
- `xiagent/api/routers/tasks.py`：让 `CreateTaskRequest.input_data` 变为可选，默认 `{}`。
- `xiagent/ui_controls/catalog.py`：注册 `ui.input.schema_form.v1` 和 `ui.input.asset_image_picker.v1`。
- `xiagent/ui_controls/validation.py`：校验 input 控件 submit schema 与当前 output schema 的兼容性。
- `workflows/global/*.workflow.yaml`：为现有全局工作流添加显式 `collect_workflow_input` 首节点，并把原 `START` 边指向该节点。
- `ui/V2/src/api/tasks.ts`：创建任务请求的 `input_data` 可选。
- `ui/V2/src/api/assets.ts`：上传资产支持 `collection_ids`、`tag_ids`。
- `ui/V2/src/node-ui/controls/SchemaInputFormControl.tsx`：新增通用 schema 输入表单控件。
- `ui/V2/src/node-ui/controls/AssetImagePickerControl.tsx`：新增资产图片选择控件。
- `ui/V2/src/node-ui/registry.ts`：注册两个新控件。
- `ui/V2/src/node-ui/types.ts`：补充工作流输入表单和资产图片选择字段类型。
- `ui/V2/src/node-ui/fixtures/workflowInput.ts`：新增控件库预览 fixture。
- `ui/V2/src/node-ui/ControlLibraryPage.tsx`：展示新控件预览。
- `ui/V2/src/app/App.tsx`：创建任务页移除业务参数表单，展示 launch 信息并创建空输入任务。
- `ui/V2/src/styles/app.css`：补充起始输入表单、资产选择弹窗、缩略图折叠和大图预览样式。
- `ui/V2/src/tests/*.test.tsx`、`tests/*.py`：覆盖后端运行时、manifest、workflow 校验、前端控件和创建任务页。

## 全局执行要求

- `workflow.input_schema` 只描述最终 `$workflow.input` 的数据契约，不得在创建任务页渲染业务表单。
- 创建任务页只展示 launch 信息和创建入口；所有初始业务入参必须进入任务详情首个输入节点后提交。
- 起始输入节点和普通等待节点必须复用 `node-ui` 控件库，不能拆出创建页专用表单、资产选择或上传分支。
- schema 表单控件使用中性命名 `ui.input.schema_form.v1`；字段控件如资产图片选择必须能在起始输入节点和普通输入节点中复用。
- 修改任何函数、类或方法前先运行对应 GitNexus impact，例如：

```powershell
# 修改 SqliteRuntimeService 前
# 使用 MCP: gitnexus_impact({target: "SqliteRuntimeService", direction: "upstream", repo: "XiAgent"})
```

- 每个任务只暂存本任务文件，避免混入当前工作区已有未提交改动。
- 后端提交前运行：

```powershell
python -m pytest tests/test_node_registry.py tests/test_runtime_service.py tests/test_api_smoke.py tests/test_ui_control_catalog.py tests/test_workflow_validator.py -q
```

- 前端提交前在 `ui/V2` 运行：

```powershell
npm run test
npm run build
```

- 全部实现完成后运行：

```powershell
python -m pytest tests/test_runninghub_workflows.py tests/test_workflow_testing_runner.py -q
python -m xiagent.workflows.testing_cli workflows/global/runninghub_image_to_image_test.workflow.yaml --input "{}"
```

---

### Task 1: 新增系统 workflow 输入节点

**Files:**
- Create: `xiagent/nodes/system/workflow_input.py`
- Modify: `xiagent/nodes/system/__init__.py`
- Modify: `xiagent/nodes/__init__.py`
- Test: `tests/test_node_registry.py`

- [ ] **Step 1: 运行影响分析**

使用 GitNexus：

```text
gitnexus_impact({target: "build_node_registry", direction: "upstream", repo: "XiAgent"})
gitnexus_impact({target: "NodeDescriptor", direction: "upstream", repo: "XiAgent"})
```

Expected: 记录风险等级、直接调用方和受影响执行流。若 HIGH 或 CRITICAL，先向用户说明再继续。

- [ ] **Step 2: 写失败测试**

在 `tests/test_node_registry.py` 增加：

```python
async def test_workflow_input_node_waits_with_output_schema_metadata() -> None:
    from xiagent.nodes.system.workflow_input import WorkflowInputNode
    from xiagent.nodes.base import NodeContext

    output_schema = {
        "type": "object",
        "required": ["prompt", "image_urls"],
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "image_urls": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
        },
        "additionalProperties": False,
    }
    ctx = NodeContext(
        user_id="user_1",
        project_id="project_1",
        task_id="task_1",
        node_id="collect_workflow_input",
        node_execution_id="node_exec_1",
        config={"title": "填写运行输入", "description": "提供图生图参数"},
        output_schema=output_schema,
        asset_service=None,
        event_sink=None,
        logger=None,
    )

    result = await WorkflowInputNode().run(ctx, {})

    assert result.status == "waiting"
    assert result.output == {}
    assert result.metadata["input_schema"] == output_schema
    assert result.metadata["title"] == "填写运行输入"
    assert result.metadata["description"] == "提供图生图参数"
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_node_registry.py::test_workflow_input_node_waits_with_output_schema_metadata -q
```

Expected: FAIL，错误包含 `No module named 'xiagent.nodes.system.workflow_input'`。

- [ ] **Step 4: 新增节点实现**

创建 `xiagent/nodes/system/workflow_input.py`：

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class WorkflowInputNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="system.workflow_input.v1",
            name="Workflow Input",
            version="1.0.0",
            kind="system",
            input_schema={
                "type": "object",
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "additionalProperties": True,
            },
            description="暂停工作流并等待用户填写本次运行输入。",
            ui_defaults={
                "controls": {
                    "interaction": {
                        "control_id": "ui.input.schema_form.v1",
                        "variant": "default",
                        "mode": "input",
                    }
                }
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        output_schema = dict(ctx.output_schema) if ctx is not None else {}
        config = dict(ctx.config) if ctx is not None else {}
        return NodeResult(
            status="waiting",
            output={},
            metadata={
                "input_schema": output_schema,
                "title": str(config.get("title") or "填写运行输入"),
                "description": str(config.get("description") or ""),
                "requested_inputs": dict(inputs),
            },
        )
```

- [ ] **Step 5: 注册节点**

在 `xiagent/nodes/system/__init__.py` 增加：

```python
from xiagent.nodes.system.workflow_input import WorkflowInputNode

__all__ = ["HumanApprovalNode", "SystemUserChoiceNode", "WorkflowInputNode"]
```

在 `xiagent/nodes/__init__.py` 中导入并注册：

```python
from xiagent.nodes.system.workflow_input import WorkflowInputNode
```

并在 `build_node_registry()` 中系统节点注册区加入：

```python
registry.register(WorkflowInputNode())
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```powershell
python -m pytest tests/test_node_registry.py::test_workflow_input_node_waits_with_output_schema_metadata tests/test_node_registry.py::test_registry_contains_builtin_nodes -q
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add xiagent/nodes/system/workflow_input.py xiagent/nodes/system/__init__.py xiagent/nodes/__init__.py tests/test_node_registry.py
git commit -m "feat: add workflow input system node"
```

---

### Task 2: 运行时支持创建后等待 workflow 输入

**Files:**
- Modify: `xiagent/runtime/service.py`
- Test: `tests/test_runtime_service.py`

- [ ] **Step 1: 运行影响分析**

使用 GitNexus：

```text
gitnexus_impact({target: "create_task_from_contract", direction: "upstream", repo: "XiAgent"})
gitnexus_impact({target: "resume_task", direction: "upstream", repo: "XiAgent"})
```

Expected: 记录 `create_task_from_contract` 和 `resume_task` 的直接调用方、受影响执行流和风险等级。HIGH 或 CRITICAL 时先停下说明。

- [ ] **Step 2: 写创建后等待输入的失败测试**

在 `tests/test_runtime_service.py` 增加一个 workflow contract helper：

```python
def _workflow_input_contract() -> dict:
    input_schema = {
        "type": "object",
        "required": ["topic"],
        "properties": {"topic": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    }
    return {
        "workflow": {
            "id": "workflow_input_demo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Workflow Input Demo",
            "input_schema": input_schema,
        },
        "nodes": [
            {
                "id": "collect_workflow_input",
                "ref": "system.workflow_input.v1",
                "inputs": {},
                "outputs": input_schema,
            },
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {
                    "type": "object",
                    "required": ["echo"],
                    "properties": {"echo": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        ],
        "edges": [
            {"from": "START", "to": "collect_workflow_input"},
            {"from": "collect_workflow_input", "to": "echo"},
            {"from": "echo", "to": "END"},
        ],
    }
```

再增加测试：

```python
async def test_create_task_without_input_waits_on_workflow_input_node(runtime_service, test_user_project) -> None:
    user, project = test_user_project

    task = await runtime_service.create_task_from_contract(
        user_id=user.user_id,
        project_id=project.project_id,
        contract=_workflow_input_contract(),
        input_data={},
    )

    executions = await runtime_service.list_node_executions(
        user_id=user.user_id,
        project_id=project.project_id,
        task_id=task.task_id,
    )

    assert task.status == "waiting"
    assert task.input_data == {}
    assert executions[0].node_id == "collect_workflow_input"
    assert executions[0].node_ref == "system.workflow_input.v1"
    assert executions[0].status == "waiting"
```

再增加创建前业务入参拒绝测试：

```python
async def test_create_task_rejects_business_input_before_start_node(runtime_service, test_user_project) -> None:
    user, project = test_user_project

    with pytest.raises(ValueError, match="workflow input must be submitted through start input node"):
        await runtime_service.create_task_from_contract(
            user_id=user.user_id,
            project_id=project.project_id,
            contract=_workflow_input_contract(),
            input_data={"topic": "不应在创建页提交"},
        )
```

- [ ] **Step 3: 写恢复后更新 workflow input 的失败测试**

继续在 `tests/test_runtime_service.py` 增加：

```python
async def test_resume_workflow_input_updates_task_input_and_continues(runtime_service, test_user_project) -> None:
    user, project = test_user_project
    task = await runtime_service.create_task_from_contract(
        user_id=user.user_id,
        project_id=project.project_id,
        contract=_workflow_input_contract(),
        input_data={},
    )

    resumed = await runtime_service.resume_task(
        user_id=user.user_id,
        project_id=project.project_id,
        task_id=task.task_id,
        node_id="collect_workflow_input",
        output={"topic": "统一输入"},
    )
    executions = await runtime_service.list_node_executions(
        user_id=user.user_id,
        project_id=project.project_id,
        task_id=task.task_id,
    )

    assert resumed.status == "succeeded"
    assert resumed.input_data == {"topic": "统一输入"}
    assert [execution.node_id for execution in executions] == ["collect_workflow_input", "echo"]
    assert executions[-1].input_snapshot == {"topic": "统一输入"}
```

- [ ] **Step 4: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_runtime_service.py::test_create_task_without_input_waits_on_workflow_input_node tests/test_runtime_service.py::test_resume_workflow_input_updates_task_input_and_continues -q
```

Expected: 第一个测试因 `json_value_validation_failed` 失败，第二个测试因 `resumed.input_data == {}` 或后续节点未读取新输入失败。

- [ ] **Step 5: 修改创建任务逻辑**

在 `xiagent/runtime/service.py` 中新增 helper：

```python
def _workflow_input_node_ids(contract: dict[str, Any]) -> set[str]:
    return {
        str(node["id"])
        for node in contract.get("nodes", [])
        if node.get("ref") == "system.workflow_input.v1"
    }


def _has_workflow_input_node(contract: dict[str, Any]) -> bool:
    return bool(_workflow_input_node_ids(contract))
```

在 `create_task_from_contract()` 中把：

```python
validate_json_value(contract["workflow"]["input_schema"], input_data)
```

替换为：

```python
has_workflow_input_node = _has_workflow_input_node(contract)
if has_workflow_input_node and input_data:
    raise ValueError("workflow input must be submitted through start input node")
if not has_workflow_input_node:
    validate_json_value(contract["workflow"]["input_schema"], input_data)
```

带起始输入节点的新任务保持 `input_json` 写入 `{}`，然后调用 `_continue_task(... workflow_input={} ...)`，让首个输入节点进入 waiting。

- [ ] **Step 6: 修改恢复逻辑以固化 workflow input**

在 `resume_task()` 中 `node_def = _node_by_id(contract, node_id)` 后新增：

```python
is_workflow_input_node = node_def.get("ref") == "system.workflow_input.v1"
if is_workflow_input_node:
    validate_json_value(contract["workflow"]["input_schema"], output)
else:
    validate_json_value(node_def["outputs"], output)
```

并删除原来的单行：

```python
validate_json_value(node_def["outputs"], output)
```

在更新 `tasks` 的 SQL 中把：

```sql
update tasks
set status = ?, current_view_json = ?, updated_at = ?
where task_id = ?
```

替换为：

```sql
update tasks
set status = ?, input_json = ?, current_view_json = ?, updated_at = ?
where task_id = ?
```

参数替换为：

```python
(
    "running",
    dump_json(output if is_workflow_input_node else task.input_data),
    dump_json(task.current_view | {"status": "running"}),
    now,
    task_id,
)
```

在 `_continue_task()` 调用前设置：

```python
next_workflow_input = output if is_workflow_input_node else task.input_data
```

并传入：

```python
workflow_input=next_workflow_input,
```

- [ ] **Step 7: 运行测试确认通过**

Run:

```powershell
python -m pytest tests/test_runtime_service.py::test_create_task_without_input_waits_on_workflow_input_node tests/test_runtime_service.py::test_resume_workflow_input_updates_task_input_and_continues tests/test_runtime_service.py::test_resume_with_invalid_output_keeps_task_waiting -q
```

Expected: PASS。

- [ ] **Step 8: 提交**

```powershell
git add xiagent/runtime/service.py tests/test_runtime_service.py
git commit -m "feat: defer workflow input until first task node"
```

---

### Task 3: API 允许创建任务时省略 input_data

**Files:**
- Modify: `xiagent/api/routers/tasks.py`
- Test: `tests/test_api_smoke.py`

- [ ] **Step 1: 运行影响分析**

使用 GitNexus：

```text
gitnexus_impact({target: "CreateTaskRequest", direction: "upstream", repo: "XiAgent"})
gitnexus_impact({target: "create_task", file_path: "xiagent/api/routers/tasks.py", direction: "upstream", repo: "XiAgent"})
```

Expected: 记录 API 调用影响。若 HIGH 或 CRITICAL，先向用户说明。

- [ ] **Step 2: 写失败测试**

在 `tests/test_api_smoke.py` 增加：

```python
def test_task_create_accepts_missing_input_data_and_waits(test_settings) -> None:
    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "workflow-input-user", "password": "secret-123"},
        )
        headers = _auth_headers(client, username="workflow-input-user")
        project = client.post(
            "/api/projects",
            json={"name": "Workflow Input Project"},
            headers=headers,
        ).json()
        contract = {
            "workflow": {
                "id": "api_workflow_input_demo",
                "version": "1.0.0",
                "scope": "global",
                "name": "API Workflow Input Demo",
                "input_schema": {
                    "type": "object",
                    "required": ["topic"],
                    "properties": {"topic": {"type": "string", "minLength": 1}},
                    "additionalProperties": False,
                },
            },
            "nodes": [
                {
                    "id": "collect_workflow_input",
                    "ref": "system.workflow_input.v1",
                    "inputs": {},
                    "outputs": {
                        "type": "object",
                        "required": ["topic"],
                        "properties": {"topic": {"type": "string", "minLength": 1}},
                        "additionalProperties": False,
                    },
                }
            ],
            "edges": [{"from": "START", "to": "collect_workflow_input"}, {"from": "collect_workflow_input", "to": "END"}],
        }

        response = client.post(
            "/api/tasks",
            json={"project_id": project["project_id"], "contract": contract},
            headers=headers,
        )

        assert response.status_code == 200
        task = response.json()
        assert task["status"] == "waiting"
        assert task["input_data"] == {}
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_api_smoke.py::test_task_create_accepts_missing_input_data_and_waits -q
```

Expected: FAIL，HTTP 422，提示 `input_data` 字段缺失。

- [ ] **Step 4: 修改请求模型**

在 `xiagent/api/routers/tasks.py` 中把：

```python
input_data: dict[str, Any]
```

改为：

```python
input_data: dict[str, Any] = {}
```

如果 Pydantic 报 mutable default 警告，则使用：

```python
from pydantic import BaseModel, ConfigDict, Field

input_data: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```powershell
python -m pytest tests/test_api_smoke.py::test_task_create_accepts_missing_input_data_and_waits tests/test_api_smoke.py::test_task_interactions_endpoint_resumes_waiting_task -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add xiagent/api/routers/tasks.py tests/test_api_smoke.py
git commit -m "feat: allow tasks to start without input data"
```

---

### Task 4: 注册 workflow 表单和资产图片选择控件 manifest

**Files:**
- Modify: `xiagent/ui_controls/catalog.py`
- Modify: `xiagent/ui_controls/validation.py`
- Test: `tests/test_ui_control_catalog.py`
- Test: `tests/test_workflow_validator.py`

- [ ] **Step 1: 运行影响分析**

使用 GitNexus：

```text
gitnexus_impact({target: "build_builtin_ui_control_catalog", direction: "upstream", repo: "XiAgent"})
gitnexus_impact({target: "_validate_control_config", direction: "upstream", repo: "XiAgent"})
```

Expected: 记录受影响测试和验证流程。若 HIGH 或 CRITICAL，先向用户说明。

- [ ] **Step 2: 写 manifest 失败测试**

在 `tests/test_ui_control_catalog.py` 增加：

```python
def test_workflow_input_controls_are_registered() -> None:
    catalog = build_builtin_ui_control_catalog()
    control_ids = {control.control_id for control in catalog.list_controls()}

    assert "ui.input.schema_form.v1" in control_ids
    assert "ui.input.asset_image_picker.v1" in control_ids

    image_picker = catalog.get("ui.input.asset_image_picker.v1")
    assert image_picker.kind == "input"
    assert image_picker.variants[0].name == "thumbnails"
    assert "input" in image_picker.variants[0].modes
```

- [ ] **Step 3: 写 workflow 校验失败测试**

在 `tests/test_workflow_validator.py` 增加：

```python
def test_workflow_input_node_can_use_asset_image_picker_control() -> None:
    contract = {
        "workflow": {
            "id": "asset_picker_input_demo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Asset Picker Input Demo",
            "input_schema": {
                "type": "object",
                "required": ["image_urls"],
                "properties": {
                    "image_urls": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    }
                },
                "additionalProperties": False,
            },
        },
        "nodes": [
            {
                "id": "collect_workflow_input",
                "ref": "system.workflow_input.v1",
                "inputs": {},
                "outputs": {
                    "type": "object",
                    "required": ["image_urls"],
                    "properties": {
                        "image_urls": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        }
                    },
                    "additionalProperties": False,
                },
                "ui": {
                    "controls": {
                        "interaction": {
                            "control_id": "ui.input.schema_form.v1",
                            "variant": "default",
                            "mode": "input",
                            "options": {
                                "fields": {
                                    "image_urls": {
                                        "control_id": "ui.input.asset_image_picker.v1",
                                        "variant": "thumbnails",
                                        "mode": "input",
                                        "options": {"selection_mode": "multiple"},
                                    }
                                }
                            },
                        }
                    }
                },
            }
        ],
        "edges": [{"from": "START", "to": "collect_workflow_input"}, {"from": "collect_workflow_input", "to": "END"}],
    }

    validate_workflow_contract(contract, _node_registry())
```

- [ ] **Step 4: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_ui_control_catalog.py::test_workflow_input_controls_are_registered tests/test_workflow_validator.py::test_workflow_input_node_can_use_asset_image_picker_control -q
```

Expected: FAIL，错误包含 `unknown_ui_control`。

- [ ] **Step 5: 添加控件 descriptor**

在 `xiagent/ui_controls/catalog.py` 的 `UiControlCatalog([...])` 列表中加入：

```python
UiControlDescriptor(
    control_id="ui.input.schema_form.v1",
    version="1.0.0",
    name="Schema Input Form",
    kind="input",
    tags=("schema", "input", "form", "interactive"),
    variants=(
        UiControlVariant(
            name="default",
            label="通用 schema 输入表单",
            modes=("input",),
            submit_schema={"type": "object", "additionalProperties": True},
        ),
    ),
    description="在输入节点中按 schema 收集用户提交的结构化参数。",
),
UiControlDescriptor(
    control_id="ui.input.asset_image_picker.v1",
    version="1.0.0",
    name="Asset Image Picker",
    kind="input",
    tags=("asset", "image", "picker", "upload", "single", "multiple"),
    variants=(
        UiControlVariant(
            name="thumbnails",
            label="缩略图资产图片选择",
            modes=("input", "readonly"),
            submit_schema={
                "type": "object",
                "required": ["value"],
                "properties": {
                    "value": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    }
                },
                "additionalProperties": False,
            },
        ),
    ),
    description="从资产库选择或上传图片，最终输出图片 URL 数组。",
),
```

- [ ] **Step 6: 扩展 input slot submit schema 兼容校验**

在 `xiagent/ui_controls/validation.py` 中把兼容校验条件：

```python
if (
    slot == "interaction"
    and variant.submit_schema is not None
    and current_output_schema is not None
):
```

改为：

```python
if (
    slot in {"interaction", "input"}
    and variant.submit_schema is not None
    and current_output_schema is not None
):
```

如果 `ui.input.asset_image_picker.v1` 只作为 `ui.input.schema_form.v1` 的字段子控件使用，不直接作为 slot 控件，则不需要字段级 manifest 校验；字段级配置由前端控件内部处理，后端只校验外层 `ui.input.schema_form.v1`。

- [ ] **Step 7: 运行测试确认通过**

Run:

```powershell
python -m pytest tests/test_ui_control_catalog.py::test_workflow_input_controls_are_registered tests/test_workflow_validator.py::test_workflow_input_node_can_use_asset_image_picker_control tests/test_workflow_validator.py::test_workflow_node_ui_rejects_unknown_control -q
```

Expected: PASS。

- [ ] **Step 8: 提交**

```powershell
git add xiagent/ui_controls/catalog.py xiagent/ui_controls/validation.py tests/test_ui_control_catalog.py tests/test_workflow_validator.py
git commit -m "feat: register workflow input ui controls"
```

---

### Task 5: 迁移全局工作流到显式起始输入节点

**Files:**
- Modify: `workflows/global/deepseek_echo.workflow.yaml`
- Modify: `workflows/global/runninghub_text_to_image_test.workflow.yaml`
- Modify: `workflows/global/runninghub_image_to_image_test.workflow.yaml`
- Modify: `workflows/global/storyboard_generation.workflow.yaml`
- Modify: `workflows/global/asset_catalog.workflow.yaml`
- Modify: `workflows/global/asset_storyboard_generation.workflow.yaml`
- Modify: `workflows/global/storyboard_from_sketch.workflow.yaml`
- Test: `tests/test_workflow_validator.py`

- [ ] **Step 1: 写全局工作流校验测试**

在 `tests/test_workflow_validator.py` 增加：

```python
def test_global_workflows_use_explicit_workflow_input_node() -> None:
    workflow_dir = Path("workflows/global")
    registry = _node_registry()
    for workflow_file in workflow_dir.glob("*.workflow.yaml"):
        contract = yaml.safe_load(workflow_file.read_text(encoding="utf-8"))
        validate_workflow_contract(contract, registry)
        if contract["workflow"].get("input_schema", {}).get("required"):
            first_edges = [edge for edge in contract["edges"] if edge["from"] == "START"]
            assert first_edges == [{"from": "START", "to": "collect_workflow_input"}]
            node_refs = {node["id"]: node["ref"] for node in contract["nodes"]}
            assert node_refs["collect_workflow_input"] == "system.workflow_input.v1"
```

确保文件顶部已有：

```python
from pathlib import Path
import yaml
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_workflow_validator.py::test_global_workflows_use_explicit_workflow_input_node -q
```

Expected: FAIL，第一个仍从 `START` 指向业务节点的 workflow 断言失败。

- [ ] **Step 3: 按统一结构迁移每个工作流**

对每个 `workflows/global/*.workflow.yaml`：

1. 在 `nodes:` 后新增第一项：

```yaml
  - id: collect_workflow_input
    ref: system.workflow_input.v1
    inputs: {}
    outputs:
      type: object
      required: [...]
      properties:
        ...
      additionalProperties: false
    config:
      title: 填写运行输入
      description: 请填写本次工作流运行所需参数。
    ui:
      controls:
        interaction:
          control_id: ui.input.schema_form.v1
          variant: default
          mode: input
```

2. 将原本：

```yaml
  - from: START
    to: <old_first_node>
```

改为：

```yaml
  - from: START
    to: collect_workflow_input
  - from: collect_workflow_input
    to: <old_first_node>
```

3. 对 `runninghub_image_to_image_test.workflow.yaml` 的 `image_urls` 字段在 `ui.input.schema_form.v1` 下配置资产图片控件：

```yaml
            options:
              fields:
                image_urls:
                  control_id: ui.input.asset_image_picker.v1
                  variant: thumbnails
                  mode: input
                  options:
                    selection_mode: multiple
                    upload_scope: project
                    collapsed_rows: 1
```

- [ ] **Step 4: 运行工作流校验**

Run:

```powershell
python -m pytest tests/test_workflow_validator.py::test_global_workflows_use_explicit_workflow_input_node -q
python -m pytest tests/test_workflow_validator.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add workflows/global/*.workflow.yaml tests/test_workflow_validator.py
git commit -m "chore: move global workflow inputs into start node"
```

---

### Task 6: V2 API 类型支持空输入任务和上传归类

**Files:**
- Modify: `ui/V2/src/api/tasks.ts`
- Modify: `ui/V2/src/api/assets.ts`
- Test: `ui/V2/src/tests/tasks.test.ts`

- [ ] **Step 1: 修改任务请求类型**

在 `ui/V2/src/api/tasks.ts` 中把：

```ts
export interface CreateTaskRequest {
  project_id: string;
  contract: Record<string, unknown>;
  input_data: Record<string, unknown>;
}
```

改为：

```ts
export interface CreateTaskRequest {
  project_id: string;
  contract: Record<string, unknown>;
  input_data?: Record<string, unknown>;
}
```

- [ ] **Step 2: 修改上传资产 API**

在 `ui/V2/src/api/assets.ts` 的 `uploadAsset()` input 类型中加入：

```ts
collection_ids?: string[];
tag_ids?: string[];
```

并在 `FormData` 中写入：

```ts
if (input.collection_ids?.length) form.set("collection_ids", input.collection_ids.join(","));
if (input.tag_ids?.length) form.set("tag_ids", input.tag_ids.join(","));
```

- [ ] **Step 3: 写 API 单元测试**

在 `ui/V2/src/tests/tasks.test.ts` 增加：

```ts
it("creates task without input_data", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValueOnce(
    new Response(JSON.stringify({ task_id: "task-1", status: "waiting" }), { status: 200 }),
  );

  await createTask({ project_id: "project-1", contract: { workflow: { id: "demo" } } });

  const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
  expect(body).toEqual({ project_id: "project-1", contract: { workflow: { id: "demo" } } });
});
```

如果 `tasks.test.ts` 没有导入 `createTask` 和 `vi`，补充：

```ts
import { describe, expect, it, vi } from "vitest";
import { createTask } from "../api/tasks";
```

- [ ] **Step 4: 运行测试**

Run:

```powershell
cd ui/V2
npm run test -- src/tests/tasks.test.ts
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add ui/V2/src/api/tasks.ts ui/V2/src/api/assets.ts ui/V2/src/tests/tasks.test.ts
git commit -m "feat(ui): support deferred task input api"
```

---

### Task 7: 实现资产图片选择控件和 workflow 输入表单控件

**Files:**
- Create: `ui/V2/src/node-ui/controls/AssetImagePickerControl.tsx`
- Create: `ui/V2/src/node-ui/controls/SchemaInputFormControl.tsx`
- Create: `ui/V2/src/node-ui/fixtures/workflowInput.ts`
- Modify: `ui/V2/src/node-ui/registry.ts`
- Modify: `ui/V2/src/node-ui/types.ts`
- Modify: `ui/V2/src/node-ui/ControlLibraryPage.tsx`
- Modify: `ui/V2/src/styles/app.css`
- Test: `ui/V2/src/tests/node-ui.test.tsx`

- [ ] **Step 1: 写控件渲染测试**

在 `ui/V2/src/tests/node-ui.test.tsx` 增加：

```tsx
it("renders schema input form and submits image urls as an array", async () => {
  const onSubmit = vi.fn();
  render(
    <SchemaInputFormControl
      config={{
        control_id: "ui.input.schema_form.v1",
        variant: "default",
        mode: "input",
        options: {
          fields: {
            image_urls: {
              control_id: "ui.input.asset_image_picker.v1",
              variant: "thumbnails",
              mode: "input",
              options: { selection_mode: "single" },
            },
          },
        },
      }}
      node={{
        node_id: "collect_workflow_input",
        node_ref: "system.workflow_input.v1",
        status: "waiting",
        input_snapshot: {},
        output_snapshot: {},
        metadata: {
          input_schema: {
            type: "object",
            required: ["prompt", "image_urls"],
            properties: {
              prompt: { type: "string", title: "提示词" },
              image_urls: {
                type: "array",
                title: "参考图片",
                items: { type: "string" },
              },
            },
          },
        },
      }}
      onSubmit={onSubmit}
    />,
  );

  await userEvent.type(screen.getByLabelText("提示词"), "蓝色机器人");
  await userEvent.click(screen.getByRole("button", { name: "提交输入" }));

  expect(onSubmit).toHaveBeenCalledWith({ prompt: "蓝色机器人", image_urls: [] });
});
```

该测试先验证表单控件接入；资产弹窗选择行为在后续测试补充。

- [ ] **Step 2: 新增类型**

在 `ui/V2/src/node-ui/types.ts` 增加：

```ts
export type AssetImageSelectionMode = "single" | "multiple";

export interface SchemaInputFieldControlConfig {
  control_id: string;
  variant?: string;
  mode?: string;
  options?: Record<string, unknown>;
}

export interface SchemaInputFormOptions {
  fields?: Record<string, SchemaInputFieldControlConfig>;
}
```

- [ ] **Step 3: 实现 SchemaInputFormControl**

创建 `ui/V2/src/node-ui/controls/SchemaInputFormControl.tsx`，核心结构：

```tsx
import { useMemo, useState } from "react";

import type { JsonSchema } from "../../api/types";
import type { NodeUiControlProps, SchemaInputFormOptions } from "../types";
import { AssetImagePickerControl } from "./AssetImagePickerControl";

function schemaFromNode(node: NodeUiControlProps["node"]): JsonSchema {
  const schema = node.metadata?.input_schema;
  return schema && typeof schema === "object" ? (schema as JsonSchema) : { type: "object", properties: {} };
}

export function SchemaInputFormControl({ config, node, busy = false, onSubmit }: NodeUiControlProps) {
  const schema = schemaFromNode(node);
  const options = (config.options ?? {}) as SchemaInputFormOptions;
  const required = new Set(schema.required ?? []);
  const fields = Object.entries(schema.properties ?? {});
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const initial: Record<string, unknown> = {};
    for (const [key, fieldSchema] of fields) {
      initial[key] = fieldSchema.type === "array" ? [] : "";
    }
    return initial;
  });
  const canSubmit = useMemo(
    () => fields.every(([key]) => !required.has(key) || (Array.isArray(values[key]) ? (values[key] as unknown[]).length > 0 : values[key] !== "")),
    [fields, required, values],
  );

  return (
    <section className="workflow-input-form">
      <div>
        <p className="eyebrow">工作流输入</p>
        <h3>{typeof node.metadata?.title === "string" ? node.metadata.title : "填写运行输入"}</h3>
        {typeof node.metadata?.description === "string" && node.metadata.description ? <p>{node.metadata.description}</p> : null}
      </div>
      {fields.map(([key, fieldSchema]) => {
        const fieldControl = options.fields?.[key];
        const label = fieldSchema.title ?? key;
        if (fieldControl?.control_id === "ui.input.asset_image_picker.v1") {
          return (
            <AssetImagePickerControl
              key={key}
              fieldKey={key}
              label={label}
              required={required.has(key)}
              value={Array.isArray(values[key]) ? (values[key] as string[]) : []}
              options={fieldControl.options}
              onChange={(nextValue) => setValues((current) => ({ ...current, [key]: nextValue }))}
            />
          );
        }
        return (
          <label className="form-field" key={key}>
            <span>{label}{required.has(key) ? " *" : ""}</span>
            <input aria-label={label} value={String(values[key] ?? "")} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))} />
          </label>
        );
      })}
      <button className="primary-button" disabled={busy || !canSubmit} type="button" onClick={() => onSubmit?.(values)}>
        提交输入
      </button>
    </section>
  );
}
```

在 `SchemaInputFormControl.tsx` 中为非图片数组字段加入固定分支：

```tsx
if (fieldSchema.type === "array") {
  return (
    <label className="form-field" key={key}>
      <span>{label}{required.has(key) ? " *" : ""}</span>
      <textarea
        aria-label={label}
        value={Array.isArray(values[key]) ? (values[key] as string[]).join("\n") : ""}
        onChange={(event) =>
          setValues((current) => ({
            ...current,
            [key]: event.target.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
          }))
        }
      />
    </label>
  );
}
```

- [ ] **Step 4: 实现 AssetImagePickerControl**

创建 `ui/V2/src/node-ui/controls/AssetImagePickerControl.tsx`，导出字段组件：

```tsx
import { useEffect, useMemo, useState } from "react";

import { listAssetCollections, listAssetTags, searchAssets, uploadAsset } from "../../api/assets";
import type { AssetCollection, AssetRecord, AssetTag } from "../../api/types";
import type { AssetImageSelectionMode } from "../types";

interface AssetImagePickerFieldProps {
  fieldKey: string;
  label: string;
  required: boolean;
  value: string[];
  options?: Record<string, unknown>;
  onChange(value: string[]): void;
}

function publicImageUrl(asset: AssetRecord): string {
  return asset.metadata.public_url ?? asset.thumbnail_url ?? "";
}

export function AssetImagePickerControl({ label, required, value, options = {}, onChange }: AssetImagePickerFieldProps) {
  const selectionMode = (options.selection_mode === "single" ? "single" : "multiple") as AssetImageSelectionMode;
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [collections, setCollections] = useState<AssetCollection[]>([]);
  const [tags, setTags] = useState<AssetTag[]>([]);
  const [keyword, setKeyword] = useState("");
  const [selectedCollectionId, setSelectedCollectionId] = useState(String(options.default_collection_id ?? ""));
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>(Array.isArray(options.preset_tag_ids) ? options.preset_tag_ids.map(String) : []);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!open) return;
    let active = true;
    Promise.all([
      listAssetCollections("combined"),
      listAssetTags("combined"),
      searchAssets({ scope: "combined", keyword, collection_id: selectedCollectionId || undefined, tag_ids: selectedTagIds, mime_type: "image/*" }),
    ])
      .then(([nextCollections, nextTags, nextAssets]) => {
        if (!active) return;
        setCollections(nextCollections);
        setTags(nextTags);
        setAssets(nextAssets.filter((asset) => publicImageUrl(asset)));
      })
      .catch((error) => {
        if (active) setMessage(error instanceof Error ? error.message : "资产库暂时不可用");
      });
    return () => {
      active = false;
    };
  }, [open, keyword, selectedCollectionId, selectedTagIds]);

  const visibleValues = expanded ? value : value.slice(0, 4);
  const selectedSet = useMemo(() => new Set(value), [value]);

  function toggleUrl(url: string) {
    if (selectionMode === "single") {
      onChange([url]);
      return;
    }
    onChange(selectedSet.has(url) ? value.filter((item) => item !== url) : [...value, url]);
  }

  async function handleUpload(file: File) {
    const uploaded = await uploadAsset({
      file,
      scope: options.upload_scope === "global" ? "global" : "project",
      publish: true,
      collection_ids: Array.isArray(options.upload_collection_ids) ? options.upload_collection_ids.map(String) : [],
      tag_ids: Array.isArray(options.upload_tag_ids) ? options.upload_tag_ids.map(String) : [],
    });
    const url = publicImageUrl(uploaded);
    if (url) toggleUrl(url);
  }

  return (
    <fieldset className="asset-image-picker">
      <legend>{label}{required ? " *" : ""}</legend>
      <div className="selected-thumb-row">
        {visibleValues.map((url) => (
          <button key={url} type="button" className="selected-thumb" onClick={() => setPreviewUrl(url)}>
            <img src={url} alt={label} />
          </button>
        ))}
        <button type="button" className="secondary-button" onClick={() => setOpen(true)}>选择图片</button>
      </div>
      {value.length > 4 ? <button type="button" className="link-button" onClick={() => setExpanded((current) => !current)}>{expanded ? "收起" : "展开全部"}</button> : null}
      {open ? (
        <section className="asset-picker-dialog" role="dialog" aria-modal="true" aria-label={`${label}选择`}>
          <header><h3>选择图片</h3><button type="button" onClick={() => setOpen(false)}>关闭</button></header>
          <div className="asset-picker-filters">
            <select aria-label="资产目录" value={selectedCollectionId} onChange={(event) => setSelectedCollectionId(event.target.value)}>
              <option value="">全部目录</option>
              {collections.map((collection) => <option key={collection.collection_id} value={collection.collection_id}>{collection.name}</option>)}
            </select>
            <input aria-label="搜索资产" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          </div>
          {message ? <p className="form-error">{message}</p> : null}
          <div className="asset-picker-grid">
            {assets.map((asset) => {
              const url = publicImageUrl(asset);
              const selected = selectedSet.has(url);
              return (
                <button key={asset.asset_id} type="button" className={selected ? "asset-picker-card active" : "asset-picker-card"} onClick={() => toggleUrl(url)}>
                  <img src={url} alt={asset.name} />
                  <span>{asset.name}</span>
                </button>
              );
            })}
            {assets.length === 0 ? <p className="empty-box">当前筛选下没有可选择图片。</p> : null}
          </div>
          <label className="form-field">
            <span>本地上传</span>
            <input type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) void handleUpload(file); }} />
          </label>
        </section>
      ) : null}
      {previewUrl ? <section className="image-preview-dialog" role="dialog" aria-modal="true"><button type="button" onClick={() => setPreviewUrl("")}>关闭</button><img src={previewUrl} alt={label} /></section> : null}
    </fieldset>
  );
}
```

- [ ] **Step 5: 注册控件**

在 `ui/V2/src/node-ui/registry.ts` 增加：

```ts
import { SchemaInputFormControl } from "./controls/SchemaInputFormControl";
```

并在 `nodeUiRegistry` 增加：

```ts
"ui.input.schema_form.v1": SchemaInputFormControl,
```

`ui.input.asset_image_picker.v1` 作为 `SchemaInputFormControl` 的字段控件，不直接进入 `nodeUiRegistry`，避免 slot 控件和字段控件 props 混用。

- [ ] **Step 6: 补预览 fixture 和控件库页面**

创建 `ui/V2/src/node-ui/fixtures/workflowInput.ts`：

```ts
import type { TaskNodeExecution } from "../../api/types";

export function workflowInputPreviewNode(): TaskNodeExecution {
  return {
    node_id: "collect_workflow_input",
    node_ref: "system.workflow_input.v1",
    status: "waiting",
    input_snapshot: {},
    output_snapshot: {},
    metadata: {
      title: "填写运行输入",
      description: "提供提示词和参考图片。",
      input_schema: {
        type: "object",
        required: ["prompt", "image_urls"],
        properties: {
          prompt: { type: "string", title: "提示词" },
          image_urls: { type: "array", title: "参考图片", items: { type: "string" } },
        },
      },
    },
  };
}
```

在 `ControlLibraryPage.tsx` 中对 `ui.input.schema_form.v1` 增加预览。

- [ ] **Step 7: 样式**

在 `ui/V2/src/styles/app.css` 增加类：

```css
.workflow-input-form,
.asset-image-picker,
.asset-picker-dialog,
.image-preview-dialog {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.selected-thumb-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.selected-thumb,
.asset-picker-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
}

.selected-thumb img,
.asset-picker-card img {
  width: 88px;
  height: 64px;
  object-fit: cover;
  border-radius: 4px;
}
```

根据现有 token 名称修正 `--border`；如果项目中使用 `--line`，则统一使用已有变量。

- [ ] **Step 8: 运行测试**

Run:

```powershell
cd ui/V2
npm run test -- src/tests/node-ui.test.tsx
```

Expected: PASS。

- [ ] **Step 9: 提交**

```powershell
git add ui/V2/src/node-ui/controls/AssetImagePickerControl.tsx ui/V2/src/node-ui/controls/SchemaInputFormControl.tsx ui/V2/src/node-ui/fixtures/workflowInput.ts ui/V2/src/node-ui/registry.ts ui/V2/src/node-ui/types.ts ui/V2/src/node-ui/ControlLibraryPage.tsx ui/V2/src/styles/app.css ui/V2/src/tests/node-ui.test.tsx
git commit -m "feat(ui): add workflow input asset picker controls"
```

---

### Task 8: 创建任务页改为说明页

**Files:**
- Modify: `ui/V2/src/app/App.tsx`
- Modify: `ui/V2/src/utils/display.ts`
- Test: `ui/V2/src/tests/app.test.tsx`
- Test: `ui/V2/src/tests/display.test.ts`

- [ ] **Step 1: 写页面行为失败测试**

在 `ui/V2/src/tests/app.test.tsx` 增加：

```tsx
it("creates a task from launch information without rendering business input form", async () => {
  render(<App />);

  await userEvent.click(await screen.findByRole("button", { name: "新建任务" }));

  expect(screen.getByText("运行前准备")).toBeInTheDocument();
  expect(screen.queryByLabelText("参考图片")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "创建并进入输入节点" }));

  const createdTask = createdTasks.at(-1);
  expect(createdTask?.input_data).toEqual({});
});
```

测试 fixture 中的创建入口按钮统一改为 `新建任务`，提交按钮统一改为 `创建并进入输入节点`；断言固定检查业务字段不出现，创建请求不包含 `input_data`。

- [ ] **Step 2: 修改 CreateTaskPanel**

在 `ui/V2/src/app/App.tsx`：

1. 移除 `values`、`imageAssets`、`fields`、`WorkflowInputField` 的创建任务前业务表单逻辑。
2. `Promise.all([listWorkflows(...), searchAssets(...)])` 改为只调用 `listWorkflows(project.project_id)`。
3. 提交时调用：

```ts
const task = await createTask({
  project_id: project.project_id,
  contract: selectedTemplate.contract,
});
```

4. 按工作流配置展示 launch 信息：

```tsx
<section className="workflow-launch-summary">
  <h2>运行前准备</h2>
  <p>{selectedTemplate.launch?.summary ?? selectedTemplate.description}</p>
  <p>{selectedTemplate.launch?.input_hint ?? workflowInputSummary(selectedTemplate.inputSchema)}</p>
  <p>{selectedTemplate.launch?.output_hint ?? "创建后会进入任务详情，由第一个节点收集本次运行输入。"}</p>
</section>
```

- [ ] **Step 3: 补 display helper**

在 `ui/V2/src/utils/display.ts` 增加：

```ts
export function workflowInputSummary(schema?: JsonSchema): string {
  const fields = buildSchemaFields(schema);
  if (!fields.length) return "这个工作流不需要额外输入。";
  return `需要准备：${fields.map((field) => field.label).join("、")}。`;
}
```

- [ ] **Step 4: 扩展 WorkflowTemplate 类型**

在 `App.tsx` 中 `WorkflowTemplate` 增加：

```ts
launch?: {
  summary?: string;
  input_hint?: string;
  output_hint?: string;
};
```

在 `workflowToTemplate()` 中读取：

```ts
launch: item.workflow.ui?.launch as WorkflowTemplate["launch"],
```

- [ ] **Step 5: 运行测试**

Run:

```powershell
cd ui/V2
npm run test -- src/tests/app.test.tsx src/tests/display.test.ts
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add ui/V2/src/app/App.tsx ui/V2/src/utils/display.ts ui/V2/src/tests/app.test.tsx ui/V2/src/tests/display.test.ts
git commit -m "feat(ui): create tasks from launch summary"
```

---

### Task 9: 端到端验证与文档同步

**Files:**
- Modify: `ui/V2/docs/ui-development-rules.md`
- Modify: `workflows/AGENTS.md`
- Modify: `docs/design/2026-05-27-01-ui-control-manifest-design.md`
- Test: `ui/V2/tests/e2e/smoke.spec.ts`

- [ ] **Step 1: 更新文档**

在 `ui/V2/docs/ui-development-rules.md` 增加规则：

```markdown
- 创建任务页不得渲染 workflow 业务入参表单；业务输入统一由任务详情中的 `system.workflow_input.v1` 起始输入节点收集。
- `ui.input.schema_form.v1` 负责渲染通用 schema 输入节点，字段级资产图片选择使用 `ui.input.asset_image_picker.v1`。
```

在 `workflows/AGENTS.md` 增加规则：

```markdown
- 带必填 `workflow.input_schema` 的工作流应显式声明 `collect_workflow_input` 起始节点，节点 ref 为 `system.workflow_input.v1`，输出 schema 与 workflow input schema 保持一致。
```

在 `docs/design/2026-05-27-01-ui-control-manifest-design.md` 追加新控件清单与创建任务输入统一规则。

- [ ] **Step 2: 更新 Playwright smoke**

在 `ui/V2/tests/e2e/smoke.spec.ts` 中把创建任务阶段的业务字段填写断言改为：

```ts
await page.getByRole("button", { name: "新建任务" }).click();
await expect(page.getByText("运行前准备")).toBeVisible();
await page.getByRole("button", { name: "创建并进入输入节点" }).click();
await expect(page.getByText("填写运行输入")).toBeVisible();
```

smoke 使用 mock 后端时，补充 `system.workflow_input.v1` 的 waiting node fixture：

```ts
{
  node_execution_id: "node-input-1",
  node_id: "collect_workflow_input",
  node_ref: "system.workflow_input.v1",
  status: "waiting",
  input_snapshot: {},
  output_snapshot: {},
  metadata: {
    title: "填写运行输入",
    input_schema: {
      type: "object",
      required: ["prompt"],
      properties: { prompt: { type: "string", title: "提示词" } },
    },
  },
}
```

- [ ] **Step 3: 全量验证**

Run:

```powershell
python -m pytest tests/test_node_registry.py tests/test_runtime_service.py tests/test_api_smoke.py tests/test_ui_control_catalog.py tests/test_workflow_validator.py -q
cd ui/V2
npm run test
npm run build
npm run test:e2e
```

Expected: 全部 PASS。

- [ ] **Step 4: GitNexus 变更检查**

使用 GitNexus：

```text
gitnexus_detect_changes({repo: "XiAgent", scope: "all"})
```

Expected: 改动符号和执行流集中在 workflow input node、runtime task creation/resume、UI control catalog、V2 task creation/control rendering。若出现无关模块，先审查再提交。

- [ ] **Step 5: 提交**

```powershell
git add ui/V2/docs/ui-development-rules.md workflows/AGENTS.md docs/design/2026-05-27-01-ui-control-manifest-design.md ui/V2/tests/e2e/smoke.spec.ts
git commit -m "docs: document workflow input node controls"
```

---

## 自审结果

- 设计覆盖：计划覆盖了起始输入节点、取消创建前输入、资产图片选择控件、工作流迁移、API、V2 页面、测试和文档。
- 类型一致性：后端统一使用 `system.workflow_input.v1`；前端 slot 控件使用 `ui.input.schema_form.v1`，字段级图片控件使用 `ui.input.asset_image_picker.v1`。
- 兼容策略：历史任务快照按原数据查看；V2 新建任务路径省略业务 `input_data`；显式迁移全局工作流。
- 风险点：`SqliteRuntimeService.create_task_from_contract` 和 `resume_task` 是高影响符号，执行任务前必须运行 GitNexus impact 并报告风险。
