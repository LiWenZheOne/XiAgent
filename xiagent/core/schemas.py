from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from xiagent.core.errors import ValidationError


def validate_json_schema(schema: dict[str, Any]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValidationError(
            code="invalid_json_schema",
            message="JSON Schema 格式无效",
            details={"error": str(exc)},
        ) from exc


def validate_json_value(schema: dict[str, Any], value: Any) -> None:
    validate_json_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: item.path)
    if errors:
        first = errors[0]
        raise ValidationError(
            code="json_value_validation_failed",
            message="数据不满足 JSON Schema",
            details={"path": list(first.path), "error": first.message},
        )


# ── Asset Image Result Schemas ──────────────────────────────────────────────

ASSET_IMAGE_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["full_name", "image_url", "source"],
    "properties": {
        "full_name": {"type": "string", "minLength": 1},
        "image_url": {"type": "string", "minLength": 1},
        "variant": {"type": "string"},
        "asset_id": {"type": "string"},
        "source": {"type": "string", "enum": ["ai_generated", "manual_upload"]},
        "runninghub_task_id": {"type": "string"},
    },
    "additionalProperties": False,
}

ASSET_IMAGE_RESULT_LIST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["asset_images"],
    "properties": {
        "asset_images": {
            "type": "array",
            "items": ASSET_IMAGE_RESULT_SCHEMA,
        },
    },
    "additionalProperties": False,
}
