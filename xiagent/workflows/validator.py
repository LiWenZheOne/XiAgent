from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import NotFoundError, ValidationError
from xiagent.core.schemas import validate_json_schema
from xiagent.nodes.registry import NodeRegistry

_START = "START"
_END = "END"
_REQUIRED_WORKFLOW_KEYS = {"id", "version", "scope", "name", "input_schema"}
_NODE_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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

    node_outputs = _validate_nodes(nodes, registry)
    node_ids = set(node_outputs)
    input_properties = _schema_properties(input_schema)

    edges = contract.get("edges")
    if not isinstance(edges, list):
        _raise_contract_error("Workflow edges must be a list")

    upstream_nodes = _validate_edges(edges, node_ids, input_properties, node_outputs)

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
                node_outputs=node_outputs,
                available_node_refs=upstream_nodes[node["id"]],
            )


def _validate_nodes(nodes: list[Any], registry: NodeRegistry) -> dict[str, dict[str, Any]]:
    node_outputs: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            _raise_contract_error("Workflow node must be an object")

        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            _raise_invalid_node_id(node_id)
        if not _NODE_ID_PATTERN.fullmatch(node_id):
            _raise_invalid_node_id(node_id)
        if node_id in node_outputs:
            raise ValidationError(
                code="duplicate_workflow_node_id",
                message="工作流节点 id 重复",
                details={"node_id": node_id},
            )

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
        node_outputs[node_id] = outputs

    return node_outputs


def _validate_edges(
    edges: list[Any],
    node_ids: set[str],
    workflow_input_properties: set[str] | None,
    node_outputs: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    graph: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    allowed_edge_nodes = node_ids | {_START, _END}
    edge_pairs: list[tuple[str, str]] = []
    outgoing_counts: dict[str, int] = {}

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

        if from_node == _END or to_node == _START or (from_node == _START and to_node == _END):
            raise ValidationError(
                code="invalid_workflow_edge",
                message="工作流 START/END 边方向无效",
                details={"from": from_node, "to": to_node},
            )

        edge_pairs.append((from_node, to_node))
        outgoing_counts[from_node] = outgoing_counts.get(from_node, 0) + 1
        if outgoing_counts[from_node] > 1:
            raise ValidationError(
                code="unsupported_workflow_fanout",
                message="Workflow fan-out is not supported by the MVP runtime",
                details={"from": from_node},
            )
        if from_node not in {_START, _END} and to_node not in {_START, _END}:
            graph[from_node].append(to_node)

    _detect_cycle(graph)
    upstream_nodes = _build_upstream_nodes(graph)

    for edge, (from_node, _to_node) in zip(edges, edge_pairs, strict=True):
        when = edge.get("when")
        if when is not None:
            if not isinstance(when, Mapping):
                raise ValidationError(
                    code="invalid_workflow_condition",
                    message="Workflow edge condition must be an object",
                    details={},
                )
            condition_keys = set(when)
            unsupported_keys = sorted(condition_keys.difference({"path", "equals"}))
            if unsupported_keys:
                raise ValidationError(
                    code="unsupported_workflow_condition",
                    message="Workflow edge condition contains unsupported keys",
                    details={"keys": sorted(condition_keys)},
                )
            missing_keys = sorted({"path", "equals"}.difference(condition_keys))
            if missing_keys:
                raise ValidationError(
                    code="invalid_workflow_condition",
                    message="Workflow edge condition requires path and equals",
                    details={"missing_keys": missing_keys},
                )
            path = when.get("path")
            if not isinstance(path, str):
                raise ValidationError(
                    code="invalid_workflow_condition",
                    message="Workflow edge condition path must be a string",
                    details={"path": path},
                )
            available_node_refs: set[str] = set()
            if from_node not in {_START, _END}:
                available_node_refs = upstream_nodes[from_node] | {from_node}
            _validate_reference(
                path,
                node_ids=node_ids,
                workflow_input_properties=workflow_input_properties,
                node_outputs=node_outputs,
                available_node_refs=available_node_refs,
            )

    return upstream_nodes


def _validate_reference(
    reference: Any,
    *,
    node_ids: set[str],
    workflow_input_properties: set[str] | None,
    node_outputs: dict[str, dict[str, Any]],
    available_node_refs: set[str] | None = None,
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
        if available_node_refs is not None and node_id not in available_node_refs:
            raise ValidationError(
                code="non_upstream_workflow_reference",
                message="工作流引用的节点输出不可用",
                details={"reference": reference, "node_id": node_id},
            )
        _validate_output_field(node_outputs[node_id], parts[3:], reference)
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


def _build_upstream_nodes(graph: dict[str, list[str]]) -> dict[str, set[str]]:
    reverse_graph: dict[str, list[str]] = {node_id: [] for node_id in graph}
    for from_node, to_nodes in graph.items():
        for to_node in to_nodes:
            reverse_graph[to_node].append(from_node)

    upstream_nodes: dict[str, set[str]] = {}
    for node_id in graph:
        upstream_nodes[node_id] = _collect_upstream_nodes(node_id, reverse_graph)
    return upstream_nodes


def _collect_upstream_nodes(node_id: str, reverse_graph: dict[str, list[str]]) -> set[str]:
    upstream: set[str] = set()
    stack = list(reverse_graph[node_id])
    while stack:
        current = stack.pop()
        if current in upstream:
            continue
        upstream.add(current)
        stack.extend(reverse_graph[current])
    return upstream


def _validate_output_field(
    output_schema: dict[str, Any],
    field_path: list[str],
    reference: str,
) -> None:
    schema: Any = output_schema
    for field in field_path:
        if not isinstance(schema, Mapping):
            return
        properties = schema.get("properties")
        if properties is None:
            return
        if not isinstance(properties, Mapping):
            return
        if field not in properties:
            raise ValidationError(
                code="unknown_workflow_output_field",
                message="工作流引用了未知节点输出字段",
                details={"reference": reference, "field": field},
            )
        schema = properties[field]


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


def _raise_invalid_node_id(node_id: Any) -> None:
    raise ValidationError(
        code="invalid_workflow_node_id",
        message="工作流节点 id 格式无效",
        details={"node_id": node_id},
    )
