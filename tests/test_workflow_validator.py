from __future__ import annotations

from pathlib import Path

import pytest

from xiagent.core.errors import ConflictError, NotFoundError, ValidationError
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult
from xiagent.nodes.registry import NodeRegistry
from xiagent.nodes.system.human_approval import HumanApprovalNode
from xiagent.nodes.system.user_choice import SystemUserChoiceNode
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


def test_literal_and_template_node_inputs_are_accepted() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    contract = _two_node_contract()
    contract["nodes"][0]["inputs"] = {"question": {"value": "你喜欢什么颜色？"}}
    contract["nodes"][1]["inputs"] = {
        "prompt": {
            "template": "回答：{answer}",
            "vars": {"answer": {"from": "$nodes.a.output.ok"}},
        }
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


def test_start_fanout_parallel_dag_is_accepted_when_branches_converge() -> None:
    registry = _registry()
    contract = _parallel_join_contract()

    validate_workflow_contract(contract, registry)


def test_parallel_branches_can_converge_directly_at_end() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"][1]["inputs"] = {"topic": {"from": "$workflow.input.topic"}}
    contract["edges"] = [
        {"from": "START", "to": "a"},
        {"from": "START", "to": "b"},
        {"from": "a", "to": "END"},
        {"from": "b", "to": "END"},
    ]

    validate_workflow_contract(contract, registry)


def test_node_fanout_parallel_dag_is_accepted_when_branches_converge() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"].append(
        {"id": "c", "ref": "tool.echo.v1", "inputs": {}, "outputs": _output_schema()}
    )
    contract["nodes"].append(
        {
            "id": "join",
            "ref": "tool.echo.v1",
            "inputs": {
                "left": {"from": "$nodes.b.output.ok"},
                "right": {"from": "$nodes.c.output.ok"},
            },
            "outputs": _output_schema(),
        }
    )
    contract["edges"] = [
        {"from": "START", "to": "a"},
        {"from": "a", "to": "b"},
        {"from": "a", "to": "c"},
        {"from": "b", "to": "join"},
        {"from": "c", "to": "join"},
        {"from": "join", "to": "END"},
    ]

    validate_workflow_contract(contract, registry)


