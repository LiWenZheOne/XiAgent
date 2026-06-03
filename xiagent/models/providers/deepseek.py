from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from openai import AsyncOpenAI

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.infrastructure.api_logging import log_api_request, log_api_response
from xiagent.models.router import ChatModelProvider
from xiagent.models.types import ChatRequest, ChatResponse, DeepSeekModelConfig


class DeepSeekChatProvider(ChatModelProvider):
    def __init__(
        self,
        *,
        config: DeepSeekModelConfig,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        self._client_factory = client_factory or AsyncOpenAI

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if not self._config.api_key:
            raise ValidationError(
                code="deepseek_api_key_missing",
                message="DeepSeek API key is not configured",
                details={"provider": "deepseek"},
            )

        try:
            payload = {
                "model": request.model,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                "stream": False,
                "extra_body": {"thinking": {"type": "disabled"}},
            }
            response_format = request.metadata.get("response_format")
            if _is_json_object_response_format(response_format):
                payload["response_format"] = {"type": "json_object"}
            log_api_request(
                provider="deepseek",
                url=f"{self._config.base_url.rstrip('/')}/chat/completions",
                payload=payload,
            )
            async with self._client_factory(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
            ) as client:
                response = await client.chat.completions.create(**payload)
        except Exception as exc:
            raise ExternalServiceError(
                code="deepseek_request_failed",
                message="DeepSeek request failed",
                details={"provider": "deepseek"},
            ) from exc

        log_api_response(
            provider="deepseek",
            url=f"{self._config.base_url.rstrip('/')}/chat/completions",
            payload=response.model_dump() if hasattr(response, "model_dump") else {"response": response},
        )
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message.content else ""
        usage = response.usage.model_dump() if response.usage else {}
        return ChatResponse(
            text=content,
            model=response.model,
            usage=usage,
            metadata={"provider": "deepseek"},
        )


def _is_json_object_response_format(value: Any) -> bool:
    return isinstance(value, Mapping) and value.get("type") == "json_object"
