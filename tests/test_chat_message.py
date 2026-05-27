from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from xiagent.models.providers.deepseek import DeepSeekChatProvider
from xiagent.models.types import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    DeepSeekModelConfig,
)


def test_chat_message_with_string_content() -> None:
    """纯文本 ChatMessage 正常工作."""
    msg = ChatMessage(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert isinstance(msg.content, str)


def test_chat_message_with_multimodal_content() -> None:
    """list 类型 content（多模态）被接受."""
    multimodal: list[dict[str, Any]] = [
        {"type": "text", "text": "hi"},
        {"type": "image_url", "image_url": {"url": "https://x.com/a.png"}},
    ]
    msg = ChatMessage(role="user", content=multimodal)
    assert msg.role == "user"
    assert msg.content == multimodal
    assert isinstance(msg.content, list)


def test_chat_message_multimodal_content_has_correct_structure() -> None:
    """list 中的 type 字段正确."""
    multimodal: list[dict[str, Any]] = [
        {"type": "text", "text": "hi"},
        {"type": "image_url", "image_url": {"url": "https://x.com/a.png"}},
    ]
    msg = ChatMessage(role="user", content=multimodal)
    content = msg.content
    assert isinstance(content, list)
    assert len(content) == 2
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "hi"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"] == {"url": "https://x.com/a.png"}


# ============================================================================
# Edge case: DeepSeek provider with multimodal ChatMessage
# ============================================================================


@pytest.mark.asyncio
async def test_deepseek_provider_handles_multimodal_chatmessage() -> None:
    """构造 multimodal ChatMessage 通过 DeepSeekChatProvider (mock) 发送 → 不崩溃."""

    # ---- mock OpenAI client with async context manager support ----
    mock_completion = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "测试回复"
    mock_completion.choices = [mock_choice]
    mock_completion.model = "deepseek-v4-flash"
    mock_completion.usage = None

    mock_create = AsyncMock(return_value=mock_completion)
    mock_completions = MagicMock()
    mock_completions.create = mock_create
    mock_chat = MagicMock()
    mock_chat.completions = mock_completions

    class _MockClient:
        def __init__(self) -> None:
            self.chat = mock_chat

        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

    # client_factory that returns the mock client (supports async with)
    def _mock_factory(**kwargs: Any) -> _MockClient:
        return _MockClient()

    # ---- construct multimodal ChatMessage ----
    multimodal_content: list[dict[str, Any]] = [
        {"type": "text", "text": "描述这张图片"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
        },
    ]
    messages = [
        ChatMessage(role="system", content="你是图像描述助手"),
        ChatMessage(role="user", content=multimodal_content),
    ]
    request = ChatRequest(
        provider="deepseek",
        model="deepseek-v4-flash",
        messages=messages,
    )

    # ---- configure provider with mock ----
    config = DeepSeekModelConfig(api_key="sk-test-key")
    provider = DeepSeekChatProvider(config=config, client_factory=_mock_factory)

    # ---- verify no crash when content is a list ----
    response = await provider.chat(request)

    assert response.text == "测试回复"
    assert response.model == "deepseek-v4-flash"

    # ---- verify the messages were passed through correctly ----
    call_kwargs = mock_create.call_args.kwargs
    sent_messages = call_kwargs["messages"]
    assert len(sent_messages) == 2
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[0]["content"] == "你是图像描述助手"
    assert sent_messages[1]["role"] == "user"
    # content should be the list (multimodal) — no crash on JSON serialization
    assert isinstance(sent_messages[1]["content"], list)
    assert sent_messages[1]["content"] == multimodal_content
