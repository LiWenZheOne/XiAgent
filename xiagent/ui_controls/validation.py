from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.ui_controls.catalog import UiControlCatalog, build_builtin_ui_control_catalog
from xiagent.ui_controls.models import UiControlBindingRequirement, UiControlVariant

_CONTROL_SLOTS = {"input", "output", "interaction", "detail"}


def merge_ui_configs(*configs: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for config in configs:
        if not config:
            continue
        _deep_merge(merged, config)
    return merged


def validate_node_ui_defaults(
    *,
    node_ref: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    ui_defaults: Mapping[str, Any] | None,
    catalog: UiControlCatalog | None = None,
) -> None:
    if not ui_defaults:
        return
    validate_ui_config(
        ui_defaults,
        catalog=catalog,
        current_input_schema=input_schema,
        current_output_schema=output_schema,
        location=f"nodes.{node_ref}.ui_defaults",
    )


def validate_ui_config(
    ui_config: Mapping[str, Any],
    *,
    catalog: UiControlCatalog | None = None,
    current_input_schema: dict[str, Any] | None = None,
    current_output_schema: dict[str, Any] | None = None,
    current_metadata_schema: dict[str, Any] | None = None,
    node_outputs: Mapping[str, dict[str, Any]] | None = None,
    upstream_node_ids: set[str] | None = None,
    location: str = "ui",
) -> None:
    active_catalog = catalog or build_builtin_ui_control_catalog()
    if not isinstance(ui_config, Mapping):
        _raise("invalid_ui_config", "UI config must be an object", location=location)
    controls = ui_config.get("controls", {})
    if controls in ({}, None):
        return
    if not isinstance(controls, Mapping):
        _raise(
            "invalid_ui_config",
            "UI controls must be an object",
            location=f"{location}.controls",
        )
    unsupported_slots = sorted(set(controls).difference(_CONTROL_SLOTS))
    if unsupported_slots:
        _raise(
            "invalid_ui_config",
            "UI controls contain unsupported slots",
            location=f"{location}.controls",
            slots=unsupported_slots,
        )
    for slot, control_config in controls.items():
        _validate_control_config(
            control_config,
            slot=str(slot),
            catalog=active_catalog,
            current_input_schema=current_input_schema,
            current_output_schema=current_output_schema,
            current_metadata_schema=current_metadata_schema,
            node_outputs=node_outputs or {},
            upstream_node_ids=upstream_node_ids,
            location=f"{location}.controls.{slot}",
        )


def _validate_control_config(
    control_config: Any,
    *,
    slot: str,
    catalog: UiControlCatalog,
    current_input_schema: dict[str, Any] | None,
    current_output_schema: dict[str, Any] | None,
    current_metadata_schema: dict[str, Any] | None,
    node_outputs: Mapping[str, dict[str, Any]],
    upstream_node_ids: set[str] | None,
    location: str,
) -> None:
    if not isinstance(control_config, Mapping):
        _raise("invalid_ui_config", "UI control config must be an object", location=location)
    control_id = control_config.get("control_id")
    if not isinstance(control_id, str) or not control_id:
        _raise("missing_ui_control", "UI control_id is required", location=location)
    try:
        control = catalog.get(control_id)
    except KeyError as exc:
        raise ValidationError(
            code="unknown_ui_control",
            message="UI 控件未注册",
            details={"control_id": control_id, "location": location},
        ) from exc

    variant_name = control_config.get("variant") or control.variants[0].name
    variant = _find_variant(control.variants, str(variant_name), control_id, location)
    mode = control_config.get("mode") or variant.modes[0]
    if mode not in variant.modes:
        _raise(
            "unsupported_ui_control_mode",
            "UI 控件不支持该模式",
            control_id=control_id,
            variant=variant.name,
            mode=mode,
            location=location,
        )
    bindings = control_config.get("bindings", {})
    if not isinstance(bindings, Mapping):
        _raise(
            "invalid_ui_config",
            "UI bindings must be an object",
            location=f"{location}.bindings",
        )

    resolved_item_schema: dict[str, Any] | None = None
    for requirement in variant.required_bindings:
        if requirement.required and requirement.name not in bindings:
            _raise(
                "missing_ui_binding",
                "UI 控件缺少必需 binding",
                control_id=control_id,
                variant=variant.name,
                binding=requirement.name,
                location=location,
            )
        if requirement.name not in bindings:
            continue
        value = bindings[requirement.name]
        if requirement.binding_kind == "schema_path":
            target_schema = _resolve_binding_schema(
                value,
                current_input_schema=current_input_schema,
                current_output_schema=current_output_schema,
                current_metadata_schema=current_metadata_schema,
                node_outputs=node_outputs,
                upstream_node_ids=upstream_node_ids,
                location=f"{location}.bindings.{requirement.name}",
            )
            _validate_schema_constraints(
                target_schema,
                requirement,
                control_id=control_id,
                variant=variant.name,
                location=f"{location}.bindings.{requirement.name}",
            )
            if requirement.schema_constraints.get("type") == "array":
                resolved_item_schema = _array_item_schema(target_schema)
        elif requirement.binding_kind == "item_field":
            if resolved_item_schema is None:
                _raise(
                    "ui_binding_schema_mismatch",
                    "UI item field binding requires an items_path binding first",
                    control_id=control_id,
                    variant=variant.name,
                    binding=requirement.name,
                    location=location,
                )
            binding_location = f"{location}.bindings.{requirement.name}"
            field_schema = _schema_field(resolved_item_schema, value, binding_location)
            _validate_schema_constraints(
                field_schema,
                requirement,
                control_id=control_id,
                variant=variant.name,
                location=binding_location,
            )
        else:
            _raise(
                "invalid_ui_config",
                "UI binding requirement has unsupported binding kind",
                control_id=control_id,
                variant=variant.name,
                binding=requirement.name,
                binding_kind=requirement.binding_kind,
                location=location,
            )

    if (
        slot in {"interaction", "input"}
        and variant.submit_schema is not None
        and current_output_schema is not None
    ):
        _validate_submit_schema_compatible(
            variant.submit_schema,
            current_output_schema,
            control_id=control_id,
            variant=variant.name,
            location=location,
        )


def _find_variant(
    variants: tuple[UiControlVariant, ...],
    variant_name: str,
    control_id: str,
    location: str,
) -> UiControlVariant:
    for variant in variants:
        if variant.name == variant_name:
            return variant
    _raise(
        "unknown_ui_control_variant",
        "UI 控件变体未注册",
        control_id=control_id,
        variant=variant_name,
        location=location,
    )


def _resolve_binding_schema(
    binding: Any,
    *,
    current_input_schema: dict[str, Any] | None,
    current_output_schema: dict[str, Any] | None,
    current_metadata_schema: dict[str, Any] | None,
    node_outputs: Mapping[str, dict[str, Any]],
    upstream_node_ids: set[str] | None,
    location: str,
) -> dict[str, Any]:
    if not isinstance(binding, str) or not binding:
        _raise("invalid_ui_binding_path", "UI binding path must be a string", location=location)
    if binding.startswith("$workflow.input."):
        _raise(
            "invalid_ui_binding_path",
            "Workflow input UI bindings are no longer supported",
            binding=binding,
            location=location,
        )
    if binding.startswith("$node.input."):
        return _schema_at_path(
            current_input_schema,
            binding.removeprefix("$node.input.").split("."),
            binding,
            location,
        )
    if binding.startswith("$node.output."):
        return _schema_at_path(
            current_output_schema,
            binding.removeprefix("$node.output.").split("."),
            binding,
            location,
        )
    if binding.startswith("$node.metadata."):
        return _schema_at_path(
            current_metadata_schema,
            binding.removeprefix("$node.metadata.").split("."),
            binding,
            location,
        )
    if binding.startswith("$nodes."):
        parts = binding.split(".")
        if len(parts) < 4 or parts[2] != "output" or not parts[3]:
            _raise(
                "invalid_ui_binding_path",
                "Node output UI binding path is malformed",
                binding=binding,
            )
        node_id = parts[1]
        if upstream_node_ids is not None and node_id not in upstream_node_ids:
            _raise(
                "invalid_ui_binding_path",
                "UI binding references a non-upstream node",
                binding=binding,
                node_id=node_id,
                location=location,
            )
        if node_id not in node_outputs:
            _raise(
                "invalid_ui_binding_path",
                "UI binding references an unknown node output",
                binding=binding,
                node_id=node_id,
                location=location,
            )
        return _schema_at_path(node_outputs[node_id], parts[3:], binding, location)
    _raise("invalid_ui_binding_path", "UI binding path has unsupported format", binding=binding)


def _schema_at_path(
    schema: dict[str, Any] | None,
    path: list[str],
    binding: str,
    location: str,
) -> dict[str, Any]:
    if schema is None:
        _raise(
            "invalid_ui_binding_path",
            "UI binding source is not available",
            binding=binding,
            location=location,
        )
    current: Any = schema
    for field in path:
        if not field:
            _raise(
                "invalid_ui_binding_path",
                "UI binding path is incomplete",
                binding=binding,
                location=location,
            )
        if not isinstance(current, Mapping):
            _raise(
                "ui_binding_schema_mismatch",
                "UI binding path points into a non-object schema",
                binding=binding,
                field=field,
                location=location,
            )
        if current.get("type") == "array":
            if not field.isdecimal():
                _raise(
                    "ui_binding_schema_mismatch",
                    "UI binding array item path must use a numeric index",
                    binding=binding,
                    field=field,
                    location=location,
                )
            current = current.get("items", {})
            continue
        properties = current.get("properties")
        if not isinstance(properties, Mapping) or field not in properties:
            _raise(
                "invalid_ui_binding_path",
                "UI binding path references an unknown field",
                binding=binding,
                field=field,
                location=location,
            )
        current = properties[field]
    if not isinstance(current, Mapping):
        _raise("ui_binding_schema_mismatch", "UI binding target schema is invalid", binding=binding)
    return dict(current)


def _schema_field(schema: dict[str, Any], field_name: Any, location: str) -> dict[str, Any]:
    if not isinstance(field_name, str) or not field_name:
        _raise(
            "invalid_ui_binding_path",
            "UI item field binding must be a field name",
            location=location,
        )
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or field_name not in properties:
        _raise(
            "ui_binding_schema_mismatch",
            "UI item field binding references an unknown field",
            field=field_name,
            location=location,
        )
    field_schema = properties[field_name]
    if not isinstance(field_schema, Mapping):
        _raise("ui_binding_schema_mismatch", "UI item field schema is invalid", field=field_name)
    return dict(field_schema)


def _array_item_schema(schema: dict[str, Any]) -> dict[str, Any]:
    items = schema.get("items", {})
    return dict(items) if isinstance(items, Mapping) else {}


def _validate_schema_constraints(
    schema: dict[str, Any],
    requirement: UiControlBindingRequirement,
    *,
    control_id: str,
    variant: str,
    location: str,
) -> None:
    expected_type = requirement.schema_constraints.get("type")
    if expected_type is not None and schema.get("type") != expected_type:
        _raise(
            "ui_binding_schema_mismatch",
            "UI binding schema type does not match control requirement",
            control_id=control_id,
            variant=variant,
            binding=requirement.name,
            expected_type=expected_type,
            actual_type=schema.get("type"),
            location=location,
        )
    min_items = requirement.schema_constraints.get("minItems")
    if min_items is not None and schema.get("type") == "array":
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and max_items < min_items:
            _raise(
                "ui_binding_schema_mismatch",
                "UI binding array cannot satisfy minimum item requirement",
                control_id=control_id,
                variant=variant,
                binding=requirement.name,
                min_items=min_items,
                max_items=max_items,
                location=location,
            )


def _validate_submit_schema_compatible(
    submit_schema: dict[str, Any],
    output_schema: dict[str, Any],
    *,
    control_id: str,
    variant: str,
    location: str,
) -> None:
    submit_required = set(submit_schema.get("required", []))
    output_properties = output_schema.get("properties")
    output_required = set(output_schema.get("required", []))
    if not isinstance(output_properties, Mapping):
        return
    missing_required = sorted(
        submit_required.difference(output_properties).difference(output_required)
    )
    if missing_required and output_schema.get("additionalProperties") is not True:
        _raise(
            "ui_control_payload_mismatch",
            "UI control submit payload does not fit node output schema",
            control_id=control_id,
            variant=variant,
            missing_fields=missing_required,
            location=location,
        )


def _deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)  # type: ignore[index]
            continue
        target[key] = deepcopy(value)


def _raise(code: str, message: str, **details: Any) -> None:
    raise ValidationError(code=code, message=message, details=details)
