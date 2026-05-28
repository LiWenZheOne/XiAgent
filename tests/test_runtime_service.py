from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from xiagent.assets.service import SqliteAssetService
from xiagent.core.errors import PermissionDeniedError, ValidationError
from xiagent.infrastructure.database import connect_db
from xiagent.infrastructure.migrations import migrate
from xiagent.nodes.base import AssetRef, BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.system.user_input import SystemUserInputNode
from xiagent.nodes.system.user_choice import SystemUserChoiceNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.runtime.input_resolver import resolve_node_inputs
from xiagent.runtime.models import TaskRecord
from xiagent.runtime.service import SqliteRuntimeService
from xiagent.users.service import SqliteUserService


def _echo_contract() -> dict:
    return _with_user_input_node({
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
                "inputs": {"topic": {"from": "$nodes.collect_user_input.output.topic"}},
                "outputs": {"type": "object"},
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    })


def _user_input_contract() -> dict:
    input_schema = {
        "type": "object",
        "required": ["topic"],
        "properties": {"topic": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    }
    return {
        "workflow": {
            "id": "workflow-input-echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Node Input Echo",
            "input_schema": input_schema,
        },
        "nodes": [
            {
                "id": "collect_user_input",
                "ref": "system.user_input.v1",
                "inputs": _user_input_specs(input_schema),
                "outputs": input_schema,
                "config": {"title": "填写运行输入"},
            },
            {
                "id": "echo",
                "ref": "tool.echo.v1",
                "inputs": {"topic": {"from": "$nodes.collect_user_input.output.topic"}},
                "outputs": {
                    "type": "object",
                    "required": ["echo"],
                    "properties": {"echo": {"type": "object"}},
                    "additionalProperties": False,
                },
            },
        ],
        "edges": [
            {"from": "START", "to": "collect_user_input"},
            {"from": "collect_user_input", "to": "echo"},
            {"from": "echo", "to": "END"},
        ],
    }


def _approval_contract() -> dict:
    return _with_user_input_node({
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
                "inputs": {"topic": {"from": "$nodes.collect_user_input.output.topic"}},
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
    })


def _user_input_specs(input_schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    if not isinstance(properties, Mapping):
        return {}
    return {
        name: {
            "from_user": True,
            "schema": dict(schema) if isinstance(schema, Mapping) else {},
            "required": name in required,
        }
        for name, schema in properties.items()
        if isinstance(name, str)
    }


def _with_user_input_node(contract: dict[str, Any]) -> dict[str, Any]:
    input_schema = contract["workflow"].get("input_schema", {})
    if not input_schema.get("properties"):
        return contract
    contract["nodes"].append(
        {
            "id": "collect_user_input",
            "ref": "system.user_input.v1",
            "inputs": _user_input_specs(input_schema),
            "outputs": input_schema,
        }
    )
    contract["edges"] = [
        {"from": "START", "to": "collect_user_input"},
        *[
            (
                {"from": "collect_user_input", "to": edge["to"]}
                if edge["from"] == "START"
                else edge
            )
            for edge in contract["edges"]
        ],
    ]
    return contract


def _user_choice_contract() -> dict:
    return {
        "workflow": {
            "id": "user-choice",
            "version": "1.0.0",
            "scope": "global",
            "name": "User Choice",
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": "choose_image",
                "ref": "system.user_choice.v1",
                "inputs": {
                    "question": {"value": "选择一张图"},
                    "candidates": {
                        "value": [
                            {
                                "id": "image-a",
                                "label": "A",
                                "image_url": "https://example.test/a.png",
                            },
                            {
                                "id": "image-b",
                                "label": "B",
                                "image_url": "https://example.test/b.png",
                            },
                            {
                                "id": "image-c",
                                "label": "C",
                                "image_url": "https://example.test/c.png",
                            },
                        ]
                    },
                },
                "outputs": {
                    "type": "object",
                    "required": ["selected_id", "selected_item"],
                    "properties": {
                        "selected_id": {"type": "string"},
                        "selected_index": {"type": "integer", "minimum": 0},
                        "selected_item": {"type": "object"},
                        "selected_image_url": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            }
        ],
        "edges": [
            {"from": "START", "to": "choose_image"},
            {"from": "choose_image", "to": "END"},
        ],
    }


def _parallel_join_contract(*, failing_branch: bool = False) -> dict:
    branch_b_ref = "test.failing_branch_value.v1" if failing_branch else "test.branch_value.v1"
    return {
        "workflow": {
            "id": "parallel-join",
            "version": "1.0.0",
            "scope": "global",
            "name": "Parallel Join",
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": "a",
                "ref": "test.branch_value.v1",
                "inputs": {"value": {"value": "A"}},
                "outputs": _branch_value_output_schema(),
            },
            {
                "id": "b",
                "ref": branch_b_ref,
                "inputs": {"value": {"value": "B"}},
                "outputs": _branch_value_output_schema(),
            },
            {
                "id": "join",
                "ref": "test.join_inputs_probe.v1",
                "inputs": {
                    "left": {"from": "$nodes.a.output.value"},
                    "right": {"from": "$nodes.b.output.value"},
                },
                "outputs": {
                    "type": "object",
                    "required": ["joined"],
                    "properties": {"joined": {"type": "object"}},
                    "additionalProperties": False,
                },
            },
        ],
        "edges": [
            {"from": "START", "to": "a"},
            {"from": "START", "to": "b"},
            {"from": "a", "to": "join"},
            {"from": "b", "to": "join"},
            {"from": "join", "to": "END"},
        ],
    }


def _branch_value_output_schema() -> dict:
    return {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "string"}},
        "additionalProperties": False,
    }


class OutputSchemaProbeNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.output_schema_probe.v1",
            name="Output Schema Probe",
            version="1.0.0",
            kind="test",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "required": ["schema"],
                "properties": {"schema": {"type": "object"}},
                "additionalProperties": False,
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if ctx is None:
            raise AssertionError("runtime must pass node context")
        return NodeResult(status="succeeded", output={"schema": ctx.output_schema})


class AssetServiceProbeNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.asset_service_probe.v1",
            name="Asset Service Probe",
            version="1.0.0",
            kind="test",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "required": ["asset_ids"],
                "properties": {
                    "asset_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "additionalProperties": False,
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        if ctx is None:
            raise AssertionError("runtime must pass node context")
        assert ctx.asset_service is not None
        result = await ctx.asset_service.search_assets(
            user_id=ctx.user_id,
            scope="combined",
            project_id=ctx.project_id,
            keyword="角色",
            limit=10,
            offset=0,
        )
        return NodeResult(
            status="succeeded",
            output={"asset_ids": [item.asset_id for item in result.items]},
        )


class AssetRefsProbeNode(BaseNode):
    def __init__(self, asset_id: str) -> None:
        self._asset_id = asset_id

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.asset_refs_probe.v1",
            name="Asset Refs Probe",
            version="1.0.0",
            kind="test",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
                "additionalProperties": False,
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(
            status="succeeded",
            output={"ok": True},
            asset_refs=[
                AssetRef(
                    asset_id=self._asset_id,
                    usage_type="reference",
                    source="test.asset_refs_probe.v1",
                )
            ],
        )


class BranchValueNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.branch_value.v1",
            name="Branch Value",
            version="1.0.0",
            kind="test",
            input_schema={
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema=_branch_value_output_schema(),
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(status="succeeded", output={"value": inputs["value"]})


class FailingBranchValueNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.failing_branch_value.v1",
            name="Failing Branch Value",
            version="1.0.0",
            kind="test",
            input_schema={
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema=_branch_value_output_schema(),
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        raise ValidationError(
            code="test_branch_failed",
            message="Test branch failed",
            details={"value": inputs["value"]},
        )


class JoinInputsProbeNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.join_inputs_probe.v1",
            name="Join Inputs Probe",
            version="1.0.0",
            kind="test",
            input_schema={
                "type": "object",
                "required": ["left", "right"],
                "properties": {
                    "left": {"type": "string"},
                    "right": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["joined"],
                "properties": {"joined": {"type": "object"}},
                "additionalProperties": False,
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(status="succeeded", output={"joined": dict(inputs)})


class CountingValueNode(BaseNode):
    def __init__(self) -> None:
        self._count = 0

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.counting_value.v1",
            name="Counting Value",
            version="1.0.0",
            kind="test",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        self._count += 1
        return NodeResult(status="succeeded", output={"value": self._count})


class ValueConsumerNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.value_consumer.v1",
            name="Value Consumer",
            version="1.0.0",
            kind="test",
            input_schema={
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["seen"],
                "properties": {"seen": {"type": "integer"}},
                "additionalProperties": False,
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(status="succeeded", output={"seen": inputs["value"]})


def _single_node_contract(*, workflow_id: str, node_id: str, ref: str) -> dict:
    return {
        "workflow": {
            "id": workflow_id,
            "version": "1.0.0",
            "scope": "global",
            "name": workflow_id,
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": node_id,
                "ref": ref,
                "inputs": {},
                "outputs": {"type": "object"},
            }
        ],
        "edges": [{"from": "START", "to": node_id}, {"from": node_id, "to": "END"}],
    }


async def _runtime(test_settings, registry: NodeRegistry) -> tuple[SqliteRuntimeService, str, str]:
    if all(node.describe().ref != "system.user_input.v1" for node in registry.list()):
        registry.register(SystemUserInputNode())
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


async def _create_task_with_user_input(
    runtime: SqliteRuntimeService,
    *,
    user_id: str,
    project_id: str,
    contract: dict[str, Any],
    input_data: dict[str, Any],
) -> TaskRecord:
    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=contract,
        input_data={},
    )
    assert task.status == "waiting"
    return await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="collect_user_input",
        input=input_data,
    )


def _parallel_join_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(BranchValueNode())
    registry.register(FailingBranchValueNode())
    registry.register(JoinInputsProbeNode())
    return registry


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


def _rerun_contract() -> dict:
    return {
        "workflow": {
            "id": "rerun-linear",
            "version": "1.0.0",
            "scope": "global",
            "name": "Rerun Linear",
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": "produce",
                "ref": "test.counting_value.v1",
                "inputs": {},
                "outputs": {
                    "type": "object",
                    "required": ["value"],
                    "properties": {"value": {"type": "integer"}},
                    "additionalProperties": False,
                },
            },
            {
                "id": "consume",
                "ref": "test.value_consumer.v1",
                "inputs": {"value": {"from": "$nodes.produce.output.value"}},
                "outputs": {
                    "type": "object",
                    "required": ["seen"],
                    "properties": {"seen": {"type": "integer"}},
                    "additionalProperties": False,
                },
            },
        ],
        "edges": [
            {"from": "START", "to": "produce"},
            {"from": "produce", "to": "consume"},
            {"from": "consume", "to": "END"},
        ],
    }


async def test_simple_workflow_task_succeeds(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await _create_task_with_user_input(
        runtime,
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
    assert [execution.node_id for execution in executions] == ["collect_user_input", "echo"]
    assert executions[0].output_snapshot == {"topic": "测试"}
    assert executions[1].input_snapshot == {"topic": "测试"}
    assert executions[1].output_snapshot == {"echo": {"topic": "测试"}}


async def test_create_task_without_business_input_waits_on_user_input_node(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(SystemUserInputNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_user_input_contract(),
        input_data={},
    )

    assert task.status == "waiting"
    assert task.input_data == {}
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert [execution.node_id for execution in executions] == ["collect_user_input"]
    assert executions[0].node_ref == "system.user_input.v1"
    assert executions[0].status == "waiting"
    assert executions[0].metadata["input_schema"] == _user_input_contract()["workflow"]["input_schema"]


async def test_create_task_rejects_business_input_when_workflow_has_input_node(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(SystemUserInputNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    with pytest.raises(ValidationError) as exc_info:
        await runtime.create_task_from_contract(
            user_id=user_id,
            project_id=project_id,
            contract=_user_input_contract(),
            input_data={"topic": "不应在创建页提交"},
        )

    assert exc_info.value.code == "task_input_data_not_supported"


async def test_resume_user_input_updates_node_snapshots_and_continues(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(SystemUserInputNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_user_input_contract(),
        input_data={},
    )

    resumed = await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="collect_user_input",
        input={"topic": "统一输入"},
    )

    assert resumed.status == "succeeded"
    assert resumed.input_data == {}
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert [execution.node_id for execution in executions] == ["collect_user_input", "echo"]
    assert executions[0].output_snapshot == {"topic": "统一输入"}
    assert executions[1].input_snapshot == {"topic": "统一输入"}


async def test_parallel_workflow_waits_for_all_branches_before_join(test_settings) -> None:
    registry = _parallel_join_registry()
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_parallel_join_contract(),
        input_data={},
    )

    assert task.status == "succeeded"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert [execution.node_id for execution in executions] == ["a", "b", "join"]
    assert [execution.status for execution in executions] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert executions[0].output_snapshot == {"value": "A"}
    assert executions[1].output_snapshot == {"value": "B"}
    assert executions[2].input_snapshot == {"left": "A", "right": "B"}
    assert executions[2].output_snapshot == {"joined": {"left": "A", "right": "B"}}


async def test_parallel_workflow_can_converge_directly_at_end(test_settings) -> None:
    registry = _parallel_join_registry()
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    contract = _parallel_join_contract()
    contract["nodes"] = [node for node in contract["nodes"] if node["id"] in {"a", "b"}]
    contract["edges"] = [
        {"from": "START", "to": "a"},
        {"from": "START", "to": "b"},
        {"from": "a", "to": "END"},
        {"from": "b", "to": "END"},
    ]

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=contract,
        input_data={},
    )

    assert task.status == "succeeded"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert [execution.node_id for execution in executions] == ["a", "b"]
    assert [execution.output_snapshot for execution in executions] == [
        {"value": "A"},
        {"value": "B"},
    ]


async def test_parallel_workflow_does_not_run_join_after_branch_failure(test_settings) -> None:
    registry = _parallel_join_registry()
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_parallel_join_contract(failing_branch=True),
        input_data={},
    )

    assert task.status == "failed"
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
    assert [execution.node_id for execution in executions] == ["a", "b"]
    assert [execution.status for execution in executions] == ["succeeded", "failed"]
    assert "join" not in {execution.node_id for execution in executions}
    assert [event.event_type for event in events][-2:] == ["node_failed", "task_failed"]


async def test_runtime_passes_declared_output_schema_to_node_context(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(OutputSchemaProbeNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    output_schema = {
        "type": "object",
        "required": ["schema"],
        "properties": {"schema": {"type": "object"}},
        "additionalProperties": False,
    }
    contract = {
        "workflow": {
            "id": "output-schema-probe",
            "version": "1.0.0",
            "scope": "global",
            "name": "Output Schema Probe",
            "input_schema": {"type": "object", "additionalProperties": False},
        },
        "nodes": [
            {
                "id": "probe",
                "ref": "test.output_schema_probe.v1",
                "inputs": {},
                "outputs": output_schema,
            }
        ],
        "edges": [{"from": "START", "to": "probe"}, {"from": "probe", "to": "END"}],
    }

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=contract,
        input_data={},
    )

    assert task.status == "succeeded"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert executions[0].output_snapshot == {"schema": output_schema}


async def test_runtime_injects_asset_service_into_node_context(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        name="角色设定",
        text="主角角色是一名调查记者。",
        metadata={"kind": "character"},
    )
    registry = NodeRegistry()
    registry.register(AssetServiceProbeNode())
    runtime = SqliteRuntimeService(
        database_path=test_settings.database_path,
        user_service=users,
        node_registry=registry,
        asset_service=assets,
    )

    task = await runtime.create_task_from_contract(
        user_id=user.user_id,
        project_id=project.project_id,
        contract=_single_node_contract(
            workflow_id="asset-service-probe",
            node_id="probe",
            ref="test.asset_service_probe.v1",
        ),
        input_data={},
    )

    assert task.status == "succeeded"
    executions = await runtime.list_node_executions(
        user_id=user.user_id,
        project_id=project.project_id,
        task_id=task.task_id,
    )
    assert executions[0].output_snapshot == {"asset_ids": [asset.asset_id]}


async def test_runtime_persists_node_result_asset_refs(test_settings) -> None:
    await migrate(test_settings.database_path)
    users = SqliteUserService(test_settings.database_path)
    user = await users.create_user(username="alice", password="secret-123")
    project = await users.create_project(owner_user_id=user.user_id, name="漫画项目A")
    assets = SqliteAssetService(
        database_path=test_settings.database_path,
        storage_dir=test_settings.asset_storage_dir,
        user_service=users,
    )
    asset = await assets.create_text_asset(
        user_id=user.user_id,
        scope="project",
        project_id=project.project_id,
        name="角色设定",
        text="主角角色是一名调查记者。",
        metadata={"kind": "character"},
    )
    expected_refs = [
        AssetRef(
            asset_id=asset.asset_id,
            usage_type="reference",
            source="test.asset_refs_probe.v1",
        )
    ]
    registry = NodeRegistry()
    registry.register(AssetRefsProbeNode(asset.asset_id))
    runtime = SqliteRuntimeService(
        database_path=test_settings.database_path,
        user_service=users,
        node_registry=registry,
    )

    task = await runtime.create_task_from_contract(
        user_id=user.user_id,
        project_id=project.project_id,
        contract=_single_node_contract(
            workflow_id="asset-refs-probe",
            node_id="probe",
            ref="test.asset_refs_probe.v1",
        ),
        input_data={},
    )

    assert task.status == "succeeded"
    executions = await runtime.list_node_executions(
        user_id=user.user_id,
        project_id=project.project_id,
        task_id=task.task_id,
    )
    assert executions[0].asset_refs == expected_refs


async def test_human_node_waits_and_resume_succeeds(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await _create_task_with_user_input(
        runtime,
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


async def test_user_choice_node_waits_with_candidates_and_resume_succeeds(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(SystemUserChoiceNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_user_choice_contract(),
        input_data={},
    )
    assert task.status == "waiting"
    executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert executions[0].metadata["selection_mode"] == "single"
    assert [item["id"] for item in executions[0].metadata["candidates"]] == [
        "image-a",
        "image-b",
        "image-c",
    ]

    resumed = await runtime.resume_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="choose_image",
        output={
            "selected_id": "image-b",
            "selected_index": 1,
            "selected_item": {
                "id": "image-b",
                "label": "B",
                "image_url": "https://example.test/b.png",
            },
            "selected_image_url": "https://example.test/b.png",
        },
    )

    assert resumed.status == "succeeded"
    resumed_executions = await runtime.list_node_executions(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    assert resumed_executions[0].output_snapshot["selected_id"] == "image-b"


async def test_list_events_are_ordered_for_wait_and_resume(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await _create_task_with_user_input(
        runtime,
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
        "node_waiting",
        "human_input_requested",
        "task_waiting",
        "task_resumed",
        "node_succeeded",
        "node_started",
        "node_waiting",
        "human_input_requested",
        "task_waiting",
        "task_resumed",
        "node_succeeded",
        "node_started",
        "node_succeeded",
        "task_succeeded",
    ]


async def test_rerun_node_creates_new_attempt_and_rebuilds_downstream_current_view(
    test_settings,
) -> None:
    registry = NodeRegistry()
    registry.register(CountingValueNode())
    registry.register(ValueConsumerNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    task = await runtime.create_task_from_contract(
        user_id=user_id,
        project_id=project_id,
        contract=_rerun_contract(),
        input_data={},
    )

    rerun_task = await runtime.rerun_node(
        user_id=user_id,
        project_id=project_id,
        task_id=task.task_id,
        node_id="produce",
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
    attempts_by_node = {
        node_id: [item.attempt for item in executions if item.node_id == node_id]
        for node_id in {"produce", "consume"}
    }
    latest_by_node = {
        node_id: [item for item in executions if item.node_id == node_id][-1]
        for node_id in {"produce", "consume"}
    }

    assert rerun_task.status == "succeeded"
    assert attempts_by_node == {"produce": [1, 2], "consume": [1, 2]}
    assert latest_by_node["produce"].output_snapshot == {"value": 2}
    assert latest_by_node["consume"].input_snapshot == {"value": 2}
    assert latest_by_node["consume"].output_snapshot == {"seen": 2}
    assert rerun_task.current_view["active_node_outputs"] == {
        "produce": latest_by_node["produce"].node_execution_id,
        "consume": latest_by_node["consume"].node_execution_id,
    }
    assert "node_rerun_started" in [event.event_type for event in events]
    assert "downstream_cleared" in [event.event_type for event in events]


async def test_resume_with_invalid_output_keeps_task_waiting(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await _create_task_with_user_input(
        runtime,
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
    waiting_reviews = [
        execution
        for execution in executions
        if execution.node_id == "review"
        and execution.status == "waiting"
        and execution.output_snapshot == {}
    ]
    assert len(waiting_reviews) == 1


async def test_resume_preserves_node_output_history(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await _create_task_with_user_input(
        runtime,
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

    task = await _create_task_with_user_input(
        runtime,
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
    assert [item.node_id for item in executions] == ["collect_user_input", "review"]
    assert resumed.current_view["active_node_outputs"] == {
        "collect_user_input": executions[0].node_execution_id,
        "review": executions[1].node_execution_id,
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
    next(node for node in contract["nodes"] if node["id"] == "collect_user_input")[
        "outputs"
    ] = contract["workflow"]["input_schema"]
    next(node for node in contract["nodes"] if node["id"] == "collect_user_input")[
        "inputs"
    ] = _user_input_specs(contract["workflow"]["input_schema"])
    contract["nodes"][0]["inputs"] = {"value": {"from": "$nodes.collect_user_input.output.optional_field"}}

    with pytest.raises(ValidationError) as exc_info:
        await _create_task_with_user_input(
            runtime,
            user_id=user_id,
            project_id=project_id,
            contract=contract,
            input_data={},
        )

    assert exc_info.value.code == "workflow_reference_missing_key"
    tasks = await _list_tasks(test_settings)
    assert len(tasks) == 1
    assert tasks[0]["status"] == "failed"
    assert exc_info.value.details["task_id"] == tasks[0]["task_id"]
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

    project_task = await _create_task_with_user_input(
        runtime,
        user_id=user_id,
        project_id=project_id,
        contract=project_contract,
        input_data={"topic": "project"},
    )
    global_task = await _create_task_with_user_input(
        runtime,
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


async def test_changed_workflow_contract_creates_new_template_snapshot(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)
    first_contract = _echo_contract()
    second_contract = _echo_contract()
    second_contract["workflow"]["name"] = "Echo Updated"
    second_contract["nodes"][0]["config"] = {"title": "Updated Echo"}

    first_task = await _create_task_with_user_input(
        runtime,
        user_id=user_id,
        project_id=project_id,
        contract=first_contract,
        input_data={"topic": "first"},
    )
    second_task = await _create_task_with_user_input(
        runtime,
        user_id=user_id,
        project_id=project_id,
        contract=second_contract,
        input_data={"topic": "second"},
    )

    first_snapshot = await runtime.get_task_workflow_snapshot(
        user_id=user_id,
        project_id=project_id,
        task_id=first_task.task_id,
    )
    second_snapshot = await runtime.get_task_workflow_snapshot(
        user_id=user_id,
        project_id=project_id,
        task_id=second_task.task_id,
    )

    assert first_snapshot["workflow"]["name"] == "Echo"
    assert second_snapshot["workflow"]["name"] == "Echo Updated"
    assert await _workflow_template_count(test_settings) == 2


async def test_repeated_resume_does_not_duplicate_downstream_work(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(EchoToolNode())
    runtime, user_id, project_id = await _runtime(test_settings, registry)

    task = await _create_task_with_user_input(
        runtime,
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
    assert [item.node_id for item in executions] == ["collect_user_input", "review", "echo"]
    assert len([item for item in executions if item.node_id == "echo"]) == 1
    assert event_types.count("task_resumed") == 2
    assert event_types.count("task_succeeded") == 1
    assert event_types.count("node_started") == 3
    assert event_types.count("node_succeeded") == 3
    assert [payload["node_id"] for payload in node_succeeded_payloads] == [
        "collect_user_input",
        "review",
        "echo",
    ]


async def test_runtime_read_apis_require_project_access(test_settings) -> None:
    registry = NodeRegistry()
    registry.register(SystemUserInputNode())
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
    task = await _create_task_with_user_input(
        runtime,
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

    first = await _create_task_with_user_input(
        runtime,
        user_id=user_id,
        project_id=project_id,
        contract=_echo_contract(),
        input_data={"topic": "测试1"},
    )
    second = await _create_task_with_user_input(
        runtime,
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
        node_outputs={"plan": {"story": {"title": "第一章"}}},
    )

    assert resolved == {"title": "第一章"}


def test_input_resolver_resolves_literal_values_and_templates() -> None:
    resolved = resolve_node_inputs(
        {
            "question": {"value": "你喜欢什么颜色？"},
            "prompt": {
                "template": "颜色：{color}\n食物：{food}",
                "vars": {
                    "color": {"from": "$nodes.color.output.answer"},
                    "food": {"from": "$nodes.food.output.answer"},
                },
            },
        },
        node_outputs={"color": {"answer": "蓝色"}, "food": {"answer": "米饭"}},
    )

    assert resolved == {"question": "你喜欢什么颜色？", "prompt": "颜色：蓝色\n食物：米饭"}


def test_input_resolver_missing_path_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_node_inputs(
            {"title": {"from": "$nodes.plan.output.story.title"}},
            node_outputs={"plan": {"story": {}}},
        )

    assert exc_info.value.code == "workflow_reference_missing_key"
