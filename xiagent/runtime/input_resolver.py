from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError


def resolve_node_inputs(
    input_specs: Mapping[str, Any],
    workflow_input: Mapping[str, Any],
    node_outputs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for input_name, input_spec in input_specs.items():
        if not isinstance(input_spec, Mapping):
            raise ValidationError(
                code="invalid_workflow_reference",
                message="Node input spec must be an object",
                details={"input_name": input_name},
            )
        resolved[input_name] = resolve_path(
            input_spec.get("from"),
            workflow_input=workflow_input,
            node_outputs=node_outputs,
        )
    return resolved


def resolve_path(
    reference: Any,
    *,
    workflow_input: Mapping[str, Any],
    node_outputs: Mapping[str, Mapping[str, Any]],
) -> Any:
    if not isinstance(reference, str):
        raise ValidationError(
            code="invalid_workflow_reference",
            message="Workflow reference must be a string",
            details={"reference": reference},
        )

    if reference.startswith("$workflow.input."):
        field_path = reference.removeprefix("$workflow.input.").split(".")
        if not field_path or not field_path[0]:
            _raise_invalid_reference(reference)
        return _resolve_segments(workflow_input, field_path, reference)

    if reference.startswith("$nodes."):
        parts = reference.split(".")
        if len(parts) < 4 or parts[2] != "output" or not parts[1] or not parts[3]:
            _raise_invalid_reference(reference)
        node_id = parts[1]
        if node_id not in node_outputs:
            raise ValidationError(
                code="workflow_reference_missing_node_output",
                message="Node output is not available",
                details={"reference": reference, "node_id": node_id},
            )
        return _resolve_segments(node_outputs[node_id], parts[3:], reference)

    _raise_invalid_reference(reference)


def _resolve_segments(value: Any, segments: list[str], reference: str) -> Any:
    current = value
    for segment in segments:
        if not isinstance(current, Mapping) or segment not in current:
            raise ValidationError(
                code="workflow_reference_missing_key",
                message="Workflow reference path is missing a key",
                details={"reference": reference, "key": segment},
            )
        current = current[segment]
    return current


def _raise_invalid_reference(reference: str) -> None:
    raise ValidationError(
        code="invalid_workflow_reference",
        message="Workflow reference has unsupported format",
        details={"reference": reference},
    )
