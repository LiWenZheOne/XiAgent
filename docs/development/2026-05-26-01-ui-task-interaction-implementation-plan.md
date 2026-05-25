# UI 任务交互实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 XiAgent 第一版 UI 任务交互垂直切片：工作流 `ui` 契约、任务快照、节点级 SSE、用户交互节点、节点重跑、`ui/V1/` 前端、控件注册表、任务详情节点块和真实前后端场景测试。

**Architecture:** 后端继续保持模块化单体，任务运行能力放在 `xiagent.runtime`，HTTP/SSE 放在 `xiagent.api.routers.tasks`，节点能力放在 `xiagent.nodes.system`。前端是独立 React + Vite + TypeScript 工程，放在 `ui/V1/`，只通过 HTTP API 和 SSE 与后端通信。UI 控件通过契约化注册表解析 `workflow.nodes[].ui.block_ref`，任务详情页只消费注册表，不直接依赖具体控件实现。

**Tech Stack:** Python 3.11、FastAPI、SQLite、pytest、React、Vite、TypeScript、Vitest、Playwright。

---

## 设计依据

- 设计文档：`docs/design/2026-05-26-01-ui-task-interaction-design.md`
- 工作流契约设计：`docs/design/2026-05-19-04-workflow-contract-design.md`
- 节点与运行时设计：`docs/design/2026-05-19-05-node-runtime-task-design.md`
- API 设计：`docs/design/2026-05-19-06-api-integration-design.md`
- 项目约束：`AGENTS.md`

## 文件结构

后端新增或修改：

```text
xiagent/workflows/validator.py
xiagent/runtime/models.py
xiagent/runtime/task_view.py
xiagent/runtime/execution_store.py
xiagent/runtime/service.py
xiagent/runtime/event_stream.py
xiagent/nodes/system/user_interaction.py
xiagent/nodes/system/__init__.py
xiagent/nodes/__init__.py
xiagent/api/routers/tasks.py
tests/test_workflow_validator.py
tests/test_runtime_service.py
tests/test_api_smoke.py
```

前端新增：

```text
ui/V1/package.json
ui/V1/index.html
ui/V1/tsconfig.json
ui/V1/tsconfig.node.json
ui/V1/vite.config.ts
ui/V1/src/main.tsx
ui/V1/src/app/App.tsx
ui/V1/src/app/routes.ts
ui/V1/src/api/client.ts
ui/V1/src/api/auth.ts
ui/V1/src/api/tasks.ts
ui/V1/src/api/workflows.ts
ui/V1/src/api/types.ts
ui/V1/src/app/authState.ts
ui/V1/src/task/TaskListPage.tsx
ui/V1/src/task/CreateTaskPage.tsx
ui/V1/src/task/TaskDetailPage.tsx
ui/V1/src/task/TaskNodeBlock.tsx
ui/V1/src/task/taskState.ts
ui/V1/src/ui-blocks/registry.ts
ui/V1/src/ui-blocks/types.ts
ui/V1/src/ui-blocks/fallback/FallbackJsonBlock.tsx
ui/V1/src/ui-blocks/input/FormInputBlock.tsx
ui/V1/src/ui-blocks/output/TextOutputBlock.tsx
ui/V1/src/ui-blocks/output/ImageGridBlock.tsx
ui/V1/src/ui-blocks/choice/ImageChoiceBlock.tsx
ui/V1/src/ui-blocks/approval/ApprovalBlock.tsx
ui/V1/src/ui-blocks/detail/RunDetailBlock.tsx
ui/V1/src/ui-blocks/fixtures.ts
ui/V1/src/ui-blocks/index.ts
ui/V1/src/ui-library/UiBlockLibraryPage.tsx
ui/V1/src/styles/app.css
ui/V1/src/tests/setup.ts
ui/V1/src/tests/*.test.tsx
ui/V1/tests/e2e/task-interaction.spec.ts
```

工作流新增：

```text
workflows/global/ui_task_interaction_demo.workflow.yaml
```

开发文档修改：

```text
docs/README.md
```

## Task 1: 工作流 `ui` 契约校验

**Files:**
- Modify: `xiagent/workflows/validator.py`
- Test: `tests/test_workflow_validator.py`

- [ ] **Step 1: 写合法 `ui` 契约测试**

在 `tests/test_workflow_validator.py` 增加：

```python
def test_workflow_node_ui_contract_is_accepted() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _valid_contract()
    contract["nodes"][0]["ui"] = {
        "block_ref": "ui.text_output.v1",
        "variant": "compact",
        "sections": {
            "input": {"collapsed": False, "fields": ["topic"]},
            "output": {"collapsed": False, "fields": ["echo"]},
        },
        "actions": {"rerun": True},
    }

    validate_workflow_contract(contract, registry)
```

- [ ] **Step 2: 写非法 `ui` 契约测试**

在同一文件增加：

```python
def test_workflow_node_ui_contract_requires_block_ref_string() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _valid_contract()
    contract["nodes"][0]["ui"] = {"block_ref": 123}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "invalid_workflow_ui_contract"
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_workflow_validator.py::test_workflow_node_ui_contract_is_accepted tests/test_workflow_validator.py::test_workflow_node_ui_contract_requires_block_ref_string -q
```

Expected: 第二个测试失败，因为校验器尚未检查 `ui.block_ref`。

- [ ] **Step 4: 实现 `ui` 基本结构校验**

在 `xiagent/workflows/validator.py` 增加：

```python
_UI_SECTION_KEYS = {"input", "output", "detail", "error"}


def _validate_node_ui(ui: Any, *, node_id: str) -> None:
    if ui is None:
        return
    if not isinstance(ui, Mapping):
        raise ValidationError(
            code="invalid_workflow_ui_contract",
            message="Workflow node ui must be an object",
            details={"node_id": node_id},
        )
    block_ref = ui.get("block_ref")
    if not isinstance(block_ref, str) or not block_ref:
        raise ValidationError(
            code="invalid_workflow_ui_contract",
            message="Workflow node ui.block_ref must be a non-empty string",
            details={"node_id": node_id},
        )
    variant = ui.get("variant")
    if variant is not None and (not isinstance(variant, str) or not variant):
        raise ValidationError(
            code="invalid_workflow_ui_contract",
            message="Workflow node ui.variant must be a non-empty string",
            details={"node_id": node_id},
        )
    mode = ui.get("mode")
    if mode is not None and (not isinstance(mode, str) or not mode):
        raise ValidationError(
            code="invalid_workflow_ui_contract",
            message="Workflow node ui.mode must be a non-empty string",
            details={"node_id": node_id},
        )
    sections = ui.get("sections")
    if sections is not None:
        _validate_ui_sections(sections, node_id=node_id)
    for object_key in ("bindings", "actions"):
        value = ui.get(object_key)
        if value is not None and not isinstance(value, Mapping):
            raise ValidationError(
                code="invalid_workflow_ui_contract",
                message=f"Workflow node ui.{object_key} must be an object",
                details={"node_id": node_id},
            )


def _validate_ui_sections(sections: Any, *, node_id: str) -> None:
    if not isinstance(sections, Mapping):
        raise ValidationError(
            code="invalid_workflow_ui_contract",
            message="Workflow node ui.sections must be an object",
            details={"node_id": node_id},
        )
    unsupported = sorted(set(sections).difference(_UI_SECTION_KEYS))
    if unsupported:
        raise ValidationError(
            code="invalid_workflow_ui_contract",
            message="Workflow node ui.sections contains unsupported keys",
            details={"node_id": node_id, "keys": unsupported},
        )
```

在 `_validate_nodes()` 校验 outputs 后调用：

