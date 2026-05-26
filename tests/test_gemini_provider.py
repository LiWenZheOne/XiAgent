from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.models.providers.gemini import GeminiChatProvider
from xiagent.models.types import ChatMessage, ChatRequest, GeminiModelConfig


def _make_request(
    *,
    messages: list[ChatMessage] | None = None,
    provider: str = "gemini",
    model: str = "gemini-3-flash-preview",
) -> ChatRequest:
    if messages is None:
        messages = [ChatMessage(role="user", content="hello")]
    return ChatRequest(provider=provider, model=model, messages=messages)


# ---------------------------------------------------------------------------
# Test 1: api_key 为空时必须抛出 ValidationError
# ---------------------------------------------------------------------------
async def test_gemini_provider_requires_api_key() -> None:
    config = GeminiModelConfig(api_key=None)
    provider = GeminiChatProvider(config=config)

    with pytest.raises(ValidationError) as exc_info:
        await provider.chat(_make_request())

    assert exc_info.value.code == "gemini_api_key_missing"


# ---------------------------------------------------------------------------
# Test 2: multimodal ChatMessage 的 content 被正确传递给 API
# ---------------------------------------------------------------------------
async def test_gemini_provider_sends_multimodal_messages() -> None:
    mock_create = AsyncMock()
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="response text"))],
        model="gemini-3-flash-preview",
        usage=MagicMock(model_dump=MagicMock(return_value={"prompt_tokens": 10, "completion_tokens": 5})),
    )

    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = mock_create
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client_factory: Callable[..., Any] = MagicMock(return_value=mock_client)

    config = GeminiModelConfig(api_key="test-key")
    provider = GeminiChatProvider(config=config, client_factory=client_factory)

    multimodal_content: list[dict[str, Any]] = [
        {"type": "text", "text": "Describe this image"},
        {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
    ]
    request = _make_request(
        messages=[ChatMessage(role="user", content=multimodal_content)],
    )

    response = await provider.chat(request)

    # 验证 client factory 使用正确的参数调用
    client_factory.assert_called_once_with(api_key="test-key", base_url=config.base_url)

    # 验证 messages 的多模态 content 被透传
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == request.model
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"
    assert call_kwargs["messages"][0]["content"] == multimodal_content
    assert call_kwargs["stream"] is False

    assert response.text == "response text"
    assert response.model == "gemini-3-flash-preview"


# ---------------------------------------------------------------------------
# Test 3: API 异常时抛出 ExternalServiceError
# ---------------------------------------------------------------------------
async def test_gemini_provider_handles_api_error() -> None:
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("API connection refused")
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    client_factory: Callable[..., Any] = MagicMock(return_value=mock_client)

    config = GeminiModelConfig(api_key="test-key")
    provider = GeminiChatProvider(config=config, client_factory=client_factory)

    with pytest.raises(ExternalServiceError) as exc_info:
        await provider.chat(_make_request())

    assert exc_info.value.code == "gemini_request_failed"


# ---------------------------------------------------------------------------
# Test 4: client_factory 参数注入后使用 mock client
# ---------------------------------------------------------------------------
async def test_gemini_provider_client_factory_injection() -> None:
    """验证自定义 client_factory 被正确存储并使用，而不是默认的 AsyncOpenAI。"""
    mock_create = AsyncMock()
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="injected client response"))],
        model="gemini-3-flash-preview",
        usage=MagicMock(model_dump=MagicMock(return_value={})),
    )

    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = mock_create
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    custom_factory: Callable[..., Any] = MagicMock(return_value=mock_client)

    config = GeminiModelConfig(api_key="injected-key")
    provider = GeminiChatProvider(config=config, client_factory=custom_factory)

    response = await provider.chat(_make_request())

    custom_factory.assert_called_once_with(
        api_key="injected-key", base_url=config.base_url
    )
    assert response.text == "injected client response"
