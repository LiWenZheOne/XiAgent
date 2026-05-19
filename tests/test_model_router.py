from __future__ import annotations

from typing import Any

import pytest

from xiagent.core.errors import ExternalServiceError, NotFoundError
from xiagent.models import ChatModelProvider


class RecordingProvider(ChatModelProvider):
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def chat(self, request: Any) -> Any:
        from xiagent.models import ChatResponse

        self.requests.append(request)
        return ChatResponse(
            text="fake response",
            model=request.model,
            usage={"prompt_tokens": 1, "completion_tokens": 2},
            metadata={"provider": request.provider},
        )


class FakeUsage:
    def model_dump(self) -> dict[str, int]:
        return {"prompt_tokens": 3, "completion_tokens": 5}


class FakeMessage:
    content = "deepseek response"


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    model = "deepseek-test-model"
    usage = FakeUsage()
    choices = [FakeChoice()]


class FakeCompletions:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> FakeResponse:
        self.kwargs = kwargs
        if self.should_fail:
            raise RuntimeError("upstream unavailable")
        return FakeResponse()


class FakeChat:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.completions = FakeCompletions(should_fail=should_fail)


class FakeClient:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.chat = FakeChat(should_fail=should_fail)
        self.closed = False

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True


async def test_chat_model_router_registers_provider_and_routes_chat() -> None:
    from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest

    provider = RecordingProvider()
    router = ChatModelRouter()
    router.register_provider("fake", provider)
    request = ChatRequest(
        provider="fake",
        model="fake-model",
        messages=[ChatMessage(role="user", content="hello")],
    )

    response = await router.chat(request)

    assert provider.requests == [request]
    assert response.text == "fake response"
    assert response.model == "fake-model"
    assert response.usage == {"prompt_tokens": 1, "completion_tokens": 2}
    assert response.metadata == {"provider": "fake"}


async def test_chat_model_router_rejects_unknown_provider() -> None:
    from xiagent.models import ChatMessage, ChatModelRouter, ChatRequest

    router = ChatModelRouter()
    request = ChatRequest(
        provider="missing",
        model="fake-model",
        messages=[ChatMessage(role="user", content="hello")],
    )

    with pytest.raises(NotFoundError) as exc:
        await router.chat(request)

    assert exc.value.code == "model_provider_not_found"
    assert exc.value.details == {"provider": "missing"}


def test_chat_model_router_rejects_non_provider() -> None:
    from xiagent.models import ChatModelRouter

    router = ChatModelRouter()

    with pytest.raises(TypeError):
        router.register_provider("bad", object())  # type: ignore[arg-type]


async def test_deepseek_provider_uses_client_factory_and_disables_thinking() -> None:
    from xiagent.models import ChatMessage, ChatRequest, DeepSeekModelConfig
    from xiagent.models.providers.deepseek import DeepSeekChatProvider

    fake_client = FakeClient()
    captured_factory_kwargs: dict[str, Any] = {}

    def client_factory(**kwargs: Any) -> FakeClient:
        captured_factory_kwargs.update(kwargs)
        return fake_client

    provider = DeepSeekChatProvider(
        config=DeepSeekModelConfig(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-test-model",
        ),
        client_factory=client_factory,
    )
    request = ChatRequest(
        provider="deepseek",
        model="deepseek-test-model",
        messages=[
            ChatMessage(role="system", content="be brief"),
            ChatMessage(role="user", content="hello"),
        ],
    )

    response = await provider.chat(request)

    assert captured_factory_kwargs == {
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
    }
    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["model"] == "deepseek-test-model"
    assert fake_client.chat.completions.kwargs["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello"},
    ]
    assert fake_client.chat.completions.kwargs["stream"] is False
    assert fake_client.chat.completions.kwargs["extra_body"] == {
        "thinking": {"type": "disabled"},
    }
    assert "thinking" not in fake_client.chat.completions.kwargs
    assert fake_client.closed is True
    assert response.text == "deepseek response"
    assert response.model == "deepseek-test-model"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 5}


async def test_deepseek_provider_wraps_request_failures() -> None:
    from xiagent.models import ChatMessage, ChatRequest, DeepSeekModelConfig
    from xiagent.models.providers.deepseek import DeepSeekChatProvider

    provider = DeepSeekChatProvider(
        config=DeepSeekModelConfig(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-test-model",
        ),
        client_factory=lambda **_: FakeClient(should_fail=True),
    )
    request = ChatRequest(
        provider="deepseek",
        model="deepseek-test-model",
        messages=[ChatMessage(role="user", content="hello")],
    )

    with pytest.raises(ExternalServiceError) as exc:
        await provider.chat(request)

    assert exc.value.code == "deepseek_request_failed"
    assert exc.value.details["provider"] == "deepseek"
