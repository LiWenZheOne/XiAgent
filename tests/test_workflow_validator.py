from __future__ import annotations

from pathlib import Path

import pytest

from xiagent.core.errors import ConflictError, NotFoundError, ValidationError
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.tools.echo_tool import EchoToolNode
from xiagent.workflows.loader import load_workflow_file
from xiagent.workflows.service import WorkflowCatalog
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
    ]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "workflow_cycle_detected"


def test_start_fanout_is_rejected_for_mvp_runtime() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["edges"] = [
        {"from": "START", "to": "a"},
        {"from": "START", "to": "b"},
        {"from": "a", "to": "END"},
        {"from": "b", "to": "END"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unsupported_workflow_fanout"
    assert exc_info.value.details == {"from": "START"}


def test_node_fanout_is_rejected_for_mvp_runtime() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"].append(
        {"id": "c", "ref": "tool.echo.v1", "inputs": {}, "outputs": _output_schema()}
    )
    contract["edges"] = [
        {"from": "START", "to": "a"},
        {"from": "a", "to": "b"},
        {"from": "a", "to": "c"},
        {"from": "b", "to": "END"},
        {"from": "c", "to": "END"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unsupported_workflow_fanout"
    assert exc_info.value.details == {"from": "a"}


def test_condition_path_referencing_unknown_node_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _valid_contract()
    contract["edges"] = [
        {
            "from": "START",
            "to": "echo",
            "when": {"path": "$nodes.planner.output.approved", "equals": True},
        },
        {"from": "echo", "to": "END"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "invalid_workflow_reference"


def test_edge_condition_requires_path_and_equals_only() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["edges"][1]["when"] = {
        "path": "$nodes.a.output.ok",
        "not_equals": "reject",
    }

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unsupported_workflow_condition"
    assert exc_info.value.details == {"keys": ["not_equals", "path"]}


def test_edge_condition_requires_path_and_equals_keys() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["edges"][1]["when"] = {"path": "$nodes.a.output.ok"}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "invalid_workflow_condition"
    assert exc_info.value.details == {"missing_keys": ["equals"]}


def test_edge_condition_path_can_reference_workflow_input() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["edges"][1]["when"] = {"path": "$workflow.input.topic", "equals": "approve"}

    validate_workflow_contract(contract, registry)


def test_edge_condition_path_referencing_unknown_workflow_input_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["edges"][1]["when"] = {"path": "$workflow.input.missing", "equals": "approve"}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "invalid_workflow_reference"


def test_self_input_reference_is_rejected() -> None:
    registry = _registry()
    contract = _valid_contract()
    contract["nodes"][0]["id"] = "a"
    contract["nodes"][0]["inputs"] = {"value": {"from": "$nodes.a.output.ok"}}
    contract["nodes"][0]["outputs"] = _output_schema()
    contract["edges"] = [{"from": "START", "to": "a"}, {"from": "a", "to": "END"}]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "non_upstream_workflow_reference"


def test_downstream_input_reference_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"][0]["inputs"] = {"value": {"from": "$nodes.b.output.ok"}}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "non_upstream_workflow_reference"


@pytest.mark.parametrize(
    "edge",
    [
        {"from": "END", "to": "a"},
        {"from": "a", "to": "START"},
    ],
)
def test_invalid_start_end_edge_direction_is_rejected(edge: dict[str, str]) -> None:
    registry = _registry()
    contract = _valid_contract()
    contract["nodes"][0]["id"] = "a"
    contract["edges"] = [edge]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "invalid_workflow_edge"


def test_node_output_reference_to_unknown_field_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"][1]["inputs"] = {"value": {"from": "$nodes.a.output.missing"}}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unknown_workflow_output_field"


def test_edge_condition_path_referencing_downstream_node_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["edges"][1]["when"] = {"path": "$nodes.b.output.ok", "equals": "yes"}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "non_upstream_workflow_reference"


def test_edge_condition_path_referencing_unknown_output_field_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["edges"][1]["when"] = {"path": "$nodes.a.output.missing", "equals": "yes"}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unknown_workflow_output_field"


def test_dotted_node_id_is_rejected() -> None:
    registry = _registry()
    contract = _valid_contract()
    contract["nodes"][0]["id"] = "bad.node"

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "invalid_workflow_node_id"


def test_workflow_catalog_rejects_duplicate_workflow_identity(tmp_path) -> None:
    registry = _registry()
    _write_workflow(tmp_path / "one.workflow.yaml", workflow_id="echo")
    _write_workflow(tmp_path / "two.workflow.yaml", workflow_id="echo")
    catalog = WorkflowCatalog(registry)

    with pytest.raises(ConflictError) as exc_info:
        catalog.load_directory(tmp_path)

    assert exc_info.value.code == "workflow_template_exists"


def test_workflow_catalog_get_missing_raises_not_found() -> None:
    catalog = WorkflowCatalog(_registry())

    with pytest.raises(NotFoundError) as exc_info:
        catalog.get("missing")

    assert exc_info.value.code == "workflow_template_not_found"


def test_workflow_catalog_returns_deep_copied_contracts(tmp_path) -> None:
    _write_workflow(tmp_path / "echo.workflow.yaml", workflow_id="echo")
    catalog = WorkflowCatalog(_registry())
    catalog.load_directory(tmp_path)

    contract = catalog.get("echo")
    contract["workflow"]["name"] = "Mutated"
    listed_contract = catalog.list()[0]
    listed_contract["workflow"]["name"] = "Also Mutated"

    assert catalog.get("echo")["workflow"]["name"] == "Echo"


def test_deepseek_echo_workflow_contract_declares_node_outputs() -> None:
    contract = load_workflow_file(Path("workflows/global/deepseek_echo.workflow.yaml"))

    assert contract["workflow"]["id"] == "deepseek_echo"
    chat_node = next(node for node in contract["nodes"] if node["id"] == "chat")
    assert set(chat_node["outputs"]["required"]) == {"text", "model", "usage"}

    registry = NodeRegistry()
    registry.register(
        DeepSeekChatNode(
            api_key=None,
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
        )
    )

    validate_workflow_contract(contract, registry)


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


def _two_node_contract() -> dict:
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
                "id": "a",
                "ref": "tool.echo.v1",
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": _output_schema(),
            },
            {
                "id": "b",
                "ref": "tool.echo.v1",
                "inputs": {"value": {"from": "$nodes.a.output.ok"}},
                "outputs": _output_schema(),
            },
        ],
        "edges": [
            {"from": "START", "to": "a"},
            {"from": "a", "to": "b"},
            {"from": "b", "to": "END"},
        ],
    }


def _output_schema() -> dict:
    return {"type": "object", "properties": {"ok": {"type": "string"}}}


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    return registry


def _write_workflow(path, *, workflow_id: str) -> None:
    path.write_text(
        f"""
workflow:
  id: {workflow_id}
  version: "1.0.0"
  scope: global
  name: Echo
  input_schema:
    type: object
    properties:
      topic:
        type: string
nodes:
  - id: echo
    ref: tool.echo.v1
    inputs:
      topic:
        from: "$workflow.input.topic"
    outputs:
      type: object
      properties:
        ok:
          type: string
edges:
  - from: START
    to: echo
  - from: echo
    to: END
""",
        encoding="utf-8",
    )