def test_start_fanout_branch_without_path_to_end_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"][1]["inputs"] = {"topic": {"from": "$workflow.input.topic"}}
    contract["edges"] = [
        {"from": "START", "to": "a"},
        {"from": "START", "to": "b"},
        {"from": "a", "to": "END"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "workflow_node_not_connected_to_end"
    assert exc_info.value.details == {"node_id": "b"}


def test_join_node_can_reference_all_direct_upstream_outputs() -> None:
    registry = _registry()
    contract = _parallel_join_contract()

    validate_workflow_contract(contract, registry)


def test_parallel_branch_cannot_reference_sibling_output_before_join() -> None:
    registry = _registry()
    contract = _parallel_join_contract()
    branch_a = next(node for node in contract["nodes"] if node["id"] == "a")
    branch_a["inputs"] = {"value": {"from": "$nodes.b.output.ok"}}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "non_upstream_workflow_reference"


def test_join_node_rejects_output_reference_from_non_upstream_branch() -> None:
    registry = _registry()
    contract = _parallel_join_contract()
    contract["nodes"].append(
        {"id": "c", "ref": "tool.echo.v1", "inputs": {}, "outputs": _output_schema()}
    )
    contract["nodes"].append(
        {"id": "final", "ref": "tool.echo.v1", "inputs": {}, "outputs": _output_schema()}
    )
    join = next(node for node in contract["nodes"] if node["id"] == "join")
    join["inputs"]["outside"] = {"from": "$nodes.c.output.ok"}
    contract["edges"] = [
        {"from": "START", "to": "a"},
        {"from": "START", "to": "b"},
        {"from": "START", "to": "c"},
        {"from": "a", "to": "join"},
        {"from": "b", "to": "join"},
        {"from": "c", "to": "final"},
        {"from": "join", "to": "final"},
        {"from": "final", "to": "END"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "non_upstream_workflow_reference"


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


def test_node_output_reference_can_read_field_inside_array_items() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"][0]["outputs"] = _array_output_schema()
    contract["nodes"][1]["inputs"] = {
        "value": {"from": "$nodes.a.output.segments.0.description"}
    }

    validate_workflow_contract(contract, registry)


def test_node_output_reference_to_unknown_array_item_field_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"][0]["outputs"] = _array_output_schema()
    contract["nodes"][1]["inputs"] = {"value": {"from": "$nodes.a.output.segments.0.missing"}}

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unknown_workflow_output_field"


def test_node_output_reference_to_non_numeric_array_item_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["nodes"][0]["outputs"] = _array_output_schema()
    contract["nodes"][1]["inputs"] = {
        "value": {"from": "$nodes.a.output.segments.one.description"}
    }

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unknown_workflow_output_field"


def test_workflow_input_reference_can_read_field_inside_array_items() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["workflow"]["input_schema"] = _array_workflow_input_schema()
    contract["nodes"][0]["inputs"] = {
        "value": {"from": "$workflow.input.segments.0.description"}
    }

    validate_workflow_contract(contract, registry)


def test_workflow_input_reference_to_unknown_array_item_field_is_rejected() -> None:
    registry = _registry()
    contract = _two_node_contract()
    contract["workflow"]["input_schema"] = _array_workflow_input_schema()
    contract["nodes"][0]["inputs"] = {
        "value": {"from": "$workflow.input.segments.0.missing"}
    }

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


class MetadataChoiceProbeNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.metadata_choice_probe.v1",
            name="Metadata Choice Probe",
            version="1.0.0",
            kind="test",
            input_schema={
                "type": "object",
                "properties": {"prompt": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "selected_id": {"type": "string"},
                    "selected_item": {"type": "object"},
                },
                "required": ["selected_id", "selected_item"],
                "additionalProperties": True,
            },
        )

    async def run(self, ctx: NodeContext | None, inputs: dict) -> NodeResult:
        return NodeResult(status="waiting", metadata={"candidates": []})


class BadChoiceInputProbeNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.bad_choice_input_probe.v1",
            name="Bad Choice Input Probe",
            version="1.0.0",
            kind="test",
            input_schema={
                "type": "object",
                "properties": {"candidates": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema={"type": "object", "additionalProperties": True},
        )

    async def run(self, ctx: NodeContext | None, inputs: dict) -> NodeResult:
        return NodeResult(status="waiting")


class PlainChoiceProbeNode(BaseNode):
    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="test.plain_choice_probe.v1",
            name="Plain Choice Probe",
            version="1.0.0",
            kind="test",
            input_schema=SystemUserChoiceNode().describe().input_schema,
            output_schema=SystemUserChoiceNode().describe().output_schema,
        )

    async def run(self, ctx: NodeContext | None, inputs: dict) -> NodeResult:
        return NodeResult(status="waiting")


def test_workflow_node_ui_choice_control_is_accepted() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    registry.register(SystemUserChoiceNode())
    contract = _image_choice_contract()

    validate_workflow_contract(contract, registry)


def test_workflow_node_ui_unknown_control_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    registry.register(SystemUserChoiceNode())
    contract = _image_choice_contract()
    choose_node = next(node for node in contract["nodes"] if node["id"] == "choose_image")
    choose_node["ui"]["controls"]["interaction"]["control_id"] = "ui.missing.v1"

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "unknown_ui_control"


def test_workflow_node_ui_missing_binding_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    registry.register(PlainChoiceProbeNode())
    contract = _image_choice_contract(choice_ref="test.plain_choice_probe.v1")
    choose_node = next(node for node in contract["nodes"] if node["id"] == "choose_image")
    choose_node["ui"]["controls"]["interaction"]["bindings"].pop("image_url_path")

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "missing_ui_binding"


def test_workflow_node_ui_binding_to_non_array_candidates_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    registry.register(BadChoiceInputProbeNode())
    contract = _image_choice_contract(choice_ref="test.bad_choice_input_probe.v1")

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "ui_binding_schema_mismatch"


def test_workflow_node_ui_binding_to_missing_image_field_is_rejected() -> None:
    registry = NodeRegistry()
    registry.register(EchoToolNode())
    registry.register(SystemUserChoiceNode())
    contract = _image_choice_contract()
    choose_node = next(node for node in contract["nodes"] if node["id"] == "choose_image")
    choose_node["ui"]["controls"]["interaction"]["bindings"]["image_url_path"] = "missing_url"

    with pytest.raises(ValidationError) as exc_info:
        validate_workflow_contract(contract, registry)

    assert exc_info.value.code == "ui_binding_schema_mismatch"


def test_workflow_node_ui_can_bind_waiting_metadata_for_compound_node() -> None:
    registry = NodeRegistry()
    registry.register(MetadataChoiceProbeNode())
    contract = {
        "workflow": {
            "id": "compound-choice",
            "version": "1.0.0",
            "scope": "global",
            "name": "Compound Choice",
            "input_schema": {
                "type": "object",
                "properties": {"prompt": {"type": "string"}},
            },
        },
        "nodes": [
            {
                "id": "generate_and_choose",
                "ref": "test.metadata_choice_probe.v1",
                "inputs": {"prompt": {"from": "$workflow.input.prompt"}},
                "outputs": {
                    "type": "object",
                    "required": ["selected_id", "selected_item"],
                    "properties": {
                        "selected_id": {"type": "string"},
                        "selected_item": {"type": "object"},
                    },
                    "additionalProperties": True,
                },
                "ui": {
                    "metadata_schema": _image_candidates_schema(),
                    "controls": {
                        "interaction": {
                            "control_id": "ui.choice.image_three.v1",
                            "variant": "hover_focus",
                            "mode": "interactive",
                            "bindings": {
                                "items_path": "$node.metadata.candidates",
                                "image_url_path": "image_url",
                                "value_path": "id",
                            },
                        }
                    },
                },
            }
        ],
        "edges": [
            {"from": "START", "to": "generate_and_choose"},
            {"from": "generate_and_choose", "to": "END"},
        ],
    }

    validate_workflow_contract(contract, registry)


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
    from xiagent.models import ChatModelRouter

    contract = load_workflow_file(Path("workflows/global/deepseek_echo.workflow.yaml"))

    assert contract["workflow"]["id"] == "deepseek_echo"
    profile_node = next(node for node in contract["nodes"] if node["id"] == "profile")
    assert set(profile_node["outputs"]["required"]) == {"text", "model", "usage"}

    registry = NodeRegistry()
    registry.register(HumanApprovalNode())
    registry.register(
        DeepSeekChatNode(
            model_router=ChatModelRouter(),
            provider="deepseek",
            model="deepseek-v4-flash",
        )
    )

    validate_workflow_contract(contract, registry)


@pytest.mark.parametrize(
    ("workflow_path", "workflow_id", "node_id", "node_ref", "required_inputs"),
    [
        (
            Path("workflows/global/runninghub_text_to_image_test.workflow.yaml"),
            "runninghub_text_to_image_test",
            "generate_image",
            "ai.runninghub_text_to_image.v1",
            {"prompt"},
        ),
        (
            Path("workflows/global/runninghub_image_to_image_test.workflow.yaml"),
            "runninghub_image_to_image_test",
            "transform_image",
            "ai.runninghub_image_to_image.v1",
            {"prompt", "image_urls"},
        ),
    ],
)
def test_runninghub_workflow_contracts_call_registered_nodes(
    test_settings,
    workflow_path: Path,
    workflow_id: str,
    node_id: str,
    node_ref: str,
    required_inputs: set[str],
) -> None:
    from xiagent.nodes import build_node_registry

    contract = load_workflow_file(workflow_path)

    assert contract["workflow"]["id"] == workflow_id
    node = next(item for item in contract["nodes"] if item["id"] == node_id)
    assert node["ref"] == node_ref
    assert required_inputs.issubset(node["inputs"])
    assert set(node["outputs"]["required"]) == {
        "image_url",
        "model",
        "usage",
        "results",
    }

    validate_workflow_contract(contract, build_node_registry(test_settings))


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


def _parallel_join_contract() -> dict:
    return {
        "workflow": {
            "id": "parallel_join",
            "version": "1.0.0",
            "scope": "global",
            "name": "Parallel Join",
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
                "inputs": {"topic": {"from": "$workflow.input.topic"}},
                "outputs": _output_schema(),
            },
            {
                "id": "join",
                "ref": "tool.echo.v1",
                "inputs": {
                    "left": {"from": "$nodes.a.output.ok"},
                    "right": {"from": "$nodes.b.output.ok"},
                },
                "outputs": _output_schema(),
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


def _output_schema() -> dict:
    return {"type": "object", "properties": {"ok": {"type": "string"}}}


def _array_output_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"description": {"type": "string"}},
                },
            }
        },
    }