```python
        _validate_node_ui(node.get("ui"), node_id=node_id)
```

- [ ] **Step 5: 运行校验测试**

Run:

```powershell
python -m pytest tests/test_workflow_validator.py -q
```

Expected: PASS.

- [ ] **Step 6: 提交**

```powershell
git add xiagent/workflows/validator.py tests/test_workflow_validator.py
git commit -m "feat: 校验工作流节点 UI 契约"
```

## Task 2: 任务 workflow snapshot 和任务详情视图

**Files:**
- Modify: `xiagent/runtime/models.py`
- Modify: `xiagent/runtime/execution_store.py`
- Modify: `xiagent/runtime/service.py`
- Modify: `xiagent/api/routers/tasks.py`
- Test: `tests/test_runtime_service.py`
- Test: `tests/test_api_smoke.py`

- [ ] **Step 1: 写任务快照 API 测试**

在 `tests/test_api_smoke.py` 增加测试，使用现有注册 / 登录 / 项目创建 helper 风格：

```python
def test_get_task_returns_workflow_snapshot(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_project(client, auth_headers, name="UI 项目")["project_id"]
    contract = _echo_contract()
    contract["nodes"][0]["ui"] = {"block_ref": "ui.text_output.v1"}
    created = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"project_id": project_id, "contract": contract, "input_data": {"topic": "UI"}},
    )
    assert created.status_code == 200

    task_id = created.json()["task_id"]
    response = client.get(
        f"/api/tasks/{task_id}",
        headers=auth_headers,
        params={"project_id": project_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_snapshot"]["nodes"][0]["ui"] == {"block_ref": "ui.text_output.v1"}
    assert body["node_attempts"]["echo"][0]["attempt"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_api_smoke.py::test_get_task_returns_workflow_snapshot -q
```

Expected: FAIL because `workflow_snapshot` and `node_attempts` are missing.

- [ ] **Step 3: 扩展运行时读取任务契约**

在 `xiagent/runtime/service.py` 增加公共方法：

```python
    async def get_task_workflow_snapshot(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        await self._authorize_task_read(user_id=user_id, project_id=project_id, task_id=task_id)
        _task, contract = await self._get_task_and_contract(task_id)
        return contract
```

- [ ] **Step 4: 增加 attempts 聚合 helper**

在 `xiagent/api/routers/tasks.py` 增加：

```python
def _group_attempts(node_executions: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for execution in node_executions:
        grouped.setdefault(execution["node_id"], []).append(execution)
    return grouped
```

- [ ] **Step 5: 修改任务详情 API 响应**

在 `get_task()` 中追加：

```python
    workflow_snapshot = await services.runtime.get_task_workflow_snapshot(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )
    node_execution_dicts = [asdict(execution) for execution in node_executions]
```

返回结构改为：

```python
    return {
        "task": asdict(task),
        "workflow_snapshot": workflow_snapshot,
        "node_executions": node_execution_dicts,
        "node_attempts": _group_attempts(node_execution_dicts),
        "events": [asdict(event) for event in events],
    }
```

- [ ] **Step 6: 运行 API 测试**

Run:

```powershell
python -m pytest tests/test_api_smoke.py::test_get_task_returns_workflow_snapshot -q
```

Expected: PASS.

- [ ] **Step 7: 运行运行时和 API 测试**

Run:

```powershell
python -m pytest tests/test_runtime_service.py tests/test_api_smoke.py -q
```

Expected: PASS.

- [ ] **Step 8: 提交**

```powershell
git add xiagent/runtime/service.py xiagent/api/routers/tasks.py tests/test_api_smoke.py
git commit -m "feat: 返回任务工作流快照"
```

## Task 3: 节点级 SSE 事件流

**Files:**
- Create: `xiagent/runtime/event_stream.py`
- Modify: `xiagent/runtime/service.py`
- Modify: `xiagent/api/routers/tasks.py`
- Test: `tests/test_runtime_service.py`
- Test: `tests/test_api_smoke.py`

- [ ] **Step 1: 写事件游标测试**

创建 `tests/test_runtime_event_stream.py`：

```python
from __future__ import annotations

from xiagent.runtime.event_stream import format_sse_event
from xiagent.runtime.models import TaskEventRecord


def test_format_sse_event_serializes_task_event() -> None:
    event = TaskEventRecord(
        event_id="event_1",
        task_id="task_1",
        event_type="node_succeeded",
        payload={"node_id": "generate"},
        created_at="2026-05-26T00:00:00+00:00",
    )

    assert format_sse_event(event) == (
        'event: node_succeeded\n'
        'id: event_1\n'
        'data: {"created_at":"2026-05-26T00:00:00+00:00","event_id":"event_1",'
        '"payload":{"node_id":"generate"},"task_id":"task_1","type":"node_succeeded"}\n\n'
    )
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_runtime_event_stream.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: 实现 SSE 格式化**

创建 `xiagent/runtime/event_stream.py`：

```python
from __future__ import annotations

import json
from dataclasses import asdict

from xiagent.runtime.models import TaskEventRecord


def task_event_payload(event: TaskEventRecord) -> dict:
    payload = asdict(event)
    payload["type"] = event.event_type
    return payload


def format_sse_event(event: TaskEventRecord) -> str:
    data = json.dumps(task_event_payload(event), ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event_type}\nid: {event.event_id}\ndata: {data}\n\n"
```

- [ ] **Step 4: 增加 API SSE 测试**

在 `tests/test_api_smoke.py` 增加：

```python
def test_task_stream_returns_existing_events(client: TestClient, auth_headers: dict[str, str]) -> None:
    project_id = _create_project(client, auth_headers, name="SSE 项目")["project_id"]
    created = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"project_id": project_id, "contract": _echo_contract(), "input_data": {"topic": "SSE"}},
    )
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    with client.stream(
        "GET",
        f"/api/tasks/{task_id}/stream",
        headers=auth_headers,
        params={"project_id": project_id, "once": "true"},
    ) as response:
        text = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "event: node_started" in text
    assert "event: node_succeeded" in text
```

- [ ] **Step 5: 实现任务流接口**

在 `xiagent/api/routers/tasks.py` 增加 imports：

```python
import asyncio
from collections.abc import AsyncIterator
from fastapi.responses import StreamingResponse
from xiagent.runtime.event_stream import format_sse_event
```

增加 endpoint：

```python
@router.get("/{task_id}/stream")
async def stream_task_events(
    task_id: str,
    project_id: str,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    once: bool = False,
) -> StreamingResponse:
    await services.runtime.get_task(
        user_id=current_user.user_id,
        project_id=project_id,
        task_id=task_id,
    )

    async def event_source() -> AsyncIterator[str]:
        sent_event_ids: set[str] = set()
        while True:
            events = await services.runtime.list_events(
                user_id=current_user.user_id,
                project_id=project_id,
                task_id=task_id,
            )
            for event in events:
                if event.event_id in sent_event_ids:
                    continue
                sent_event_ids.add(event.event_id)
                yield format_sse_event(event)
            if once:
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(event_source(), media_type="text/event-stream")
```

- [ ] **Step 6: 运行事件测试**

Run:

```powershell
python -m pytest tests/test_runtime_event_stream.py tests/test_api_smoke.py::test_task_stream_returns_existing_events -q
```

Expected: PASS.

- [ ] **Step 7: 运行 API 测试**

Run:

```powershell
python -m pytest tests/test_api_smoke.py -q
```

Expected: PASS.

- [ ] **Step 8: 提交**

```powershell
git add xiagent/runtime/event_stream.py xiagent/api/routers/tasks.py tests/test_runtime_event_stream.py tests/test_api_smoke.py
git commit -m "feat: 增加任务节点事件流"
```

## Task 4: 用户交互节点和交互提交接口

**Files:**
- Create: `xiagent/nodes/system/user_interaction.py`
- Modify: `xiagent/nodes/system/__init__.py`
- Modify: `xiagent/nodes/__init__.py`
- Modify: `xiagent/api/routers/tasks.py`
- Test: `tests/test_node_registry.py`
- Test: `tests/test_runtime_service.py`
- Test: `tests/test_api_smoke.py`

- [ ] **Step 1: 写节点注册测试**

在 `tests/test_node_registry.py` 增加：

```python
from xiagent.nodes.system.user_interaction import (
    UserApprovalNode,
    UserChoiceNode,
    UserInputNode,
    UserInteractionNode,
)


