from __future__ import annotations

import pytest

from xiagent.core.errors import ValidationError
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
    executions = await runtime.list_node_executions(task_id=task.task_id)
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

    events = await runtime.list_events(task_id=task.task_id)
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

    waiting_task = await runtime.get_task(task.task_id)
    executions = await runtime.list_node_executions(task_id=task.task_id)
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

    executions = await runtime.list_node_executions(task_id=task.task_id)
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

    executions = await runtime.list_node_executions(task_id=task.task_id)
    assert resumed.status == "succeeded"
    assert [item.node_id for item in executions] == ["review"]
    assert resumed.current_view["active_node_outputs"] == {
        "review": executions[0].node_execution_id
    }


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