def _array_workflow_input_schema() -> dict:
    return _array_output_schema()


def _image_candidates_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "image_url": {"type": "string"},
                    },
                    "required": ["id", "image_url"],
                    "additionalProperties": True,
                },
            }
        },
    }


def _image_generation_output_schema() -> dict:
    return {
        "type": "object",
        "required": ["results"],
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "image_url": {"type": "string"},
                    },
                    "required": ["id", "image_url"],
                    "additionalProperties": True,
                },
            }
        },
        "additionalProperties": True,
    }


def _image_choice_contract(*, choice_ref: str = "system.user_choice.v1") -> dict:
    return {
        "workflow": {
            "id": "image-choice",
            "version": "1.0.0",
            "scope": "global",
            "name": "Image Choice",
            "input_schema": {
                "type": "object",
                "properties": {"prompt": {"type": "string"}},
            },
        },
        "nodes": [
            {
                "id": "generate_images",
                "ref": "tool.echo.v1",
                "inputs": {"prompt": {"from": "$workflow.input.prompt"}},
                "outputs": _image_generation_output_schema(),
            },
            {
                "id": "choose_image",
                "ref": choice_ref,
                "inputs": {"candidates": {"from": "$nodes.generate_images.output.results"}},
                "outputs": {
                    "type": "object",
                    "required": ["selected_id", "selected_item"],
                    "properties": {
                        "selected_id": {"type": "string"},
                        "selected_item": {"type": "object"},
                        "selected_image_url": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
                "ui": {
                    "controls": {
                        "interaction": {
                            "control_id": "ui.choice.image_three.v1",
                            "variant": "hover_focus",
                            "mode": "interactive",
                            "bindings": {
                                "items_path": "$node.input.candidates",
                                "image_url_path": "image_url",
                                "value_path": "id",
                            },
                        }
                    }
                },
            },
        ],
        "edges": [
            {"from": "START", "to": "generate_images"},
            {"from": "generate_images", "to": "choose_image"},
            {"from": "choose_image", "to": "END"},
        ],
    }


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
