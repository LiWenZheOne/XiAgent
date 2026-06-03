from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest
from xiagent.nodes.ai.deepseek_structured_json import (
    _json_object_response_metadata,
    _parse_json_object,
    _schema_instruction,
    _system_messages,
)
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class ParallelDeepSeekStructuredJsonNode(BaseNode):
    def __init__(
        self,
        *,
        model_router: ChatModelRouter,
        provider: str,
        model: str,
    ) -> None:
        if not isinstance(model_router, ChatModelRouter):
            raise TypeError("model_router must be ChatModelRouter")
        self._model_router = model_router
        self._provider = provider
        self._model = model

    def describe(self) -> NodeDescriptor:
        return NodeDescriptor(
            ref="ai.parallel_deepseek_structured_json.v1",
            name="Parallel DeepSeek Structured JSON",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "items": {
                        "oneOf": [
                            {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                            {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "array",
                                    "items": {"type": "object"},
                                },
                            },
                        ],
                    },
                    "system": {"type": "string"},
                    "prompt_template": {"type": "string", "minLength": 1},
                    "prompt_fields": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "shared_context": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "passthrough_fields": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "required_input_fields": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "continue_on_item_error": {"type": "boolean"},
                    "max_attempts": {"type": "integer", "minimum": 1},
                },
                "required": ["items", "prompt_template"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["results"],
                "additionalProperties": False,
            },
            description="对数组中每个元素独立并行调用 DeepSeek LLM，隔离上下文。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        items = _normalise_items(inputs.get("items"))
        if not items:
            raise ValidationError(
                code="parallel_llm_items_required",
                message="items must be a non-empty array or an object containing non-empty arrays",
            )

        prompt_template = inputs.get("prompt_template")
        if not isinstance(prompt_template, str) or not prompt_template.strip():
            raise ValidationError(
                code="parallel_llm_template_required",
                message="prompt_template cannot be empty",
            )

        max_attempts = inputs.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValidationError(
                code="parallel_llm_max_attempts_invalid",
                message="max_attempts must be an integer >= 1",
            )

        system = inputs.get("system")
        if not isinstance(system, str) or not system.strip():
            system = None

        shared_context = inputs.get("shared_context")
        if shared_context is None:
            shared_context = {}
        if not isinstance(shared_context, Mapping):
            raise ValidationError(
                code="parallel_llm_shared_context_invalid",
                message="shared_context must be an object",
            )

        prompt_fields = _string_list(inputs.get("prompt_fields"))
        passthrough_fields = _string_list(inputs.get("passthrough_fields"))
        required_input_fields = _string_list(inputs.get("required_input_fields"))
        continue_on_item_error = bool(inputs.get("continue_on_item_error"))
        schema = ctx.output_schema if ctx is not None else self.describe().output_schema
        item_schema = schema.get("properties", {}).get("results", {}).get("items", {})
        llm_item_schema = _schema_without_passthrough_fields(_success_item_schema(item_schema), passthrough_fields)

        async def process_one(item: dict[str, Any]) -> dict[str, Any]:
            if _item_failed(item):
                return _failed_item(item, item.get("error"), passthrough_fields)
            missing_fields = _missing_required_fields(item, required_input_fields)
            if missing_fields:
                error = ValidationError(
                    code="parallel_llm_required_input_missing",
                    message="Required input fields are missing.",
                    details={"missing_fields": missing_fields},
                )
                if continue_on_item_error:
                    return _failed_item(item, error, passthrough_fields)
                raise error

            prompt_item = _project_item(item, prompt_fields)
            if shared_context:
                prompt_item = {"shared_context": dict(shared_context), **prompt_item}
            item_json = json.dumps(prompt_item, ensure_ascii=False)
            prompt = _render_prompt_template(prompt_template, prompt_item, item_json)

            schema_instruction = _schema_instruction(llm_item_schema)
            last_error: ValidationError | None = None
            current_prompt = prompt

            for attempt in range(max_attempts):
                messages = _system_messages(system, schema_instruction)
                messages.append(ChatMessage(role="user", content=current_prompt))

                response = await self._model_router.chat(
                    ChatRequest(
                        provider=self._provider,
                        model=self._model,
                        messages=messages,
                        metadata=_json_object_response_metadata(),
                    )
                )

                try:
                    parsed = _parse_json_object(response.text)
                except (json.JSONDecodeError, ValidationError) as exc:
                    if isinstance(exc, ValidationError):
                        last_error = ValidationError(
                            code=exc.code,
                            message=exc.message,
                            details={"attempt": attempt + 1, "error": exc.details},
                        )
                    else:
                        last_error = ValidationError(
                            code="structured_json_parse_failed",
                            message="DeepSeek response is not valid JSON",
                            details={"attempt": attempt + 1, "error": str(exc)},
                        )
                else:
                    parsed = _without_passthrough_fields(parsed, passthrough_fields)
                    try:
                        validate_json_value(llm_item_schema, parsed)
                    except ValidationError as exc:
                        last_error = ValidationError(
                            code="structured_json_validation_failed",
                            message="DeepSeek JSON response does not match output schema",
                            details={"attempt": attempt + 1, "error": exc.details},
                        )
                    else:
                        return _with_passthrough_fields(parsed, item, passthrough_fields)

                current_prompt = (
                    f"{prompt}\n\n"
                    f"The previous response failed validation: "
                    f"{last_error.message if last_error else 'unknown error'}.\n"
                    f"{schema_instruction}\n"
                    "Return only one valid JSON object. Do not include explanations or Markdown."
                )

            if continue_on_item_error:
                return _failed_item(item, last_error, passthrough_fields)
            if last_error is not None:
                raise last_error
            raise ValidationError(
                code="structured_json_parse_failed",
                message="DeepSeek response is not valid JSON",
            )

        tasks = [process_one(item) for item in items]
        results = await asyncio.gather(*tasks)

        return NodeResult(
            status="succeeded",
            output={"results": list(results)},
        )


