from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest
from xiagent.nodes.ai.deepseek_structured_json import (
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
        schema = ctx.output_schema if ctx is not None else self.describe().output_schema
        item_schema = schema.get("properties", {}).get("results", {}).get("items", {})
        llm_item_schema = _schema_without_passthrough_fields(item_schema, passthrough_fields)

        async def process_one(item: dict[str, Any]) -> dict[str, Any]:
            prompt_item = _project_item(item, prompt_fields)
            if shared_context:
                prompt_item = {"shared_context": dict(shared_context), **prompt_item}
            item_json = json.dumps(prompt_item, ensure_ascii=False)
            prompt = prompt_template.replace("{item}", item_json)

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
    if field == "full_name" and "name" in source:
        return source["name"]
    return None
