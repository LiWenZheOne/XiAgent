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
