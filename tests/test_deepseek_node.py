from __future__ import annotations

import inspect
from typing import Any

import pytest

from xiagent.core.errors import ValidationError
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode


class FakeUsage:
    def model_dump(self) -> dict[str, int]:
        return {"prompt_tokens": 1, "completion_tokens": 2}


class FakeMessage:
    content = "response text"


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    model = "deepseek-v4-flash"
    usage = FakeUsage()
    choices = [FakeChoice()]


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> FakeResponse:
        self.kwargs = kwargs
        return FakeResponse()


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self) -> None:
        self.chat = FakeChat()
        self.closed = False

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True


async def test_deepseek_node_requires_api_key() -> None:
    node = DeepSeekChatNode(
        api_key=None,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )
    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": "你好"})
    assert exc.value.code == "deepseek_api_key_missing"


async def test_deepseek_node_requires_non_empty_prompt() -> None:
    node = DeepSeekChatNode(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )

    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": " "})

    assert exc.value.code == "deepseek_prompt_required"


def test_deepseek_constructor_requires_keyword_arguments() -> None:
    signature = inspect.signature(DeepSeekChatNode)

    assert signature.parameters["api_key"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["base_url"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["model"].kind is inspect.Parameter.KEYWORD_ONLY
    with pytest.raises(TypeError):
        DeepSeekChatNode("test-key", "https://api.deepseek.com", "deepseek-v4-flash")  # type: ignore[misc]


async def test_deepseek_passes_thinking_via_extra_body_and_closes_client() -> None:
    fake_client = FakeClient()
    captured_factory_kwargs: dict[str, Any] = {}

    def client_factory(**kwargs: Any) -> FakeClient:
        captured_factory_kwargs.update(kwargs)
        return fake_client

    node = DeepSeekChatNode(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        client_factory=client_factory,
    )

    result = await node.run(ctx=None, inputs={"prompt": "hello", "system": "be brief"})

    assert captured_factory_kwargs == {
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
    }
    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["extra_body"] == {
        "thinking": {"type": "disabled"},
    }
    assert "thinking" not in fake_client.chat.completions.kwargs
    assert fake_client.closed is True
    assert result.status == "succeeded"
    assert result.output == {
        "text": "response text",
        "model": "deepseek-v4-flash",
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }


def test_deepseek_descriptor_requires_prompt() -> None:
    node = DeepSeekChatNode(
        api_key=None,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )

    descriptor = node.describe()

    assert descriptor.ref == "ai.deepseek_chat.v1"
    assert descriptor.input_schema["required"] == ["prompt"]
