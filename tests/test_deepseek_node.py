from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from xiagent.core.errors import ExternalServiceError, ValidationError
from xiagent.models import ChatModelRouter
from xiagent.nodes.ai.deepseek_chat import DeepSeekChatNode


class FakeRouter(ChatModelRouter):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []

    async def chat(self, request: Any) -> Any:
        from xiagent.models import ChatResponse

        self.requests.append(request)
        return ChatResponse(
            text="response text",
            model=request.model,
            usage={"prompt_tokens": 1, "completion_tokens": 2},
            metadata={"provider": request.provider},
        )


class FailingRouter(ChatModelRouter):
    def __init__(self) -> None:
        super().__init__()

    async def chat(self, request: Any) -> Any:
        raise ExternalServiceError(
            code="deepseek_request_failed",
            message="DeepSeek request failed",
            details={"provider": request.provider},
        )


def test_deepseek_constructor_requires_router_keyword_arguments() -> None:
    signature = inspect.signature(DeepSeekChatNode)

    assert signature.parameters["model_router"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["provider"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["model"].kind is inspect.Parameter.KEYWORD_ONLY
    assert "api_key" not in signature.parameters
    assert "base_url" not in signature.parameters
    assert "client_factory" not in signature.parameters
    with pytest.raises(TypeError):
        DeepSeekChatNode(FakeRouter(), "deepseek", "deepseek-test-model")  # type: ignore[misc]


def test_deepseek_constructor_rejects_invalid_router() -> None:
    with pytest.raises(TypeError):
        DeepSeekChatNode(
            model_router=object(),  # type: ignore[arg-type]
            provider="deepseek",
            model="deepseek-test-model",
        )


async def test_deepseek_node_converts_inputs_to_chat_request_and_calls_router() -> None:
    from xiagent.models import ChatRequest

    router = FakeRouter()
    node = DeepSeekChatNode(
        model_router=router,
        provider="deepseek",
        model="deepseek-test-model",
    )

    result = await node.run(ctx=None, inputs={"prompt": "hello", "system": "be brief"})

    assert len(router.requests) == 1
    request = router.requests[0]
    assert isinstance(request, ChatRequest)
    assert request.provider == "deepseek"
    assert request.model == "deepseek-test-model"
    assert [(message.role, message.content) for message in request.messages] == [
        ("system", "be brief"),
        ("user", "hello"),
    ]
    assert result.status == "succeeded"
    assert result.output == {
        "text": "response text",
        "model": "deepseek-test-model",
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }
    assert result.metadata == {"provider": "deepseek"}


async def test_deepseek_node_omits_blank_system_message() -> None:
    router = FakeRouter()
    node = DeepSeekChatNode(
        model_router=router,
        provider="deepseek",
        model="deepseek-test-model",
    )

    await node.run(ctx=None, inputs={"prompt": "hello", "system": " "})

    assert [(message.role, message.content) for message in router.requests[0].messages] == [
        ("user", "hello"),
    ]


async def test_deepseek_node_requires_non_empty_prompt() -> None:
    router = FakeRouter()
    node = DeepSeekChatNode(
        model_router=router,
        provider="deepseek",
        model="deepseek-test-model",
    )

    with pytest.raises(ValidationError) as exc:
        await node.run(ctx=None, inputs={"prompt": " "})

    assert exc.value.code == "deepseek_prompt_required"
    assert router.requests == []


async def test_deepseek_node_propagates_router_errors() -> None:
    node = DeepSeekChatNode(
        model_router=FailingRouter(),
        provider="deepseek",
        model="deepseek-test-model",
    )

    with pytest.raises(ExternalServiceError) as exc:
        await node.run(ctx=None, inputs={"prompt": "hello"})

    assert exc.value.code == "deepseek_request_failed"
    assert exc.value.details == {"provider": "deepseek"}


def test_deepseek_descriptor_requires_prompt() -> None:
    node = DeepSeekChatNode(
        model_router=FakeRouter(),
        provider="deepseek",
        model="deepseek-test-model",
    )

    descriptor = node.describe()

    assert descriptor.ref == "ai.deepseek_chat.v1"
    assert descriptor.input_schema["required"] == ["prompt"]
    assert descriptor.output_schema["required"] == ["text", "model", "usage"]


def test_deepseek_node_source_no_longer_imports_openai_sdk() -> None:
    source = Path("xiagent/nodes/ai/deepseek_chat.py").read_text(encoding="utf-8")

    assert "from openai import" not in source
    assert "AsyncOpenAI" not in source
