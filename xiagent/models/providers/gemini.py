from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openai import AsyncOpenAI

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.models.router import ChatModelProvider
from xiagent.models.types import ChatRequest, ChatResponse, GeminiModelConfig


class GeminiChatProvider(ChatModelProvider):
    def __init__(
        self,
        *,
        config: GeminiModelConfig,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        self._client_factory = client_factory or AsyncOpenAI

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if not self._config.api_key:
            raise ValidationError(
                code="gemini_api_key_missing",
                message="Gemini API key is not configured",
                details={"provider": "gemini"},
            )

        try:
            async with self._client_factory(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
            ) as client:
                response = await client.chat.completions.create(
                    model=request.model,
                    messages=[
                        {"role": message.role, "content": message.content}
                        for message in request.messages
                    ],
                    stream=False,
                )
        except Exception as exc:
            raise ExternalServiceError(
                code="gemini_request_failed",
                message="Gemini request failed",
                details={"provider": "gemini"},
            ) from exc

        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message.content else ""
        usage = response.usage.model_dump() if response.usage else {}
        return ChatResponse(
            text=content,
            model=response.model,
            usage=usage,
            metadata={"provider": "gemini"},
        )
