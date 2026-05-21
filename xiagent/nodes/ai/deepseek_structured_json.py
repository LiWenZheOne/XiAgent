from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.core.schemas import validate_json_value
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult

_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


class DeepSeekStructuredJsonNode(BaseNode):
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
            ref="ai.deepseek_structured_json.v1",
            name="DeepSeek Structured JSON",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "system": {"type": "string"},
                    "max_attempts": {"type": "integer", "minimum": 1},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "additionalProperties": True,
            },
            description="Call DeepSeek Chat and validate the response as structured JSON.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        prompt = inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError(
                code="structured_json_prompt_required",
                message="Structured JSON prompt cannot be empty",
            )

        max_attempts = inputs.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValidationError(
                code="structured_json_max_attempts_invalid",
                message="max_attempts must be an integer greater than or equal to 1",
            )

        schema = ctx.output_schema if ctx is not None else self.describe().output_schema
        schema_instruction = _schema_instruction(schema)
        last_error: ValidationError | None = None
        current_prompt = prompt

        for attempt in range(max_attempts):
            messages = _system_messages(inputs.get("system"), schema_instruction)
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
            except json.JSONDecodeError as exc:
                last_error = ValidationError(
                    code="structured_json_parse_failed",
                    message="DeepSeek response is not valid JSON",
                    details={"attempt": attempt + 1, "error": str(exc)},
                )
            except ValidationError as exc:
                last_error = ValidationError(
                    code=exc.code,
                    message=exc.message,
                    details={"attempt": attempt + 1, "error": exc.details},
                )
            else:
                try:
                    validate_json_value(schema, parsed)
                except ValidationError as exc:
                    last_error = ValidationError(
                        code="structured_json_validation_failed",
                        message="DeepSeek JSON response does not match output schema",
                        details={"attempt": attempt + 1, "error": exc.details},
                    )
                else:
                    return NodeResult(
                        status="succeeded",
                        output=parsed,
                        metadata=response.metadata,
                    )

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


def _parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    match = _JSON_FENCE_PATTERN.search(candidate)
    if match is not None:
        candidate = match.group(1).strip()
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValidationError(
            code="structured_json_validation_failed",
            message="DeepSeek JSON response must be an object",
            details={"type": type(parsed).__name__},
        )
    return parsed


def _schema_instruction(schema: dict[str, Any]) -> str:
    schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    return f"Target JSON Schema:\n{schema_text}"


def _system_messages(system: Any, schema_instruction: str) -> list[ChatMessage]:
    if isinstance(system, str) and system.strip():
        return [ChatMessage(role="system", content=f"{system.strip()}\n\n{schema_instruction}")]
    return [ChatMessage(role="system", content=schema_instruction)]
