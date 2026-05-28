from __future__ import annotations

from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.infrastructure.migrations import migrate
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.runtime.service import SqliteRuntimeService
from xiagent.users.service import SqliteUserService


def _user_input_echo_contract() -> dict[str, Any]:
    return {
        "workflow": {
            "id": "user-input-echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "User Input Echo",
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {
                    "topic": {
                        "from_user": True,
                        "schema": {"type": "string", "minLength": 1},
                    }
                },
                "outputs": {
                    "type": "object",
                    "required": ["echo"],
                    "properties": {"echo": {"type": "object"}},
                    "additionalProperties": False,
                },
                "ui": {
                    "controls": {
                        "input": {
                            "control_id": "ui.input.schema_form.v1",
                            "variant": "default",
                            "mode": "input",
                        }
                    }
                },
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    }


@pytest.mark.asyncio
async def test_node_user_input_waits_then_executes_with_submitted_input(test_settings) -> None:
    runtime, user_id, project_id = await _runtime(test_settings)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_user_input_echo_contract(),
        input_data={},
    )

    assert task.status == "waiting"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert [execution.node_id for execution in executions] == ["echo"]
    assert executions[0].status == "waiting"
    assert executions[0].input_snapshot == {}
    assert executions[0].output_snapshot == {}
    assert executions[0].metadata["input_schema"] == {
        "type": "object",
        "required": ["topic"],
        "properties": {"topic": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    }

    resumed = await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="echo",
        input={"topic": "雨夜城市"},
    )

    assert resumed.status == "succeeded"
    assert resumed.input_data == {}
    resumed_executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert resumed_executions[0].status == "succeeded"
    assert resumed_executions[0].input_snapshot == {"topic": "雨夜城市"}
    assert resumed_executions[0].output_snapshot == {"echo": {"topic": "雨夜城市"}}


@pytest.mark.asyncio
async def test_invalid_node_user_input_keeps_task_waiting(test_settings) -> None:
    runtime, user_id, project_id = await _runtime(test_settings)
    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_user_input_echo_contract(),
        input_data={},
    )

    with pytest.raises(ValidationError) as exc_info:
        await runtime.resume_task(
            user_id=user_id,
            project_id=project_id,
            task_id=task.task_id,
            node_id="echo",
            input={"topic": ""},
        )

    assert exc_info.value.code == "json_value_validation_failed"
    waiting = await runtime.get_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert waiting.status == "waiting"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert executions[0].status == "waiting"
    assert executions[0].input_snapshot == {}
    assert executions[0].output_snapshot == {}


async def _runtime(test_settings) -> tuple[SqliteRuntimeService, str, str]:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime = SqliteRuntimeService(
        database_path=test_settings.database_path,
        user_service=users,
        node_registry=registry,
    )
    return runtime, user.user_id, project.project_id