def _normalise_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]

    if not isinstance(value, Mapping):
        return []

    ordered_keys = ["characters", "assets", "props"]
    remaining_keys = [key for key in value.keys() if key not in ordered_keys]
    items: list[dict[str, Any]] = []
    for key in [*ordered_keys, *remaining_keys]:
        group = value.get(key)
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict):
                continue
            normalised = dict(item)
            normalised.setdefault("_source_collection", key)
            items.append(normalised)
    return items


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _project_item(item: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    if not fields:
        return item
    return {field: item[field] for field in fields if field in item}


def _render_prompt_template(template: str, prompt_item: Mapping[str, Any], item_json: str) -> str:
    values = _template_values(prompt_item)
    values["item"] = item_json

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            return match.group(0)
        return values[key]

    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}", replace, template)


def _template_values(value: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}

    def visit(prefix: str, current: Any) -> None:
        if isinstance(current, Mapping):
            for key, item in current.items():
                if not isinstance(key, str) or not key:
                    continue
                next_key = f"{prefix}.{key}" if prefix else key
                visit(next_key, item)
                if prefix == "shared_context" and not isinstance(item, Mapping):
                    values.setdefault(key, _template_value(item))
                if prefix.endswith("prompt_rules"):
                    values.setdefault(key, _template_value(item))
            return
        values[prefix] = _template_value(current)

    visit("", value)
    return values


def _template_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _schema_without_passthrough_fields(schema: Any, passthrough_fields: list[str]) -> Any:
    if not isinstance(schema, dict) or not passthrough_fields:
        return schema
    next_schema = dict(schema)
    properties = next_schema.get("properties")
    if isinstance(properties, dict):
        next_schema["properties"] = {
            key: value for key, value in properties.items() if key not in passthrough_fields
        }
    required = next_schema.get("required")
    if isinstance(required, list):
        next_schema["required"] = [
            key for key in required if not (isinstance(key, str) and key in passthrough_fields)
        ]
    return next_schema


def _success_item_schema(schema: Any) -> Any:
    if not isinstance(schema, Mapping):
        return schema
    variants = schema.get("oneOf")
    if not isinstance(variants, list):
        return schema
    for variant in variants:
        if not isinstance(variant, Mapping):
            continue
        required = variant.get("required")
        if isinstance(required, list) and "status" in required and "error" in required:
            continue
        return dict(variant)
    return schema


def _with_passthrough_fields(
    parsed: dict[str, Any],
    source: dict[str, Any],
    passthrough_fields: list[str],
) -> dict[str, Any]:
    if not passthrough_fields:
        return parsed
    result = dict(parsed)
    for field in passthrough_fields:
        inherited = _inherited_field_value(source, field)
        if inherited is not None:
            result[field] = inherited
    return result


def _without_passthrough_fields(
    parsed: dict[str, Any],
    passthrough_fields: list[str],
) -> dict[str, Any]:
    if not passthrough_fields:
        return parsed
    return {key: value for key, value in parsed.items() if key not in passthrough_fields}


def _inherited_field_value(source: dict[str, Any], field: str) -> Any:
    if field in source:
        return source[field]
    return None


def _item_failed(item: Mapping[str, Any]) -> bool:
    return item.get("status") == "failed"


def _missing_required_fields(item: Mapping[str, Any], fields: list[str]) -> list[str]:
    return [field for field in fields if not _field_has_value(item, field)]


def _field_has_value(item: Mapping[str, Any], field: str) -> bool:
    current: Any = item
    for part in field.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    if current is None:
        return False
    if isinstance(current, str):
        return bool(current.strip())
    if isinstance(current, list | dict):
        return bool(current)
    return True


def _failed_item(
    source: dict[str, Any],
    error: Any,
    passthrough_fields: list[str],
) -> dict[str, Any]:
    result = dict(source)
    if passthrough_fields:
        for field in passthrough_fields:
            inherited = _inherited_field_value(source, field)
            if inherited is not None:
                result[field] = inherited
    result["status"] = "failed"
    result["error"] = _error_payload(error)
    return result


def _error_payload(error: Any) -> dict[str, Any]:
    if isinstance(error, ValidationError):
        return {
            "code": error.code,
            "message": error.message,
            "details": dict(error.details),
        }
    if isinstance(error, Mapping):
        code = error.get("code")
        message = error.get("message")
        details = error.get("details")
        return {
            "code": code if isinstance(code, str) and code else "item_failed",
            "message": message if isinstance(message, str) and message else "Item failed in an upstream step.",
            "details": dict(details) if isinstance(details, Mapping) else {},
        }
    return {
        "code": "item_failed",
        "message": str(error) if error else "Item failed in an upstream step.",
        "details": {},
    }
