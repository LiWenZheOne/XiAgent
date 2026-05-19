from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiagent.core.errors import ValidationError
from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest
from xiagent.nodes.base import BaseNode, NodeContext, NodeDescriptor, NodeResult


class DeepSeekChatNode(BaseNode):
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
            ref="ai.deepseek_chat.v1",
            name="DeepSeek Chat",
            version="1.0.0",
            kind="ai",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                    "system": {"type": "string"},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "model": {"type": "string"},
                    "usage": {"type": "object"},
                },
                "required": ["text", "model", "usage"],
                "additionalProperties": False,
            },
            description="Call DeepSeek Chat API to generate a text response.",
        )

    async def run(self, ctx: NodeContext | None, inputs: Mapping[str, Any]) -> NodeResult:
        prompt = inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError(
                code="deepseek_prompt_required",
                message="DeepSeek prompt cannot be empty",
            )

        messages: list[ChatMessage] = []
        system = inputs.get("system")
        if isinstance(system, str) and system.strip():
            messages.append(ChatMessage(role="system", content=system))
        messages.append(ChatMessage(role="user", content=prompt))

        response = await self._model_router.chat(
            ChatRequest(
                provider=self._provider,
                model=self._model,
                messages=messages,
            )
        )
        return NodeResult(
            status="succeeded",
            output={"text": response.text, "model": response.model, "usage": response.usage},
            metadata=response.metadata,
        )
