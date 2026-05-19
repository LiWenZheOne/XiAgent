from __future__ import annotations

import pytest

from xiagent.core.errors import ValidationError
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.validator import validate_workflow_contract


def test_valid_workflow_contract_is_accepted() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = {
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
                "outputs": {"type": "object", "properties": {"echo": {"type": "object"}}},
            }
        ],
        "edges": [{"from": "START", "to": "echo"}, {"from": "echo", "to": "END"}],
    }
    validate_workflow_contract(contract, registry)


def test_unknown_node_ref_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    contract = {
        "workflow": {
            "id": "bad",
            "version": "1.0.0",
            "scope": "global",
            "name": "Bad",
            "input_schema": {"type": "object"},
        },
        "nodes": [
            {"id": "missing", "ref": "tool.missing.v1", "inputs": {}, "outputs": {"type": "object"}}
        ],
        "edges": [{"from": "START", "to": "missing"}, {"from": "missing", "to": "END"}],
    }
    with pytest.raises(ValidationError):
        validate_workflow_contract(contract, registry)


def test_duplicate_node_id_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _valid_contract()
    contract["nodes"].append(
        {"id": "echo", "ref": "tool.echo.v1", "inputs": {}, "outputs": {"type": "object"}}
    )

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "duplicate_workflow_node_id"


def test_short_input_reference_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _valid_contract()
    contract["nodes"][0]["inputs"] = {"topic": {"from": "@planner.plan"}}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "invalid_workflow_reference"


def test_edge_to_missing_node_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _valid_contract()
    contract["edges"] = [{"from": "START", "to": "echo"}, {"from": "echo", "to": "missing"}]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unknown_workflow_edge_node"


def test_cycle_in_edges_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _valid_contract()
    contract["nodes"].append(
        {"id": "second", "ref": "tool.echo.v1", "inputs": {}, "outputs": {"type": "object"}}
    )
    contract["edges"] = [
        {"from": "START", "to": "echo"},
        {"from": "echo", "to": "second"},
        {"from": "second", "to": "echo"},
        {"from": "second", "to": "END"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "workflow_cycle_detected"


def test_condition_path_referencing_unknown_node_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _valid_contract()
    contract["edges"] = [
        {"from": "START", "to": "echo", "when": {"path": "$nodes.planner.output.approved"}},
        {"from": "echo", "to": "END"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "invalid_workflow_reference"


def test_load_workflow_file_loads_yaml_object(tmp_path) -> None:
    workflow_path = tmp_path / "echo.workflow.yaml"
    workflow_path.write_text(
        """
workflow:
  id: echo
nodes: []
edges: []
""",
        encoding="utf-8",
    )

    assert load_workflow_file(workflow_path) == {
        "workflow": {"id": "echo"},
        "nodes": [],
        "edges": [],
    }


def test_load_workflow_file_rejects_yaml_list(tmp_path) -> None:
    workflow_path = tmp_path / "bad.workflow.yaml"
    workflow_path.write_text("- workflow\n", encoding="utf-8")

    with pytest.raises(ValueError, match="workflow file must contain object"):
        load_workflow_file(workflow_path)


def _valid_contract() -> dict:
    return {
        "workflow": {
            "id": "echo",
            "version": "1.0.0",
            "scope": "global",
            "name": "Echo",
            "input_schema": {"type": "object", "properties": {"topic": {"type": "string"}}},
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
