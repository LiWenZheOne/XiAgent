from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult

_THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_CAPTION_PATTERN = re.compile(r"<caption>(.*?)</caption>", re.DOTALL)


class GeminiVisionNode(BaseNode):
    """Call Gemini Vision model to analyze images with structured think+caption output."""

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
            ref="ai.gemini_vision.v1",
            name="Gemini Vision",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string", "format": "uri"},
                        "minItems": 1,
                    },
                    "system": {"type": "string", "minLength": 1},
                    "max_attempts": {"type": "integer", "minimum": 1},
                },
                "required": ["prompt", "image_urls", "system"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "think": {"type": "string"},
                    "caption": {"type": "string"},
                    "model": {"type": "string"},
                    "usage": {"type": "object"},
                },
            },
            description=(
                "Call Gemini Vision model to analyze images. "
                "The model follows a structured thinking chain and returns "
                "<think> analysis and <caption> description."
            ),
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        # ---- validate prompt ----
        prompt = inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError(
                code="gemini_vision_prompt_empty",
                message="Gemini Vision prompt cannot be empty",
            )

        # ---- validate image_urls ----
        image_urls: list[str] = inputs.get("image_urls", [])
        if not isinstance(image_urls, list) or len(image_urls) == 0:
            raise ValidationError(
                code="gemini_vision_image_urls_empty",
                message="Gemini Vision requires at least one image URL",
            )

        # ---- validate max_attempts ----
        max_attempts = inputs.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValidationError(
                code="gemini_vision_max_attempts_invalid",
                message="max_attempts must be an integer greater than or equal to 1",
            )

        # ---- resolve system prompt ----
        system_text = inputs.get("system")
        if isinstance(system_text, str) and system_text.strip():
            system_prompt = system_text.strip()
        else:
            raise ValidationError(
                code="gemini_vision_system_empty",
                message="Gemini Vision system prompt cannot be empty",
            )

        # ---- attempt loop ----
        last_error: Exception | None = None
        current_prompt = prompt

        for attempt in range(max_attempts):
            content: list[dict[str, Any]] = [{"type": "text", "text": current_prompt}]
            for url in image_urls:
                content.append({"type": "image_url", "image_url": {"url": url}})

            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=content),
            ]

            try:
                response = await self._model_router.chat(
                    ChatRequest(
                        provider=self._provider,
                        model=self._model,
                        messages=messages,
                    )
                )
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"Previous response failed: {exc}.\n"
                        "Please try again and return a valid response with "
                        "<think>...</think> and <caption>...</caption> tags."
                    )
                    continue
                raise

            # ---- extract <think> and <caption> ----
            think_text = ""
            caption_text = ""

            think_match = _THINK_PATTERN.search(response.text)
            if think_match is not None:
                think_text = think_match.group(1).strip()

            caption_match = _CAPTION_PATTERN.search(response.text)
            if caption_match is not None:
                caption_text = caption_match.group(1).strip()
            else:
                # fallback: use the entire response text as caption
                caption_text = response.text.strip()

            return NodeResult(
                status="succeeded",
                output={
                    "think": think_text,
                    "caption": caption_text,
                    "model": response.model,
                    "usage": response.usage,
                },
                metadata=response.metadata,
            )

        # ---- exhausted all attempts ----
        if last_error is not None:
            raise last_error
        raise ValidationError(
            code="gemini_vision_all_attempts_failed",
            message="All Gemini Vision attempts failed",
        )
