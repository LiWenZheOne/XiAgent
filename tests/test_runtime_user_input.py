from __future__ import annotations

from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.infrastructure.migrations import migrate
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
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


@pytest.mark.asyncio
async def test_waiting_interaction_accepts_declared_output_payload_overrides(test_settings) -> None:
    runtime, user_id, project_id = await _runtime(test_settings)
    runtime._node_registry.register(HumanApprovalNode())
    contract = {
        "workflow": {
            "id": "approval-with-editable-output",
            "version": "1.0.0",
            "scope": "global",
            "name": "Approval With Editable Output",
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": "review",
                "ref": "system.human_approval.v1",
                "inputs": {
                    "prompt_results": {"value": [{"full_name": "林冲", "prompt": "原提示词"}]},
                    "decision": {
                        "from_user": True,
                        "schema": {"type": "string", "enum": ["finish", "generate_missing"]},
                    },
                    "asset_images": {
                        "from_user": True,
                        "schema": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["asset_name", "image_url"],
                                "properties": {
                                    "asset_name": {"type": "string"},
                                    "image_url": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                    },
                    "target_asset_key": {"value": ""},
                },
                "outputs": {
                    "type": "object",
                    "required": ["decision", "asset_images"],
                    "properties": {
                        "decision": {"type": "string"},
                        "asset_images": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["asset_name", "image_url"],
                                "properties": {
                                    "asset_name": {"type": "string"},
                                    "image_url": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "prompt_results": {
                            "type": "array",
                            "items": {"type": "object", "additionalProperties": True},
                        },
                        "target_asset_key": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            }
        ],
        "edges": [{"from": "START", "to": "review"}, {"from": "review", "to": "END"}],
    }

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=contract,
        input_data={},
    )

    assert task.status == "waiting"
    resumed = await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="review",
        input={
            "decision": "generate_missing",
            "asset_images": [],
            "prompt_results": [{"full_name": "林冲", "prompt": "编辑后提示词"}],
            "target_asset_key": "林冲",
        },
    )

    assert resumed.status == "succeeded"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert executions[0].output_snapshot["prompt_results"] == [
        {"full_name": "林冲", "prompt": "编辑后提示词"}
    ]
    assert executions[0].output_snapshot["target_asset_key"] == "林冲"


@pytest.mark.asyncio
async def test_waiting_interaction_resume_ignores_unchanged_non_user_draft_fields(test_settings) -> None:
    runtime, user_id, project_id = await _runtime(test_settings)
    runtime._node_registry.register(HumanApprovalNode())
    contract = {
        "workflow": {
            "id": "approval-with-upstream-summary",
            "version": "1.0.0",
            "scope": "global",
            "name": "Approval With Upstream Summary",
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": "review",
                "ref": "system.human_approval.v1",
                "inputs": {
                    "generation_summary": {"value": {"total_asset_count": 3}},
                    "decision": {
                        "from_user": True,
                        "schema": {"type": "string", "enum": ["finish", "generate_missing"]},
                    },
                    "asset_images": {
                        "from_user": True,
                        "schema": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["asset_name", "image_url"],
                                "properties": {
                                    "asset_name": {"type": "string"},
                                    "image_url": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                    },
                },
                "outputs": {
                    "type": "object",
                    "required": ["decision", "asset_images"],
                    "properties": {
                        "decision": {"type": "string"},
                        "asset_images": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["asset_name", "image_url"],
                                "properties": {
                                    "asset_name": {"type": "string"},
                                    "image_url": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                    },
                    "additionalProperties": False,
                },
            }
        ],
        "edges": [{"from": "START", "to": "review"}, {"from": "review", "to": "END"}],
    }

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=contract,
        input_data={},
    )
    await runtime.save_waiting_node_draft(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="review",
        input={
            "decision": "finish",
            "asset_images": [
                {
                    "asset_name": "林冲",
                    "image_url": "https://cdn.example.com/linchong.png",
                    "source": "ai_generated",
                    "generation_summary": {"total_asset_count": 3},
                }
            ],
        },
    )
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert executions[0].input_snapshot["generation_summary"] == {"total_asset_count": 3}
    assert executions[0].input_snapshot["asset_images"][0]["generation_summary"] == {"total_asset_count": 3}

    resumed = await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="review",
        input=dict(executions[0].input_snapshot),
    )

    assert resumed.status == "succeeded"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert executions[0].output_snapshot == {
        "decision": "finish",
        "asset_images": [
            {
                "asset_name": "林冲",
                "image_url": "https://cdn.example.com/linchong.png",
                "source": "ai_generated",
            }
        ],
    }


@pytest.mark.asyncio
async def test_waiting_interaction_rejects_undeclared_extra_payload(test_settings) -> None:
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
            input={"topic": "雨夜城市", "unexpected": True},
        )

    assert exc_info.value.code == "json_value_validation_failed"
    assert exc_info.value.details["node_id"] == "echo"
    assert exc_info.value.details["validation_phase"] == "resume_user_input"
    assert exc_info.value.details["schema_path"] == "input+outputs"
    assert exc_info.value.details["payload_path"] == "$"


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
