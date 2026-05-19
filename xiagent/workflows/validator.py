from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import NotFoundError, ValidationError
from xiagent.core.schemas import validate_json_schema
from xiagent.nodes.registry import NodeRegistry

_START = "START"
_END = "END"
_REQUIRED_WORKFLOW_KEYS = {"id", "version", "scope", "name", "input_schema"}


def validate_workflow_contract(contract: dict[str, Any], registry: NodeRegistry) -> None:
    if not isinstance(contract, dict):
        _raise_contract_error("Workflow contract must be an object")

    workflow = contract.get("workflow")
    if not isinstance(workflow, dict):
        _raise_contract_error("Workflow section must be an object")

    missing_keys = sorted(_REQUIRED_WORKFLOW_KEYS.difference(workflow))
    if missing_keys:
        _raise_contract_error(
            "Workflow section is missing required keys",
            missing_keys=missing_keys,
        )

    scope = workflow["scope"]
    if scope not in {"global", "project"}:
        _raise_contract_error("Workflow scope must be global or project", scope=scope)

    input_schema = workflow["input_schema"]
    _validate_schema_object(input_schema, "workflow.input_schema")

    nodes = contract.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        _raise_contract_error("Workflow nodes must be a non-empty list")

    node_ids = _validate_nodes(nodes, registry)
    input_properties = _schema_properties(input_schema)

    for node in nodes:
        inputs = node.get("inputs", {})
        if not isinstance(inputs, Mapping):
            _raise_invalid_reference("Node inputs must be an object", node_id=node.get("id"))
        for input_name, input_spec in inputs.items():
            if not isinstance(input_spec, Mapping):
                _raise_invalid_reference(
                    "Node input spec must be an object",
                    node_id=node.get("id"),
                    input_name=input_name,
                )
            _validate_reference(
                input_spec.get("from"),
                node_ids=node_ids,
                workflow_input_properties=input_properties,
            )

    edges = contract.get("edges")
    if not isinstance(edges, list):
        _raise_contract_error("Workflow edges must be a list")

    _validate_edges(edges, node_ids, input_properties)


def _validate_nodes(nodes: list[Any], registry: NodeRegistry) -> set[str]:
    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            _raise_contract_error("Workflow node must be an object")

        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            _raise_contract_error("Workflow node id must be a non-empty string")
        if node_id in node_ids:
            raise ValidationError(
                code="duplicate_workflow_node_id",
                message="工作流节点 id 重复",
                details={"node_id": node_id},
            )
        node_ids.add(node_id)

        ref = node.get("ref")
        if not isinstance(ref, str) or not ref:
            _raise_contract_error("Workflow node ref must be a non-empty string", node_id=node_id)
        try:
            registry.get(ref)
        except NotFoundError as exc:
            raise ValidationError(
                code="unknown_workflow_node_ref",
                message="工作流节点 ref 未注册",
                details={"node_id": node_id, "ref": ref},
            ) from exc

        outputs = node.get("outputs")
        _validate_schema_object(outputs, f"nodes.{node_id}.outputs")

    return node_ids


def _validate_edges(
    edges: list[Any],
    node_ids: set[str],
    workflow_input_properties: set[str] | None,
) -> None:
    graph: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    allowed_edge_nodes = node_ids | {_START, _END}

    for edge in edges:
        if not isinstance(edge, dict):
            _raise_contract_error("Workflow edge must be an object")

        from_node = edge.get("from")
        to_node = edge.get("to")
        if from_node not in allowed_edge_nodes or to_node not in allowed_edge_nodes:
            raise ValidationError(
                code="unknown_workflow_edge_node",
                message="工作流边引用了未知节点",
                details={"from": from_node, "to": to_node},
            )

        when = edge.get("when")
        if when is not None:
            if not isinstance(when, Mapping):
                _raise_contract_error("Workflow edge condition must be an object")
            if "path" in when:
                _validate_reference(
                    when.get("path"),
                    node_ids=node_ids,
                    workflow_input_properties=workflow_input_properties,
                )

        if from_node not in {_START, _END} and to_node not in {_START, _END}:
            graph[from_node].append(to_node)

    _detect_cycle(graph)


def _validate_reference(
    reference: Any,
    *,
    node_ids: set[str],
    workflow_input_properties: set[str] | None,
) -> None:
    if not isinstance(reference, str):
        _raise_invalid_reference("Workflow reference must be a string", reference=reference)

    if reference.startswith("$workflow.input."):
        field = reference.removeprefix("$workflow.input.")
        if not field:
            _raise_invalid_reference(
                "Workflow input reference is missing a field",
                reference=reference,
            )
        root_field = field.split(".", 1)[0]
        if workflow_input_properties is not None and root_field not in workflow_input_properties:
            _raise_invalid_reference("Workflow input reference is unknown", reference=reference)
        return

    if reference.startswith("$nodes."):
        parts = reference.split(".")
        if len(parts) < 4 or parts[2] != "output" or not parts[3]:
            _raise_invalid_reference("Node output reference is malformed", reference=reference)
        node_id = parts[1]
        if node_id not in node_ids:
            _raise_invalid_reference("Node output reference is unknown", reference=reference)
        return

    _raise_invalid_reference("Workflow reference has unsupported format", reference=reference)


def _detect_cycle(graph: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValidationError(
                code="workflow_cycle_detected",
                message="工作流节点边存在循环",
                details={"node_id": node_id},
            )
        if node_id in visited:
            return

        visiting.add(node_id)
        for next_node_id in graph[node_id]:
            visit(next_node_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in graph:
        visit(node_id)


def _schema_properties(schema: dict[str, Any]) -> set[str] | None:
    properties = schema.get("properties")
    if properties is None:
        return None
    if not isinstance(properties, Mapping):
        _raise_contract_error("Workflow input_schema.properties must be an object")
    return set(properties)


def _validate_schema_object(schema: Any, location: str) -> None:
    if not isinstance(schema, dict):
        _raise_contract_error("JSON Schema must be an object", location=location)
    validate_json_schema(schema)


def _raise_contract_error(message: str, **details: Any) -> None:
    raise ValidationError(
        code="invalid_workflow_contract",
        message=message,
        details=details,
    )


def _raise_invalid_reference(message: str, **details: Any) -> None:
    raise ValidationError(
        code="invalid_workflow_reference",
        message=message,
        details=details,
    )
