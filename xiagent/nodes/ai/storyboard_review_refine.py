from __future__ import annotations

import json
import asyncio
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
)
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class StoryboardReviewRefineNode(BaseNode):
    """审查并有界修订逐段分镜描述。"""

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
            ref="ai.storyboard_review_refine.v1",
            name="Storyboard Review And Refine",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "required": ["items", "review_system", "review_prompt_template", "revision_system", "revision_prompt_template"],
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "storyboard_items": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "shared_context": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "review_system": {"type": "string", "minLength": 1},
                    "review_prompt_template": {"type": "string", "minLength": 1},
                    "revision_system": {"type": "string", "minLength": 1},
                    "revision_prompt_template": {"type": "string", "minLength": 1},
                    "review_output_field": {"type": "string", "minLength": 1},
                    "review_history_output_field": {"type": "string", "minLength": 1},
                    "required_input_fields": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "max_revision_rounds": {"type": "integer", "minimum": 0},
                    "max_attempts": {"type": "integer", "minimum": 1},
                    "continue_on_item_error": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["results"],
                "properties": {
                    "results": {
                        "type": "array",
                        "items": _refined_segment_schema(),
                    },
                },
                "additionalProperties": False,
            },
            description="按工作流提供的审查和修订提示词，对逐项结构化结果进行有限轮次审查修订。",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        items = _object_list(inputs.get("items"))
        if not items:
            raise ValidationError(
                code="storyboard_review_items_required",
                message="items must be a non-empty array",
            )

        items_by_key = _items_by_key(inputs.get("storyboard_items"))
        shared_context = _mapping(inputs.get("shared_context"))
        review_system = _required_text(inputs.get("review_system"), "review_system")
        review_prompt_template = _required_text(inputs.get("review_prompt_template"), "review_prompt_template")
        revision_system = _required_text(inputs.get("revision_system"), "revision_system")
        revision_prompt_template = _required_text(inputs.get("revision_prompt_template"), "revision_prompt_template")
        review_output_field = _text(inputs.get("review_output_field")) or "review"
        review_history_output_field = _text(inputs.get("review_history_output_field")) or "review_history"
        required_input_fields = _string_list(inputs.get("required_input_fields"))
        max_revision_rounds = _int(inputs.get("max_revision_rounds"), 2)
        max_attempts = _int(inputs.get("max_attempts"), 2)
        continue_on_item_error = bool(inputs.get("continue_on_item_error"))
        output_item_schema = _success_item_schema(_output_item_schema(ctx))

        tasks = [
                self._review_and_refine_segment(
                    source=current_item,
                    item=items_by_key.get(_item_key(current_item), {}),
                shared_context=shared_context,
                review_system=review_system,
                review_prompt_template=review_prompt_template,
                revision_system=revision_system,
                revision_prompt_template=revision_prompt_template,
                review_output_field=review_output_field,
                review_history_output_field=review_history_output_field,
                required_input_fields=required_input_fields,
                output_item_schema=output_item_schema,
                max_revision_rounds=max_revision_rounds,
                max_attempts=max_attempts,
                continue_on_item_error=continue_on_item_error,
            )
            for current_item in items
        ]
        results = list(await asyncio.gather(*tasks))

        results.sort(key=lambda item: _item_key(item))
        return NodeResult(status="succeeded", output={"results": results})

    async def _review_and_refine_segment(
        self,
        *,
        source: Mapping[str, Any],
        item: Mapping[str, Any],
        shared_context: Mapping[str, Any],
        review_system: str,
        review_prompt_template: str,
        revision_system: str,
        revision_prompt_template: str,
        review_output_field: str,
        review_history_output_field: str,
        required_input_fields: list[str],
        output_item_schema: dict[str, Any],
        max_revision_rounds: int,
        max_attempts: int,
        continue_on_item_error: bool,
    ) -> dict[str, Any]:
        current = dict(source)
        current.setdefault("index", _int(source.get("index"), 0))
        current.setdefault("segment_title", _text(source.get("segment_title")) or "未命名段落")
        if _item_failed(current):
            return _failed_item(current, current.get("error"))
        missing_fields = _missing_required_fields(current, required_input_fields)
        if missing_fields:
            error = ValidationError(
                code="storyboard_review_required_input_missing",
                message="Required input fields are missing.",
                details={"missing_fields": missing_fields},
            )
            if continue_on_item_error:
                return _failed_item(current, error)
            raise error
        review_history: list[dict[str, Any]] = []

        try:
            for review_round in range(1, max_revision_rounds + 2):
                review = await self._call_structured_json(
                    system=review_system,
                    prompt=_render_template(
                        review_prompt_template,
                        source=current,
                        item=item,
                        shared_context=shared_context,
                        review={},
                    ),
                    schema=_review_schema(),
                    max_attempts=max_attempts,
                )
                review_record = {
                    "round": review_round,
                    "passed": bool(review.get("passed")),
                    "think": _text(review.get("think")),
                    "issues": _string_list(review.get("issues")),
                    "revision_instructions": _text(review.get("revision_instructions")),
                    "revision_summary": _text(review.get("revision_summary")),
                }
                review_history.append(review_record)
                if review_record["passed"] or review_round > max_revision_rounds:
                    return _with_review_fields(
                        current,
                        review_record,
                        review_history,
                        review_output_field=review_output_field,
                        review_history_output_field=review_history_output_field,
                    )

                revision = await self._call_structured_json(
                    system=revision_system,
                    prompt=_render_template(
                        revision_prompt_template,
                        source=current,
                        item=item,
                        shared_context=shared_context,
                        review=review_record,
                    ),
                    schema=_revision_item_schema(output_item_schema),
                    max_attempts=max_attempts,
                )
                current = _merge_revision_fields(current, revision)
        except ValidationError as exc:
            if continue_on_item_error:
                return _failed_item(current, exc)
            raise

        raise ValidationError(
            code="storyboard_review_loop_failed",
            message="review loop ended unexpectedly",
        )

    async def _call_structured_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_attempts: int,
    ) -> dict[str, Any]:
        schema_instruction = _schema_instruction(schema)
        current_prompt = prompt
        last_error: ValidationError | None = None

        for attempt in range(max_attempts):
            response = await self._model_router.chat(
                ChatRequest(
                    provider=self._provider,
                    model=self._model,
                    messages=[
                        ChatMessage(role="system", content=f"{system}\n\n{schema_instruction}"),
                        ChatMessage(role="user", content=current_prompt),
                    ],
                    metadata=_json_object_response_metadata(),
                )
            )
            try:
                parsed = _parse_json_object(response.text)
                validate_json_value(schema, parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc if isinstance(exc, ValidationError) else ValidationError(
                    code="structured_json_parse_failed",
                    message="DeepSeek response is not valid JSON",
                    details={"attempt": attempt + 1, "error": str(exc)},
                )
                current_prompt = (
                    f"{prompt}\n\n"
                    f"上一次返回不符合结构要求：{last_error.message}。\n"
                    "请只返回一个合法 JSON 对象，不要包含 Markdown 或解释文字。"
                )
            else:
                return parsed

        if last_error is not None:
            raise last_error
        raise ValidationError(
            code="structured_json_parse_failed",
            message="DeepSeek response is not valid JSON",
        )


def _review_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["think", "passed", "issues", "revision_instructions", "revision_summary"],
        "properties": {
            "think": {"type": "string"},
            "passed": {"type": "boolean"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "revision_instructions": {"type": "string"},
            "revision_summary": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _revision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["index", "segment_title", "thinking", "description"],
        "properties": {
            "index": {"type": "integer", "minimum": 0},
            "segment_title": {"type": "string", "minLength": 1},
            "thinking": {"type": "string", "minLength": 1},
            "description": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }


def _refined_segment_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "index",
            "segment_title",
            "scene_layout",
            "panel_plan",
            "thinking",
            "description",
            "review",
            "review_history",
        ],
        "properties": {
            "index": {"type": "integer", "minimum": 0},
            "segment_title": {"type": "string", "minLength": 1},
            "scene_layout": {"type": "object", "additionalProperties": True},
            "panel_plan": {"type": "object", "additionalProperties": True},
            "thinking": {"type": "string", "minLength": 1},
            "description": {"type": "string", "minLength": 1},
            "review": {
                "type": "object",
                "required": ["passed", "rounds", "issues", "revision_summary"],
                "properties": {
                    "passed": {"type": "boolean"},
                    "rounds": {"type": "integer", "minimum": 1},
                    "think": {"type": "string"},
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "revision_summary": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "review_history": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "round",
                        "passed",
                        "think",
                        "issues",
                        "revision_instructions",
                        "revision_summary",
                    ],
                    "properties": {
                        "round": {"type": "integer", "minimum": 1},
                        "passed": {"type": "boolean"},
                        "think": {"type": "string"},
                        "issues": {"type": "array", "items": {"type": "string"}},
                        "revision_instructions": {"type": "string"},
                        "revision_summary": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "status": {"type": "string"},
            "error": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": True,
    }


def _items_by_key(value: Any) -> dict[tuple[int, int], Mapping[str, Any]]:
    result: dict[tuple[int, int], Mapping[str, Any]] = {}
    for item in _object_list(value):
        if isinstance(item.get("index"), int) and not isinstance(item.get("index"), bool):
            result[_item_key(item)] = item
    return result


def _item_key(item: Mapping[str, Any]) -> tuple[int, int]:
    return (
        _int(item.get("index"), 0),
        _int(item.get("prompt_variant_index"), 0),
    )


def _render_template(
    template: str,
    *,
    source: Mapping[str, Any],
    item: Mapping[str, Any],
    shared_context: Mapping[str, Any],
    review: Mapping[str, Any],
) -> str:
    values = _template_values(
        {
            "source": source,
            "item": item,
            "shared_context": shared_context,
            "review": review,
        }
    )

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}", replace, template)


def _template_values(value: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}

    def visit(prefix: str, current: Any) -> None:
        values[prefix] = _template_value(current)
        if not isinstance(current, Mapping):
            return
        for key, item in current.items():
            if isinstance(key, str) and key:
                visit(f"{prefix}.{key}" if prefix else key, item)

    visit("", value)
    return values


def _output_item_schema(ctx: NodeContext | None) -> dict[str, Any]:
    if ctx is None:
        return {"type": "object", "additionalProperties": True}
    schema = ctx.output_schema
    results = schema.get("properties", {}).get("results") if isinstance(schema, Mapping) else None
    item_schema = results.get("items") if isinstance(results, Mapping) else None
    return dict(item_schema) if isinstance(item_schema, Mapping) else {"type": "object", "additionalProperties": True}


def _success_item_schema(schema: dict[str, Any]) -> dict[str, Any]:
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


def _revision_item_schema(schema: dict[str, Any]) -> dict[str, Any]:
    review_fields = {"review", "review_history", "prompt_review", "prompt_review_history"}
    result = dict(schema)
    properties = result.get("properties")
    if isinstance(properties, Mapping):
        excluded_fields = review_fields | _INHERITED_IDENTITY_FIELDS
        result["properties"] = {key: value for key, value in properties.items() if key not in excluded_fields}
    required = result.get("required")
    if isinstance(required, list):
        result["required"] = []
    return result


_INHERITED_IDENTITY_FIELDS = {
    "index",
    "segment_title",
    "paragraph_text",
    "panel_count",
    "present_characters",
    "location",
    "key_props",
    "segment_assignment",
}


def _merge_revision_fields(current: Mapping[str, Any], revision: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(current)
    for key, value in revision.items():
        if key in _INHERITED_IDENTITY_FIELDS:
            continue
        result[key] = value
    return result


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


def _failed_item(current: Mapping[str, Any], error: Any) -> dict[str, Any]:
    result = dict(current)
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


def _with_review_fields(
    current: Mapping[str, Any],
    review_record: Mapping[str, Any],
    review_history: list[dict[str, Any]],
    *,
    review_output_field: str,
    review_history_output_field: str,
) -> dict[str, Any]:
    result = dict(current)
    summary = {
        "passed": bool(review_record.get("passed")),
        "rounds": len(review_history),
        "think": _text(review_record.get("think")),
        "issues": _string_list(review_record.get("issues")),
        "revision_summary": _text(review_record.get("revision_summary")),
    }
    result[review_output_field] = summary
    result[review_history_output_field] = review_history
    return result


def _template_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _object_list(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _list(value) if isinstance(item, Mapping)]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _required_text(value: Any, field: str) -> str:
    text = _text(value)
    if text:
        return text
    raise ValidationError(
        code="storyboard_review_prompt_required",
        message=f"{field} cannot be empty",
    )


def _int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback
