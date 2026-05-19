from __future__ import annotations

import pytest

from xiagent.core.errors import PermissionDeniedError, ValidationError
from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.migrations import migrate
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.runtime.input_resolver import resolve_node_inputs
from xiagent.runtime.service import SqliteRuntimeService
from xiagent.users.service import SqliteUserService


def _echo_contract() -> dict:
    return {
        "workflow": {
            "id": "echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Echo",
            "input_schema": {
                "type": "object",
                "required": ["topic"],
                "properties": {"topic": {"type": "string"}},
            },
        },
        "nodes": [
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {"type": "object"},
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    }


def _approval_contract() -> dict:
    return {
        "workflow": {
            "id": "approval",
            "version": "1.0.0",
            "scope": "global",
            "name": "Approval",
            "input_schema": {
                "type": "object",
                "required": ["topic"],
                "properties": {"topic": {"type": "string"}},
            },
        },
        "nodes": [
            {
                "id": "review",
                "ref": "system.human_approval.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": {
                    "type": "object",
                    "required": ["decision"],
                    "properties": {"decision": {"type": "string"}},
                },
            },
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"decision": {"from": "$nodes.review.output.decision"}},
                "outputs": {"type": "object"},
            },
        ],
        "edges": [
            {"from": "START", "to": "review"},
            {
                "from": "review",
                "to": "echo",
                "when": {"path": "$nodes.review.output.decision", "equals": "approve"},
            },
            {"from": "echo", "to": "END"},
        ],
    }


async def _runtime(test_settings, registry: NodeRegistry) -> tuple[SqliteRuntimeService, str, str]:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    runtime = SqliteRuntimeService(
        database_path=test_settings.database_path,
        user_service=users,
        node_registry=registry,
    )
    return runtime, user.user_id, project.project_id


async def _workflow_template_count(test_settings) -> int:
    async with connect_db(test_settings.database_path) as db:
        cursor = await db.execute("select count(*) as count from workflow_templates")
        row = await cursor.fetchone()
        await cursor.close()
    return int(row["count"])


async def _list_workflow_templates(test_settings) -> list[dict]:
    async with connect_db(test_settings.database_path) as db:
        cursor = await db.execute(
            """
            select workflow_id, scope, project_id
            from workflow_templates
            order by created_at asc
            """
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return [dict(row) for row in rows]


async def _list_tasks(test_settings) -> list[dict]:
    async with connect_db(test_settings.database_path) as db:
        cursor = await db.execute("select task_id, status from tasks order by created_at asc")
        rows = await cursor.fetchall()
        await cursor.close()
    return [dict(row) for row in rows]


async def test_simple_workflow_task_succeeds(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_echo_contract(),
        input_data={"topic": "测试"},
    )

    assert task.status == "succeeded"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert executions[0].input_snapshot == {"topic": "测试"}
    assert executions[0].output_snapshot == {"echo": {"topic": "测试"}}


async def test_human_node_waits_and_resume_succeeds(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_approval_contract(),
        input_data={"topic": "测试"},
    )
    assert task.status == "waiting"

    resumed = await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="review",
        output={"decision": "approve"},
    )
    assert resumed.status == "succeeded"


async def test_list_events_are_ordered_for_wait_and_resume(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_approval_contract(),
        input_data={"topic": "测试"},
    )
    await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="review",
        output={"decision": "approve"},
    )

    events = await runtime.list_events(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    event_types = [event.event_type for event in events]
    assert event_types == [
        "task_created",
        "task_started",
        "node_started",
        "human_input_requested",
        "task_waiting",
        "task_resumed",
        "node_succeeded",
        "node_started",
        "node_succeeded",
        "task_succeeded",
    ]


async def test_resume_with_invalid_output_keeps_task_waiting(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_approval_contract(),
        input_data={"topic": "测试"},
    )

    with pytest.raises(ValidationError):
        await runtime.resume_task(
            user_id=user_id,
            project_id=project_id,
            task_id=task.task_id,
            node_id="review",
            output={},
        )

    waiting_task = await runtime.get_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert waiting_task.status == "waiting"
    assert executions == [
        execution
        for execution in executions
        if execution.node_id == "review"
        and execution.status == "waiting"
        and execution.output_snapshot == {}
    ]


async def test_resume_preserves_node_output_history(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_approval_contract(),
        input_data={"topic": "测试"},
    )
    await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="review",
        output={"decision": "approve"},
    )

    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    review = [item for item in executions if item.node_id == "review"]
    echo = [item for item in executions if item.node_id == "echo"]
    assert [(item.attempt, item.output_snapshot) for item in review] == [
        (1, {"decision": "approve"})
    ]
    assert [(item.attempt, item.status) for item in echo] == [(1, "succeeded")]


async def test_resume_reject_succeeds_without_echo_execution(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_approval_contract(),
        input_data={"topic": "测试"},
    )
    resumed = await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="review",
        output={"decision": "reject"},
    )

    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert resumed.status == "succeeded"
    assert [item.node_id for item in executions] == ["review"]
    assert resumed.current_view["active_node_outputs"] == {
        "review": executions[0].node_execution_id
    }


async def test_missing_optional_input_reference_fails_persisted_task(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    contract = _echo_contract()
    contract["workflow"]["input_schema"] = {
        "type": "object",
        "properties": {"optional_field": {"type": "string"}},
    }
    contract["nodes"][0]["inputs"] = {"value": {"from": "$workflow.input.optional_field"}}

    with pytest.raises(ValidationError) as exc_info:
        await runtime.create_task_from_contract(
            user_id=user_id,
            project_id=project_id,
            contract=contract,
            input_data={},
        )

    assert exc_info.value.code == "workflow_reference_missing_key"
    tasks = await _list_tasks(test_settings)
    assert len(tasks) == 1
    assert tasks[0]["status"] == "failed"
    events = await runtime.list_events(
        user_id=user_id,
        project_id=project_id,
        task_id=tasks[0]["task_id"],
    )
    assert events[-1].event_type == "task_failed"


async def test_unsupported_condition_operator_fails_before_task_persisted(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    contract = _approval_contract()
    contract["edges"][1]["when"] = {
        "path": "$nodes.review.output.decision",
        "not_equals": "reject",
    }

    with pytest.raises(ValidationError) as exc_info:
        await runtime.create_task_from_contract(
            user_id=user_id,
            project_id=project_id,
            contract=contract,
            input_data={"topic": "condition"},
        )

    assert exc_info.value.code == "unsupported_workflow_condition"
    assert await _list_tasks(test_settings) == []


async def test_project_workflow_contract_project_id_must_match_call_context(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    contract = _echo_contract()
    contract["workflow"]["scope"] = "project"
    contract["workflow"]["project_id"] = "different-project"

    with pytest.raises(ValidationError) as exc_info:
        await runtime.create_task_from_contract(
            user_id=user_id,
            project_id=project_id,
            contract=contract,
            input_data={"topic": "project"},
        )

    assert exc_info.value.code == "workflow_project_mismatch"
    assert await _list_tasks(test_settings) == []


async def test_workflow_template_project_id_uses_call_context(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    project_contract = _echo_contract()
    project_contract["workflow"]["scope"] = "project"
    project_contract["workflow"]["project_id"] = project_id

    project_task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=project_contract,
        input_data={"topic": "project"},
    )
    global_task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_echo_contract(),
        input_data={"topic": "global"},
    )

    assert project_task.status == "succeeded"
    assert global_task.status == "succeeded"
    assert await _list_workflow_templates(test_settings) == [
        {"workflow_id": "echo", "scope": "project", "project_id": project_id},
        {"workflow_id": "echo", "scope": "global", "project_id": None},
    ]


async def test_repeated_resume_does_not_duplicate_downstream_work(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_approval_contract(),
        input_data={"topic": "测试"},
    )
    await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="review",
        output={"decision": "approve"},
    )
    with pytest.raises(ValidationError) as exc_info:
        await runtime.resume_task(
            user_id=user_id,
            project_id=project_id,
            task_id=task.task_id,
            node_id="review",
            output={"decision": "approve"},
        )

    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    events = await runtime.list_events(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    event_types = [event.event_type for event in events]
    node_succeeded_payloads = [
        event.payload for event in events if event.event_type == "node_succeeded"
    ]
    assert exc_info.value.code in {"task_not_waiting", "node_not_waiting"}
    assert [item.node_id for item in executions] == ["review", "echo"]
    assert len([item for item in executions if item.node_id == "echo"]) == 1
    assert event_types.count("task_resumed") == 1
    assert event_types.count("task_succeeded") == 1
    assert event_types.count("node_started") == 2
    assert event_types.count("node_succeeded") == 2
    assert [payload["node_id"] for payload in node_succeeded_payloads] == ["review", "echo"]


async def test_runtime_read_apis_require_project_access(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    owner = await users.create_user(username="alice", password="secret-123")
    owner_project = await users.create_project(owner_user_id=owner.user_id, name="漫画项目A")
    other = await users.create_user(username="bob", password="secret-123")
    other_project = await users.create_project(owner_user_id=other.user_id, name="漫画项目B")
    runtime = SqliteRuntimeService(
        database_path=test_settings.database_path,
        user_service=users,
        node_registry=registry,
    )
    task = await runtime.create_task_from_contract(
        user_id=owner.user_id,
        project_id=owner_project.project_id,
        contract=_echo_contract(),
        input_data={"topic": "测试"},
    )

    with pytest.raises(PermissionDeniedError) as exc_info:
        await runtime.get_task(
            user_id=other.user_id,
            project_id=other_project.project_id,
            task_id=task.task_id,
        )

    assert exc_info.value.code == "project_access_denied"

    with pytest.raises(PermissionDeniedError) as executions_exc_info:
        await runtime.list_node_executions(
            user_id=other.user_id,
            project_id=other_project.project_id,
            task_id=task.task_id,
        )

    assert executions_exc_info.value.code == "project_access_denied"

    with pytest.raises(PermissionDeniedError) as events_exc_info:
        await runtime.list_events(
            user_id=other.user_id,
            project_id=other_project.project_id,
            task_id=task.task_id,
        )

    assert events_exc_info.value.code == "project_access_denied"


async def test_repeated_direct_contract_reuses_workflow_template(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    first = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_echo_contract(),
        input_data={"topic": "测试1"},
    )
    second = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_echo_contract(),
        input_data={"topic": "测试2"},
    )

    assert first.workflow_template_id == second.workflow_template_id
    assert await _workflow_template_count(test_settings) == 1


def test_input_resolver_resolves_nested_node_outputs() -> None:
    resolved = resolve_node_inputs(
        {"title": {"from": "$nodes.plan.output.story.title"}},
        workflow_input={"topic": "测试"},
        node_outputs={"plan": {"story": {"title": "第一章"}}},
    )

    assert resolved == {"title": "第一章"}


def test_input_resolver_missing_path_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_node_inputs(
            {"title": {"from": "$nodes.plan.output.story.title"}},
            workflow_input={"topic": "测试"},
            node_outputs={"plan": {"story": {}}},
        )

    assert exc_info.value.code == "workflow_reference_missing_key"