def test_user_interaction_nodes_return_waiting() -> None:
    nodes = [UserInteractionNode(), UserInputNode(), UserChoiceNode(), UserApprovalNode()]

    assert [node.describe().ref for node in nodes] == [
        "system.user_interaction.v1",
        "system.user_input.v1",
        "system.user_choice.v1",
        "system.user_approval.v1",
    ]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_node_registry.py::test_user_interaction_nodes_return_waiting -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: 实现交互节点**

创建 `xiagent/nodes/system/user_interaction.py`：

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class _WaitingInteractionNode(BaseNode):
    ref = ""
    name = ""
    interaction_kind = "interaction"

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref=self.ref,
            name=self.name,
            version="1.0.0",
            kind="system",
            input_schema={"type": "object", "additionalProperties": True},
            output_schema={"type": "object", "additionalProperties": True},
            config_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "mode": {"type": "string"},
                },
                "additionalProperties": True,
            },
            description=f"等待用户完成 {self.interaction_kind} 交互。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        output_schema = ctx.output_schema if ctx is not None else {}
        return NodeResult(
            status="waiting",
            output={},
            metadata={
                "interaction_kind": self.interaction_kind,
                "requested_inputs": dict(inputs),
                "output_schema": output_schema,
            },
        )


class UserInteractionNode(_WaitingInteractionNode):
    ref = "system.user_interaction.v1"
    name = "User Interaction"
    interaction_kind = "interaction"


class UserInputNode(_WaitingInteractionNode):
    ref = "system.user_input.v1"
    name = "User Input"
    interaction_kind = "input"


class UserChoiceNode(_WaitingInteractionNode):
    ref = "system.user_choice.v1"
    name = "User Choice"
    interaction_kind = "choice"


class UserApprovalNode(_WaitingInteractionNode):
    ref = "system.user_approval.v1"
    name = "User Approval"
    interaction_kind = "approval"
```

- [ ] **Step 4: 注册交互节点**

在 `xiagent/nodes/__init__.py` import：

```python
from xiagent.nodes.system.user_interaction import (
    UserApprovalNode,
    UserChoiceNode,
    UserInputNode,
    UserInteractionNode,
)
```

在 `build_node_registry()` 中注册：

```python
    registry.register(UserInteractionNode())
    registry.register(UserInputNode())
    registry.register(UserChoiceNode())
    registry.register(UserApprovalNode())
```

- [ ] **Step 5: 增加交互提交 API**

在 `xiagent/api/routers/tasks.py` 增加 request model：

```python
class SubmitInteractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    node_id: str
    output: dict[str, Any]
```

增加 endpoint，第一版复用 `resume_task()`：

```python
@router.post("/{task_id}/interactions")
async def submit_interaction(
    task_id: str,
    request: SubmitInteractionRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    task = await services.runtime.resume_task(
        user_id=current_user.user_id,
        project_id=request.project_id,
        task_id=task_id,
        node_id=request.node_id,
        output=request.output,
    )
    return asdict(task)
```

- [ ] **Step 6: 写交互 API 测试**

在 `tests/test_api_smoke.py` 增加使用 `system.user_choice.v1` 的工作流，断言 `/interactions` 能恢复：

```python
def test_submit_interaction_resumes_user_choice_node(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = _create_project(client, auth_headers, name="交互项目")["project_id"]
    contract = _user_choice_contract()
    created = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"project_id": project_id, "contract": contract, "input_data": {"topic": "图"}},
    )
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/interactions",
        headers=auth_headers,
        json={
            "project_id": project_id,
            "node_id": "choose",
            "output": {"selected_image": {"url": "mock://image-b"}},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
```

- [ ] **Step 7: 运行测试**

Run:

```powershell
python -m pytest tests/test_node_registry.py tests/test_runtime_service.py tests/test_api_smoke.py -q
```

Expected: PASS.

- [ ] **Step 8: 提交**

```powershell
git add xiagent/nodes xiagent/api/routers/tasks.py tests/test_node_registry.py tests/test_api_smoke.py
git commit -m "feat: 增加用户交互节点"
```

## Task 5: 节点重跑与下游清空

**Files:**
- Modify: `xiagent/runtime/task_view.py`
- Modify: `xiagent/runtime/service.py`
- Modify: `xiagent/api/routers/tasks.py`
- Test: `tests/test_runtime_service.py`
- Test: `tests/test_api_smoke.py`

- [ ] **Step 1: 写重跑运行时测试**

在 `tests/test_runtime_service.py` 增加：

```python
async def test_rerun_node_creates_new_attempt_and_clears_downstream(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(BranchValueNode())
    registry.register(JoinInputsProbeNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_parallel_join_contract(),
        input_data={},
    )

    rerun = await runtime.rerun_node(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="a",
    )

    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    a_attempts = [item for item in executions if item.node_id == "a"]
    join_attempts = [item for item in executions if item.node_id == "join"]
    assert rerun.status == "succeeded"
    assert [item.attempt for item in a_attempts] == [1, 2]
    assert len(join_attempts) == 2
    assert rerun.current_view["active_node_outputs"]["a"] == a_attempts[-1].node_execution_id
    assert rerun.current_view["active_node_outputs"]["join"] == join_attempts[-1].node_execution_id
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/test_runtime_service.py::test_rerun_node_creates_new_attempt_and_clears_downstream -q
```

Expected: FAIL because `rerun_node` does not exist.

- [ ] **Step 3: 增加下游节点收集 helper**

在 `xiagent/runtime/service.py` 增加：

```python
def _downstream_node_ids(contract: dict[str, Any], node_id: str) -> set[str]:
    downstream: set[str] = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        for edge in contract["edges"]:
            if edge["from"] != current or edge["to"] == _END:
                continue
            target = edge["to"]
            if target in downstream:
                continue
            downstream.add(target)
            stack.append(target)
    return downstream
```

- [ ] **Step 4: 修改 `_latest_node_outputs` 支持排除 cleared 节点**

在 `xiagent/runtime/service.py` 增加参数：

```python
def _latest_node_outputs(
    executions: list[NodeExecutionRecord],
    *,
    excluded_node_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    excluded = excluded_node_ids or set()
    outputs: dict[str, dict[str, Any]] = {}
    for execution in executions:
        if execution.status == "succeeded" and execution.node_id not in excluded:
            outputs[execution.node_id] = execution.output_snapshot
    return outputs
```

- [ ] **Step 5: 实现重跑方法**

在 `SqliteRuntimeService` 增加：

```python
    async def rerun_node(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
        node_id: str,
    ) -> TaskRecord:
        await self._user_service.ensure_project_access(
            user_id=user_id,
            project_id=project_id,
            action="task:rerun",
        )
        task, contract = await self._get_task_and_contract(task_id)
        _ensure_task_belongs_to_project(task, user_id=user_id, project_id=project_id)
        _node_by_id(contract, node_id)
        downstream = _downstream_node_ids(contract, node_id)
        now = _utc_now()
        async with connect_db(self._database_path) as db:
            executions = await _fetch_node_executions(db, task_id)
            retained_view = build_current_view(
                "running",
                [item for item in executions if item.node_id not in downstream],
            )
            await db.execute(
                """
                update tasks
                set status = ?, current_view_json = ?, finished_at = ?, updated_at = ?
                where task_id = ?
                """,
                ("running", dump_json(retained_view), None, now, task_id),
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="node_rerun_started",
                payload={"node_id": node_id},
                created_at=now,
            )
            await insert_event(
                db,
                task_id=task_id,
                event_type="downstream_cleared",
                payload={"node_id": node_id, "downstream_node_ids": sorted(downstream)},
                created_at=now,
            )
        return await self._continue_task(
            task_id=task_id,
            user_id=user_id,
            project_id=project_id,
            contract=contract,
            workflow_input=task.input_data,
            start_node_id=node_id,
        )
```

- [ ] **Step 6: 修改 `_continue_task` 支持 start node 重跑**

在 `_continue_task()` 开头加载 `rerun_start_node_id = None if start_node_id == _START else start_node_id`，在计算 ready 时允许重跑节点再次执行。实现方式是给 `_ready_node_ids()` 增加 `forced_node_id` 参数；如果该节点不在 waiting/failed 状态且其上游输入可解析，则优先返回 `[forced_node_id]`。

核心判断代码：

```python
    if forced_node_id is not None:
        return [forced_node_id]
```

该逻辑只在 `rerun_node()` 调用路径使用，不影响普通任务执行。

- [ ] **Step 7: 增加重跑 API**

在 `xiagent/api/routers/tasks.py` 增加：

```python
class RerunNodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
```

增加 endpoint：

```python
@router.post("/{task_id}/nodes/{node_id}/rerun")
async def rerun_node(
    task_id: str,
    node_id: str,
    request: RerunNodeRequest,
    services: Annotated[ApiServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> dict:
    task = await services.runtime.rerun_node(
        user_id=current_user.user_id,
        project_id=request.project_id,
        task_id=task_id,
        node_id=node_id,
    )
    return asdict(task)
```

- [ ] **Step 8: 运行重跑测试**

Run:

```powershell
python -m pytest tests/test_runtime_service.py::test_rerun_node_creates_new_attempt_and_clears_downstream tests/test_api_smoke.py -q
```

Expected: PASS.

- [ ] **Step 9: 提交**

```powershell
git add xiagent/runtime xiagent/api/routers/tasks.py tests/test_runtime_service.py tests/test_api_smoke.py
git commit -m "feat: 支持任务节点重跑"
```

## Task 6: 示例工作流

**Files:**
- Create: `workflows/global/ui_task_interaction_demo.workflow.yaml`
- Modify: `tests/test_workflow_validator.py`

- [ ] **Step 1: 创建示例工作流**

创建 `workflows/global/ui_task_interaction_demo.workflow.yaml`：

```yaml
workflow:
  id: ui_task_interaction_demo
  version: "1.0.0"
  scope: global
  name: UI 任务交互演示
  description: 演示用户输入、候选输出选择、继续执行和重跑。
  input_schema:
    type: object
    required: ["prompt"]
    properties:
      prompt:
        type: string

nodes:
  - id: user_input
    ref: system.user_input.v1
    inputs:
      prompt:
        from: "$workflow.input.prompt"
    outputs:
      type: object
      required: ["prompt"]
      properties:
        prompt:
          type: string
    ui:
      block_ref: ui.form_input.v1
      variant: compact
      actions:
        confirm: true

  - id: echo_candidates
    ref: tool.echo.v1
    inputs:
      candidates:
        value:
          - url: "mock://image-a"
          - url: "mock://image-b"
          - url: "mock://image-c"
    outputs:
      type: object
      required: ["echo"]
      properties:
        echo:
          type: object
    ui:
      block_ref: ui.image_grid.v1
      variant: gallery_three
      actions:
        rerun: true

  - id: choose_image
    ref: system.user_choice.v1
    inputs:
      candidates:
        from: "$nodes.echo_candidates.output.echo.candidates"
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
        selected_output_key: selected_image
      actions:
        confirm: true

  - id: final_output
    ref: tool.echo.v1
    inputs:
      selected_image:
        from: "$nodes.choose_image.output.selected_image"
    outputs:
      type: object
    ui:
      block_ref: ui.text_output.v1
      variant: compact

edges:
  - from: START
    to: user_input
  - from: user_input
    to: echo_candidates
  - from: echo_candidates
    to: choose_image
  - from: choose_image
    to: final_output
  - from: final_output
    to: END
```

- [ ] **Step 2: 增加示例工作流测试**

在 `tests/test_workflow_validator.py` 增加：

```python
def test_ui_task_interaction_demo_workflow_is_valid(test_settings) -> None:
    from xiagent.nodes import build_node_registry

    contract = load_workflow_file(Path("workflows/global/ui_task_interaction_demo.workflow.yaml"))

    validate_workflow_contract(contract, build_node_registry(test_settings))
```

- [ ] **Step 3: 运行工作流测试**

Run:

```powershell
python -m pytest tests/test_workflow_validator.py::test_ui_task_interaction_demo_workflow_is_valid -q
```

Expected: PASS.

- [ ] **Step 4: 提交**

```powershell
git add workflows/global/ui_task_interaction_demo.workflow.yaml tests/test_workflow_validator.py
git commit -m "feat: 增加 UI 任务交互示例工作流"
```

## Task 7: 创建 `ui/V1/` 前端工程

**Files:**
- Create: `ui/V1/package.json`
- Create: `ui/V1/index.html`
- Create: `ui/V1/tsconfig.json`
- Create: `ui/V1/tsconfig.node.json`
- Create: `ui/V1/vite.config.ts`
- Create: `ui/V1/src/main.tsx`
- Create: `ui/V1/src/app/App.tsx`
- Create: `ui/V1/src/styles/app.css`
- Create: `ui/V1/src/tests/setup.ts`

- [ ] **Step 1: 创建前端目录**

Run:

```powershell
New-Item -ItemType Directory -Force ui\V1\src\app,ui\V1\src\styles
```

Expected: directories exist.

- [ ] **Step 2: 创建 `package.json`**

Create `ui/V1/package.json`:

```json
{
  "name": "xiagent-ui-v1",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^5.0.0",
    "vite": "^7.0.0",
    "typescript": "^5.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "@testing-library/react": "^16.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "jsdom": "^26.0.0",
    "vitest": "^3.0.0"
  }
}
```

- [ ] **Step 3: 创建 Vite 基础文件**

Create `ui/V1/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>XiAgent UI V1</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `ui/V1/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/tests/setup.ts",
  },
});
```

- [ ] **Step 4: 创建 TypeScript 配置**

Create `ui/V1/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `ui/V1/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: 创建入口组件**

Create `ui/V1/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import "./styles/app.css";

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Create `ui/V1/src/app/App.tsx`:

```tsx
export function App() {
  return (
    <main className="app-shell">
      <aside className="app-sidebar">
        <strong>XiAgent</strong>
        <nav>
          <a href="#/tasks">任务</a>
          <a href="#/workflows">工作流</a>
          <a href="#/assets">资产库</a>
          <a href="#/ui-blocks">UI 控件库</a>
        </nav>
      </aside>
      <section className="app-content">
        <h1>XiAgent UI V1</h1>
      </section>
    </main>
  );
}
```

- [ ] **Step 6: 创建基础样式和测试 setup**

Create `ui/V1/src/styles/app.css`:

```css
:root {
  color: #172026;
  background: #f5f8fa;
  font-family: Inter, "Microsoft YaHei", system-ui, sans-serif;
}

body {
  margin: 0;
}

.app-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 100vh;
}

.app-sidebar {
  border-right: 1px solid #d8e0e7;
  background: #ffffff;
  padding: 16px;
}

.app-sidebar nav {
  display: grid;
  gap: 8px;
  margin-top: 16px;
}

.app-sidebar a {
  color: #34444f;
  text-decoration: none;
}

.app-content {
  padding: 20px;
}
```

Create `ui/V1/src/tests/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 7: 安装依赖并构建**

Run:

```powershell
Set-Location ui\V1
npm install
npm run build
Set-Location ..\..
```

Expected: `npm run build` PASS.

- [ ] **Step 8: 提交**

```powershell
git add ui/V1
git commit -m "feat: 创建 UI V1 前端工程"
```

## Task 8: 前端 API 类型和客户端

**Files:**
- Create: `ui/V1/src/api/types.ts`
- Create: `ui/V1/src/api/client.ts`
- Create: `ui/V1/src/api/auth.ts`
- Create: `ui/V1/src/api/tasks.ts`
- Create: `ui/V1/src/api/workflows.ts`
- Test: `ui/V1/src/tests/api-client.test.ts`

- [ ] **Step 1: 创建 API 类型**

Create `ui/V1/src/api/types.ts`:

```ts
export type JsonObject = Record<string, unknown>;

export interface TaskRecord {
  task_id: string;
  workflow_id: string;
  workflow_version: string;
  project_id: string;
  input_data: JsonObject;
  status: string;
  current_view: JsonObject;
}

export interface NodeExecutionRecord {
  node_execution_id: string;
  task_id: string;
  node_id: string;
  node_ref: string;
  attempt: number;
  input_snapshot: JsonObject;
  output_snapshot: JsonObject;
  status: string;
  error: JsonObject | null;
  metadata: JsonObject;
  asset_refs: JsonObject[];
}

export interface WorkflowNodeSpec {
  id: string;
  ref: string;
  inputs?: JsonObject;
  outputs: JsonObject;
  ui?: NodeUiConfig;
}

export interface NodeUiConfig {
  block_ref: string;
  variant?: string;
  mode?: string;
  sections?: JsonObject;
  bindings?: JsonObject;
  actions?: JsonObject;
}

export interface TaskDetailResponse {
  task: TaskRecord;
  workflow_snapshot: {
    workflow: JsonObject;
    nodes: WorkflowNodeSpec[];
    edges: JsonObject[];
  };
  node_executions: NodeExecutionRecord[];
  node_attempts: Record<string, NodeExecutionRecord[]>;
  events: JsonObject[];
}
```

- [ ] **Step 2: 创建 API client**

Create `ui/V1/src/api/client.ts`:

```ts
export interface ApiClientOptions {
  baseUrl: string;
  token: string;
}

export class ApiClient {
  constructor(private readonly options: ApiClientOptions) {}

  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.options.baseUrl}${path}`, {
      headers: this.headers(),
    });
    return this.read<T>(response);
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(`${this.options.baseUrl}${path}`, {
      method: "POST",
      headers: { ...this.headers(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return this.read<T>(response);
  }

  private headers(): Record<string, string> {
    return { Authorization: `Bearer ${this.options.token}` };
  }

  private async read<T>(response: Response): Promise<T> {
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body?.error?.message ?? `HTTP ${response.status}`);
    }
    return body as T;
  }
}
```

- [ ] **Step 3: 创建认证 API**

Create `ui/V1/src/api/auth.ts`:

```ts
import { ApiClient } from "./client";

export interface LoginResponse {
  user: { user_id: string; username: string };
  access_token: string;
  token_type: "bearer";
}

export function register(client: ApiClient, username: string, password: string) {
  return client.post<{ user_id: string; username: string }>("/api/auth/register", {
    username,
    password,
  });
}

export function login(client: ApiClient, username: string, password: string) {
  return client.post<LoginResponse>("/api/auth/login", { username, password });
}
```

- [ ] **Step 4: 创建任务 API**

Create `ui/V1/src/api/tasks.ts`:

```ts
import { ApiClient } from "./client";
import type { JsonObject, TaskDetailResponse, TaskRecord } from "./types";

export function getTask(client: ApiClient, taskId: string, projectId: string) {
  return client.get<TaskDetailResponse>(`/api/tasks/${taskId}?project_id=${projectId}`);
}

export function createTask(
  client: ApiClient,
  request: { project_id: string; contract: JsonObject; input_data: JsonObject },
) {
  return client.post<TaskRecord>("/api/tasks", request);
}

export function submitInteraction(
  client: ApiClient,
  taskId: string,
  request: { project_id: string; node_id: string; output: JsonObject },
) {
  return client.post<TaskRecord>(`/api/tasks/${taskId}/interactions`, request);
}

export function rerunNode(
  client: ApiClient,
  taskId: string,
  nodeId: string,
  request: { project_id: string },
) {
  return client.post<TaskRecord>(`/api/tasks/${taskId}/nodes/${nodeId}/rerun`, request);
}

export async function streamTaskEvents(
  client: ApiClient,
  taskId: string,
  projectId: string,
  onEvent: (event: MessageEvent) => void,
) {
  const response = await fetch(`/api/tasks/${taskId}/stream?project_id=${projectId}`, {
    headers: { Authorization: `Bearer ${client.token}` },
  });
  if (!response.ok || response.body === null) {
    throw new Error(`Task stream failed: HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const dataLine = part.split("\n").find((line) => line.startsWith("data: "));
      if (dataLine) {
        onEvent(new MessageEvent("message", { data: dataLine.slice("data: ".length) }));
      }
    }
  }
}
```

- [ ] **Step 5: 创建工作流 API**

Create `ui/V1/src/api/workflows.ts`:

```ts
import { ApiClient } from "./client";
import type { JsonObject } from "./types";

export interface WorkflowListItem {
  workflow: JsonObject;
  nodes: JsonObject[];
  edges: JsonObject[];
}

export function listWorkflows(client: ApiClient) {
  return client.get<{ items: WorkflowListItem[] }>("/api/workflows");
}
```

- [ ] **Step 6: 暴露 token 只读访问**

在 `ui/V1/src/api/client.ts` 中补充 getter：

```ts
  get token() {
    return this.options.token;
  }
```

- [ ] **Step 7: 写 API client 测试**

Create `ui/V1/src/tests/api-client.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "../api/client";
import { getTask } from "../api/tasks";

describe("ApiClient", () => {
  it("adds bearer token and reads task detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ task: { task_id: "task_1" } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient({ baseUrl: "", token: "token_1" });

    const result = await getTask(client, "task_1", "project_1");

    expect(result.task.task_id).toBe("task_1");
    expect(fetchMock).toHaveBeenCalledWith("/api/tasks/task_1?project_id=project_1", {
      headers: { Authorization: "Bearer token_1" },
    });
  });
});
```

- [ ] **Step 8: 运行前端测试**

Run:

```powershell
Set-Location ui\V1
npm run test
Set-Location ..\..
```

Expected: PASS.

- [ ] **Step 9: 提交**

```powershell
git add ui/V1/src/api ui/V1/src/tests
git commit -m "feat: 增加 UI V1 API 客户端"
```

## Task 9: UI 控件注册表和核心控件

**Files:**
- Create: `ui/V1/src/ui-blocks/types.ts`
- Create: `ui/V1/src/ui-blocks/registry.ts`
- Create: `ui/V1/src/ui-blocks/fallback/FallbackJsonBlock.tsx`
- Create: `ui/V1/src/ui-blocks/input/FormInputBlock.tsx`
- Create: `ui/V1/src/ui-blocks/output/TextOutputBlock.tsx`
- Create: `ui/V1/src/ui-blocks/output/ImageGridBlock.tsx`
- Create: `ui/V1/src/ui-blocks/choice/ImageChoiceBlock.tsx`
- Create: `ui/V1/src/ui-blocks/approval/ApprovalBlock.tsx`
- Create: `ui/V1/src/ui-blocks/detail/RunDetailBlock.tsx`
- Create: `ui/V1/src/ui-blocks/index.ts`
- Test: `ui/V1/src/tests/ui-block-registry.test.tsx`

- [ ] **Step 1: 创建控件类型**

Create `ui/V1/src/ui-blocks/types.ts`:

```ts
import type { JsonObject, NodeExecutionRecord, NodeUiConfig, WorkflowNodeSpec } from "../api/types";

export type UiBlockKind = "input" | "output" | "choice" | "approval" | "detail";

export interface UiBlockVariant {
  name: string;
  label: string;
}

export interface UiBlockDescriptor {
  ref: string;
  version: string;
  name: string;
  kind: UiBlockKind;
  tags: string[];
  variants: UiBlockVariant[];
}

export interface UiBlockAction {
  type: "submit_interaction" | "select_output" | "approve" | "reject" | "save_asset";
  nodeId: string;
  payload: JsonObject;
}

export interface UiBlockProps {
  nodeSpec: WorkflowNodeSpec;
  execution: NodeExecutionRecord | null;
  attempts: NodeExecutionRecord[];
  uiConfig: NodeUiConfig;
  readonly: boolean;
  onSubmitAction(action: UiBlockAction): Promise<void>;
  onRerun(): Promise<void>;
}

export interface UiBlockModule {
  descriptor: UiBlockDescriptor;
  component: React.ComponentType<UiBlockProps>;
  isCompatible(nodeSpec: WorkflowNodeSpec): boolean;
}
```

- [ ] **Step 2: 创建注册表**

Create `ui/V1/src/ui-blocks/registry.ts`:

```ts
import type { WorkflowNodeSpec } from "../api/types";
import type { UiBlockModule } from "./types";

export class UiBlockRegistry {
  private readonly blocks = new Map<string, UiBlockModule>();

  register(block: UiBlockModule) {
    if (this.blocks.has(block.descriptor.ref)) {
      throw new Error(`Duplicate UI block: ${block.descriptor.ref}`);
    }
    this.blocks.set(block.descriptor.ref, block);
  }

  list() {
    return [...this.blocks.values()];
  }

  resolve(nodeSpec: WorkflowNodeSpec, fallback: UiBlockModule) {
    const ref = nodeSpec.ui?.block_ref;
    if (!ref) return fallback;
    const block = this.blocks.get(ref);
    if (!block) return fallback;
    return block.isCompatible(nodeSpec) ? block : fallback;
  }
}
```

- [ ] **Step 3: 创建 fallback 控件**

Create `ui/V1/src/ui-blocks/fallback/FallbackJsonBlock.tsx`:

```tsx
import type { UiBlockModule, UiBlockProps } from "../types";

function FallbackJsonBlock({ execution }: UiBlockProps) {
  return (
    <pre className="json-block">
      {JSON.stringify(
        {
          input: execution?.input_snapshot ?? {},
          output: execution?.output_snapshot ?? {},
          error: execution?.error ?? null,
        },
        null,
        2,
      )}
    </pre>
  );
}

export const fallbackJsonBlock: UiBlockModule = {
  descriptor: {
    ref: "ui.fallback_json.v1",
    version: "1.0.0",
    name: "Fallback JSON",
    kind: "detail",
    tags: ["json", "fallback"],
    variants: [{ name: "default", label: "默认" }],
  },
  component: FallbackJsonBlock,
  isCompatible: () => true,
};
```

- [ ] **Step 4: 创建核心控件**

Create each core block with the same module shape. Example for `ImageChoiceBlock`:

```tsx
import type { UiBlockModule, UiBlockProps } from "../types";

function ImageChoiceBlock({ nodeSpec, execution, onSubmitAction, readonly }: UiBlockProps) {
  const candidates = (execution?.input_snapshot.candidates as Array<{ url: string }> | undefined) ?? [];
  return (
    <div className="image-choice">
      {candidates.map((item, index) => (
        <button
          key={item.url}
          disabled={readonly}
          onClick={() =>
            onSubmitAction({
              type: "select_output",
              nodeId: nodeSpec.id,
              payload: { selected_image: item },
            })
          }
        >
          候选 {index + 1}
          <span>{item.url}</span>
        </button>
      ))}
    </div>
  );
}

export const imageChoiceBlock: UiBlockModule = {
  descriptor: {
    ref: "ui.image_choice.v1",
    version: "1.0.0",
    name: "图片选择",
    kind: "choice",
    tags: ["image", "select_one"],
    variants: [{ name: "select_one_gallery", label: "单选图库" }],
  },
  component: ImageChoiceBlock,
  isCompatible: (nodeSpec) => nodeSpec.ui?.mode === "select_one",
};
```

- [ ] **Step 5: 注册核心控件**

Create `ui/V1/src/ui-blocks/index.ts`:

```ts
import { fallbackJsonBlock } from "./fallback/FallbackJsonBlock";
import { approvalBlock } from "./approval/ApprovalBlock";
import { imageChoiceBlock } from "./choice/ImageChoiceBlock";
import { formInputBlock } from "./input/FormInputBlock";
import { imageGridBlock } from "./output/ImageGridBlock";
import { textOutputBlock } from "./output/TextOutputBlock";
import { runDetailBlock } from "./detail/RunDetailBlock";
import { UiBlockRegistry } from "./registry";

export const uiBlockRegistry = new UiBlockRegistry();
export const fallbackBlock = fallbackJsonBlock;

for (const block of [
  fallbackJsonBlock,
  formInputBlock,
  textOutputBlock,
  imageGridBlock,
  imageChoiceBlock,
  approvalBlock,
  runDetailBlock,
]) {
  uiBlockRegistry.register(block);
}
```

- [ ] **Step 6: 写注册表测试**

Create `ui/V1/src/tests/ui-block-registry.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";

import { fallbackBlock, uiBlockRegistry } from "../ui-blocks";

describe("uiBlockRegistry", () => {
  it("resolves compatible image choice block", () => {
    const block = uiBlockRegistry.resolve(
      {
        id: "choose",
        ref: "system.user_choice.v1",
        outputs: {},
        ui: { block_ref: "ui.image_choice.v1", mode: "select_one" },
      },
      fallbackBlock,
    );

    expect(block.descriptor.ref).toBe("ui.image_choice.v1");
  });

  it("falls back for missing block", () => {
    const block = uiBlockRegistry.resolve(
      { id: "x", ref: "tool.echo.v1", outputs: {}, ui: { block_ref: "ui.missing.v1" } },
      fallbackBlock,
    );

    expect(block.descriptor.ref).toBe("ui.fallback_json.v1");
  });
});
```

- [ ] **Step 7: 运行前端测试**

Run:

```powershell
Set-Location ui\V1
npm run test
Set-Location ..\..
```

Expected: PASS.

- [ ] **Step 8: 提交**

```powershell
git add ui/V1/src/ui-blocks ui/V1/src/tests
git commit -m "feat: 增加 UI 控件注册表"
```

## Task 10: 任务列表、创建任务和任务详情页

**Files:**
- Modify: `ui/V1/src/app/App.tsx`
- Create: `ui/V1/src/app/routes.ts`
- Create: `ui/V1/src/app/authState.ts`
- Create: `ui/V1/src/task/TaskListPage.tsx`
- Create: `ui/V1/src/task/CreateTaskPage.tsx`
- Create: `ui/V1/src/task/TaskDetailPage.tsx`
- Create: `ui/V1/src/task/TaskNodeBlock.tsx`
- Create: `ui/V1/src/task/taskState.ts`
- Test: `ui/V1/src/tests/task-state.test.ts`
- Test: `ui/V1/src/tests/task-node-block.test.tsx`

- [ ] **Step 1: 创建任务状态 reducer 测试**

Create `ui/V1/src/tests/task-state.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { applyTaskEvent } from "../task/taskState";

describe("applyTaskEvent", () => {
  it("updates node execution on node_succeeded event", () => {
    const state = {
      executionsByNode: {},
      clearedNodeIds: new Set<string>(),
    };

    const next = applyTaskEvent(state, {
      type: "node_succeeded",
      payload: {
        node_id: "generate",
        execution: {
          node_id: "generate",
          status: "succeeded",
          output_snapshot: { url: "mock://image" },
        },
      },
    });

    expect(next.executionsByNode.generate.status).toBe("succeeded");
  });
});
```

- [ ] **Step 2: 实现 `taskState.ts`**

Create `ui/V1/src/task/taskState.ts`:

```ts
import type { JsonObject, NodeExecutionRecord } from "../api/types";

export interface TaskUiState {
  executionsByNode: Record<string, NodeExecutionRecord>;
  clearedNodeIds: Set<string>;
}

export interface TaskStreamEvent {
  type: string;
  payload: JsonObject;
}

export function applyTaskEvent(state: TaskUiState, event: TaskStreamEvent): TaskUiState {
  if (event.type === "downstream_cleared") {
    const ids = (event.payload.downstream_node_ids as string[] | undefined) ?? [];
    return { ...state, clearedNodeIds: new Set(ids) };
  }
  const execution = event.payload.execution as NodeExecutionRecord | undefined;
  if (execution?.node_id) {
    return {
      ...state,
      executionsByNode: { ...state.executionsByNode, [execution.node_id]: execution },
    };
  }
  return state;
}
```

- [ ] **Step 3: 创建节点块组件**

Create `ui/V1/src/task/TaskNodeBlock.tsx`:

```tsx
import type { NodeExecutionRecord, WorkflowNodeSpec } from "../api/types";
import { fallbackBlock, uiBlockRegistry } from "../ui-blocks";
import type { UiBlockAction } from "../ui-blocks/types";

interface TaskNodeBlockProps {
  node: WorkflowNodeSpec;
  execution: NodeExecutionRecord | null;
  attempts: NodeExecutionRecord[];
  readonly: boolean;
  onSubmitAction(action: UiBlockAction): Promise<void>;
  onRerun(nodeId: string): Promise<void>;
}

export function TaskNodeBlock({
  node,
  execution,
  attempts,
  readonly,
  onSubmitAction,
  onRerun,
}: TaskNodeBlockProps) {
  const block = uiBlockRegistry.resolve(node, fallbackBlock);
  const Block = block.component;
  return (
    <article className="task-node-block">
      <header>
        <div>
          <strong>{node.id}</strong>
          <span>{execution?.status ?? "pending"}</span>
        </div>
        {node.ui?.actions?.["rerun"] === true ? (
          <button onClick={() => onRerun(node.id)}>重新运行</button>
        ) : null}
      </header>
      <Block
        nodeSpec={node}
        execution={execution}
        attempts={attempts}
        uiConfig={node.ui ?? { block_ref: "ui.fallback_json.v1" }}
        readonly={readonly}
        onSubmitAction={onSubmitAction}
        onRerun={() => onRerun(node.id)}
      />
    </article>
  );
}
```

- [ ] **Step 4: 创建前端认证状态**

Create `ui/V1/src/app/authState.ts`:

```ts
export interface AuthState {
  token: string;
  username: string;
}

const STORAGE_KEY = "xiagent.ui.v1.auth";

export function loadAuthState(): AuthState | null {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw ? (JSON.parse(raw) as AuthState) : null;
}

export function saveAuthState(state: AuthState) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function clearAuthState() {
  window.localStorage.removeItem(STORAGE_KEY);
}
```

- [ ] **Step 5: 创建任务详情页**

Create `ui/V1/src/task/TaskDetailPage.tsx` with authenticated SSE fetch subscription:

```tsx
import { useEffect, useState } from "react";

import { ApiClient } from "../api/client";
import { getTask, rerunNode, streamTaskEvents, submitInteraction } from "../api/tasks";
import type { TaskDetailResponse } from "../api/types";
import type { UiBlockAction } from "../ui-blocks/types";
import { TaskNodeBlock } from "./TaskNodeBlock";

export function TaskDetailPage({ client, projectId, taskId }: {
  client: ApiClient;
  projectId: string;
  taskId: string;
}) {
  const [detail, setDetail] = useState<TaskDetailResponse | null>(null);

  useEffect(() => {
    void getTask(client, taskId, projectId).then(setDetail);
  }, [client, projectId, taskId]);

  useEffect(() => {
    let cancelled = false;
    void streamTaskEvents(client, taskId, projectId, () => {
      if (!cancelled) void getTask(client, taskId, projectId).then(setDetail);
    });
    return () => {
      cancelled = true;
    };
  }, [client, projectId, taskId]);

  async function handleAction(action: UiBlockAction) {
    await submitInteraction(client, taskId, {
      project_id: projectId,
      node_id: action.nodeId,
      output: action.payload,
    });
    setDetail(await getTask(client, taskId, projectId));
  }

  async function handleRerun(nodeId: string) {
    await rerunNode(client, taskId, nodeId, { project_id: projectId });
    setDetail(await getTask(client, taskId, projectId));
  }

  if (!detail) return <p>加载中</p>;

  return (
    <section>
      <h1>任务详情</h1>
      {detail.workflow_snapshot.nodes.map((node) => (
        <TaskNodeBlock
          key={node.id}
          node={node}
          execution={detail.node_attempts[node.id]?.at(-1) ?? null}
          attempts={detail.node_attempts[node.id] ?? []}
          readonly={detail.task.status === "succeeded"}
          onSubmitAction={handleAction}
          onRerun={handleRerun}
        />
      ))}
    </section>
  );
}
```

- [ ] **Step 6: 创建任务列表和创建任务页**

`TaskListPage` 第一行显示创建任务入口。`CreateTaskPage` 调用 `/api/workflows` 获取当前项目可用工作流，选择后调用 `createTask()`。

核心 JSX:

```tsx
<button onClick={() => navigate("#/tasks/new")}>创建任务</button>
```

- [ ] **Step 7: 在 App 中接入登录和路由**

`App.tsx` 先读取 `loadAuthState()`。没有 token 时显示注册 / 登录表单，认证成功后创建 `ApiClient` 并进入任务页面。

核心代码：

```tsx
const [auth, setAuth] = useState(loadAuthState());
const anonymousClient = new ApiClient({ baseUrl: "", token: "" });

async function handleRegister(username: string, password: string) {
  await register(anonymousClient, username, password);
  await handleLogin(username, password);
}

async function handleLogin(username: string, password: string) {
  const result = await login(anonymousClient, username, password);
  const next = { token: result.access_token, username: result.user.username };
  saveAuthState(next);
  setAuth(next);
}
```

- [ ] **Step 8: 运行前端测试和构建**

Run:

```powershell
Set-Location ui\V1
npm run test
npm run build
Set-Location ..\..
```

Expected: PASS.

- [ ] **Step 9: 提交**

```powershell
git add ui/V1/src/app ui/V1/src/task ui/V1/src/tests
git commit -m "feat: 实现任务交互页面"
```

## Task 11: UI 控件库浏览页

**Files:**
- Create: `ui/V1/src/ui-blocks/fixtures.ts`
- Create: `ui/V1/src/ui-library/UiBlockLibraryPage.tsx`
- Modify: `ui/V1/src/app/App.tsx`
- Test: `ui/V1/src/tests/ui-block-library.test.tsx`

- [ ] **Step 1: 创建预览 fixture**

Create `ui/V1/src/ui-blocks/fixtures.ts`:

```ts
import type { NodeExecutionRecord, WorkflowNodeSpec } from "../api/types";

export interface UiBlockFixture {
  node: WorkflowNodeSpec;
  execution: NodeExecutionRecord | null;
}

export const uiBlockFixtures: Record<string, UiBlockFixture> = {
  "ui.image_choice.v1": {
    node: {
      id: "choose_image",
      ref: "system.user_choice.v1",
      outputs: {},
      ui: { block_ref: "ui.image_choice.v1", mode: "select_one" },
    },
    execution: {
      node_execution_id: "exec_preview",
      task_id: "task_preview",
      node_id: "choose_image",
      node_ref: "system.user_choice.v1",
      attempt: 1,
      input_snapshot: {
        candidates: [{ url: "mock://a" }, { url: "mock://b" }, { url: "mock://c" }],
      },
      output_snapshot: {},
      status: "waiting",
      error: null,
      metadata: {},
      asset_refs: [],
    },
  },
};
```

- [ ] **Step 2: 创建控件库页面**

Create `ui/V1/src/ui-library/UiBlockLibraryPage.tsx`:

```tsx
import { fallbackBlock, uiBlockRegistry } from "../ui-blocks";
import { uiBlockFixtures } from "../ui-blocks/fixtures";

export function UiBlockLibraryPage() {
  return (
    <section>
      <h1>UI 控件库</h1>
      <div className="ui-block-grid">
        {uiBlockRegistry.list().map((block) => {
          const fixture = uiBlockFixtures[block.descriptor.ref];
          const Block = block.component;
          return (
            <article key={block.descriptor.ref}>
              <h2>{block.descriptor.name}</h2>
              <p>{block.descriptor.kind}</p>
              <p>{block.descriptor.tags.join(" / ")}</p>
              {fixture ? (
                <Block
                  nodeSpec={fixture.node}
                  execution={fixture.execution}
                  attempts={fixture.execution ? [fixture.execution] : []}
                  uiConfig={fixture.node.ui ?? fallbackBlock.descriptor}
                  readonly
                  onSubmitAction={async () => undefined}
                  onRerun={async () => undefined}
                />
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: 写控件库测试**

Create `ui/V1/src/tests/ui-block-library.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UiBlockLibraryPage } from "../ui-library/UiBlockLibraryPage";

describe("UiBlockLibraryPage", () => {
  it("renders registered UI blocks", () => {
    render(<UiBlockLibraryPage />);

    expect(screen.getByText("UI 控件库")).toBeInTheDocument();
    expect(screen.getByText("图片选择")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: 运行前端测试**

Run:

```powershell
Set-Location ui\V1
npm run test
Set-Location ..\..
```

Expected: PASS.

- [ ] **Step 5: 提交**

```powershell
git add ui/V1/src/ui-blocks/fixtures.ts ui/V1/src/ui-library ui/V1/src/tests
git commit -m "feat: 增加 UI 控件库页面"
```

## Task 12: 真实前后端用户场景测试

**Files:**
- Create: `ui/V1/playwright.config.ts`
- Create: `ui/V1/tests/e2e/task-interaction.spec.ts`
- Create: `tests/e2e/test_ui_backend_smoke.py`

- [ ] **Step 1: 增加 Playwright 配置**

Create `ui/V1/playwright.config.ts`:

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
  },
});
```

- [ ] **Step 2: 创建前端真实后端 E2E 测试**

Create `ui/V1/tests/e2e/task-interaction.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("user creates task, selects candidate, and reruns node", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名").fill("ui-e2e-user");
  await page.getByLabel("密码").fill("secret-123");
  await page.getByText("注册").click();
  await page.getByText("登录").click();
  await page.getByText("任务").click();
  await page.getByText("创建任务").click();
  await page.getByText("UI 任务交互演示").click();
  await page.getByLabel("prompt").fill("电影感人物主视觉");
  await page.getByText("创建").click();

  await expect(page.getByText("填写工作流输入")).toBeVisible();
  await expect(page.getByText("生成 3 张候选图")).toBeVisible();
  await page.getByText("候选 2").click();
  await expect(page.getByText("最终输出")).toBeVisible();

  await page.getByText("重新运行").click();
  await expect(page.getByText("pending")).toBeVisible();
});
```

- [ ] **Step 3: 增加后端集成测试说明性 smoke**

Create `tests/e2e/test_ui_backend_smoke.py`:

```python
from __future__ import annotations

from pathlib import Path


def test_ui_v1_e2e_files_exist() -> None:
    assert Path("ui/V1/playwright.config.ts").exists()
    assert Path("ui/V1/tests/e2e/task-interaction.spec.ts").exists()
```

- [ ] **Step 4: 运行真实前后端 E2E**

启动后端：

```powershell
python -m uvicorn xiagent.api.app:app --host 127.0.0.1 --port 8000
```

另一个终端运行：

```powershell
Set-Location ui\V1
npm run test:e2e
Set-Location ..\..
```

Expected: Playwright PASS，浏览器真实访问 `ui/V1` 页面并通过代理调用 FastAPI。

- [ ] **Step 5: 运行全量测试**

Run:

```powershell
python -m pytest -q
Set-Location ui\V1
npm run test
npm run build
Set-Location ..\..
```

Expected: PASS.

- [ ] **Step 6: 提交**

```powershell
git add ui/V1/playwright.config.ts ui/V1/tests/e2e tests/e2e
git commit -m "test: 增加 UI 前后端场景测试"
```

## Task 13: 文档索引和最终验证

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/development/2026-05-26-01-ui-task-interaction-implementation-plan.md`

- [ ] **Step 1: 更新文档索引**

在 `docs/README.md` 开发文档列表加入：

```markdown
- [UI 任务交互实现计划](development/2026-05-26-01-ui-task-interaction-implementation-plan.md)
```

- [ ] **Step 2: 运行后端测试**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: 运行前端测试和构建**

Run:

```powershell
Set-Location ui\V1
npm run test
npm run build
Set-Location ..\..
```

Expected: PASS.

- [ ] **Step 4: 运行前后端真实场景测试**

Run:

```powershell
Set-Location ui\V1
npm run test:e2e
Set-Location ..\..
```

Expected: PASS.

- [ ] **Step 5: 查看 git 状态**

Run:

```powershell
git status --short
```

Expected: clean working tree.

- [ ] **Step 6: 提交文档索引**

```powershell
git add docs/README.md docs/development/2026-05-26-01-ui-task-interaction-implementation-plan.md
git commit -m "docs: 增加 UI 任务交互实现计划"
```

## 自检

- 设计文档中的信息架构由 Task 10 覆盖。
- 工作流 `ui` 契约由 Task 1 和 Task 6 覆盖。
- 任务 workflow snapshot 由 Task 2 覆盖。
- 节点级 SSE 由 Task 3 覆盖。
- 用户交互节点由 Task 4 覆盖。
- 节点重跑和下游清空由 Task 5 覆盖。
- `ui/V1/` 前端目录约束由 Task 7 覆盖。
- UI 控件注册表由 Task 9 覆盖。
- UI 控件库页面由 Task 11 覆盖。
- 真实前端调用真实后端的用户场景测试由 Task 12 覆盖。
