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
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "system": {"type": "string"},
                    "prompt_template": {"type": "string", "minLength": 1},
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
        items = inputs.get("items")
        if not isinstance(items, list) or len(items) == 0:
            raise ValidationError(
                code="parallel_llm_items_required",
                message="items must be a non-empty array",
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

        schema = ctx.output_schema if ctx is not None else self.describe().output_schema
        item_schema = schema.get("properties", {}).get("results", {}).get("items", {})

        async def process_one(item: dict[str, Any]) -> dict[str, Any]:
            item_json = json.dumps(item, ensure_ascii=False)
            prompt = prompt_template.replace("{item}", item_json)

            schema_instruction = _schema_instruction(item_schema)
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
                    try:
                        validate_json_value(item_schema, parsed)
                    except ValidationError as exc:
                        last_error = ValidationError(
                            code="structured_json_validation_failed",
                            message="DeepSeek JSON response does not match output schema",
                            details={"attempt": attempt + 1, "error": exc.details},
                        )
                    else:
                        return parsed

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
